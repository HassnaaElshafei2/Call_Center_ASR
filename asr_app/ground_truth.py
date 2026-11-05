"""Load reference transcripts (our JSON format, other JSON, or SRT) and match them to audio files."""
import json
import re
from pathlib import Path

from .config import DATA_DIR, REF_EXTS

AGENT_HINTS = ("agent", "خدمة", "خدمه", "موظف", "الموظف")
CUSTOMER_HINTS = ("customer", "client", "عميل", "العميل")
IVR_HINTS = ("ivr", "system", "النظام", "الرد الآلي", "الرد الالي")


def _role_from(label: str) -> str:
    l = (label or "").lower()
    if any(h in l for h in IVR_HINTS):
        return "ivr"
    if any(h in l for h in CUSTOMER_HINTS):
        return "customer"
    if any(h in l for h in AGENT_HINTS):
        return "agent"
    return ""


# ---------- JSON ----------
_TEXT_KEYS = ["text", "transcript", "content", "utterance", "sentence"]
_START_KEYS = ["start", "start_time", "startTime", "begin", "from", "timestamp", "time", "offset"]
_SPK_KEYS = ["speaker_name", "speaker", "speaker_label", "speakerLabel", "name", "speaker_id", "channel"]


def _first(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _raw_time(v):
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    m = re.match(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", s)
    return int(m[1] or 0) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def _walk(o):
    if isinstance(o, list):
        out = []
        for v in o:
            out += _walk(v)
        return out
    if isinstance(o, dict):
        children = []
        for v in o.values():
            if isinstance(v, (list, dict)):
                children += _walk(v)
        if children:
            return children
        t = _first(o, _TEXT_KEYS)
        if isinstance(t, str) and t.strip():
            spk = str(_first(o, _SPK_KEYS) or "")
            role = str(o.get("role") or "").lower() or _role_from(spk)
            return [{"start": _raw_time(_first(o, _START_KEYS)), "speaker": spk, "role": role, "text": t.strip()}]
    return []


def parse_json(raw: str):
    data = json.loads(raw)
    items = _walk(data)
    nums = [i["start"] for i in items if i["start"] is not None]
    if nums and max(nums) > 7200:              # milliseconds
        for i in items:
            if i["start"] is not None:
                i["start"] /= 1000.0
    meta = {}
    if isinstance(data, dict):
        rec = data.get("recording", data)
        if isinstance(rec, dict):
            meta = {"call_id": rec.get("call_id", ""), **(rec.get("metadata") or {})}
    return items, meta


# ---------- SRT ----------
def _ts(x):
    h, m, rest = x.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest.replace(",", "."))


def parse_srt(text: str):
    items = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        tl = [l for l in lines if "-->" in l]
        if not tl:
            continue
        body = " ".join(l for l in lines if "-->" not in l and not l.strip().isdigit())
        m = re.match(r"\s*\[([^\]]*)\]\s*(.*)", body) or re.match(r"\s*([^:]{1,40}):\s*(.*)", body)
        spk, txt = (m.group(1), m.group(2)) if m else ("", body)
        txt = re.sub(r"\[[^\]]*\]", " ", txt).strip()
        if txt:
            items.append({"start": _ts(tl[0].split("-->")[0]), "speaker": spk, "role": _role_from(spk), "text": txt})
    return items, {}


def load_reference(path):
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    items, meta = parse_json(raw) if path.suffix.lower() == ".json" else parse_srt(raw)
    for i in items:
        i["text"] = re.sub(r"\[[^\]]*\]", " ", i["text"]).strip()
    items = [i for i in items if i["text"]]
    # SRT files with plain names: the first non-IVR speaker is the agent, the other one the customer
    if items and not any(i["role"] in ("agent", "customer") for i in items):
        names = [i["speaker"] for i in items if i["role"] != "ivr"]
        order = list(dict.fromkeys(names))
        for i in items:
            if i["role"] != "ivr" and order:
                i["role"] = "agent" if i["speaker"] == order[0] else "customer"
    return items, meta


# ---------- matching audio <-> reference ----------
def call_key(name: str) -> str:
    """The long numeric recording id in a file name, e.g. 2024081123502787709761251380702201."""
    m = re.findall(r"\d{15,}", Path(name).name)
    return max(m, key=len) if m else ""


def find_reference(audio_path, search_dirs=(DATA_DIR,)):
    key = call_key(str(audio_path))
    if not key:
        return None
    for d in search_dirs:
        d = Path(d)
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() in REF_EXTS and key in p.name:
                return p
    return None
