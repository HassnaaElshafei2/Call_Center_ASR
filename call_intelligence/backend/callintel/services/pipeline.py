"""The steps a call goes through: transcribe -> analyse -> index for search. Each step is a queued job."""
import logging

from sqlalchemy.orm import Session

from ..models import Call, Turn
from . import asr_client, jobs, llm, storage
from .analysis import analyze_call
from .roles import assign
from .search import embed_call

log = logging.getLogger(__name__)


def set_status(db: Session, call: Call, status: str, detail: str = ""):
    call.status, call.status_detail = status, detail[:2000]
    db.commit()


def process_call(db: Session, call_id: str):
    call = db.get(Call, call_id)
    if not call:
        return
    if not call.turns:
        if not asr_client.configured():
            set_status(db, call, "waiting_asr", "No transcription service is connected yet. The call will be "
                                                "transcribed once one is set (Administration → System → Retry).")
            return
        path = storage.resolve(call.audio_path)
        if not path:
            set_status(db, call, "failed", "The recording file is missing.")
            return
        set_status(db, call, "transcribing", "Separating speakers and transcribing")
        out = asr_client.process(path)
        raw = [t for t in out.get("turns", []) if (t.get("text") or "").strip()]
        roles = assign(raw)
        for i, t in enumerate(raw):
            call.turns.append(Turn(idx=i, speaker=roles.get(t["speaker"], "unknown"), start=float(t["start"]),
                                   end=float(t["end"]), text=t["text"].strip(), confidence=t.get("confidence")))
        call.duration_s = float(out.get("duration") or (raw[-1]["end"] if raw else 0))
        call.asr_model = (out.get("model") or "")[:80]
        confs = [t["confidence"] for t in raw if t.get("confidence") is not None]
        call.transcript_quality = round(sum(confs) / len(confs), 3) if confs else None
        if not raw:
            set_status(db, call, "failed", "No speech was found in the recording.")
            return
        db.commit()
    jobs.enqueue(db, "analyze_call", {"call_id": call.id})
    set_status(db, call, "analyzing", "Analysing the conversation")


def run_analysis(db: Session, call_id: str):
    call = db.get(Call, call_id)
    if not call:
        return
    if not llm.available():
        set_status(db, call, "failed", "LLM_API_KEY is not set, so the call can't be analysed.")
        return
    set_status(db, call, "analyzing", "Analysing the conversation")
    analyze_call(db, call)
    call.status, call.status_detail = "done", ""
    jobs.enqueue(db, "embed_call", {"call_id": call.id})
    db.commit()


def run_embedding(db: Session, call_id: str):
    call = db.get(Call, call_id)
    if call:
        embed_call(db, call)
        db.commit()


HANDLERS = {"process_call": process_call, "analyze_call": run_analysis, "embed_call": run_embedding}
