"""Transcription service: Mohammed's fine-tuned Cohere Transcribe Arabic model + speaker separation.

    MODEL_PATH=/models/eg_callcenter_asr/model uvicorn app:app --host 0.0.0.0 --port 9000

Contract (what the platform's backend calls; the same when this runs on the DGX later):
    GET  /health   -> {"ok": true, "model": ..., "device": ..., "diarization": ...}
    POST /process  multipart file=<audio> -> {"model", "duration", "turns": [{"speaker","start","end","text","confidence"}]}

Speakers, in order of preference:
  1. stereo recordings with one party per channel (common in call centres): each channel is a speaker;
  2. pyannote speaker diarization (HF_TOKEN with the model's terms accepted);
  3. otherwise: voice-activity segments, all one speaker (the backend still guesses roles from the words).
Decoding follows Mohammed's transcribe.py: beam 8, at most 12 tokens per second of audio + 20, no length penalty
(this stopped the runaway repetitions in our evaluation).
"""
from __future__ import annotations

import io
import logging
import math
import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, HTTPException, UploadFile

log = logging.getLogger("asr")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SR = 16000
MODEL_PATH = os.environ.get("MODEL_PATH", "CohereLabs/cohere-transcribe-arabic-07-2026")
BEAMS = int(os.environ.get("BEAMS", "8"))
MAX_SEGMENT_S = float(os.environ.get("MAX_SEGMENT_S", "28"))
DIARIZATION = os.environ.get("DIARIZATION", "auto")          # auto, channels, pyannote, vad
HF_TOKEN = os.environ.get("HF_TOKEN")
PYANNOTE_MODEL = os.environ.get("PYANNOTE_MODEL", "pyannote/speaker-diarization-community-1")

app = FastAPI(title="Call transcription service")
_lock = threading.Lock()          # one GPU job at a time
_model = _proc = _device = _dtype = _pipeline = None


