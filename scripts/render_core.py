#!/usr/bin/env python3
"""render_core: agtLog skill 的唯一渲染核心（單一事實來源）。

職責：jsonl → 結構化 turns → txt/html 文字。所有 CLI 入口（agtLog.py 與三支
舊轉接 script）都呼叫這裡，避免邏輯重複。

三種視圖 view：
  full   ：逐字 + 工具全展開 + tool_result（保留 isMeta 注入，1:1 還原；不合併）
  simple ：對話 + 工具單行摘要（濾 isMeta、合併連續同角色、略過 tool_result/thinking）
  talk   ：只有 user/assistant 對話文字（同 simple 但工具全不顯示）

時間戳：每則 turn 取首筆 entry 的 timestamp，轉本地時間 [YYYY-MM-DD HH:MM:SS]。
HTML：依元素類型上色，並把檔案/路徑高亮成藍色 span。
"""
from __future__ import annotations
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # 純函式庫，僅為跨平台一致性
except Exception:
    pass

# ── 視圖設定 ────────────────────────────────────────────────────────────────
VIEWS = {
    "full":   {"keep_meta": True,  "merge": False, "tools": "full", "results": True,  "think": True,  "style": "block"},
    "simple": {"keep_meta": False, "merge": True,  "tools": "one",  "results": False, "think": False, "style": "compact"},
    "talk":   {"keep_meta": False, "merge": True,  "tools": "none", "results": False, "think": False, "style": "compact"},
}

DISPLAY = {"Edit": "Update", "MultiEdit": "Update", "NotebookEdit": "Update"}  # 仿 Claude Code 畫面


