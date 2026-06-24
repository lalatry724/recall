# deploy.ps1 — Windows-native (PowerShell) twin of deploy.sh.
# Syncs this dev repo into the live skill folder so Claude Code (and its
# SessionStart/SessionEnd hooks) run the latest code. `git pull` only updates
# THIS repo; the deployed skill at ~\.claude\skills\agtLog is a separate copy
# and must be refreshed by running this.
#
# Usage:  powershell -ExecutionPolicy Bypass -File deploy.ps1
#         $env:DEST="C:\custom\path"; .\deploy.ps1
$ErrorActionPreference = "Stop"

$Src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest = if ($env:DEST) { $env:DEST } else { Join-Path $HOME ".claude\skills\agtLog" }

Write-Host "agtLog deploy"
Write-Host "  source: $Src"
Write-Host "  dest  : $Dest"

New-Item -ItemType Directory -Force (Join-Path $Dest "scripts") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Dest "evals")   | Out-Null

# Files always refreshed (code + skill docs). __pycache__ is never copied.
$Items = @(
  "scripts\agtLog.py",
  "scripts\catalog.py",
  "scripts\render_core.py",
  "scripts\session_end_archive.py",
  "scripts\session_start_reminder.py",
  "SKILL.md",
  "COMMANDS.md",
  "README.md",
  "version.md",
  "devlog.md",
  "install.sh",
  "LICENSE",
  "evals\triggers.json"
)

foreach ($rel in $Items) {
  $s = Join-Path $Src $rel
  if (Test-Path $s) {
    $d = Join-Path $Dest $rel
    New-Item -ItemType Directory -Force (Split-Path -Parent $d) | Out-Null
    Copy-Item $s $d -Force
    Write-Host "  + $rel"
  }
}

# Config: copy ONLY if missing — never clobber a user-edited deployed conf.
$confDst = Join-Path $Dest "archive.conf.json"
$confSrc = Join-Path $Src  "archive.conf.json"
if ((-not (Test-Path $confDst)) -and (Test-Path $confSrc)) {
  Copy-Item $confSrc $confDst -Force
  Write-Host "  + archive.conf.json (new)"
} else {
  Write-Host "  = archive.conf.json (kept existing)"
}

# Drop stale bytecode so Python can't load an old compiled copy.
$pyc = Join-Path $Dest "scripts\__pycache__"
if (Test-Path $pyc) { Remove-Item $pyc -Recurse -Force }

Write-Host "Done. Deployed skill now matches this repo."
