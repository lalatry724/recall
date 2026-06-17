# Version History — agtLog

本檔記錄 agtLog skill 的所有版本異動。最新在上。

## v1.2.0 — 2026-06-17

歸檔結構扁平化 + 預設單一 talk 版本。

- **歸檔結構扁平化**：由 `<archive>/<專案>/<view>/<檔>` 改為 `<archive>/<專案>/<檔>`，移除多餘的 `simple/`、`talk/` view 子資料夾。
- **預設只產 talk**：SessionEnd hook 與 `agtLog.py`（current / init-all）一律預設僅產出 talk 版本（最乾淨的純對話），不再同時產 simple。
  - `agtLog.py --view` 預設值 `simple` → `talk`。
  - `archive.conf.json` 的 `views` 預設 `["simple","talk"]` → `["talk"]`。
- **多 view 仍可選**：要同時產 simple/full 時，以檔名後綴區分、仍維持扁平：
  - talk → `<base>.html`（預設、無後綴）
  - simple → `<base>.simple.html`
  - full → `<base>.full.html`
  - 指令：current 用 `--view simple` / `--view full`；init-all 用 `--views simple,talk,full`；自動歸檔改 `archive.conf.json` 的 `views`。
- **既有歸檔遷移**：`~/.claude/session-archive/` 既有 `<專案>/simple/`、`<專案>/talk/` 一次性扁平化（刪 simple/、talk/* 上移、刪 talk/），並重建 index.html。
- 文件補上「重產 / 補產 / 重建」說明（README + SKILL）：釐清 SessionEnd 只在結束當下產、`init-all` 為冪等掃描補產、`--force` 重建。
- 新增本 `version.md`。

## v1.1.0 — 2026-06-16

- 可讀指令、markdown 表格、per-role 背景色、跨平台安裝。
- LICENSE 設定著作權人。

## v1.0.0 — 2026-06-16

- 首版：agtLog — Claude Code transcript exporter skill。
- 將對話 transcript JSONL 還原成人可讀 HTML/txt，三種 view（full / simple / talk）、本地時間戳、路徑高亮。
