"""Arabic normalisation and transcript clean-up (shared by every model)."""
import re
import zlib

_DIACRITICS = re.compile(r"[ً-ْٰـ]")    # tashkeel, superscript alef, tatweel
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def norm(t: str) -> str:
    """Normalisation used for scoring: no diacritics, unified alef/ya/ta-marbuta, no punctuation."""
    t = _DIACRITICS.sub("", t or "")
    t = re.sub("[إأآٱا]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").translate(_ARABIC_DIGITS)
    t = re.sub(r"[^\w\s]", " ", t)
    t = t.replace("_", " ")
    return re.sub(r"\s+", " ", t).strip()


# Known Whisper hallucinations (YouTube subtitle credits etc.)
HALLUCINATIONS = ["ترجمة نانسي قنقر", "نانسي قنقر", "اشتركوا في القناة", "اشترك في القناة",
                  "اشتركوا في قناتنا", "شكرا على المشاهدة", "شكرا للمشاهدة", "لا تنسوا الاشتراك"]
_HALLUC_NORM = sorted({norm(h) for h in HALLUCINATIONS}, key=len, reverse=True)


def compression_ratio(text: str) -> float:
    b = text.encode("utf-8")
    return len(b) / max(1, len(zlib.compress(b)))


def is_loop(text: str) -> bool:
    return compression_ratio(text) > 2.4 and len(text.split()) > 8


def collapse_repeats(text: str, max_n: int = 8, min_reps: int = 3) -> str:
    """'a b a b a b c' -> 'a b c'; keeps the words around the loop."""
    w = text.split()
    changed = True
    while changed:
        changed = False
        for n in range(1, max_n + 1):
            i, out = 0, []
            while i < len(w):
                g = w[i:i + n]
                reps = 1
                while len(g) == n and w[i + reps * n:i + (reps + 1) * n] == g:
                    reps += 1
                if len(g) == n and reps >= min_reps:
                    out += g
                    i += reps * n
                    changed = True
                else:
                    out.append(w[i])
                    i += 1
            w = out
    return " ".join(w)


def postprocess(text: str):
    """Returns (display text, status). Keeps the original spelling/punctuation for display."""
    text = (text or "").strip()
    status = []
    if is_loop(text):
        text = collapse_repeats(text)
        status.append("loop-collapsed")
    n = norm(text)
    hit = [h for h in _HALLUC_NORM if h and h in n]
    if hit:
        # remove the phrase from the normalised text; display the cleaned normalised form
        for h in hit:
            n = n.replace(h, " ")
        text = re.sub(r"\s+", " ", n).strip()
        status.append("hallucination-removed")
    return text, ",".join(status)
