#!/usr/bin/env python3
"""agtLog: agtLog skill 的單一 CLI 入口。

把 Claude Code 對話 transcript 轉成人可讀檔，渲染全走 render_core（單一事實來源）。

  --scope current|all|init-all   當前 session（預設）/ 全部→session-export/ /
                                 全部→session-archive/<專案>/<view>/（與 hook 合一，產 index）
  --force               init-all 時強制重建已存在的歸檔（預設冪等跳過）
  --view  full|simple|talk   逐字 / 工具單行(預設) / 純對話
  --format html|txt     預設 html
  --timestamps / --no-timestamps   每則前綴本地時間（預設開）
  --include-thinking    full 視圖額外納入 thinking
  --include-subagents   scope=all 時連子 agent 對話一起匯出
  --max-result-chars N  full 的 tool_result 截斷
  --arg-width N         simple 工具參數截斷寬（預設 80）
  --output / --output-dir / --transcript / --cwd

輸出 JSON 到 stdout (UTF-8)。exit 0 成功，1 業務失敗，2 內部錯誤。
"""
from __future__ import annotations
import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_core as rc  # noqa: E402
import catalog  # noqa: E402

EXT = {"html": "html", "txt": "txt"}


def _default_name(view: str, fmt: str) -> str:
    suffix = "" if view == "full" else f"-{view}"
    return f"agtLog{suffix}.{EXT[fmt]}"


def _human_size(n: int) -> str:
    """位元組轉人類可讀（B/KB/MB）。"""
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{int(f)} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{n} B"


def run_current(cwd, transcript, view, fmt, show_ts, include_thinking, max_result_chars, arg_width, output) -> dict:
    if transcript:
        tp = Path(transcript).expanduser()
        if not tp.is_file():
            return {"status": "fail", "error": f"指定的 transcript 不存在: {tp}"}
    else:
        tp = rc.find_transcript(cwd)
        if tp is None:
            return {"status": "fail", "error": "找不到任何 transcript jsonl"}

    body, turns = rc.render(tp, view, fmt, show_ts, include_thinking, max_result_chars, arg_width)
    out_path = Path(output).expanduser() if output else Path(cwd) / _default_name(view, fmt)
    out_path.write_text(body, encoding="utf-8")
    return {"status": "ok", "scope": "current", "transcript": str(tp), "output": str(out_path),
            "view": view, "format": fmt, "timestamps": show_ts, "turns": turns,
            "bytes": len(body.encode("utf-8"))}


