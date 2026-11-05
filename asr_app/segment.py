"""Speech detection (Silero VAD) + speaker diarization (pyannote community-1) -> short segments.

Fixes from the review of v4:
- uses pyannote's *exclusive* diarization (no overlapping turns), so overlapped audio is not
  transcribed twice;
- long turns are cut at a pause (VAD gap) near the 15 s limit instead of blindly mid-word.
"""
import numpy as np

from .config import HF_TOKEN

SR = 16000
MAX_LEN = 15.0
DIAR_MODEL = "pyannote/speaker-diarization-community-1"
_diar = None
_vad = None


# ---------------- VAD ----------------
def _energy_vad(a, frame=0.03, min_speech=0.2, min_sil=0.35):
    """Fallback when torch/silero is not installed (e.g. a quick UI test). Much cruder than Silero."""
    n = int(frame * SR)
    frames = a[: len(a) // n * n].reshape(-1, n)
    db = 10 * np.log10(np.mean(frames ** 2, axis=1) + 1e-10)
    thr = max(np.percentile(db, 20) + 10, db.max() - 45)
    on = db > thr
    segs, start = [], None
    for i, v in enumerate(on):
        t = i * frame
        if v and start is None:
            start = t
        elif not v and start is not None:
            segs.append([start, t])
            start = None
    if start is not None:
        segs.append([start, len(on) * frame])
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < min_sil:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [{"start": s, "end": e} for s, e in merged if e - s >= min_speech]


def vad(a, log=print):
    global _vad
    try:
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad
    except ImportError:
        log("silero-vad/torch not installed: using a simple energy VAD")
        return _energy_vad(a)
    if _vad is None:
        _vad = load_silero_vad()
    return get_speech_timestamps(torch.from_numpy(a), _vad, sampling_rate=SR, return_seconds=True,
                                 threshold=0.45, min_silence_duration_ms=350,
                                 speech_pad_ms=120, min_speech_duration_ms=200)


# ---------------- diarization ----------------
def diarize(a, min_speakers=2, max_speakers=2, log=print):
    global _diar
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError as e:
        raise RuntimeError(f"Diarization needs torch and pyannote.audio in the app environment "
                           f"(pip install -r requirements.txt), or untick 'Speaker diarization'. ({e})")
    if _diar is None:
        if not HF_TOKEN:
            raise RuntimeError("HF_TOKEN is not set. pyannote community-1 is gated: create a Read token and "
                               "accept the terms on its Hugging Face page.")
        log("loading pyannote community-1 ...")
        _diar = Pipeline.from_pretrained(DIAR_MODEL, token=HF_TOKEN)
        if torch.cuda.is_available():
            _diar.to(torch.device("cuda"))
    kw = ({"num_speakers": min_speakers} if min_speakers == max_speakers
          else {"min_speakers": min_speakers, "max_speakers": max_speakers})
    out = _diar({"waveform": torch.from_numpy(a)[None, :], "sample_rate": SR}, **kw)
    ann = getattr(out, "exclusive_speaker_diarization", None) or getattr(out, "speaker_diarization", out)
    return [{"start": t.start, "end": t.end, "speaker": spk} for t, _, spk in ann.itertracks(yield_label=True)]


# ---------------- segment building ----------------
def speech_fraction(s, e, speech):
    cov = sum(max(0.0, min(e, v["end"]) - max(s, v["start"])) for v in speech)
    return cov / max(1e-6, e - s)


def _cut_points(speech):
    return [(a["end"] + b["start"]) / 2 for a, b in zip(speech, speech[1:])]


def merge_and_split(segs, speech, max_gap=0.6, max_len=MAX_LEN):
    segs = sorted(segs, key=lambda s: s["start"])
    out = []
    for s in segs:
        if (out and out[-1]["speaker"] == s["speaker"] and s["start"] - out[-1]["end"] <= max_gap
                and s["end"] - out[-1]["start"] <= max_len):
            out[-1]["end"] = max(out[-1]["end"], s["end"])
        else:
            out.append(dict(s))
    cuts = _cut_points(speech)
    final = []
    for s in out:
        a = s["start"]
        while s["end"] - a > max_len:
            inside = [c for c in cuts if a + 3.0 < c <= a + max_len]
            b = max(inside) if inside else a + max_len         # cut at the last pause before the limit
            final.append({"start": a, "end": b, "speaker": s["speaker"]})
            a = b
        final.append({"start": a, "end": s["end"], "speaker": s["speaker"]})
    return final


def merge_short(segs, min_len=1.5, max_gap=2.0, max_len=MAX_LEN):
    segs = [dict(s) for s in sorted(segs, key=lambda s: s["start"])]
    i = 0
    while i < len(segs):
        s = segs[i]
        if s["end"] - s["start"] >= min_len:
            i += 1
            continue
        best = None
        for j in (i - 1, i + 1):
            if 0 <= j < len(segs) and segs[j]["speaker"] == s["speaker"]:
                n = segs[j]
                gap = s["start"] - n["end"] if j < i else n["start"] - s["end"]
                span = max(s["end"], n["end"]) - min(s["start"], n["start"])
                if gap <= max_gap and span <= max_len and (best is None or gap < best[0]):
                    best = (gap, j)
        if best:
            j = best[1]
            n = segs[j]
            n["start"] = min(n["start"], s["start"])
            n["end"] = max(n["end"], s["end"])
            segs.pop(i)
            i = j if j < i else i
        else:
            i += 1
    return segs


def build_segments(a, use_diarization=True, min_speakers=2, max_speakers=2, log=print):
    """a: original 16 kHz mono audio. Returns segments [{start, end, speaker}]."""
    speech = vad(a, log)
    log(f"VAD: {len(speech)} speech regions, {sum(v['end'] - v['start'] for v in speech):.0f}s of speech")
    if use_diarization:
        raw = diarize(a, min_speakers, max_speakers, log)
        segs = [s for s in merge_and_split(raw, speech) if speech_fraction(s["start"], s["end"], speech) >= 0.3]
    else:
        raw = [{"start": v["start"], "end": v["end"], "speaker": "?"} for v in speech]
        segs = merge_and_split(raw, speech)
    segs = merge_short(segs)
    # drop tiny leftovers (< 0.4 s): they make models hallucinate (Esraa's min_len)
    return [s for s in segs if s["end"] - s["start"] >= 0.4]
