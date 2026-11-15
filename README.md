# red-blue-green

**Make TDD a machine-enforced gate in Claude Code, not a suggestion.**

`red-blue-green` is a [Claude Code](https://claude.com/claude-code) skill + hook pair that enforces the classic red-green-refactor cycle (with the refactor phase called **blue** here, so the cycle reads **RED → GREEN → BLUE**):

- **RED** — write one small failing test. It must fail.
- **GREEN** — write the minimum code that makes it pass.
- **BLUE** — refactor while the suite stays green. Commit. Repeat.

Most models (and humans) *know* TDD and still skip steps under pressure: code first, test after, or a test that never fails. Prompts can't fix that reliably. Hooks can — the test runner, not the model, is the referee.

## What you get

| File | Purpose |
|---|---|
| `.claude/skills/red-blue-green/SKILL.md` | The skill: the cycle, its rules, and when Claude loads it |
| `hooks/rbg_gate.py` | The gate: a `PostToolUse` hook that runs your suite after every edit and reports RBG state |
| `.claude/settings.json` | Project-level hook wiring |
| `install.sh` | Optional global install (skill + hook into `~/.claude`) |

## How the gate works

After every `Edit`/`Write`/`MultiEdit` of a code file, the hook detects your test runner, runs the suite, and feeds state-aware guidance back to Claude:

| Situation | Gate says |
|---|---|
| Test edited, suite **fails** | ✅ RED confirmed — implement minimally, touch nothing else |
| Test edited, suite **passes instantly** | ⚠️ GREEN without RED — verify the test can fail first |
| Source edited, suite fails, RED on record | 🔁 Still RED — keep implementing minimally (never weaken old tests) |
| Source edited, suite fails, no RED | 🚫 Violation — no failing test governs this change; write one first |
| Source edited, suite passes, RED on record | ✅ GREEN — commit now, then refactor (BLUE) |
| Source edited, suite passes, no RED | ⚠️ Untested behavior — write the failing test first, or confirm it's a pure refactor |

The hook is a no-op on non-code files (docs, assets, lockfiles) and in projects where it can't detect a test suite.

**Supported runners** (auto-detected): npm (`package.json` scripts.test), Go (`go test`), Cargo, pytest, .NET (`dotnet test`), Make (`make test`). Anything else: set `RBG_TEST_CMD`.

## Install

### Option A — project-level (recommended for teams)

Copy into the repo you want to protect:

```bash
# from this repo
cp -R .claude /path/to/your-project/
cp -R hooks   /path/to/your-project/
```

Commit it. Everyone opening that project in Claude Code gets the gate — no per-person setup.

### Option B — global (personal, all projects)

```bash
./install.sh
```

This copies the skill to `~/.claude/skills/`, the hook to `~/.claude/hooks/`, and merges the hook entry into `~/.claude/settings.json` (a timestamped backup is written first).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `RBG_TEST_CMD` | auto-detect | Shell string for the test command, e.g. `RBG_TEST_CMD="npm run test:unit"` |
| `RBG_TEST_TIMEOUT` | `120` | Seconds before the run is killed |
| `RBG_SCOPE` | `full` | `full` runs the whole suite after every edit; `related` runs only the tests connected to the edited file |

Set them in `~/.claude/settings.json` (`env` block) or export them in your shell.

## Slow suites? Use `RBG_SCOPE=related`

Running the full suite after every edit is the strongest gate, but on a large or slow codebase it turns every edit into a full CI run. Set `RBG_SCOPE=related` and the gate runs only what the edited file can affect:

| Runner | Related scope runs |
|---|---|
| jest / vitest | `--findRelatedTests <file>` / `vitest related <file>` |
| Go | `go test ./<package-dir>/...` |
| pytest | the counterpart test file (`test_<module>.py`, `<module>_test.py`) |

Runners without a cheap related scope (Cargo, dotnet, make) fall back to the full suite. The tradeoff: related scope is much faster but can miss failures in distant consumers — for big repos, related scope during iteration plus one full run before commit is a solid compromise.

## Does the model matter?

No — that's the point. The referee is the test runner, so the gate behaves identically whether the session runs Claude models or another model routed into Claude Code (e.g. via a router/proxy). Weaker models skip TDD steps more often, which makes the gate *more* useful, not less.

## Requirements

- Claude Code
- Python 3.9+ (ships with macOS; used only to run the gate script)

## License

[MIT](LICENSE)
