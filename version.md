# Version History — agtLog

本檔記錄 agtLog skill 的所有版本異動。最新在上。

## v1.5.1 — 2026-06-24

新增 `deploy.sh` / `deploy.ps1` 雙版本部署腳本：把開發 repo 同步進 live skill 資料夾。

- **問題根因**：開發 repo（`<repo>/`）與部署 skill（`~/.claude/skills/agtLog/`）是**兩份獨立複製**。`install.sh` 只註冊 hook 到 `settings.json`、**不複製檔案**，故 `git pull` 更新 repo 後部署版仍是舊的——Claude Code 與 SessionEnd/SessionStart hook 跑的都是部署版，新功能（如 `remove`/`tidy`）不生效。
- **`deploy.sh`（mac/Linux/Git-Bash）+ `deploy.ps1`（Windows 原生 PowerShell）**：白名單複製（scripts 的 .py、SKILL/COMMANDS/README/version/devlog、install.sh、LICENSE、evals）；明確排除開發專屬檔（`.claude/`、`_internal/`、`CLAUDE.md`、`userChatLog.md`、`.gemini/`、`.git`、`__pycache__`）。
- **保護使用者設定**：`archive.conf.json` 只在部署版缺檔時複製，**已存在則保留不覆蓋**（避免洗掉手動改的 `enabled:false` 等）。複製後清部署版 `__pycache__` 避免載到舊 bytecode；冪等可重跑，`DEST` 環境變數可覆寫目標。
- **新 SOP**：`git pull` 後跑一次 `deploy.sh`（或 `deploy.ps1`）→ 部署版即追到最新。

## v1.5.0 — 2026-06-23

`index.html` 每列加 remove 鈕：在索引頁直接標記要清掉的對話，套用後封存＋拉黑。

- **索引頁 remove 鈕（前端）**：`init-all` 產的 `index.html` 每列前多一顆 ✕。按下標記該則（變暗＋刪除線、存 `localStorage`），底部固定面板統計待移除數並產出一條可複製的套用指令。純 vanilla JS、無外部相依，`file://` 雙擊即可用；複製走 `navigator.clipboard`，失敗自動 fallback `execCommand`。
- **套用指令 `--scope remove --items proj:stem,proj:stem,...`**：把選定 session 的歸檔檔**移到 `<archive>/<專案>/_removed/`**（封存非刪，可手動救回）並加入黑名單，最後自動重建索引——之後 `init-all` / SessionEnd hook 不再產出該則。
- **設計取捨**：靜態 HTML 受瀏覽器沙箱限制無法自行搬檔/寫黑名單，故採「前端標記 → 複製指令 → 終端機套用」兩段式；黑名單與 `reset` 救回機制沿用 v1.4.0 的 `catalog.py`，零新狀態檔。

## v1.4.0 — 2026-06-23

新增「對話記錄 整理 / 清理」機制：歸檔黑名單 + 每專案記錄檔 + 全域目錄加檔案大小。

- **每專案記錄檔 `_catalog.json`**：`<archive>/<專案>/` 下一份，記錄曾產生過的 session（manifest：turns / bytes / 摘要 / 時間）＋ `blacklist`。新增共用模組 `scripts/catalog.py`（state 讀寫，原子落盤，純標準庫）。
- **整理指令 `--scope tidy [--project <名>] [--confirm]`**：比對記錄 vs 磁碟，把「曾產生、現已被手刪」的對話自動拉黑，之後永不重產。觸發詞「整理對話記錄」「清理對話記錄」。單專案候選 > 20 筆且無 `--confirm` → 只回報不寫（防誤拉黑整批）。
- **重置指令 `--scope reset --project <名>`**：清空指定專案的黑名單 + 殘留記錄 → 下次 init-all 可重產（後悔藥；`--project` 必填防手滑）。
- **黑名單落實兩處**：`init-all` 產出前跳過黑名單 session 並回報 `blacklisted` 計數、產出後更新 catalog；SessionEnd hook 同步認黑名單 + 維護 catalog。
- **全域 `index.html` 加檔案大小欄**、排除黑名單 session；摘要沿用首句 user 訊息（維持零 AI token）。

## v1.3.0 — 2026-06-17

skill 改名 `recall` → `agtLog`。

- **全面改名**：skill name、主程式 `scripts/recall.py` → `scripts/agtLog.py`（內部 `from recall import` → `from agtLog import`）、輸出檔名前綴 `recall*` → `agtLog*`、文件/路徑全數更新。
- **保留 `recall` 別名**：triggers 仍含 `recall`、`/recall`，召喚率不退步；主名為 `agtLog`、`/agtLog`。
- **部署端同步**：`~/.claude/skills/recall/` → `~/.claude/skills/agtLog/`，`settings.json` 兩個 hook 路徑就地更新（無重複註冊）。
- **remote**：`github.com/lalatry724/recall` → `github.com/lalatry724/agtLog`。

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
