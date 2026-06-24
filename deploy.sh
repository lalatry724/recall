#!/usr/bin/env bash
# deploy.sh — sync this dev repo into the live skill folder so Claude Code (and
# its SessionStart/SessionEnd hooks) run the latest code. `git pull` only updates
# THIS repo; the deployed skill at ~/.claude/skills/agtLog is a separate copy and
# must be refreshed by running this. Cross-platform: macOS / Linux / Git Bash (Win).
#
# Usage:  bash deploy.sh            # deploy to ~/.claude/skills/agtLog
#         DEST=/custom/path bash deploy.sh
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${DEST:-$HOME/.claude/skills/agtLog}"

echo "agtLog deploy"
echo "  source: $SRC"
echo "  dest  : $DEST"

mkdir -p "$DEST/scripts" "$DEST/evals"

# Files always refreshed (code + skill docs). __pycache__ is never copied.
ITEMS=(
  "scripts/agtLog.py"
  "scripts/catalog.py"
  "scripts/render_core.py"
  "scripts/session_end_archive.py"
  "scripts/session_start_reminder.py"
  "SKILL.md"
  "COMMANDS.md"
  "README.md"
  "version.md"
  "devlog.md"
  "install.sh"
  "LICENSE"
  "evals/triggers.json"
)

for rel in "${ITEMS[@]}"; do
  if [ -f "$SRC/$rel" ]; then
    mkdir -p "$DEST/$(dirname "$rel")"
    cp "$SRC/$rel" "$DEST/$rel"
    echo "  + $rel"
  fi
done

# Config: copy ONLY if missing — never clobber a user-edited deployed conf.
if [ ! -f "$DEST/archive.conf.json" ] && [ -f "$SRC/archive.conf.json" ]; then
  cp "$SRC/archive.conf.json" "$DEST/archive.conf.json"
  echo "  + archive.conf.json (new)"
else
  echo "  = archive.conf.json (kept existing)"
fi

# Drop stale bytecode so Python can't load an old compiled copy.
rm -rf "$DEST/scripts/__pycache__"

echo "Done. Deployed skill now matches this repo."
