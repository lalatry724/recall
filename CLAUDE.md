# CLAUDE.md — agtLog 專案地圖

> 開發本專案的導航入口（自動載入）。這裡只放「去哪查、看哪檔」的指路，**權威內容不複製**，改動時改它的 SoT 即可。

## 這是什麼

Claude Code skill：把 `~/.claude/projects/*/*.jsonl` transcript 還原成可讀 HTML/txt（三視圖 full/simple/talk）。薄包裝，渲染核心是純標準庫 Python、零 AI token。主名 `agtLog`，保留別名 `recall`。

## 權威文件（SoT — 要查先看這些）

| 想知道 | 看哪份 |
|--------|--------|
| **指令速查（可直接複製跑）** | `COMMANDS.md` |
| 對 AI 的呼叫規約、CLI 選項、view 選擇、hook 行為 | `SKILL.md` |
| 對外說明、安裝（mac/Win 差異）、補建/重建機制、repo 版面 | `README.md` |
| 版本異動史（最新在上） | `version.md` |
| 開發歷程隨筆 | `devlog.md` |
| 結案檢討報告 | `_internal/report/retrospective_*.md` |

## 程式檔職責（`scripts/`）

| 檔 | 職責 |
|----|------|
| `render_core.py` | **唯一渲染核心（single source of truth）**。JSONL→區塊→HTML/txt 全在此；改 render 行為只動這支 |
| `agtLog.py` | CLI 入口。解析 args、定位 transcript、呼叫 render_core、輸出 JSON 狀態；含 tidy/reset/init-all |
| `catalog.py` | 歸檔狀態共用模組。每專案 `_catalog.json`（manifest + 黑名單）讀寫；agtLog.py 與 hook 共用 |
| `session_end_archive.py` | SessionEnd hook：session 結束自動存 talk HTML（fail-open，永不阻擋結束） |
| `session_start_reminder.py` | SessionStart hook：印一行歸檔提醒 |

其他：`archive.conf.json`（自動歸檔設定）、`install.sh`（冪等註冊 hook 進 settings.json）、`evals/triggers.json`（skill 觸發 eval）。

## 改動時的鐵則

1. **render 邏輯只改 `render_core.py`**——agtLog.py 與兩個 hook 都走它，別在別處重做解析。
2. **JSONL 永遠經 `agtLog.py`，不手解析**——編碼/路徑/區塊/meta 陷阱都封在核心裡。
3. **路徑/編碼真源**：`render_core.encode_project_dirname`（`~/.claude/projects/<非英數→->`）。
4. **改了對外行為/CLI/檔案清單** → 同步 `SKILL.md` + `README.md` + `version.md`（語意化版號）。**內容不複製進本檔**，只在表格補一行指路。
5. **跨平台**：純標準庫、相容 Python 3.8（保留 `from __future__ import annotations`）；Windows 用 `python` 非 `python3`。

## 驗證

```bash
python scripts/agtLog.py                 # 當前 session → agtLog-talk.html
python scripts/agtLog.py --scope init-all  # 補建全部歷史 + index.html（冪等）
```
完成判準：stdout JSON `status == "ok"`。
