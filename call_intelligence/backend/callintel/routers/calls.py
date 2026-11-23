"""Calls: list, detail, upload, audio, transcript corrections, review, re-analysis, CSV export."""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from ..config import settings
from ..deps import Ctx, ctx
from ..models import RESOLUTION, Action, Agent, Call, CallAnalysis, Correction, Promise, Scorecard, Turn
from ..services import identity, jobs, storage
from .common import CallFilters, apply_filters, call_filters, call_row

router = APIRouter(prefix="/api/e/{ent}")
SORTS = {"newest": desc(Call.started_at), "oldest": Call.started_at, "satisfaction": Call.satisfaction,
         "qa": Call.qa_score, "duration": desc(Call.duration_s)}


@router.get("/calls")
def list_calls(page: int = 1, size: int = 50, sort: str = "newest", c: Ctx = Depends(ctx),
               f: CallFilters = Depends(call_filters)):
    size = max(1, min(size, 200))
    q = apply_filters(c, c.db.query(Call), f).options(joinedload(Call.agent), joinedload(Call.customer))
    total = q.count()
    rows = q.order_by(SORTS.get(sort, SORTS["newest"]).nulls_last(), Call.id).offset((page - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size, "calls": [call_row(x) for x in rows]}


def get_call(c: Ctx, call_id: str) -> Call:
    call = apply_filters(c, c.db.query(Call), CallFilters(period="all"), use_window=False).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(404, "Call not found.")
    return call


@router.get("/calls/{call_id}")
def call_detail(call_id: str, c: Ctx = Depends(ctx)):
    call = get_call(c, call_id)
    an = c.db.query(CallAnalysis).filter_by(call_id=call.id).order_by(CallAnalysis.id.desc()).first()
    out = call_row(call)
    out["turns"] = [{"idx": t.idx, "speaker": t.speaker, "start": t.start, "end": t.end, "text": t.text,
                     "confidence": t.confidence, "mood": t.mood, "edited": t.edited} for t in call.turns]
    out["analysis"] = an.data if an else None
    # the scorecard items this call was scored against (names, severity, points), for the QA card
    card = c.db.get(Scorecard, an.scorecard_id) if an and an.scorecard_id else None
    out["qa_items"] = card.kpis if card else []
    out["analysis_meta"] = {"model": an.model, "prompt_version": an.prompt_version, "at": an.created_at.isoformat(),
                            "second_opinion": an.second_opinion} if an else None
    out["metrics"] = call.metrics
    out["has_audio"] = bool(storage.resolve(call.audio_path))
    out["asr_model"] = call.asr_model or ""
    out["transcript_quality"] = call.transcript_quality
    out["promises"] = [{"id": p.id, "text": p.text, "due": p.due_date.isoformat() if p.due_date else None,
                        "status": p.status, "turn": p.turn_idx} for p in c.db.query(Promise).filter_by(call_id=call.id)]
    from .actions import action_row
    out["actions"] = [action_row(a) for a in c.db.query(Action).filter_by(call_id=call.id).order_by(Action.created_at)]
    out["possible_customers"] = identity.possible_matches(c.db, call, call.customer.name if call.customer else "")
    if call.repeat_of:
        prev = c.db.get(Call, call.repeat_of)
        out["repeat_of_call"] = call_row(prev) if prev else None
    out["later_calls"] = [call_row(x) for x in c.db.query(Call).filter(
        Call.customer_id == call.customer_id, Call.started_at > call.started_at, Call.id != call.id)
        .order_by(Call.started_at).limit(5)] if call.customer_id else []
    return out


@router.get("/calls/{call_id}/audio")
def call_audio(call_id: str, c: Ctx = Depends(ctx)):
    call = get_call(c, call_id)
    p = storage.resolve(call.audio_path)
    if not p:
        raise HTTPException(404, "No recording for this call.")
    return FileResponse(p)


@router.post("/calls/upload")
async def upload(ent: str, files: list[UploadFile] = File(...), agent_id: str | None = Form(None),
                 queue: str = Form(""), started_at: str | None = Form(None), c: Ctx = Depends(ctx)):
    if ent == "all":
        raise HTTPException(400, "Choose ADIB or B.TECH before uploading.")
    c.require("upload", ent)
    if agent_id and not c.db.query(Agent).filter_by(id=agent_id, enterprise_id=ent).first():
        raise HTTPException(400, "Unknown agent.")
    when = datetime.fromisoformat(started_at).replace(tzinfo=timezone.utc) if started_at else datetime.now(timezone.utc)
    created = []
    for f in files:
        ext = "." + (f.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in storage.AUDIO_EXT:
            raise HTTPException(400, f"{f.filename}: not an audio file ({', '.join(sorted(storage.AUDIO_EXT))}).")
        call = Call(enterprise_id=ent, external_ref=f.filename or "", agent_id=agent_id, queue=queue,
                    started_at=when, source="upload", status="queued")
        c.db.add(call)
        c.db.flush()
        dest = storage.path_for(ent, call.id, f.filename or "recording")
        size, limit = 0, settings().max_upload_mb * 1024 * 1024
        with dest.open("wb") as out:
            while chunk := await f.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"{f.filename} is larger than {settings().max_upload_mb} MB.")
                out.write(chunk)
        call.audio_path = storage.relative(dest)
        cust = identity.from_recording_name(c.db, call)
        if cust:
            call.customer_id = cust.id
        jobs.enqueue(c.db, "process_call", {"call_id": call.id})
        created.append(call.id)
    c.db.commit()
    return {"created": created}


class TurnEdit(BaseModel):
    text: str


@router.patch("/calls/{call_id}/turns/{idx}")
def edit_turn(call_id: str, idx: int, body: TurnEdit, c: Ctx = Depends(ctx)):
    call = get_call(c, call_id)
    c.require("review", call.enterprise_id)
    t = c.db.query(Turn).filter_by(call_id=call.id, idx=idx).first()
    if not t:
        raise HTTPException(404, "Turn not found.")
    c.db.add(Correction(call_id=call.id, target="turn", turn_idx=idx, old_value=t.text, new_value=body.text,
                        user_id=c.user.id))
    t.text, t.edited, t.embedding = body.text.strip(), True, None
    c.db.commit()
    return {"ok": True}


class Review(BaseModel):
    resolution: str | None = None
    satisfaction: int | None = None
    reason_code: str | None = None
    note: str = ""


@router.post("/calls/{call_id}/review")
def review(call_id: str, body: Review, c: Ctx = Depends(ctx)):
    """Approve the analysis, or correct labels. Corrections are kept as training/evaluation data."""
    call = get_call(c, call_id)
    c.require("review", call.enterprise_id)
    for field, val in (("resolution", body.resolution), ("satisfaction", body.satisfaction), ("reason_code", body.reason_code)):
        if val is None or val == getattr(call, field):
            continue
        if field == "resolution" and val not in RESOLUTION:
            raise HTTPException(400, "Unknown resolution.")
        if field == "satisfaction" and not 1 <= int(val) <= 5:
            raise HTTPException(400, "Satisfaction is 1 to 5.")
        c.db.add(Correction(call_id=call.id, target=field, old_value=str(getattr(call, field)), new_value=str(val),
                            user_id=c.user.id))
        setattr(call, field, val)
        c.audit("label_change", call.id, f"{field} -> {val}", call.enterprise_id)
    call.needs_review, call.reviewed_by, call.reviewed_at = False, c.user.id, datetime.now(timezone.utc)
    if body.note:
        c.audit("review_note", call.id, body.note[:500], call.enterprise_id)
    c.db.commit()
    return call_row(call)


@router.post("/calls/{call_id}/reanalyze")
def reanalyze(call_id: str, c: Ctx = Depends(ctx)):
    call = get_call(c, call_id)
    c.require("review", call.enterprise_id)
    jobs.enqueue(c.db, "process_call" if not call.turns else "analyze_call", {"call_id": call.id})
    call.status, call.status_detail = "queued", "Queued again"
    c.db.commit()
    return {"ok": True}


@router.get("/calls.csv")
def export_csv(c: Ctx = Depends(ctx), f: CallFilters = Depends(call_filters)):
    rows = apply_filters(c, c.db.query(Call), f).options(joinedload(Call.agent), joinedload(Call.customer)) \
        .order_by(Call.started_at.desc()).limit(20000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["call", "enterprise", "started", "duration_s", "agent", "customer", "phone", "reason", "resolution",
                "satisfaction", "sentiment", "mood_end", "churn_risk", "qa_score", "needs_review", "summary"])
    safe = lambda v: ("'" + v) if isinstance(v, str) and v[:1] in "=+-@" else v     # no spreadsheet formulas
    for x in rows:
        w.writerow([safe(v) for v in [x.id, x.enterprise_id, x.started_at.isoformat(), round(x.duration_s or 0),
                    x.agent.name if x.agent else "", x.customer.name if x.customer else "",
                    x.customer.phone_masked if x.customer else "", x.reason_code, x.resolution, x.satisfaction,
                    x.sentiment, x.mood_end, x.churn_risk, x.qa_score, x.needs_review, x.summary]])
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=calls.csv"})
