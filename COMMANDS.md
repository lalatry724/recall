# COMMANDS.md — agtLog 指令清單（速查）

> 可直接複製貼上執行。權威選項表在 `SKILL.md` / `README.md`；本檔是常用指令的單頁速查。
> **Windows 用 `python`，mac/Linux 用 `python3`**（裸 `python3` 在 Windows 是 Store 空跳板）。

## 最常用

| 想做的事 | 指令 |
|----------|------|
| 存當前 session（talk，預設） | `python scripts/agtLog.py` |
| 當前 session ＋工具單行摘要 | `python scripts/agtLog.py --view simple` |
| 當前 session 逐字＋工具本文 | `python scripts/agtLog.py --view full` |
| 匯出全部歷史到 `./session-export/` | `python scripts/agtLog.py --scope all` |
| 補建全部歷史到歸檔區（冪等＋index） | `python scripts/agtLog.py --scope init-all` |
| 補建三視圖 | `python scripts/agtLog.py --scope init-all --views simple,talk,full` |
| 重建全部（改了 render 後） | `python scripts/agtLog.py --scope init-all --force` |
| 重產單一 session | `python scripts/agtLog.py --transcript <jsonl> --output <path>` |

## 整理 / 清理歸檔（黑名單）

先到 `~/.claude/session-archive/<專案>/` 手刪沒價值的 HTML，再跑整理把它們拉黑（之後不重產）。

| 想做的事 | 指令 |
|----------|------|
| 整理（拉黑已手刪的對話） | `python scripts/agtLog.py --scope tidy` |
| 只整理某專案資料夾 | `python scripts/agtLog.py --scope tidy --project <名>` |
| 拉黑數 >20 仍要執行 | `python scripts/agtLog.py --scope tidy --confirm` |
| 重置某專案（解黑→可重產） | `python scripts/agtLog.py --scope reset --project <名>` |

- 拉黑只在明確跑 `tidy` 時發生，init-all 不會自動拉黑。
- 單專案候選 >20 筆且無 `--confirm` → 只回報不寫（防誤刪整批）。
- `reset` 是後悔藥；`--project` 必填防手滑全清。

## 選項一覽

| 選項 | 值（粗體為預設） | 意義 |
|------|------------------|------|
| `--scope` | **current** / all / init-all | 當前 session／全部→`./session-export/`／全部→`~/.claude/session-archive/<專案>/`(+index) |
| `--view` | full / simple / **talk** | 逐字+工具／工具單行／純對話 |
| `--views` | — | 限 init-all：逗號清單覆寫 conf，如 `simple,talk,full` |
| `--format` | **html** / txt | 預設彩色 HTML |
| `--timestamps` / `--no-timestamps` | **on** | 每輪前綴本地時間 `[YYYY-MM-DD HH:MM:SS]` |
| `--include-thinking` | off | full 視圖含 thinking 區塊 |
| `--include-subagents` | off | 含 sub-agent transcript（scope all / init-all） |
| `--force` | off | init-all：重建既有歸檔（預設冪等跳過） |
| `--project` | — | tidy/reset：限定某專案歸檔資料夾名（reset 必填） |
| `--confirm` | off | tidy：拉黑數超門檻(20)時確認執行 |
| `--arg-width N` | 80 | simple 視圖工具參數截斷寬度 |
| `--max-result-chars N` | 0 | full 視圖 tool_result 截斷（0=不截） |
| `--output` / `--output-dir` / `--transcript` / `--cwd` | — | 路徑覆寫 |

## 三視圖怎麼選

| 視圖 | 內容 | 適用 |
|------|------|------|
| **talk**（預設） | 只 user/assistant 文字，隱藏工具 | 讀脈絡，最乾淨 |
| **simple** | 對話＋工具單行摘要 `• Update(file)` | 回顧、找未處理項目 |
| **full** | 逐字＋工具本文＋結果，meta 保留 1:1 | 稽核、重現 |

## 安裝 / 維運

| 想做的事 | 指令 |
|----------|------|
| 註冊自動歸檔 hook（Git Bash） | `bash ~/.claude/skills/agtLog/install.sh` |
| 關閉自動歸檔 | 改 `archive.conf.json` → `"enabled": false` |
| 不裝 skill 直接跑 | `python ~/.claude/skills/agtLog/scripts/agtLog.py --scope all` |

## 完成判準

stdout 是一行 JSON：`status == "ok"` 即成功（附 `output` / `turns`）。`status == "fail"` 多為 transcript 找不到，照 `error` 欄回報、勿自行繞道。