# ------------------------------------------------------------------------------------------- audio
def load_audio(data: bytes, name: str) -> tuple[np.ndarray, int]:
    """Any format -> float32 [samples, channels] at 16 kHz (ffmpeg handles MP3/M4A/AMR...)."""
    try:
        x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception:
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(name)[1] or ".bin") as f:
            f.write(data)
            f.flush()
            r = subprocess.run(["ffmpeg", "-v", "error", "-i", f.name, "-ar", str(SR), "-f", "f32le", "-acodec", "pcm_f32le",
                                "-ac", "2", "-"], capture_output=True)
            if r.returncode != 0:
                raise HTTPException(400, f"can't read the audio: {r.stderr[-200:]!r}")
            x, sr = np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy(), SR
            if np.allclose(x[:, 0], x[:, 1], atol=1e-4):
                x = x[:, :1]
    if sr != SR:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(sr, SR)
        x = resample_poly(x, SR // g, sr // g, axis=0).astype(np.float32)
    return x, SR


def vad(x: np.ndarray, frame_s: float = 0.03, min_speech_s: float = 0.3, min_gap_s: float = 0.5) -> list[tuple[float, float]]:
    """Energy-based speech regions (seconds) for a mono signal."""
    n = int(frame_s * SR)
    frames = len(x) // n
    if frames == 0:
        return []
    e = 10 * np.log10(np.mean(x[: frames * n].reshape(frames, n) ** 2, axis=1) + 1e-10)
    thr = max(np.percentile(e, 20) + 12, np.max(e) - 45)
    on = e > thr
    regs, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            regs.append([start * frame_s, i * frame_s])
            start = None
    if start is not None:
        regs.append([start * frame_s, frames * frame_s])
    merged = []
    for s, t in regs:
        if merged and s - merged[-1][1] < min_gap_s:
            merged[-1][1] = t
        else:
            merged.append([s, t])
    return [(s, t) for s, t in merged if t - s >= min_speech_s]


@dataclass
class Seg:
    speaker: str
    start: float
    end: float


def split_long(segs: list[Seg]) -> list[Seg]:
    out = []
    for s in segs:
        n = max(1, math.ceil((s.end - s.start) / MAX_SEGMENT_S))
        step = (s.end - s.start) / n
        out += [Seg(s.speaker, s.start + i * step, s.start + (i + 1) * step) for i in range(n)]
    return out


def diarize(x: np.ndarray) -> tuple[list[Seg], str]:
    mode = DIARIZATION
    if x.shape[1] >= 2 and mode in ("auto", "channels"):
        a, b = x[:, 0], x[:, 1]
        # two different parties per channel: the channels are not near-copies of each other
        corr = float(np.corrcoef(a[:: 10], b[:: 10])[0, 1]) if np.std(a) > 0 and np.std(b) > 0 else 1.0
        if corr < 0.6 or mode == "channels":
            segs = [Seg("SPEAKER_00", s, t) for s, t in vad(a)] + [Seg("SPEAKER_01", s, t) for s, t in vad(b)]
            return sorted(segs, key=lambda s: s.start), "channels"
    mono = x.mean(axis=1)
    if mode in ("auto", "pyannote"):
        p = pyannote_pipeline()
        if p is not None:
            import torch
            ann = p({"waveform": torch.from_numpy(mono[None, :]), "sample_rate": SR})
            ann = getattr(ann, "speaker_diarization", ann)
            segs = [Seg(spk, t.start, t.end) for t, _, spk in ann.itertracks(yield_label=True) if t.end - t.start >= 0.25]
            # merge consecutive pieces of the same speaker
            merged: list[Seg] = []
            for s in sorted(segs, key=lambda s: s.start):
                if merged and merged[-1].speaker == s.speaker and s.start - merged[-1].end < 0.6:
                    merged[-1].end = max(merged[-1].end, s.end)
                else:
                    merged.append(s)
            return merged, "pyannote"
    return [Seg("SPEAKER_00", s, t) for s, t in vad(mono)], "vad"


def pyannote_pipeline():
    global _pipeline
    if _pipeline is None:
        try:
            from pyannote.audio import Pipeline
            _pipeline = Pipeline.from_pretrained(PYANNOTE_MODEL, token=HF_TOKEN)
            if _device == "cuda":
                import torch
                _pipeline.to(torch.device("cuda"))
        except Exception as e:                    # noqa: BLE001 - optional component
            log.warning("pyannote unavailable (%s); falling back to voice activity", e)
            _pipeline = False
    return _pipeline or None


# ------------------------------------------------------------------------------------------- model
def load_model():
    global _model, _proc, _device, _dtype
    if _model is not None:
        return
    import torch
    from transformers import AutoProcessor, CohereAsrForConditionalGeneration
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    if _device == "cuda":
        _dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    else:
        _dtype = torch.float32
    _proc = AutoProcessor.from_pretrained(MODEL_PATH, token=HF_TOKEN)
    _model = CohereAsrForConditionalGeneration.from_pretrained(MODEL_PATH, dtype=_dtype, token=HF_TOKEN).to(_device).eval()
    log.info("loaded %s on %s (%s)", MODEL_PATH, _device, _dtype)


def transcribe(audio: np.ndarray) -> tuple[str, float | None]:
    import torch
    inputs = _proc([audio], sampling_rate=SR, return_tensors="pt", language="ar")
    inputs = {k: (v.to(_device, _dtype) if v.is_floating_point() else v.to(_device)) for k, v in inputs.items() if torch.is_tensor(v)}
    limit = int(len(audio) / SR * 12) + 20
    with torch.inference_mode():
        out = _model.generate(**inputs, num_beams=BEAMS, max_new_tokens=limit, length_penalty=0.0, do_sample=False,
                              return_dict_in_generate=True, output_scores=True)
    seq = out.sequences
    text = _proc.batch_decode(seq, skip_special_tokens=True)[0].strip()
    conf = None
    if getattr(out, "sequences_scores", None) is not None:
        n = max(1, int((seq[0] != _proc.tokenizer.pad_token_id).sum()) - inputs.get("decoder_input_ids", seq).shape[-1])
        conf = round(float(math.exp(out.sequences_scores[0].item() / n)), 3)       # mean token probability
    return text, conf


# ------------------------------------------------------------------------------------------- API
@app.on_event("startup")
def startup():
    try:
        load_model()
    except Exception as e:                        # noqa: BLE001 - reported by /health
        log.error("model failed to load: %s", e)


@app.get("/health")
def health():
    return {"ok": _model is not None, "model": MODEL_PATH, "device": _device, "dtype": str(_dtype),
            "diarization": DIARIZATION, "beams": BEAMS}


@app.post("/process")
async def process(file: UploadFile = File(...)):
    if _model is None:
        raise HTTPException(503, "the model isn't loaded")
    x, _ = load_audio(await file.read(), file.filename or "")
    duration = len(x) / SR
    with _lock:
        segs, method = diarize(x)
        mono = x.mean(axis=1)
        turns = []
        for s in split_long(segs):
            chan = x[:, int(s.speaker[-1])] if method == "channels" else mono
            piece = chan[int(s.start * SR): int(s.end * SR)]
            if len(piece) < SR * 0.2:
                continue
            text, conf = transcribe(piece)
            if text:
                turns.append({"speaker": s.speaker, "start": round(s.start, 2), "end": round(s.end, 2), "text": text,
                              "confidence": conf})
    return {"model": MODEL_PATH, "duration": round(duration, 2), "diarization": method, "turns": turns}
