---
name: agtLog
description: Restore Claude Code conversation transcripts into human-readable HTML/text — current session or all historical sessions — with three views (full verbatim / simple one-line tools / talk pure conversation), local timestamps, and path highlighting. Equivalent to saving the on-screen conversation 1:1 for review and context.
userInvocable: true
triggers: agtLog, save conversation, save transcript, export all sessions, export conversation, dump transcript, recall, /agtLog, /recall, 整理對話記錄, 清理對話記錄, tidy archive, reset archive
pattern: tool-wrapper
---

# Skill: agtLog (Tool Wrapper)

> Wraps "locate transcript JSONL → restore → write file" so the agent never hand-parses JSONL.
> All rendering goes through `scripts/render_core.py` (single source of truth); the CLI entry is `scripts/agtLog.py`.

## Capability boundary

- ✅ Can: restore **all the text** of a conversation to HTML/txt. Source is the transcript JSONL Claude Code stores itself — more complete than the screen (which collapses long output).
- ❌ Cannot: capture pixel-level terminal screenshots (borders/colors/UI chrome). HTML colors are by element type, not reconstructed from the screen.

## Core rules

1. **Never let the agent read JSONL and hand-parse it** — always go through `scripts/agtLog.py`. Encoding / path / block / meta traps are sealed inside.
2. On wrapper failure, read the JSON `error` field; **do not switch to an ad-hoc workaround**.
3. Done = stdout JSON `status == "ok"`; report `output`/`turns` to the user.

## Main entry: `scripts/agtLog.py`

```
python3 scripts/agtLog.py [options]
```

| Option | Values (default) | Meaning |
|--------|------------------|---------|
| `--scope` | **current** / all / init-all / tidy / reset | Current / all→`./session-export/` / init-all→archive (+index) / tidy→blacklist deleted / reset→clear a project's records |
| `--view` | full / simple / **talk** | Verbatim+tools / tools one-liner / pure conversation (default) |
| `--views` | — | init-all only: comma list overriding conf (e.g. `simple,talk,full`) |
| `--format` | **html** / txt | Colored HTML by default |
| `--timestamps` / `--no-timestamps` | **on** | Prefix each turn with local time |
| `--include-thinking` | off | Include thinking in `full` |
| `--include-subagents` | off | Include sub-agent transcripts (scope all / init-all) |
| `--force` | off | init-all: rebuild existing archives (default idempotent skip) |
| `--project` | — | tidy/reset: limit to one archive project folder (required for reset) |
| `--confirm` | off | tidy: proceed when blacklist candidates exceed the safety threshold (20) |
| `--arg-width N` | 80 | Truncate tool args in `simple` |
| `--max-result-chars N` | 0 | Truncate tool_result in `full` |
| `--output` / `--output-dir` / `--transcript` / `--cwd` | — | Path overrides |

Common:
```bash
python3 scripts/agtLog.py                       # current session → agtLog-talk.html (talk, default)
python3 scripts/agtLog.py --view simple         # conversation + one-line tool summaries
python3 scripts/agtLog.py --view full           # verbatim + tool bodies
python3 scripts/agtLog.py --scope all           # all history → ./session-export/ + index.html
python3 scripts/agtLog.py --scope init-all      # backfill all history (talk) into the archive + index.html
python3 scripts/agtLog.py --scope init-all --views simple,talk,full   # backfill all three views
```

### Choosing a view
- **talk** (default): only user/assistant text, tools hidden. For reading the narrative — the cleanest, lowest-noise view.
- **simple**: conversation + one-line tool summaries (`• Update(file)`). For review / finding loose ends. Filters injected meta, merges consecutive same-role turns.
- **full**: verbatim + tool body + tool_result, meta preserved, 1:1. For audit / reproduction.

To produce **simple / full / all** views: pass `--view simple` or `--view full` (current/all scope), `--views simple,talk,full` (init-all scope), or set `views` in `archive.conf.json` for the auto-archive hook.

### scope=all vs scope=init-all
- `all` writes one view to `./session-export/` in the current dir (throwaway export).
- `init-all` backfills all history into `~/.claude/session-archive/<project>/` (flat, talk by default; `--views` to add more), merged with the auto-archive tree, plus a top-level `index.html`. Multiple views are disambiguated by filename suffix (`<base>.html` / `<base>.simple.html` / `<base>.full.html`). Idempotent; `--force` rebuilds; re-run to refresh.