# ── transcript 定位 ─────────────────────────────────────────────────────────
def encode_project_dirname(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def find_transcript(cwd: str) -> Path | None:
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return None
    candidates: list[Path] = []
    proj_dir = projects / encode_project_dirname(cwd)
    if proj_dir.is_dir():
        candidates = list(proj_dir.glob("*.jsonl"))
    if not candidates:
        candidates = list(projects.glob("*/*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def to_local(ts) -> str:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


# slash command 在 jsonl 裡存成 <command-name>/foo</command-name><command-args>…</command-args>
# （使用者實際只打了 `/foo 參數`）。還原成可讀指令，非 command 文字原樣回傳。
_CMD_NAME_RE = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.S)
_CMD_ARGS_RE = re.compile(r"<command-args>\s*(.*?)\s*</command-args>", re.S)


def clean_command_text(text: str) -> str:
    if "<command-name>" not in text:
        return text
    m = _CMD_NAME_RE.search(text)
    if not m:
        return text
    name = m.group(1).strip()
    am = _CMD_ARGS_RE.search(text)
    args = am.group(1).strip() if am else ""
    return f"{name} {args}".strip() if args else name


def _user_text_piece(text: str, clean_cmd: bool) -> tuple[str, str]:
    """user 文字 → (kind, text)。命令還原成 `/cmd` 並標 kind='command'（HTML 另上色）。"""
    if clean_cmd and "<command-name>" in text:
        return ("command", clean_command_text(text))
    return ("text", text)


# ── block 渲染 ──────────────────────────────────────────────────────────────
def _short_home(p: str) -> str:
    home = str(Path.home())
    return "~" + p[len(home):] if p.startswith(home) else p


def tool_summary(block: dict, arg_width: int = 80) -> str:
    """tool_use → 單行 `ToolName(主要參數)`。"""
    name = block.get("name", "?")
    inp = block.get("input", {}) or {}
    display = DISPLAY.get(name, name)
    if name in ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit"):
        arg = _short_home(str(inp.get("file_path") or inp.get("notebook_path") or ""))
    elif name == "Bash":
        cmd_lines = str(inp.get("command", "")).strip().splitlines()
        arg = inp.get("description") or (cmd_lines[0] if cmd_lines else "")
    elif name == "Skill":
        arg = inp.get("skill") or inp.get("command", "")
    elif name in ("Glob", "Grep"):
        arg = inp.get("pattern", "")
    elif name in ("Task", "Agent"):
        arg = inp.get("description", "")
    elif name == "WebFetch":
        arg = inp.get("url", "")
    elif name in ("TodoWrite", "ExitPlanMode", "EnterPlanMode"):
        arg = ""
    else:
        arg = next((str(v) for v in inp.values() if isinstance(v, str)), "")
    arg = str(arg).strip().replace("\n", " ")
    if len(arg) > arg_width:
        arg = arg[:arg_width] + "…"
    return f"{display}({arg})"


def _tool_use_full(block: dict) -> str:
    name = block.get("name", "?")
    inp = block.get("input", {})
    if isinstance(inp, dict) and "command" in inp and len(inp) <= 3:
        body = str(inp.get("command", ""))
        extra = {k: v for k, v in inp.items() if k != "command"}
        if extra:
            body += "\n" + json.dumps(extra, ensure_ascii=False, indent=2)
    else:
        body = json.dumps(inp, ensure_ascii=False, indent=2)
    return f"🔧 [TOOL_USE: {name}]\n{body}"


def _tool_result(block: dict, max_result_chars: int) -> str:
    content = block.get("content", "")
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(c.get("text", "") if c.get("type") == "text" else json.dumps(c, ensure_ascii=False))
            else:
                parts.append(str(c))
        content = "\n".join(parts)
    content = str(content)
    if max_result_chars and len(content) > max_result_chars:
        content = content[:max_result_chars] + f"\n…[截斷，原長 {len(content)} 字]"
    return f"📤 [TOOL_RESULT]\n{content}"


# ── 收集 ────────────────────────────────────────────────────────────────────
def collect(transcript: Path, view: str, include_thinking: bool = False,
            max_result_chars: int = 0, arg_width: int = 80) -> list[dict]:
    """jsonl → [{role, ts, pieces:[(kind, text)]}]，依 view 過濾/合併。"""
    cfg = VIEWS[view]
    turns: list[dict] = []
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
            if not cfg["keep_meta"] and obj.get("type") == "user" and obj.get("isMeta"):
                continue  # 濾 skill 注入 / hook feedback 等非對話內容
            msg = obj.get("message")
            if not isinstance(msg, dict):
                continue
            role = (msg.get("role") or obj["type"]).lower()
            model = msg.get("model") if role == "assistant" else None
            content = msg.get("content")

            # full 視圖逐字 1:1，保留原始 <command-*>；simple/talk 還原成可讀 /cmd
            clean_cmd = role == "user" and not cfg["keep_meta"]

            pieces: list[tuple[str, str]] = []
            if isinstance(content, str):
                if content.strip():
                    pieces.append(_user_text_piece(content, clean_cmd) if role == "user" else ("text", content))
            elif isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "text" and b.get("text", "").strip():
                        pieces.append(_user_text_piece(b["text"], clean_cmd) if role == "user"
                                      else ("text", b["text"]))
                    elif bt == "thinking" and cfg["think"] and include_thinking:
                        pieces.append(("thinking", f"🧠 [THINKING]\n{b.get('thinking', '')}"))
                    elif bt == "tool_use":
                        if cfg["tools"] == "full":
                            pieces.append(("tool_use", _tool_use_full(b)))
                        elif cfg["tools"] == "one":
                            pieces.append(("tool", tool_summary(b, arg_width)))
                        # none → 略過
                    elif bt == "tool_result" and cfg["results"]:
                        pieces.append(("tool_result", _tool_result(b, max_result_chars)))

            if not pieces:
                continue
            ts = to_local(obj.get("timestamp"))
            if cfg["merge"] and turns and turns[-1]["role"] == role:
                turns[-1]["pieces"].extend(pieces)
                if not _real_model(turns[-1].get("model")) and _real_model(model):
                    turns[-1]["model"] = model  # 合併時補上真模型名
            else:
                turns.append({"role": role, "ts": ts, "model": model, "pieces": pieces})
    return turns


def _real_model(m) -> bool:
    return bool(m) and m != "<synthetic>"


def role_label(turn: dict) -> str:
    """assistant 顯示 model 名（如 claude-opus-4-8）；合成/缺值退回 ASSISTANT。"""
    if turn["role"] == "assistant":
        return turn["model"] if _real_model(turn.get("model")) else "ASSISTANT"
    return turn["role"].upper()


# ── txt 輸出 ────────────────────────────────────────────────────────────────
def emit_txt(turns: list[dict], view: str, show_ts: bool = True) -> str:
    style = VIEWS[view]["style"]
    out: list[str] = []
    for t in turns:
        hdr = (f"[{t['ts']}] " if (show_ts and t["ts"]) else "") + f"[{role_label(t)}]"
        if style == "block":
            out += ["=" * 80, hdr, "", "\n\n".join(text for _k, text in t["pieces"]), ""]
        else:
            out.append(hdr)
            for kind, text in t["pieces"]:
                if kind == "tool":
                    out.append(f"  • {text}")
                elif kind == "command":
                    out.append(f"⌘ {text.rstrip()}")
                else:
                    out.append(text.rstrip())
            out.append("")
    return "\n".join(out) + "\n"


# ── html 輸出（含路徑高亮）──────────────────────────────────────────────────
# ASCII-only 字元類，避免 `\w` 匹配到中文（`中文/中文` 會被誤判為路徑）
_PATH_RE = re.compile(
    r"((?:~|/)?[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)+|\b[A-Za-z0-9._\-]+\.(?:py|md|js|ts|tsx|jsx|json|jsonl|html|sh|txt|css|cjs|mjs|yml|yaml|toml|conf|cfg|ini|lock|sql|rs|go|java|rb|c|h|cpp))\b"
)


def _esc_paths(text: str) -> str:
    """HTML-escape，並把檔案/路徑 token 包成 <span class='path'>。"""
    out, last = [], 0
    for m in _PATH_RE.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        out.append(f"<span class='path'>{html.escape(m.group(0))}</span>")
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


# ── markdown 表格 → HTML <table>（僅 simple/talk；full 逐字保留）──────────────
def _md_cells(line: str) -> list[str]:
    """`| a | b |` → ['a','b']（剝除首尾 pipe，逐格 strip）。"""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_md_sep(line: str) -> bool:
    """表格分隔列：`|---|:--:|` 各格只含 - 與選用對齊冒號。"""
    if "|" not in line:
        return False
    cells = _md_cells(line)
    return bool(cells) and any(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells if c)


def _md_table_html(header: str, sep: str, rows: list[str]) -> str:
    aligns = []
    for c in _md_cells(sep):
        l, r = c.startswith(":"), c.endswith(":")
        aligns.append("center" if l and r else "right" if r else "left" if l else "")

    def cell(c: str, tag: str, i: int) -> str:
        a = aligns[i] if i < len(aligns) else ""
        st = f" style='text-align:{a}'" if a else ""
        return f"<{tag}{st}>{_esc_paths(c)}</{tag}>"

    out = ["<table class='md'><thead><tr>"]
    out += [cell(c, "th", i) for i, c in enumerate(_md_cells(header))]
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        out += [cell(c, "td", i) for i, c in enumerate(_md_cells(row))]
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _render_text_html(text: str) -> str:
    """text piece → HTML：連續 markdown 表格區塊轉 <table>，其餘原樣（路徑高亮 + pre-wrap）。
    ``` code fence 內不轉。"""
    lines = text.split("\n")
    out: list[str] = []
    buf: list[str] = []
    fence = False
    i, n = 0, len(lines)

    def flush():
        if buf:
            out.append(_esc_paths("\n".join(buf)))
            buf.clear()

    while i < n:
        line = lines[i]
        if line.strip().startswith("```"):
            fence = not fence
            buf.append(line); i += 1; continue
        if not fence and "|" in line and i + 1 < n and _is_md_sep(lines[i + 1]):
            j = i + 2
            rows = []
            while j < n and lines[j].strip() and "|" in lines[j] and not _is_md_sep(lines[j]):
                rows.append(lines[j]); j += 1
            flush()
            out.append(_md_table_html(line, lines[i + 1], rows))
            i = j
            continue
        buf.append(line); i += 1
    flush()
    return "".join(out)


_HTML_CSS = """
:root{--bg:#1e1e2e;--fg:#cdd6f4;--user:#89dceb;--asst:#a6e3a1;--tool:#f9e2af;
--result:#9399b2;--think:#cba6f7;--line:#45475a;--path:#89b4fa;--ts:#6c7086;--cmd:#fab387;}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);margin:0;padding:24px;max-width:1000px;
margin:0 auto;font:14px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
h1{font-size:15px;border-bottom:1px solid var(--line);padding-bottom:8px;margin:0 0 20px}
.turn{border-left:3px solid var(--line);padding:8px 12px;margin:14px 0;border-radius:0 6px 6px 0}
.turn.user{border-left-color:var(--user);background:#16233d}
.turn.assistant{border-left-color:var(--asst);background:#1a2a1c}
.role{font-weight:700;margin-bottom:6px}
.user .role{color:var(--user)}.assistant .role{color:var(--asst)}
.ts{color:var(--ts);font-weight:400}
.piece{white-space:pre-wrap;word-break:break-word;margin:4px 0}
.piece.tool{color:var(--tool);margin-left:8px}.piece.tool::before{content:'• '}
.piece.tool_use{color:var(--tool);background:#181825;padding:8px 10px;border-radius:6px}
.piece.tool_result{color:var(--result);background:#181825;padding:8px 10px;border-radius:6px}
.piece.thinking{color:var(--think);font-style:italic}
.piece.command{color:var(--cmd);font-weight:600}.piece.command::before{content:'⌘ '}
.path{color:var(--path)}
table.md{border-collapse:collapse;margin:8px 0;white-space:normal;max-width:100%}
table.md th,table.md td{border:1px solid var(--line);padding:4px 10px;text-align:left;vertical-align:top}
table.md th{color:var(--user);background:#181825;font-weight:700}
""".strip()


def emit_html(turns: list[dict], view: str, title: str, show_ts: bool = True) -> str:
    # full 視圖逐字 1:1；simple/talk 把 markdown 表格轉成真表格
    convert_tables = view != "full"
    out = ["<!DOCTYPE html><html lang='zh-Hant'><head><meta charset='utf-8'>",
           f"<title>{html.escape(title)}</title><style>{_HTML_CSS}</style></head><body>",
           f"<h1>{html.escape(title)}</h1>"]
    for t in turns:
        role = t["role"]
        ts_html = f"<span class='ts'>[{html.escape(t['ts'])}]</span> " if (show_ts and t["ts"]) else ""
        out.append(f"<div class='turn {html.escape(role)}'><div class='role'>{ts_html}{html.escape(role_label(t))}</div>")
        for kind, text in t["pieces"]:
            inner = _render_text_html(text) if (kind == "text" and convert_tables) else _esc_paths(text)
            out.append(f"<div class='piece {html.escape(kind)}'>{inner}</div>")
        out.append("</div>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def render(transcript: Path, view: str, fmt: str, show_ts: bool = True,
           include_thinking: bool = False, max_result_chars: int = 0,
           arg_width: int = 80, title: str | None = None) -> tuple[str, int]:
    """一站式：transcript → (body, turn 數)。"""
    turns = collect(transcript, view, include_thinking, max_result_chars, arg_width)
    if fmt == "html":
        body = emit_html(turns, view, title or f"agtLog ({view}) — {transcript.name}", show_ts)
    else:
        body = emit_txt(turns, view, show_ts)
    return body, len(turns)
