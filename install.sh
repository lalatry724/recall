#!/usr/bin/env bash
# install.sh — register agtLog's SessionStart/SessionEnd hooks into
# ~/.claude/settings.json. Safe by design: backup -> idempotent append -> verify.
# Existing hooks are never touched; re-running is a no-op once installed.
set -euo pipefail

SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pick a python launcher that ACTUALLY runs. On Windows `python3` is often a
# Microsoft Store stub that does nothing — so probe it before trusting it, and
# fall back to `python`. The chosen name is baked into the hook command below.
if command -v python3 >/dev/null 2>&1 && python3 -c '' >/dev/null 2>&1; then
  PY=python3
elif command -v python  >/dev/null 2>&1 && python  -c '' >/dev/null 2>&1; then
  PY=python
else
  echo "ERROR: no working Python 3 found (tried python3, python)." >&2
  exit 1
fi

echo "agtLog installer"
echo "  settings : $SETTINGS"
echo "  skill dir: $SKILL_DIR"
echo "  python   : $PY"

# 0) ensure settings.json exists
mkdir -p "$(dirname "$SETTINGS")"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"

# 1) backup (timestamped, never overwrites an existing backup of the same run)
BAK="$SETTINGS.bak.agtLog.$(date +%Y%m%d%H%M%S)"
cp "$SETTINGS" "$BAK"
echo "  backup   : $BAK"

# 2) idempotent append + 4) verify, all in one Python pass (no jq dependency)
SKILL_DIR="$SKILL_DIR" PY="$PY" "$PY" - "$SETTINGS" <<'PY'
import json, os, sys

path = sys.argv[1]
skill = os.environ["SKILL_DIR"]
pyexe = os.environ["PY"]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

hooks = data.setdefault("hooks", {})

# event -> (script filename, timeout)
WANT = {
    "SessionStart": ("session_start_reminder.py", 5),
    "SessionEnd":   ("session_end_archive.py", 30),
}

def already(groups, marker):
    for g in groups:
        for h in g.get("hooks", []):
            if marker in h.get("command", ""):
                return True
    return False

added = []
for event, (script, timeout) in WANT.items():
    groups = hooks.setdefault(event, [])
    if already(groups, script):
        continue
    cmd = f'{pyexe} "{skill}/scripts/{script}"'
    groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": timeout}]})
    added.append(event)

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

# verify: re-read and confirm both markers are present
with open(path, encoding="utf-8") as f:
    check = json.load(f)
ok = all(already(check.get("hooks", {}).get(ev, []), s) for ev, (s, _) in WANT.items())

if added:
    print("  added    : " + ", ".join(added))
else:
    print("  added    : (none — already installed)")
print("  verify   : " + ("OK — both hooks present" if ok else "FAILED — hooks missing!"))
sys.exit(0 if ok else 1)
PY

echo
echo "Done. Hooks take effect on the NEXT Claude Code session."
echo "Disable later without uninstalling: set \"enabled\": false in archive.conf.json."
