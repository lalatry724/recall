#!/usr/bin/env python3
"""catalog: agtLog 歸檔狀態（記錄檔 + 黑名單）的讀寫共用模組。

每個歸檔專案資料夾 `<archive>/<專案>/` 下一份 `_catalog.json`：
  - sessions：曾產生過哪些 session（manifest）→ 供「整理(tidy)」偵測手刪
  - blacklist：被拉黑的 session stem 清單 → init-all / hook 永不重產

stem = transcript 檔名去副檔（session UUID），session 的穩定唯一身份。
純標準庫、相容 Py3.8；寫入用 temp+rename 原子落盤。
"""
from __future__ import annotations
import json
import os
from pathlib import Path

CATALOG_NAME = "_catalog.json"


def _empty(project_name: str = "") -> dict:
    return {"version": 1, "project": project_name, "sessions": {}, "blacklist": []}


def path_for(project_dir: Path) -> Path:
    return Path(project_dir) / CATALOG_NAME


def load(project_dir: Path) -> dict:
    """讀 `_catalog.json`；不存在或損壞 → 回空骨架（不覆寫原檔，save 時才落盤）。"""
    p = path_for(project_dir)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("version", 1)
                data.setdefault("project", Path(project_dir).name)
                data.setdefault("sessions", {})
                data.setdefault("blacklist", [])
                return data
        except Exception:
            pass
    return _empty(Path(project_dir).name)


def save(project_dir: Path, cat: dict) -> None:
    """原子寫回（temp + os.replace）。"""
    d = Path(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = path_for(d)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def is_blacklisted(cat: dict, stem: str) -> bool:
    return stem in cat.get("blacklist", [])


def record_session(cat: dict, stem: str, *, views: dict, turns: int,
                   bytes_: int, summary: str, start: str, end: str) -> None:
    """寫入/更新一筆 session 記錄。黑名單中的 session 不記錄（防誤復活）。"""
    if is_blacklisted(cat, stem):
        return
    cat.setdefault("sessions", {})[stem] = {
        "views": dict(views), "turns": turns, "bytes": bytes_,
        "summary": summary, "start": start, "end": end,
    }


def find_deleted(cat: dict, project_dir: Path) -> list:
    """記錄有、但其各 view 檔在磁碟『全數不存在』→ 視為被手刪。回傳 stem 清單。"""
    d = Path(project_dir)
    deleted = []
    for stem, rec in cat.get("sessions", {}).items():
        files = list((rec or {}).get("views", {}).values())
        if files and all(not (d / f).exists() for f in files):
            deleted.append(stem)
    return deleted


def add_to_blacklist(cat: dict, stems: list) -> int:
    """加入黑名單並從 sessions 移除；回傳實際新增筆數。"""
    bl = cat.setdefault("blacklist", [])
    sess = cat.setdefault("sessions", {})
    added = 0
    for s in stems:
        if s not in bl:
            bl.append(s)
            added += 1
        sess.pop(s, None)
    return added


def clear(cat: dict, project_dir: Path) -> int:
    """reset：清空 blacklist + 移除『檔已不存在』的殘留記錄。回傳解黑筆數。"""
    n = len(cat.get("blacklist", []))
    cat["blacklist"] = []
    for stem in find_deleted(cat, project_dir):
        cat.get("sessions", {}).pop(stem, None)
    return n
