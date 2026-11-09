"""HTML for the app bar, status messages, score cards and chat-style transcripts."""
import html

ARABIC_FONT = '"IBM Plex Sans Arabic","Noto Naskh Arabic","Segoe UI",sans-serif'

STYLE = f"""
<style>
.chat{{display:flex;flex-direction:column;gap:8px;max-height:640px;overflow-y:auto;padding:4px 2px}}
.msg{{max-width:86%;padding:10px 14px;border-radius:14px;color:var(--body-text-color);
      border:1px solid var(--border-color-primary)}}
.msg .who{{font-size:11.5px;color:var(--body-text-color-subdued);margin-bottom:3px;direction:ltr;text-align:left;
           font-variant-numeric:tabular-nums}}
.msg .say{{font-family:{ARABIC_FONT};font-size:16px;line-height:1.85}}
.agent{{align-self:flex-start;border-bottom-left-radius:4px;
        background:color-mix(in srgb,#2563eb 11%,var(--block-background-fill))}}
.customer{{align-self:flex-end;border-bottom-right-radius:4px;
           background:color-mix(in srgb,#0d9488 13%,var(--block-background-fill))}}
.ivr{{align-self:center;font-style:italic;background:var(--background-fill-secondary)}}
.unknown{{align-self:stretch;max-width:100%;background:var(--background-fill-secondary)}}
.flag{{font-size:11.5px;color:#b45309;direction:ltr;text-align:left;margin-top:3px}}
.no-text{{opacity:.55;font-style:italic}}
.chat-meta{{font-size:12px;color:var(--body-text-color-subdued);padding:0 2px 8px}}
.chat-empty{{padding:56px 24px;text-align:center;color:var(--body-text-color-subdued);font-size:14px;
             border:1px dashed var(--border-color-primary);border-radius:12px}}
</style>
"""


def _mmss(x):
    return f"{int(x // 60):02d}:{x % 60:04.1f}"


def _bubble(role, who, text, flag=""):
    cls = role if role in ("agent", "customer", "ivr") else "unknown"
    body = html.escape(text) if text else '<span class="no-text">(no text)</span>'
    f = f'<div class="flag">{html.escape(flag)}</div>' if flag else ""
    return (f'<div class="msg {cls}"><div class="who">{html.escape(who)}</div>'
            f'<div class="say" dir="rtl">{body}</div>{f}</div>')


def empty(msg):
    return STYLE + f'<div class="chat-empty">{html.escape(msg)}</div>'


def reference_html(items, meta=None):
    if not items:
        return empty("No reference yet. Upload a JSON or SRT transcript to see it here and get a score.")
    head = ""
    if meta and meta.get("call_id"):
        head = f'<div class="chat-meta">{html.escape(str(meta.get("call_id")))}</div>'
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


def header_html(ready, total, cloud_on):
    cloud = ('<span class="chip chip-warn">Cloud on: consented audio only</span>' if cloud_on
             else '<span class="chip">Local only</span>')
    return (f'<header class="appbar"><div><h1>Egyptian Arabic ASR Comparison</h1>'
            f'<p>Transcribe a call with any model and score it against the reference.</p></div>'
            f'<div class="chips"><span class="chip">{ready} of {total} models ready</span>{cloud}</div></header>')


def section(title):
    return f'<div class="section-title">{html.escape(title)}</div>'


def status_html(kind, message):
    """kind: ok | error | info"""
    return f'<div class="status status-{kind}">{html.escape(message)}</div>'


def _pct(x):
    return "–" if x is None else f"{x:.1%}"


def _metric(label, value, hint="", main=False):
    sub = f'<div class="metric-hint">{html.escape(hint)}</div>' if hint else ""
    return (f'<div class="metric{" metric-main" if main else ""}"><div class="metric-label">{html.escape(label)}</div>'
            f'<div class="metric-value">{value}</div>{sub}</div>')


def score_html(res, model_name):
    if not res:
        return (f'<section class="score"><div class="score-title">{html.escape(model_name)}</div>'
                '<p class="score-note">No reference transcript, so no score. Upload one to compare.</p></section>')
    roles = res["roles"]
    cards = [_metric("WER", _pct(res["wer"]), f"{res['ref_words']} reference words", main=True),
             _metric("CER", _pct(res["cer"]))]
    for role, label in (("agent", "Agent WER"), ("customer", "Customer WER")):
        r = roles.get(role)
        cards.append(_metric(label, _pct(r and r["wer"]), f"{r['ref_words']} words" if r else "needs diarization"))
    terms = ""
    if res["terms"]:
        chips = "".join(f'<span class="term{" term-miss" if hit < n else ""}" dir="rtl">{html.escape(t)} '
                        f'<b dir="ltr">{hit}/{n}</b></span>' for t, n, hit in res["terms"])
        terms = f'<div class="terms"><span class="terms-label">Key terms found</span>{chips}</div>'
    return (f'<section class="score"><div class="score-title">{html.escape(model_name)}</div>'
            f'<div class="metrics">{"".join(cards)}</div>{terms}'
            '<p class="score-note">Lower is better. The references look model-generated, so these measure agreement '
            'with them, and differences under 2 points are noise. Per-role WER also counts diarization mistakes.</p>'
            '</section>')