# ── scope=all 的索引輔助 ────────────────────────────────────────────────────
def _session_meta(transcript: Path) -> dict:
    """單次掃描取：首句、起始/結束時間（取自 user/assistant 的 timestamp）。"""
    first_prompt = ""
    start_raw = end_raw = None
    try:
        with transcript.open(encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") not in ("user", "assistant"):
                    continue
                ts = obj.get("timestamp")
                if ts:
                    if start_raw is None:
                        start_raw = ts
                    end_raw = ts
                if not first_prompt and obj.get("type") == "user" and not obj.get("isMeta"):
                    content = obj.get("message", {}).get("content")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                text = b.get("text", "")
                                break
                    text = rc.clean_command_text(text.strip())
                    if text and not text.startswith("<"):
                        first_prompt = text
    except Exception:
        pass
    return {"first_prompt": first_prompt or "(無法擷取首句)",
            "start": rc.to_local(start_raw), "end": rc.to_local(end_raw)}


def _slugify(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", text).strip("-")
    return (s[:limit] or "session").rstrip("-")


def _archive_base(start: str, title: str, stem: str) -> str:
    """歸檔檔名前綴：<date>_<HH-MM-SS>_<slug>_<id8>。
    time 取自 session 首則訊息時間（start 的時分秒），冒號換成 - 以相容 Windows 檔名。
    start 缺時間段時退回只有日期。"""
    date = start[:10]
    t = start[11:19].replace(":", "-") if len(start) >= 19 else ""
    stamp = f"{date}_{t}" if t else date
    return f"{stamp}_{_slugify(title)}_{stem[:8]}"


def archive_filename(base: str, view: str, ext: str) -> str:
    """歸檔檔名（扁平結構，無 view 子資料夾）：
    預設 talk 不加後綴（直放專案資料夾）；其餘 view 加 .<view> 後綴避免同名碰撞。
      talk   → <base>.html
      simple → <base>.simple.html
      full   → <base>.full.html
    """
    suffix = "" if view == "talk" else f".{view}"
    return f"{base}{suffix}.{ext}"


def run_all(projects_dir, output_dir, view, fmt, show_ts, include_thinking,
            include_subagents, max_result_chars, arg_width) -> dict:
    projects = Path(projects_dir).expanduser()
    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = EXT[fmt]

    jsonls = sorted(projects.glob("*/*.jsonl"))
    if include_subagents:
        jsonls += sorted(projects.glob("*/*/subagents/*.jsonl"))

    records: list[dict] = []
    errors: list[str] = []
    for jl in jsonls:
        proj = jl.relative_to(projects).parts[0].lstrip("-")
        try:
            body, turns = rc.render(jl, view, fmt, show_ts, include_thinking, max_result_chars,
                                    arg_width, title=f"{proj} — {jl.stem}")
            if turns == 0:
                continue
            meta = _session_meta(jl)
            # 日期/排序鍵優先用 session 起始時間，缺則退回檔案 mtime
            start = meta["start"] or datetime.fromtimestamp(jl.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            title = meta["first_prompt"]
            fname = f"{_archive_base(start, title, jl.stem)}.{ext}"
            (out_dir / proj).mkdir(parents=True, exist_ok=True)
            (out_dir / proj / fname).write_text(body, encoding="utf-8")
            records.append({"project": proj, "start": start, "end": meta["end"],
                            "turns": turns, "title": title, "rel": f"{proj}/{fname}"})
        except Exception as e:
            errors.append(f"{jl}: {type(e).__name__}: {e}")

    records.sort(key=lambda r: r["start"], reverse=True)
    records.sort(key=lambda r: r["project"])  # 依專案分組、組內新→舊
    index_name = "index.html" if fmt == "html" else "index.md"
    (out_dir / index_name).write_text(_index(records, fmt), encoding="utf-8")

    return {"status": "ok", "scope": "all", "output_dir": str(out_dir),
            "index": str(out_dir / index_name), "view": view, "format": fmt,
            "timestamps": show_ts, "sessions_exported": len(records),
            "sessions_total": len(jsonls), "errors": errors}


def _index(records: list[dict], fmt: str) -> str:
    if fmt != "html":
        lines = ["# Claude Code Session 匯出索引", "", f"共 {len(records)} 個 session（依專案、組內新→舊）", ""]
        cur = None
        for r in records:
            if r["project"] != cur:
                cur = r["project"]
                lines.append(f"\n## {cur}\n")
            lines.append(f"- [{_range(r)}] ({r['turns']} turns) [{r['title'][:60]}]({r['rel']})")
        return "\n".join(lines) + "\n"

    css = ("body{background:#1e1e2e;color:#cdd6f4;font:14px/1.6 ui-monospace,Menlo,Consolas,monospace;"
           "max-width:1000px;margin:0 auto;padding:24px}h1{border-bottom:1px solid #45475a;padding-bottom:8px}"
           "h2{color:#89dceb;margin-top:28px}a{color:#a6e3a1;text-decoration:none}a:hover{text-decoration:underline}"
           ".row{padding:4px 0;border-bottom:1px solid #313244}.meta{color:#9399b2}")
    out = ["<!DOCTYPE html><html lang='zh-Hant'><head><meta charset='utf-8'>",
           f"<title>Session 匯出索引</title><style>{css}</style></head><body>",
           "<h1>Claude Code Session 匯出索引</h1>",
           f"<p class='meta'>共 {len(records)} 個 session（依專案、組內新→舊）</p>"]
    cur = None
    for r in records:
        if r["project"] != cur:
            cur = r["project"]
            out.append(f"<h2>{html.escape(cur)}</h2>")
        out.append(f"<div class='row'><a href='{html.escape(r['rel'])}'>{html.escape(r['title'][:70])}</a>"
                   f"<span class='meta'> — {html.escape(_range(r))} · {r['turns']} turns</span></div>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def _range(r: dict) -> str:
    """起訖時間摘要：同日只顯一次日期。"""
    start, end = r.get("start", ""), r.get("end", "")
    if not start:
        return end or "?"
    if end and end[:10] == start[:10]:           # 同一天 → 日期 HH:MM–HH:MM
        return f"{start[:16]}–{end[11:16]}"
    return f"{start[:16]} → {end[:16]}" if end else start[:16]


# ── init-all：補建全部歷史，與 session-archive 合一 ─────────────────────────
def _load_archive_conf() -> dict:
    """讀 skill 根的 archive.conf.json（與 hook 同一份設定）。缺則用預設。"""
    conf = {"archive_dir": "~/.claude/session-archive", "views": ["talk"]}
    cfg = Path(__file__).resolve().parent.parent / "archive.conf.json"
    try:
        if cfg.is_file():
            conf.update(json.loads(cfg.read_text(encoding="utf-8")))
    except Exception:
        pass
    return conf


def run_init_all(projects_dir, archive_dir, views, fmt, show_ts, include_subagents, force) -> dict:
    """掃 ~/.claude/projects 全部 session，對每個 view 生一份，扁平落到
    <archive>/<專案>/<date>_<slug>_<id8>[.<view>].<ext>（talk 不加後綴），與 SessionEnd hook 同一棵。
    冪等：檔已存在則不重寫（--force 強制重建）。最後產頂層 index。"""
    projects = Path(projects_dir).expanduser()
    root = Path(archive_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    ext = EXT[fmt]

    jsonls = sorted(projects.glob("*/*.jsonl"))
    if include_subagents:
        jsonls += sorted(projects.glob("*/*/subagents/*.jsonl"))

    records: list[dict] = []
    errors: list[str] = []
    cats: dict[str, dict] = {}        # proj → catalog（同次 run 內快取，最後一次落盤）
    written = skipped = blacklisted = 0
    for jl in jsonls:
        proj = jl.relative_to(projects).parts[0].lstrip("-")
        try:
            cat = cats.get(proj)
            if cat is None:
                cat = cats[proj] = catalog.load(root / proj)
            if catalog.is_blacklisted(cat, jl.stem):  # 黑名單 → 完全不產
                blacklisted += 1
                continue
            meta = _session_meta(jl)
            start = meta["start"] or datetime.fromtimestamp(jl.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            title = meta["first_prompt"]
            base = _archive_base(start, title, jl.stem)
            view_rels: dict[str, str] = {}
            turns_seen = 0
            total_bytes = 0
            for view in views:
                # 一律 render（純 Python，便宜）以取得 turns；僅在缺檔/強制時才寫盤
                body, turns = rc.render(jl, view, fmt, show_ts, False, 0, 80,
                                        title=f"{proj} — {jl.stem}")
                if turns == 0:
                    continue
                turns_seen = max(turns_seen, turns)
                fname = archive_filename(base, view, ext)
                out_path = root / proj / fname
                if out_path.exists() and not force:
                    skipped += 1
                else:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(body, encoding="utf-8")
                    written += 1
                total_bytes += len(body.encode("utf-8"))
                view_rels[view] = f"{proj}/{fname}"
            if not view_rels:
                continue
            catalog.record_session(cat, jl.stem, views={v: Path(r).name for v, r in view_rels.items()},
                                   turns=turns_seen, bytes_=total_bytes, summary=title,
                                   start=start, end=meta["end"] or "")
            records.append({"project": proj, "start": start, "end": meta["end"],
                            "turns": turns_seen, "title": title, "views": view_rels,
                            "bytes": total_bytes})
        except Exception as e:
            errors.append(f"{jl}: {type(e).__name__}: {e}")

    for proj, cat in cats.items():        # 落盤各專案 catalog
        try:
            catalog.save(root / proj, cat)
        except Exception as e:
            errors.append(f"catalog {proj}: {type(e).__name__}: {e}")

    records.sort(key=lambda r: r["start"], reverse=True)
    records.sort(key=lambda r: r["project"])  # 依專案分組、組內新→舊
    index_name = "index.html" if fmt == "html" else "index.md"
    (root / index_name).write_text(_init_index(records, views, fmt), encoding="utf-8")

    return {"status": "ok", "scope": "init-all", "archive_dir": str(root),
            "index": str(root / index_name), "views": views, "format": fmt,
            "timestamps": show_ts, "sessions_total": len(jsonls),
            "sessions_indexed": len(records), "written": written,
            "skipped": skipped, "blacklisted": blacklisted, "errors": errors}


def _init_index(records: list[dict], views: list[str], fmt: str) -> str:
    """init-all 索引：依專案分組，每列一個 session 附各 view 連結。"""
    if fmt != "html":
        lines = ["# Claude Code 歷史對話歸檔索引", "",
                 f"共 {len(records)} 個 session（依專案、組內新→舊）", ""]
        cur = None
        for r in records:
            if r["project"] != cur:
                cur = r["project"]
                lines.append(f"\n## {cur}\n")
            links = " ".join(f"[{v}]({r['views'][v]})" for v in views if v in r["views"])
            size = _human_size(r.get("bytes", 0))
            lines.append(f"- [{_range(r)}] ({r['turns']} turns · {size}) {r['title'][:60]} — {links}")
        return "\n".join(lines) + "\n"

    css = ("body{background:#1e1e2e;color:#cdd6f4;font:14px/1.6 ui-monospace,Menlo,Consolas,monospace;"
           "max-width:1000px;margin:0 auto;padding:24px}h1{border-bottom:1px solid #45475a;padding-bottom:8px}"
           "h2{color:#89dceb;margin-top:28px}a{color:#a6e3a1;text-decoration:none}a:hover{text-decoration:underline}"
           ".row{padding:5px 0;border-bottom:1px solid #313244}.meta{color:#9399b2}"
           ".v{color:#f9e2af;margin-left:6px}.t{color:#cdd6f4}")
    out = ["<!DOCTYPE html><html lang='zh-Hant'><head><meta charset='utf-8'>",
           f"<title>歷史對話歸檔索引</title><style>{css}</style></head><body>",
           "<h1>Claude Code 歷史對話歸檔索引</h1>",
           f"<p class='meta'>共 {len(records)} 個 session（依專案、組內新→舊）· 每列附 {'/'.join(views)} 連結</p>"]
    cur = None
    for r in records:
        if r["project"] != cur:
            cur = r["project"]
            out.append(f"<h2>{html.escape(cur)}</h2>")
        links = "".join(f"<a class='v' href='{html.escape(r['views'][v])}'>[{html.escape(v)}]</a>"
                        for v in views if v in r["views"])
        size = _human_size(r.get("bytes", 0))
        out.append(f"<div class='row'><span class='t'>{html.escape(r['title'][:70])}</span>{links}"
                   f"<span class='meta'> — {html.escape(_range(r))} · {r['turns']} turns · {html.escape(size)}</span></div>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


# ── tidy / reset：整理與重置歸檔記錄 ────────────────────────────────────────
TIDY_THRESHOLD = 20  # 單專案單次拉黑候選 > 此數且無 --confirm → 只回報不寫


def _archive_projects(root: Path, project: str | None) -> list[Path]:
    """archive root 下、含 _catalog.json 的專案資料夾（或指定 --project）。"""
    if project:
        d = root / project
        return [d] if d.is_dir() else []
    return sorted(p for p in root.iterdir() if p.is_dir() and catalog.path_for(p).is_file())


def run_tidy(archive_dir, project, confirm) -> dict:
    """整理：比對記錄 vs 磁碟，把『曾產生、現已被手刪』的 session 拉黑。"""
    root = Path(archive_dir).expanduser()
    if not root.is_dir():
        return {"status": "fail", "error": f"歸檔目錄不存在: {root}"}
    results: list[dict] = []
    total_blacklisted = 0
    for d in _archive_projects(root, project):
        cat = catalog.load(d)
        deleted = catalog.find_deleted(cat, d)
        candidates = [s for s in deleted if not catalog.is_blacklisted(cat, s)]
        if not candidates:
            continue
        summaries = [cat["sessions"].get(s, {}).get("summary", s)[:60] for s in candidates]
        if len(candidates) > TIDY_THRESHOLD and not confirm:
            results.append({"project": d.name, "detected": len(candidates),
                            "blacklisted": 0, "needs_confirm": True, "samples": summaries[:5]})
            continue
        added = catalog.add_to_blacklist(cat, candidates)
        catalog.save(d, cat)
        total_blacklisted += added
        results.append({"project": d.name, "detected": len(candidates),
                        "blacklisted": added, "needs_confirm": False, "samples": summaries[:5]})
    return {"status": "ok", "scope": "tidy", "archive_dir": str(root),
            "total_blacklisted": total_blacklisted, "projects": results}


def run_reset(archive_dir, project) -> dict:
    """重置：清空指定專案的黑名單 + 殘留記錄 → 下次 init-all 可重產。"""
    root = Path(archive_dir).expanduser()
    if not project:
        return {"status": "fail", "error": "reset 必須指定 --project（防手滑全清）"}
    d = root / project
    if not d.is_dir():
        avail = ", ".join(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else ""
        return {"status": "fail", "error": f"找不到專案資料夾: {d}。可用: {avail}"}
    cat = catalog.load(d)
    freed = catalog.clear(cat, d)
    catalog.save(d, cat)
    return {"status": "ok", "scope": "reset", "project": project,
            "unblacklisted": freed, "hint": "跑 --scope init-all 重新生成"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["current", "all", "init-all", "tidy", "reset"], default="current")
    ap.add_argument("--view", choices=["full", "simple", "talk"], default="talk")
    ap.add_argument("--views", help="init-all 專用：逗號分隔多 view 覆寫 conf（例 simple,talk,full）")
    ap.add_argument("--format", choices=["html", "txt"], default="html")
    ap.add_argument("--timestamps", dest="timestamps", action="store_true", default=True)
    ap.add_argument("--no-timestamps", dest="timestamps", action="store_false")
    ap.add_argument("--include-thinking", action="store_true")
    ap.add_argument("--include-subagents", action="store_true")
    ap.add_argument("--force", action="store_true", help="init-all：強制重建已存在的歸檔")
    ap.add_argument("--project", help="tidy/reset：限定某專案歸檔資料夾名（reset 必填）")
    ap.add_argument("--confirm", action="store_true", help="tidy：拉黑數超門檻時確認執行")
    ap.add_argument("--max-result-chars", type=int, default=0)
    ap.add_argument("--arg-width", type=int, default=80)
    ap.add_argument("--cwd", default=os.environ.get("PWD") or os.getcwd())
    ap.add_argument("--output")
    ap.add_argument("--output-dir")
    ap.add_argument("--transcript")
    ap.add_argument("--projects-dir", default=str(Path.home() / ".claude" / "projects"))
    args = ap.parse_args()

    if args.scope == "all":
        out_dir = args.output_dir or str(Path(args.cwd) / "session-export")
        result = run_all(args.projects_dir, out_dir, args.view, args.format, args.timestamps,
                         args.include_thinking, args.include_subagents, args.max_result_chars, args.arg_width)
    elif args.scope == "init-all":
        conf = _load_archive_conf()
        archive_dir = args.output_dir or conf.get("archive_dir", "~/.claude/session-archive")
        if args.views:  # CLI 覆寫：產 simple/all 版本，例 --views simple,talk,full
            views = [v.strip() for v in args.views.split(",") if v.strip()]
        else:
            views = conf.get("views", ["talk"])
        result = run_init_all(args.projects_dir, archive_dir, views, args.format,
                              args.timestamps, args.include_subagents, args.force)
    elif args.scope in ("tidy", "reset"):
        conf = _load_archive_conf()
        archive_dir = args.output_dir or conf.get("archive_dir", "~/.claude/session-archive")
        if args.scope == "tidy":
            result = run_tidy(archive_dir, args.project, args.confirm)
        else:
            result = run_reset(archive_dir, args.project)
    else:
        result = run_current(args.cwd, args.transcript, args.view, args.format, args.timestamps,
                             args.include_thinking, args.max_result_chars, args.arg_width, args.output)

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        sys.exit(2)
