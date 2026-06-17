#!/usr/bin/env python3
"""session_start_reminder: SessionStart hook 用——開場提示「對話歸檔已啟用」。

由 settings.json 的 SessionStart hook 觸發。fail-open：任何錯誤都安靜 exit 0。
輸出一行精簡提醒到 stdout（成為 session 開場 context）。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SK = Path(__file__).resolve().parent
DEFAULTS = {"enabled": True, "archive_dir": "~/.claude/session-archive"}


def main() -> int:
    try:
        sys.stdin.read()  # 排空 payload，內容不需要
    except Exception:
        pass
    conf = dict(DEFAULTS)
    try:
        cfg = SK.parent / "archive.conf.json"
        if cfg.is_file():
            conf.update(json.loads(cfg.read_text(encoding="utf-8")))
    except Exception:
        pass
    if not conf.get("enabled", True):
        return 0
    try:
        archive = Path(conf["archive_dir"]).expanduser()
        n = len(list(archive.glob("**/*.html"))) if archive.is_dir() else 0
        loc = conf["archive_dir"]
        print(f"[agtLog] 對話歸檔已啟用：結束時自動存 talk 版到 {loc}/<專案>/（已存 {n} 檔）。"
              f"補建全部歷史：python3 ~/.claude/skills/agtLog/scripts/agtLog.py --scope init-all（產 index.html）。"
              f"要 simple/full/全部版本：加 --view simple｜--view full，或 init-all 加 --views simple,talk,full")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
