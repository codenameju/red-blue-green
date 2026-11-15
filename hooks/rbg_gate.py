#!/usr/bin/env python3
"""
Red-Blue-Green (RBG) gate - a Claude Code PostToolUse hook.

Runs the project test suite after every Edit/Write and feeds state-aware
guidance back to Claude so the RED -> GREEN -> BLUE cycle is actually
followed instead of being silently skipped.

Output contract (Claude Code hook conventions):
  exit 0, no stdout            -> silent pass
  exit 0, JSON on stdout       -> "reason" is shown to Claude as guidance
  exit 2, stderr               -> hard hook error

Configuration (environment variables):
  RBG_TEST_CMD      shell string overriding the auto-detected test command
  RBG_TEST_TIMEOUT  per-run timeout in seconds (default: 120)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

MAX_REASON = 1200
RECENT_RED_WINDOW = 6 * 3600  # seconds; a RED written within this window counts as "recent"
DEFAULT_TIMEOUT = 120

NON_CODE_EXT = {
    ".md", ".txt", ".rst", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".pdf", ".csv", ".tsv", ".xlsx", ".zip", ".tar", ".gz", ".ico", ".icns",
    ".lock", ".sum", ".mod",
}


def emit(reason: str) -> None:
    reason = reason[:MAX_REASON]
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def is_test_file(path: str) -> bool:
    p = path.lower()
    if re.search(r"/(test|tests|spec|__tests__|e2e|acceptance)/", p):
        return True
    base = os.path.basename(p)
    if re.search(r"\.(test|spec)\.[a-z0-9]+$", base):          # foo.test.ts, foo.spec.js
        return True
    if re.match(r"^(test_|.*_test)\.[a-z0-9]+$", base):        # test_x.py, x_test.go
        return True
    if re.match(r"^test[a-z0-9_.]*\.(py|js|jsx|ts|tsx|rb|exs|ex)$", base):  # test_foo.py, tests.py
        return True
    if re.match(r".*tests?\.(java|kt|swift|m|cs)$", base):      # FooTest.java
        return True
    return False


def detect_command(cwd: str) -> tuple[list[str], str] | None:
    override = os.environ.get("RBG_TEST_CMD", "").strip()
    if override:
        return shlex.split(override), "custom"

    def has(name: str) -> bool:
        return os.path.exists(os.path.join(cwd, name))

    pkg = os.path.join(cwd, "package.json")
    if has("package.json") and os.path.exists(pkg):
        try:
            with open(pkg, encoding="utf-8") as f:
                if (json.load(f).get("scripts") or {}).get("test"):
                    return ["npm", "test", "--silent"], "npm"
        except Exception:
            pass

    if has("go.mod"):
        return ["go", "test", "./..."], "go"
    if has("Cargo.toml"):
        return ["cargo", "test", "--quiet"], "cargo"
    if has("pytest.ini") or has("pyproject.toml") or has("setup.cfg"):
        return [sys.executable, "-m", "pytest", "-x", "-q"], "pytest"
    if has(".csproj") or any(n.endswith(".csproj") or n.endswith(".sln")
                             for n in os.listdir(cwd)):
        return ["dotnet", "test", "--nologo", "-v", "q"], "dotnet"
    makefile = os.path.join(cwd, "Makefile")
    if has("Makefile"):
        try:
            with open(makefile, encoding="utf-8", errors="replace") as f:
                if re.search(r"^test\s*:", f.read(), re.MULTILINE):
                    return ["make", "test"], "make"
        except Exception:
            pass
    return None


def count_failures(output: str, rc: int, kind: str) -> int:
    if kind == "go":
        n = len(re.findall(r"^\s*--- FAIL:", output, re.MULTILINE))
        if n:
            return n
    numbers = [int(m) for m in re.findall(r"(\d+)\s*(?:failed|failing)", output, re.IGNORECASE)]
    if numbers:
        return max(numbers)
    return 1 if rc != 0 else 0


def state_path(cwd: str) -> str:
    key = hashlib.sha1(cwd.encode("utf-8")).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), f"rbg-state-{key}.json")


def load_state(cwd: str) -> dict:
    try:
        with open(state_path(cwd), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(cwd: str, state: dict) -> None:
    try:
        with open(state_path(cwd), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass  # state is best-effort; never break the hook over it


def run_tests(cmd: list[str], cwd: str) -> tuple[str, int, float, bool]:
    timeout = float(os.environ.get("RBG_TEST_TIMEOUT", DEFAULT_TIMEOUT))
    env = dict(os.environ)
    env.setdefault("CI", "1")
    start = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
        )
        return (proc.stdout or "") + (proc.stderr or ""), proc.returncode, time.time() - start, False
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return out + err, 124, time.time() - start, True
    except FileNotFoundError:
        return f"command not found: {cmd[0]}", 127, 0.0, False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # malformed hook payload: stay silent

    tool_input = payload.get("tool_input") or {}
    path = (tool_input.get("file_path") or tool_input.get("path")
            or tool_input.get("notebook_path") or "")
    if not path:
        return

    cwd = payload.get("cwd") or os.getcwd()
    abs_path = os.path.abspath(path) if not os.path.isabs(path) else os.path.abspath(path)
    if not abs_path.startswith(os.path.abspath(cwd) + os.sep):
        return  # edit outside the project: not our business
    ext = os.path.splitext(abs_path)[1].lower()
    if ext in NON_CODE_EXT:
        return  # docs/assets/lockfiles: never gate on these

    detected = detect_command(cwd)
    if not detected:
        return  # no test suite detected: hook is a no-op
    cmd, kind = detected

    out, rc, elapsed, timed_out = run_tests(cmd, cwd)

    if timed_out:
        emit(f"RBG: test run exceeded {int(elapsed)}s and was killed. "
             f"Speed up the suite or raise RBG_TEST_TIMEOUT (currently "
             f"{os.environ.get('RBG_TEST_TIMEOUT', str(DEFAULT_TIMEOUT))}s). No cycle state recorded.")

    fails = count_failures(out, rc, kind)
    now = time.time()
    state = load_state(cwd)
    if is_test_file(abs_path):
        state["last_test_edit"] = now
    state["last_fails"] = fails if rc != 0 else 0
    save_state(cwd, state)

    recent_red = bool(state.get("last_test_edit")) and \
        (now - float(state["last_test_edit"]) < RECENT_RED_WINDOW)

    if is_test_file(abs_path):
        if rc == 0:
            emit(
                "RBG: the test you just wrote PASSES immediately - this is GREEN without RED. "
                "A test that never failed proves nothing. Verify it can fail: temporarily break "
                "the code under test (or assert the opposite), watch it go RED, then restore. "
                "If it genuinely tests new behavior, the implementation does not exist yet - "
                "write the RED test against the missing behavior instead."
            )
        else:
            emit(
                f"RBG RED confirmed: {fails} failing test(s). This is the goal state. Next: "
                "implement the MINIMUM code needed to make exactly these tests pass. "
                "Do not touch unrelated code, do not add features, do not refactor yet."
            )
        return

    # Source (non-test) file was edited.
    if rc != 0:
        if recent_red:
            emit(
                f"RBG still RED: {fails} failing test(s). If the failures are the tests you "
                "wrote, keep implementing minimally until they pass. If any failing test was "
                "previously green, you broke it - fix that first, do not delete or weaken it."
            )
        else:
            emit(
                f"RBG violation: source edit made {fails} test(s) fail with no RED phase on "
                "record. You are changing behavior without a failing test. Stop: identify the "
                "test that governs this change. If none exists, write it first and watch it "
                "fail (RED), then implement (GREEN)."
            )
        return

    if recent_red:
        emit(
            f"RBG GREEN: all tests pass. Commit now, while it's green. Then BLUE: refactor "
            "freely (rename, extract, simplify) - the suite must stay green after every step. "
            "Repeat the cycle for the next behavior."
        )
    else:
        emit(
            "RBG: source edit with a green suite and no RED on record. If this adds or changes "
            "behavior, it is untested - write the failing test first (RED), then make it pass "
            "(GREEN). If this is a pure refactor (BLUE), proceed, but confirm coverage exists "
            "for the code you touched."
        )


if __name__ == "__main__":
    main()
