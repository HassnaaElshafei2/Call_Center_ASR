"""WER / CER against the reference, overall and per role, plus key-term recall."""
import jiwer

from .text import norm

KEY_TERMS = ["فندم", "حضرتك", "قسط", "بي تك", "اديب", "انستاباي", "فوري", "الكارت", "تحويل", "التحصيل", "الغرامه"]


def _wer_cer(ref, hyp):
    if not ref:
        return None, None
    hyp = hyp or "-"
    return jiwer.wer(ref, hyp), jiwer.cer(ref, hyp)


def _count(text, term):
    return f" {text} ".count(f" {term} ") if " " not in term else text.count(term)


def score(ref_items, rows, include_ivr=False, terms=KEY_TERMS):
    ref_items = [i for i in ref_items if include_ivr or i.get("role") != "ivr"]
    ref = norm(" ".join(i["text"] for i in ref_items))
    hyp = norm(" ".join(r["text"] for r in rows))
    w, c = _wer_cer(ref, hyp)
    res = {"wer": w, "cer": c, "ref_words": len(ref.split()), "hyp_words": len(hyp.split()), "roles": {}}

    # per role: the reference has roles; model rows have roles after speaker mapping
    if any(r.get("role") in ("agent", "customer") for r in rows):
        for role in ("agent", "customer"):
            R = norm(" ".join(i["text"] for i in ref_items if i.get("role") == role))
            H = norm(" ".join(r["text"] for r in rows if r.get("role") == role))
            rw, rc = _wer_cer(R, H)
            if rw is not None:
                res["roles"][role] = {"wer": rw, "cer": rc, "ref_words": len(R.split())}

    res["terms"] = []
    for t in terms:
        nt = norm(t)
        n_ref = _count(ref, nt)
        if n_ref:
            res["terms"].append((t, n_ref, min(n_ref, _count(hyp, nt))))
    return res


def _fmt(x):
    return "–" if x is None else f"{x:.3f}"


def to_markdown(res, model_name):
    lines = [f"### Score: {model_name}",
             "| | WER | CER | reference words |", "|---|---|---|---|",
             f"| **Overall** | **{_fmt(res['wer'])}** | {_fmt(res['cer'])} | {res['ref_words']} |"]
    for role, r in res["roles"].items():
        lines.append(f"| {role.capitalize()} | {_fmt(r['wer'])} | {_fmt(r['cer'])} | {r['ref_words']} |")
    if not res["roles"]:
        lines.append("| Agent / Customer | – | – | turn on diarization for per-role scores |")
    if res["terms"]:
        lines += ["", "| Key term | found / in reference |", "|---|---|"]
        lines += [f"| {t} | {h} / {r} |" for t, r, h in res["terms"]]
    lines += ["", "<sub>Lower is better. Text is normalised (diacritics, alef/ya/ta-marbuta, punctuation). "
                  "Per-role WER compares all agent (or customer) words in order, so diarization mistakes "
                  "count against it. The references look model-generated, so treat these as agreement "
                  "scores, and small differences (< 0.02) as noise.</sub>"]
    return "\n".join(lines)
