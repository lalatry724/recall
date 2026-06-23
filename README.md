# agtLog

> Turn your Claude Code conversation transcripts into human-readable HTML / text — current session or your entire history — with three views (full / simple / talk), local timestamps, and optional auto-archiving on every session end.

*(繁體中文說明見下方 [中文](#中文說明))*

`agtLog` is a [Claude Code](https://claude.com/claude-code) skill. It reads the JSONL transcripts Claude Code already stores under `~/.claude/projects/` and renders them as clean, browsable HTML (or plain text). The transcript is **more complete than the on-screen view** — the terminal collapses long tool output; the JSONL keeps it all.

It is a **thin wrapper over deterministic Python**: the rendering core (`render_core.py`) and CLI (`agtLog.py`) are pure standard-library Python with **zero AI token cost**. The skill layer only tells the agent which command to run.

## What it does / does not do

- ✅ Restores **all the text** of a conversation (user, assistant, tool calls, tool results) to HTML/txt.
- ✅ Exports a single session, or **all** historical sessions across every project, with an index.
- ✅ Auto-archives each session to HTML when it ends (optional hooks).
- ❌ Does **not** capture pixel-level terminal screenshots (borders/colors/UI chrome). HTML colors are applied by element type, not reconstructed from the screen.

## Install

Requires Python 3 (standard library only — no third-party packages). Works on macOS / Linux / Windows.

> **Python command differs by OS.** macOS / Linux use `python3`. On **Windows** the bundled Python installs as **`python`**, and a bare `python3` is usually a Microsoft Store stub that silently does nothing — so use `python` everywhere on Windows. `install.sh` auto-detects this (it probes each launcher and bakes the working one into the hook command).

### macOS / Linux

1. Copy this folder into your skills directory:
   ```bash
   cp -r agtLog ~/.claude/skills/agtLog
   ```
2. (Optional) Enable auto-archiving hooks — see [Auto-archive](#auto-archive):
   ```bash
   bash ~/.claude/skills/agtLog/install.sh
   ```
   This backs up `~/.claude/settings.json`, then **appends** the SessionStart/SessionEnd hooks idempotently (existing hooks untouched).

Run the CLI directly without installing it as a skill:
```bash
python3 path/to/scripts/agtLog.py --scope all
```

### Windows

1. Copy this folder into your skills directory (PowerShell):
   ```powershell
   Copy-Item -Recurse -Force agtLog "$env:USERPROFILE\.claude\skills\agtLog"
   ```
2. (Optional) Enable auto-archiving hooks. `install.sh` is a bash script, so run it from **Git Bash** (ships with Git for Windows):
   ```bash
   bash ~/.claude/skills/agtLog/install.sh
   ```
   It detects that `python` (not `python3`) is the working launcher and writes the hook commands accordingly. If you have no bash, register the two hooks in `%USERPROFILE%\.claude\settings.json` manually, using `python "<skill>/scripts/<hook>.py"`.

Run the CLI directly without installing it as a skill:
```powershell
python path\to\scripts\agtLog.py --scope all
```

| | macOS / Linux | Windows |
|---|---|---|
| Python command | `python3` | `python` (bare `python3` is a no-op Store stub) |
| Copy folder | `cp -r agtLog ~/.claude/skills/agtLog` | `Copy-Item -Recurse -Force agtLog "$env:USERPROFILE\.claude\skills\agtLog"` |
| Run `install.sh` | native shell | **Git Bash** required |
| Hook command written | `python3 "…"` | `python "…"` (auto-detected) |

## Usage

```bash
python3 scripts/agtLog.py [options]
```

| Option | Values (default) | Meaning |
|--------|------------------|---------|
| `--scope` | **current** / all / init-all / tidy / reset | Current / all→`./session-export/` / init-all→archive (+index) / tidy→blacklist deleted / reset→clear a project's records |
| `--view` | full / simple / **talk** | Verbatim+tools / tools as one-liners / pure conversation (default) |
| `--views` | — | init-all only: comma list overriding conf, e.g. `simple,talk,full` |
| `--format` | **html** / txt | Colored HTML by default |
| `--timestamps` / `--no-timestamps` | **on** | Prefix each turn with local time `[YYYY-MM-DD HH:MM:SS]` |
| `--include-thinking` | off | Include thinking blocks in the `full` view |
| `--include-subagents` | off | Include sub-agent transcripts (scope all / init-all) |
| `--force` | off | init-all: rebuild existing archives (default is idempotent skip) |
| `--project` | — | tidy/reset: limit to one archive project folder (required for reset) |
| `--confirm` | off | tidy: proceed when blacklist candidates exceed the safety threshold (20) |
| `--arg-width N` | 80 | Truncate tool args in `simple` |
| `--max-result-chars N` | 0 | Truncate tool_result in `full` |
| `--output` / `--output-dir` / `--transcript` / `--cwd` | — | Path overrides |

Common:
```bash
python3 scripts/agtLog.py                       # current session → agtLog-talk.html (talk, default)
python3 scripts/agtLog.py --view simple         # conversation + one-line tool summaries
python3 scripts/agtLog.py --view full           # verbatim + tool bodies + results
python3 scripts/agtLog.py --scope all           # all history → ./session-export/ + index.html
python3 scripts/agtLog.py --scope init-all      # backfill all history (talk) into the archive + index.html
python3 scripts/agtLog.py --scope init-all --views simple,talk,full   # backfill all three views
```

Output is a JSON status line on stdout (`status == "ok"` on success, with `output`/`turns`).

### The three views

- **talk** (default): only user/assistant text, no tools. Best for **reading the narrative** — the cleanest, lowest-noise view.
- **simple**: conversation + one-line tool summaries (`• Update(file)`). Best for **review / finding loose ends**. Filters injected meta messages, merges consecutive same-role turns.
- **full**: verbatim, tool commands + results, meta preserved, 1:1. Best for **audit / reproduction**.

To get **simple / full / all** views: pass `--view simple` / `--view full` (current/all), `--views simple,talk,full` (init-all), or set `views` in `archive.conf.json` for the auto-archive hook.

### scope=all vs scope=init-all

- `--scope all` writes one chosen view into `./session-export/` in the current directory — a throwaway export.
- `--scope init-all` backfills **all history** into `~/.claude/session-archive/<project>/` (flat, talk by default; `--views` to add more), **merged with the auto-archive tree** so past and future conversations live together. Multiple views are disambiguated by filename suffix (`<base>.html` / `<base>.simple.html` / `<base>.full.html`). Idempotent (skips existing files; `--force` rebuilds). Re-run anytime to refresh the index and pick up new sessions.

## Pruning the archive (tidy / reset)

When archives pile up, you'll want to delete worthless conversations and have them **stay** gone. Each archive project folder keeps a `_catalog.json` recording every session ever produced (turns / bytes / summary / time) plus a `blacklist`. The workflow:

1. Manually delete the worthless HTML files from `~/.claude/session-archive/<project>/`.
2. Run **tidy** — it finds sessions whose files are now gone and blacklists them, so `init-all` and the SessionEnd hook never regenerate them.

```bash
python3 scripts/agtLog.py --scope tidy                    # scan all project folders
python3 scripts/agtLog.py --scope tidy --project <name>   # one folder
python3 scripts/agtLog.py --scope tidy --confirm          # override the >20 safety threshold
python3 scripts/agtLog.py --scope reset --project <name>  # undo: clear blacklist → init-all regenerates
```

- Blacklisting happens **only on an explicit `tidy`** — `init-all` never auto-blacklists, so moving/renaming the archive folder can't silently wipe everything.
- If one folder has more than 20 deletion candidates and you didn't pass `--confirm`, tidy only reports and writes nothing (safety against mass mis-deletion).
- `reset` is the undo (clears a project's blacklist + stale records); `--project` is required so you can't wipe everything by accident.
- The global `index.html` excludes blacklisted sessions and shows each session's file size.

## Auto-archive

Two optional Claude Code hooks (registered by `install.sh` into `~/.claude/settings.json`):

- **SessionEnd** → `scripts/session_end_archive.py`: on session end, save the conversation as **talk HTML** (default) to `~/.claude/session-archive/<project>/` (flat, no view subfolder). *fail-open* — any error exits silently, never blocking session end. To also archive simple/full, set `"views": ["simple","talk"]` (or add `"full"`).
- **SessionStart** → `scripts/session_start_reminder.py`: a one-line reminder that archiving is on and where files go.

Behavior is controlled by `archive.conf.json`:
```json
{
  "enabled": true,
  "archive_dir": "~/.claude/session-archive",
  "views": ["talk"],
  "format": "html",
  "timestamps": true
}
```
Set `"enabled": false` to turn archiving off without removing the hooks.

### Regenerate / backfill / rebuild

The SessionEnd hook only fires **when a session ends** — it never re-scans history by itself, so gaps happen (hook disabled, a crash, sessions from before install). `--scope init-all` is the scan/backfill mechanism:

| Goal | Command | Behavior |
|------|---------|----------|
| **Backfill** missing sessions | `agtLog.py --scope init-all` | Scans all history; writes only missing files, **skips existing** (idempotent — re-run anytime). |
| **Rebuild** all (e.g. after a render change) | `agtLog.py --scope init-all --force` | Rewrites every file, ignoring what exists. |
| Re-archive one session | `agtLog.py --transcript <jsonl> --output <path>` | Always overwrites that one file. |

Files are keyed by `<date>_<time>_<slug>_<id8>`, so `init-all` matches by name and skips duplicates. There's no automatic periodic backfill — run `init-all` manually (or wire it into your own cron/hook) to catch up.

## Repository layout

```
agtLog/
├── README.md             this file
├── CLAUDE.md             project map (dev entry: where to look, file roles, rules)
├── COMMANDS.md           one-page command cheatsheet
├── LICENSE               MIT
├── SKILL.md              skill manifest (how the agent invokes it)
├── archive.conf.json     auto-archive config
├── install.sh            register hooks into settings.json (backup → idempotent append → verify)
├── scripts/
│   ├── agtLog.py            single CLI entry point
│   ├── render_core.py            the one rendering core (single source of truth)
│   ├── catalog.py                archive state: per-project _catalog.json (manifest + blacklist)
│   ├── session_end_archive.py    SessionEnd hook
│   └── session_start_reminder.py SessionStart hook
└── evals/
    └── triggers.json     skill trigger evals
```

## Notes

- Standard library only; no third-party dependencies.
- The last few turns of the **current** session may not be flushed to disk yet — that's normal.
- Project path encoding (`~/.claude/projects/<non-alnum→->`) is handled by `render_core.encode_project_dirname`; if the encoded dir is missing it falls back to the globally newest JSONL.
- macOS system Python can be 3.8 — all scripts use `from __future__ import annotations`; keep that line if you add scripts.

## Changelog

This project follows [Semantic Versioning](https://semver.org/). Newest first. Full history: [`version.md`](version.md).

### 1.4.0 — 2026-06-23 · Archive pruning (tidy / reset + blacklist)
- **Per-project `_catalog.json`** — each archive project folder now keeps a record of every session ever produced (turns / bytes / summary / time) plus a `blacklist`. New shared module `scripts/catalog.py` (atomic state I/O, standard library only).
- **`--scope tidy`** ("整理對話記錄") — compares the catalog against disk and blacklists sessions whose HTML you deleted, so `init-all` and the SessionEnd hook never regenerate them. Safety threshold: >20 candidates in one folder requires `--confirm`.
- **`--scope reset --project <name>`** — undo: clears a project's blacklist + stale records so the next `init-all` regenerates (`--project` required).
- **Blacklist honored** in both `init-all` (skips + reports `blacklisted` count) and the SessionEnd hook; the global `index.html` now excludes blacklisted sessions and shows file size.

### 1.2.0 — 2026-06-17 · Flat archive, talk by default
- **Flat archive layout** — dropped the per-view subfolders: archives now land directly at `~/.claude/session-archive/<project>/` instead of `<project>/<view>/`.
- **Talk is the default view** — both the SessionEnd hook and `agtLog.py` (current / init-all) now produce only the **talk** view by default (`--view` default `simple`→`talk`, `archive.conf.json` `views` `["simple","talk"]`→`["talk"]`).
- **Multiple views still supported, flat** — when more than one view is produced, files are disambiguated by suffix: `<base>.html` (talk), `<base>.simple.html`, `<base>.full.html`. Use `--view simple|full` (current/all), `--views simple,talk,full` (init-all), or `archive.conf.json` `views`.
- **Existing archives migrated** — old `<project>/simple/` + `<project>/talk/` trees flattened (simple dropped, talk files moved up), index rebuilt.

### 1.1.0 — 2026-06-16 · Readability & cross-platform
- **Slash commands restored** — a user `/command args` stored as `<command-name>…</command-args>` is rendered back as the typed `/command args` (simple/talk) with its own color (`⌘`-prefixed); `full` keeps the raw tags verbatim. The command also becomes the filename's first-prompt slug.
- **Markdown tables → HTML tables** — contiguous `| … |` blocks render as real `<table>` (borders, header tint, column alignment) in simple/talk; `full` keeps them verbatim; code-fence content untouched.
- **Per-role backgrounds** — user / assistant turns get distinct solid block backgrounds (deep blue / deep green), not just a left border.
- **Filenames include the first message's time** — `<date>_<HH-MM-SS>_<slug>_<id8>` (was date-only); colons swapped for `-` for Windows.
- **Cross-platform install** — README splits macOS/Linux vs Windows (`python3` vs `python`, `cp -r` vs `Copy-Item`, Git Bash for `install.sh`); `install.sh` now probes for a working Python launcher and bakes it into the hook command (fixes the Windows `python3` Store-stub trap).

### 1.0.0 — 2026-06-15 · First public release
Consolidates the internal development milestones into one public release:
- **Three views** — `full` (verbatim + tools + results) / `simple` (one-line tools) / `talk` (pure conversation), with local timestamps and path highlighting.
- **Scopes** — `current` (one session), `all` (export every session to `./session-export/` + index).
- **`init_all`** (`--scope init-all`) — backfill **all** history into `~/.claude/session-archive/<project>/<view>/`, idempotent (`--force` to rebuild), with a top-level `index.html` linking simple/talk per session.
- **Per-view archive layout** — `<project>/<view>/` so simple and talk live in separate folders.
- **Auto-archive hooks** — SessionEnd saves simple+talk HTML on session end (fail-open); SessionStart prints a reminder. Registered via `install.sh` (backup → idempotent append → verify).
- **Single rendering core** — `render_core.py` is the one source of truth; pure standard-library Python, zero AI token cost.

<!-- Template for future entries:
### X.Y.Z — YYYY-MM-DD
- Added: ...
- Changed: ...
- Fixed: ...
-->

## License

MIT — see [LICENSE](LICENSE).

---

## 中文說明

`agtLog` 是一個 [Claude Code](https://claude.com/claude-code) 技能（skill）。它讀取 Claude Code 自存在 `~/.claude/projects/` 下的 JSONL transcript，還原成乾淨可瀏覽的 HTML（或純文字）。transcript **比畫面更完整**——終端機會摺疊長輸出，JSONL 全留著。

它是**薄包裝、核心是免 token 程式**：渲染核心 `render_core.py` 與 CLI `agtLog.py` 是純標準庫 Python，**零 AI token**；技能層只告訴 agent 跑哪支指令。

### 能做 / 不能做
- ✅ 把對話**所有文字**（user / assistant / 工具呼叫 / 工具結果）還原成 HTML/txt。
- ✅ 匯出單一 session，或跨全部專案的**所有**歷史 session，並產索引。
- ✅ session 結束時自動把對話歸檔成 HTML（選用 hook）。
- ❌ **不**抓終端機像素級截圖。HTML 顏色依元素類型上色，非還原螢幕色票。

### 安裝
需要 Python 3（純標準庫）。

> **Python 指令依系統不同**：mac / Linux 用 `python3`；**Windows 用 `python`**（裸 `python3` 多半是 Microsoft Store 跳板，會靜默失效）。`install.sh` 會自動偵測（逐一試跑 launcher，把能用的那個寫進 hook 指令）。

**mac / Linux：**
```bash
cp -r agtLog ~/.claude/skills/agtLog
bash ~/.claude/skills/agtLog/install.sh   # 選用：啟用自動歸檔 hook
```

**Windows（PowerShell 複製 + Git Bash 跑 install）：**
```powershell
Copy-Item -Recurse -Force agtLog "$env:USERPROFILE\.claude\skills\agtLog"
```
```bash
bash ~/.claude/skills/agtLog/install.sh   # 在 Git Bash 內跑；自動用 python 而非 python3
```
沒有 bash → 手動把兩個 hook 寫進 `%USERPROFILE%\.claude\settings.json`，指令用 `python "<skill>/scripts/<hook>.py"`。

`install.sh` 會先備份 `~/.claude/settings.json`，再**冪等 append** 兩個 hook（既有 hook 不動）。

| | mac / Linux | Windows |
|---|---|---|
| Python 指令 | `python3` | `python`（`python3` 是空跳板）|
| 複製資料夾 | `cp -r …` | `Copy-Item -Recurse -Force …` |
| 跑 `install.sh` | 原生 shell | 需 **Git Bash** |
| hook 寫入的指令 | `python3 "…"` | `python "…"`（自動偵測）|

### 三視圖
- **talk**（預設）：只有對話文字、隱藏工具，最乾淨，適合純脈絡整理。
- **simple**：對話＋工具單行摘要，適合回顧、找未處理項目。
- **full**：逐字＋工具本文＋結果，1:1 還原，適合稽核重現。

要產 **simple / full / 全部** 版本：current/all 用 `--view simple`｜`--view full`；init-all 用 `--views simple,talk,full`；自動歸檔改 `archive.conf.json` 的 `views`。

### init_all（補建全部歷史）
```bash
python3 scripts/agtLog.py --scope init-all                          # 預設只補 talk
python3 scripts/agtLog.py --scope init-all --views simple,talk,full # 補三視圖
```
把全部歷史補建到 `~/.claude/session-archive/<專案>/`（扁平、預設 talk），**與自動歸檔合一**（過去+未來同一棵），並產頂層 `index.html`。多視圖以檔名後綴區分（`<base>.html`／`<base>.simple.html`／`<base>.full.html`）。**冪等**：已存在跳過（`--force` 強制重建），隨時重跑刷新索引。

### 自動歸檔設定
由 `archive.conf.json` 控（`enabled` / `archive_dir` / `views` / `format` / `timestamps`）。預設只產 talk；要連 simple/full 一起存，把 `views` 設成 `["simple","talk"]`（或加 `"full"`）。要關閉把 `enabled` 設 `false` 即可。

### 重產 / 補產 / 重建
SessionEnd hook **只在 session 結束當下產**，不會自己回掃歷史，所以會有缺口（hook 曾停用、當機、安裝前的舊 session）。掃描補產機制就是 `--scope init-all`：

| 目的 | 指令 | 行為 |
|------|------|------|
| **補產**漏掉的 session | `agtLog.py --scope init-all` | 掃全歷史，只寫缺檔、**已存在跳過**（冪等，可隨時重跑） |
| **重建**全部（改了 render 邏輯後） | `agtLog.py --scope init-all --force` | 忽略既有，全部重寫 |
| 重產單一 session | `agtLog.py --transcript <jsonl> --output <path>` | 直接覆寫該檔 |

檔名以 `<date>_<time>_<slug>_<id8>` 為鍵，故 `init-all` 靠檔名比對跳過重複。**無自動定期補產**——需手動跑 `init-all`（或自行接 cron/hook）來補上。

### 變更紀錄
採[語意化版號](https://semver.org/)，完整內容見上方 [Changelog](#changelog) 與 [`version.md`](version.md)。
- **1.4.0（2026-06-23）歸檔整理（tidy/reset＋黑名單）**：每專案 `_catalog.json`（記錄 turns/bytes/摘要/時間＋blacklist）、新增 `scripts/catalog.py`；`--scope tidy`（整理對話記錄）比對記錄 vs 磁碟把手刪的對話拉黑、>20 筆需 `--confirm`；`--scope reset --project <名>` 解黑重產；init-all 與 hook 認黑名單、全域 index 排除黑名單並顯示檔案大小。
- **1.2.0（2026-06-17）扁平歸檔、預設 talk**：歸檔結構去掉 view 子資料夾（改 `<專案>/` 直放）、SessionEnd 與 agtLog.py 預設只產 talk（`--view` 預設改 talk、conf `views` 改 `["talk"]`）、多視圖以檔名後綴 `.simple`/`.full` 區分、既有歸檔一次性扁平化並重建 index。
- **1.1.0（2026-06-16）可讀性與跨平台**：slash command 還原成 `/cmd args` 並上色（full 保留原始標籤）、markdown 表格轉真 `<table>`（full 逐字）、user/assistant 整塊深藍/深綠底色區分、檔名加首則訊息時間 `HH-MM-SS`、README 拆 mac/Windows 安裝差異 + `install.sh` 自動偵測 `python`/`python3`。
- **1.0.0（2026-06-15）首次公開**：三視圖（full/simple/talk）、scope current/all/init-all、init_all 補建全部歷史（冪等 + index）、simple/talk 分資料夾版面、SessionEnd/SessionStart 自動歸檔 hook（install.sh 安裝）、單一渲染核心 render_core.py。

### 授權
MIT。
