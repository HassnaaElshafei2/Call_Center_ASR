"""audio -> (preprocess) -> segments -> model -> post-process -> roles -> score."""
import csv
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import models, preprocess, scoring, segment
from .config import RESULTS_CSV, WORK_DIR
from .text import norm, postprocess

AGENT_MARKERS = [norm(x) for x in ["حضرتك", "فندم", "معاك", "مع حضرتك", "أهلا وسهلا", "أهلا بحضرتك",
                                   "خدمة العملاء", "أقدر أساعد", "تحت أمرك", "أي خدمة", "تقييم"]]


@dataclass
class Prepared:
    key: str
    workdir: Path
    original: Path            # 16 kHz mono, untouched (used for diarization)
    asr_audio: Path           # what the models hear (preprocessed or original)
    segments: list            # [{start, end, speaker, path}]
    steps: tuple
    prep_seconds: float


_CACHE = {}


def _file_hash(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def prepare(audio_path, steps=(), use_diarization=True, min_speakers=2, max_speakers=2, log=print):
    steps = tuple(s for s in preprocess.ORDER if s in steps)
    fh = _file_hash(audio_path)
    key = f"{fh}|{','.join(steps)}|{use_diarization}|{min_speakers}-{max_speakers}"
    if key in _CACHE:
        log("re-using preprocessing and segments from the previous run")
        return _CACHE[key]
    t0 = time.time()
    base = WORK_DIR / fh
    base.mkdir(parents=True, exist_ok=True)
    original = base / "original_16k.wav"
    if not original.exists():
        preprocess.ffmpeg_to_16k(audio_path, original)

    variant = base / (("pre-" + "-".join(steps)) if steps else "raw")
    variant.mkdir(exist_ok=True)
    asr_audio = preprocess.run_chain(original, steps, variant, log) if steps else original

    orig, _ = preprocess.read(original)
    segs = segment.build_segments(orig, use_diarization, min_speakers, max_speakers, log)
    if not segs:
        raise RuntimeError("No speech found in this audio.")

    a, sr = preprocess.read(asr_audio)
    segdir = variant / f"segs_{'diar' if use_diarization else 'vad'}_{min_speakers}-{max_speakers}"
    segdir.mkdir(exist_ok=True)
    pad = 0.15
    for k, s in enumerate(segs):
        i, j = max(0, int((s["start"] - pad) * sr)), min(len(a), int((s["end"] + pad) * sr))
        s["path"] = str(segdir / f"seg_{k:04d}.wav")
        preprocess.write(s["path"], a[i:j], sr)
    log(f"{len(segs)} segments ready (longest {max(s['end'] - s['start'] for s in segs):.1f}s)")
    p = Prepared(key, base, original, asr_audio, segs, steps, time.time() - t0)
    if len(_CACHE) > 16:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = p
    return p


def assign_roles(rows, swap=False):
    """Map diarization labels to agent/customer: the speaker who uses the most service phrases
    («حضرتك», «فندم», «معاك», ...) is the agent; ties go to whoever spoke first."""
    labels = list(dict.fromkeys(r["speaker"] for r in rows if r["speaker"] != "?"))
    if not labels:
        for r in rows:
            r["role"] = ""
        return rows
    score, words = {l: 0 for l in labels}, {l: 0 for l in labels}
    for r in rows:
        if r["speaker"] in score:
            n = f" {norm(r['text'])} "
            score[r["speaker"]] += sum(n.count(f" {m} ") for m in AGENT_MARKERS)
            words[r["speaker"]] += len(n.split())
    agent = max(labels, key=lambda l: (score[l], -labels.index(l)))
    others = sorted((l for l in labels if l != agent), key=lambda l: -words[l])
    roles = {agent: "agent"}
    if others:
        roles[others[0]] = "customer"
    for l in others[1:]:
        roles[l] = "other"
    if swap and others:
        roles[agent], roles[others[0]] = "customer", "agent"
    for r in rows:
        r["role"] = roles.get(r["speaker"], "")
    return rows


def transcribe(prep: Prepared, spec: models.ModelSpec, prompt="", swap_roles=False):
    texts, secs = models.transcribe(spec, [s["path"] for s in prep.segments], prompt=prompt)
    if len(texts) != len(prep.segments):
        raise RuntimeError(f"{spec.name} returned {len(texts)} texts for {len(prep.segments)} segments")
    rows = []
    for s, t in zip(prep.segments, texts):
        clean, status = postprocess(t)
        rows.append({"start": round(s["start"], 2), "end": round(s["end"], 2), "speaker": s["speaker"],
                     "raw": t, "text": clean, "status": status})
    return assign_roles(rows, swap_roles), secs


def _srt_time(x):
    ms = int(round(x * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def save_outputs(prep: Prepared, spec, rows, score_res, audio_name):
    out = prep.workdir / "outputs"
    out.mkdir(exist_ok=True)
    stem = f"{Path(audio_name).stem}__{spec.key}__{'pre-' + '-'.join(prep.steps) if prep.steps else 'raw'}"
    jpath, spath = out / f"{stem}.json", out / f"{stem}.srt"
    jpath.write_text(json.dumps({"audio": audio_name, "model": spec.name, "preprocessing": list(prep.steps),
                                 "score": score_res, "segments": rows}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    srt = []
    for k, r in enumerate([r for r in rows if r["text"]], 1):
        srt.append(f"{k}\n{_srt_time(r['start'])} --> {_srt_time(r['end'])}\n[{r['role'] or r['speaker']}] {r['text']}\n")
    spath.write_text("\n".join(srt), encoding="utf-8")
    return [str(jpath), str(spath)]


RUN_FIELDS = ["time", "audio", "model", "tried_by", "preprocessing", "diarization", "wer", "cer",
              "agent_wer", "customer_wer", "segments", "asr_seconds"]


def log_run(record):
    new = not RESULTS_CSV.exists()
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RUN_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(record)


def make_record(audio_name, spec, prep, use_diar, res, secs):
    def r3(x):
        return None if x is None else round(x, 3)
    roles = (res or {}).get("roles", {})
    return {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "audio": audio_name, "model": spec.name,
            "tried_by": spec.tried_by, "preprocessing": "+".join(prep.steps) or "none",
            "diarization": "yes" if use_diar else "no",
            "wer": r3(res and res["wer"]), "cer": r3(res and res["cer"]),
            "agent_wer": r3(roles.get("agent", {}).get("wer")),
            "customer_wer": r3(roles.get("customer", {}).get("wer")),
            "segments": len(prep.segments), "asr_seconds": round(secs, 1)}
