"""Stand-in transcription through ElevenLabs Scribe, until Mohammed's model runs on the DGX.

Use it for synthetic or consented recordings only: the audio is sent to ElevenLabs. Returns the same shape as the
transcription service (asr_service/), so the rest of the pipeline doesn't know the difference:
    {"model", "duration", "diarization", "turns": [{"speaker", "start", "end", "text", "confidence"}]}
"""
import math
from pathlib import Path

import httpx

from ..config import settings

URL = "https://api.elevenlabs.io/v1/speech-to-text"
MAX_GAP_S = 2.0          # a pause this long starts a new turn, even for the same speaker
MAX_TURN_S = 30.0        # and so does a very long stretch of speech


class ElevenLabsError(RuntimeError):
    pass


def transcribe(path: Path) -> dict:
    s = settings()
    if not s.elevenlabs_api_key.isascii():
        raise ElevenLabsError("ELEVENLABS_API_KEY contains characters like • (copied from a display that hides secrets?). "
                              "Paste the full key into .env, then run: docker compose up -d")
    data = {"model_id": s.elevenlabs_stt_model, "diarize": "true", "tag_audio_events": "false",
            "timestamps_granularity": "word"}
    if s.elevenlabs_language:
        data["language_code"] = s.elevenlabs_language
    if s.elevenlabs_num_speakers:
        data["num_speakers"] = str(s.elevenlabs_num_speakers)
    with path.open("rb") as f:
        r = httpx.post(URL, headers={"xi-api-key": s.elevenlabs_api_key}, data=data, files={"file": (path.name, f)},
                       timeout=httpx.Timeout(900, connect=15))
    if r.status_code >= 400:
        raise ElevenLabsError(f"ElevenLabs answered {r.status_code}: {r.text[:300]}")
    return to_turns(r.json(), s.elevenlabs_stt_model)


def to_turns(body: dict, model: str = "scribe") -> dict:
    """Scribe's word list -> turns: a new turn when the speaker changes, after a long pause, or every ~30 s."""
    if body.get("transcripts"):                       # multichannel answer: one transcript per channel
        words = []
        for t in body["transcripts"]:
            ch = t.get("channel_index", 0)
            words += [w | {"speaker_id": w.get("speaker_id") or f"channel_{ch}"} for w in t.get("words", [])]
        words.sort(key=lambda w: (w.get("start") or 0))
    else:
        words = body.get("words") or []

    turns, cur = [], None
    for w in words:
        kind = w.get("type", "word")
        if kind == "audio_event":
            continue
        if kind == "spacing":
            if cur:
                cur["parts"].append(w.get("text", " "))
            continue
        spk = w.get("speaker_id") or "speaker_0"
        start, end = float(w.get("start") or 0), float(w.get("end") or w.get("start") or 0)
        if (cur is None or spk != cur["speaker"] or start - cur["end"] > MAX_GAP_S
                or end - cur["start"] > MAX_TURN_S):
            cur = {"speaker": spk, "start": start, "end": end, "parts": [], "probs": []}
            turns.append(cur)
        cur["parts"].append(w.get("text", ""))
        cur["end"] = max(cur["end"], end)
        if w.get("logprob") is not None:
            cur["probs"].append(math.exp(min(0.0, float(w["logprob"]))))

    out = []
    for t in turns:
        text = " ".join("".join(t["parts"]).split())
        if text:
            conf = round(sum(t["probs"]) / len(t["probs"]), 3) if t["probs"] else None
            out.append({"speaker": t["speaker"], "start": round(t["start"], 2), "end": round(t["end"], 2),
                        "text": text, "confidence": conf})
    duration = max([t["end"] for t in out], default=0.0)
    return {"model": f"ElevenLabs {model}", "duration": duration, "diarization": "elevenlabs", "turns": out}