## Pruning the archive: tidy / reset (blacklist)

Once archives pile up you'll want to delete worthless conversations and have them **stay** deleted. Mechanism:

1. Each archive project folder keeps `_catalog.json` — a record of every session ever produced (turns / bytes / summary / time) plus a `blacklist`.
2. You manually delete the worthless HTML files from `~/.claude/session-archive/<project>/`.
3. Run **tidy** ("整理對話記錄"): it compares the catalog against disk, finds sessions whose files are now gone, and blacklists them. `init-all` and the SessionEnd hook then never regenerate them.

```bash
python3 scripts/agtLog.py --scope tidy                 # all project folders
python3 scripts/agtLog.py --scope tidy --project <name> # one folder
python3 scripts/agtLog.py --scope tidy --confirm        # >20 candidates safety override
python3 scripts/agtLog.py --scope reset --project <name> # undo: clear blacklist → init-all can regenerate
```

- **Blacklisting only happens on an explicit `tidy`** — `init-all` never auto-blacklists, so moving/renaming the archive folder can't silently nuke everything.
- **Safety threshold**: if one folder has >20 candidates and you didn't pass `--confirm`, tidy only reports and writes nothing.
- **reset** is the undo: it clears a project's blacklist (and stale records) so the next `init-all` regenerates. `--project` is required to avoid wiping everything by accident.
- The global `index.html` excludes blacklisted sessions and shows each session's file size.

## Architecture: thin wrapper, token-free core

- **Execution layer** (`render_core.py` + `agtLog.py`): pure Python, deterministic, **zero AI token**.
- **Invocation layer** (this SKILL.md): only tells the agent which script + args to run.
- Fully skippable by the agent — run the CLI directly:
  ```bash
  python3 ~/.claude/skills/agtLog/scripts/agtLog.py --scope all
  ```

## Auto-archive (SessionEnd / SessionStart hooks)

Register via `install.sh` into `~/.claude/settings.json` (takes effect next session):
- **SessionEnd** → `scripts/session_end_archive.py`: save the conversation as **talk HTML** (default) to `~/.claude/session-archive/<project>/` (flat, no view subfolder). fail-open, never blocks session end.
- **SessionStart** → `scripts/session_start_reminder.py`: a one-line reminder of where archives go.
- Controlled by `archive.conf.json` (`enabled` / `archive_dir` / `views` / `format` / `timestamps`). Set `enabled` false to disable. To also archive simple/full, set `"views": ["simple","talk"]` (or add `"full"`) — extra views land as `<base>.simple.html` / `<base>.full.html` alongside the talk file.

### Regenerate / backfill / rebuild

The SessionEnd hook only fires **at the moment a session ends** — it never re-scans history on its own. So gaps happen (hook was disabled, a crash, sessions from before install). The scan/backfill mechanism is `--scope init-all`:

| Goal | Command | Behavior |
|------|---------|----------|
| **Backfill** missing sessions | `agtLog.py --scope init-all` | Scans all `~/.claude/projects/*/*.jsonl`; writes only files that don't exist yet, **skips existing** (idempotent — safe to re-run anytime). |
| **Rebuild** everything (e.g. after a render change) | `agtLog.py --scope init-all --force` | Ignores existing files and rewrites all of them. |
| Re-archive one current session | `agtLog.py --transcript <jsonl> --output <path>` | Always overwrites that one file. |

Note: each archive file is keyed by `<date>_<time>_<slug>_<id8>`, so re-running `init-all` matches existing files by name and skips them. There is no automatic periodic backfill — run `init-all` manually (or wire it into your own cron/hook) to catch up.

Note: the assistant label shows the actual model name (e.g. `claude-opus-4-8`); synthetic messages fall back to `ASSISTANT`.

## Failure handling
- `status == "fail"`: usually transcript not found → report `error` verbatim, do not reroute.
- exit 2 / `status == "error"`: internal exception → report `error`, do not retry.

## Notes
- Cross-platform (standard library only, no third-party deps).
- The last few turns of the **current** session may not be flushed yet — normal.
- Path encoding (`~/.claude/projects/<non-alnum→->`) is in `render_core.encode_project_dirname`; missing encoded dir falls back to the globally newest JSONL.
