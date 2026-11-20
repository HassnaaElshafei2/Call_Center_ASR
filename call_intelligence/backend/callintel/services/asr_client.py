"""Client for the transcription service (asr_service/): Mohammed's fine-tuned Cohere model + pyannote.

Contract (the same wherever the service runs, our own container now, the DGX later):
    POST {ASR_SERVICE_URL}/process   multipart: file=<audio>
    -> {"model": str, "duration": float,
        "turns": [{"speaker": "SPEAKER_00", "start": float, "end": float, "text": str, "confidence": float|null}]}
    GET  {ASR_SERVICE_URL}/health    -> {"ok": true, "model": str, "device": str}
"""
from pathlib import Path

import httpx

from ..config import settings


class ASRUnavailable(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings().asr_service_url)


def health() -> dict:
    if not configured():
        return {"ok": False, "reason": "ASR_SERVICE_URL is not set"}
    try:
        r = httpx.get(f"{settings().asr_service_url}/health", timeout=10)
        return r.json() | {"ok": r.status_code == 200}
    except httpx.HTTPError as e:
        return {"ok": False, "reason": str(e)}


def process(path: Path) -> dict:
    if not configured():
        raise ASRUnavailable("no transcription service configured")
    try:
        with path.open("rb") as f:
            r = httpx.post(f"{settings().asr_service_url}/process", files={"file": (path.name, f)},
                           timeout=httpx.Timeout(1800, connect=10))
    except httpx.ConnectError as e:
        raise ASRUnavailable(f"transcription service unreachable: {e}") from e
    r.raise_for_status()
    return r.json()
