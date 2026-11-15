#!/usr/bin/env bash
# Global install for red-blue-green: skill + hook into ~/.claude
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_HOME="${HOME}/.claude"

mkdir -p "$CLAUDE_HOME/skills" "$CLAUDE_HOME/hooks"
rm -rf "$CLAUDE_HOME/skills/red-blue-green"
cp -R "$SRC/.claude/skills/red-blue-green" "$CLAUDE_HOME/skills/"
cp "$SRC/hooks/rbg_gate.py" "$CLAUDE_HOME/hooks/"
chmod +x "$CLAUDE_HOME/hooks/rbg_gate.py"

python3 - "$CLAUDE_HOME/settings.json" <<'PY'
import json, shutil, sys, time

settings_path = sys.argv[1]
hook_cmd = "$HOME/.claude/hooks/rbg_gate.py"
backup = f"{settings_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"

try:
    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}
except Exception as e:
    sys.exit(f"Cannot parse {settings_path} ({e}); refusing to modify it.")

shutil.copy2(settings_path, backup)

matcher = "Edit|Write|MultiEdit|NotebookEdit"
entries = settings.setdefault("hooks", {}).setdefault("PostToolUse", [])
group = next((e for e in entries if e.get("matcher") == matcher), None)
if group is None:
    group = {"matcher": matcher, "hooks": []}
    entries.append(group)
if not any(h.get("command") == hook_cmd for h in group.get("hooks", [])):
    group.setdefault("hooks", []).append({"type": "command", "command": hook_cmd})

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"settings updated (backup: {backup})")
PY

echo "Installed:"
echo "  skill -> $CLAUDE_HOME/skills/red-blue-green"
echo "  hook  -> $CLAUDE_HOME/hooks/rbg_gate.py"
echo "Open a project with a test suite and start with a failing test (RED)."
