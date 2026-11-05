"""Chat-style HTML for the reference and model transcripts (agent on one side, customer on the other)."""
import html

STYLE = """
<style>
.chat{font-family:system-ui,-apple-system,"Segoe UI","Noto Naskh Arabic",sans-serif;display:flex;flex-direction:column;gap:6px;
      max-height:640px;overflow-y:auto;padding:8px;border-radius:10px;background:var(--block-background-fill)}
.msg{max-width:85%;padding:8px 12px;border-radius:12px;line-height:1.6;font-size:15px;color:#111}
.msg .who{font-size:11px;opacity:.7;margin-bottom:2px;direction:ltr;text-align:left}
.agent{align-self:flex-start;background:#e8f0fe}
.customer{align-self:flex-end;background:#e6f4ea}
.ivr{align-self:center;background:#eee;font-style:italic;color:#555}
.unknown{align-self:flex-start;background:#fdf3e1}
.flag{font-size:11px;color:#b45309;direction:ltr;text-align:left}
.empty{opacity:.5;font-style:italic}
.chat-empty{padding:24px;text-align:center;opacity:.6}
</style>
"""


def _mmss(x):
    return f"{int(x // 60):02d}:{x % 60:04.1f}"


def _bubble(role, who, text, flag=""):
    cls = role if role in ("agent", "customer", "ivr") else "unknown"
    body = html.escape(text) if text else '<span class="empty">(no text)</span>'
    f = f'<div class="flag">{html.escape(flag)}</div>' if flag else ""
    return (f'<div class="msg {cls}"><div class="who">{html.escape(who)}</div>'
            f'<div dir="rtl">{body}</div>{f}</div>')


def empty(msg):
    return STYLE + f'<div class="chat"><div class="chat-empty">{html.escape(msg)}</div></div>'


def reference_html(items, meta=None):
    if not items:
        return empty("No reference transcript for this audio. Upload one (JSON or SRT) to see it here and get a score.")
    head = ""
    if meta and meta.get("call_id"):
        head = f'<div class="who" style="padding:4px 2px">{html.escape(str(meta.get("call_id")))}</div>'
    parts = []
    for i in items:
        role = i.get("role") or ""
        who = role.capitalize() or "Speaker"
        if i.get("speaker") and role != "ivr":
            who += f" · {i['speaker']}"
        if i.get("start") is not None:
            who += f" · {_mmss(i['start'])}"
        parts.append(_bubble(role, who, i["text"]))
    return STYLE + head + '<div class="chat">' + "".join(parts) + "</div>"


def model_html(rows, show_blank=False):
    if not rows:
        return empty("Run a model to see its transcript here.")
    parts = []
    for r in rows:
        if not r["text"] and not show_blank:
            continue
        role = r.get("role") or ""
        spk = "" if r["speaker"] == "?" else f" · {r['speaker']}"
        who = f"{role.capitalize() or 'Segment'}{spk} · {_mmss(r['start'])}–{_mmss(r['end'])}"
        parts.append(_bubble(role, who, r["text"], r.get("status", "")))
    return STYLE + '<div class="chat">' + "".join(parts) + "</div>"
