"""Action Center: recommended and created actions, message drafts (a person approves before anything is sent),
outcomes, promises made to customers, and alerts."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from ..deps import Ctx, ctx
from ..models import (ACTION_OUTCOME, ACTION_STATUS, ACTION_TYPES, LEVEL, Action, ActionEvent, Alert, Call, Customer,
                      Promise, User)
from ..services import llm
from .common import customer_brief

router = APIRouter(prefix="/api/e/{ent}")


def action_row(a: Action) -> dict:
    return {"id": a.id, "enterprise": a.enterprise_id, "call_id": a.call_id, "customer_id": a.customer_id,
            "agent_id": a.agent_id, "type": a.type, "title": a.title, "reason": a.reason, "priority": a.priority,
            "status": a.status, "owner_id": a.owner_id, "due": a.due_date.isoformat() if a.due_date else None,
            "outcome": a.outcome, "outcome_note": a.outcome_note, "draft_message": a.draft_message,
            "draft_approved": bool(a.draft_approved_by), "value_egp": a.value_egp, "created_by": a.created_by,
            "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            "overdue": bool(a.due_date and a.due_date < date.today() and a.status in ("suggested", "open", "in_progress"))}


def _scoped(c: Ctx, q):
    q = q.filter(Action.enterprise_id.in_(c.ents))
    for ent, agent_id in c.agent_scope.items():
        q = q.filter(or_(Action.enterprise_id != ent, Action.agent_id == (agent_id or "-")))
    return q


@router.get("/actions")
def list_actions(status: str | None = None, type: str | None = None, owner: str | None = None,
                 priority: str | None = None, call: str | None = None, customer: str | None = None,
                 c: Ctx = Depends(ctx)):
    q = _scoped(c, c.db.query(Action))
    if status:
        q = q.filter(Action.status.in_(status.split(",")))
    if type:
        q = q.filter(Action.type.in_(type.split(",")))
    if owner == "me":
        q = q.filter(Action.owner_id == c.user.id)
    elif owner:
        q = q.filter(Action.owner_id == owner)
    if priority:
        q = q.filter(Action.priority.in_(priority.split(",")))
    if call:
        q = q.filter(Action.call_id == call)
    if customer:
        q = q.filter(Action.customer_id == customer)
    order = {"high": 0, "medium": 1, "low": 2}
    rows = q.order_by(Action.created_at.desc()).limit(1000).all()
    rows.sort(key=lambda a: (a.status in ("done", "dismissed"), order.get(a.priority, 3), a.due_date or date.max))
    calls = {x.id: x for x in c.db.query(Call).options(joinedload(Call.customer), joinedload(Call.agent))
             .filter(Call.id.in_({a.call_id for a in rows if a.call_id}))}
    custs = {x.id: x for x in c.db.query(Customer).filter(Customer.id.in_({a.customer_id for a in rows if a.customer_id}))}
    out = []
    for a in rows:
        r = action_row(a)
        cl = calls.get(a.call_id)
        r["call"] = {"summary": cl.summary, "started_at": cl.started_at.isoformat(), "satisfaction": cl.satisfaction,
                     "resolution": cl.resolution, "reason": cl.reason_code,
                     "agent": cl.agent.name if cl.agent else None} if cl else None
        r["customer"] = customer_brief(custs[a.customer_id]) if a.customer_id in custs else None
        out.append(r)
    done = [a for a in rows if a.status == "done"]
    summary = {"open": sum(a.status in ("suggested", "open", "in_progress") for a in rows),
               "suggested": sum(a.status == "suggested" for a in rows),
               "overdue": sum(r["overdue"] for r in out), "done": len(done),
               "recovered": sum(a.outcome in ("recovered", "offer_accepted", "resolved_later") for a in done),
               "value_egp": round(sum(a.value_egp or 0 for a in done if a.outcome in ("recovered", "offer_accepted")), 2)}
    return {"actions": out, "summary": summary}


class NewAction(BaseModel):
    call_ids: list[str] = []
    customer_id: str | None = None
    type: str
    title: str
    reason: str = ""
    priority: str = "medium"
    due: date | None = None
    owner_id: str | None = None


@router.post("/actions")
def create_actions(ent: str, body: NewAction, c: Ctx = Depends(ctx)):
    if body.type not in ACTION_TYPES or body.priority not in LEVEL:
        raise HTTPException(400, "Unknown action type or priority.")
    targets = []
    for cid in body.call_ids or [None]:
        call = c.db.get(Call, cid) if cid else None
        if cid and (not call or call.enterprise_id not in c.ents):
            raise HTTPException(404, f"Call {cid} not found.")
        e = call.enterprise_id if call else (ent if ent != "all" else None)
        if not e:
            raise HTTPException(400, "Choose an enterprise.")
        c.require("act", e)
        a = Action(enterprise_id=e, call_id=cid, customer_id=(call.customer_id if call else body.customer_id),
                   agent_id=call.agent_id if call else None, type=body.type, title=body.title[:240],
                   reason=body.reason, priority=body.priority, status="open", owner_id=body.owner_id,
                   due_date=body.due, created_by=c.user.id)
        a.events.append(ActionEvent(user_id=c.user.id, kind="created", detail="created by " + c.user.name))
        c.db.add(a)
        targets.append(a)
    c.db.commit()
    return {"created": [action_row(a) for a in targets]}


class ActionPatch(BaseModel):
    status: str | None = None
    owner_id: str | None = None
    due: date | None = None
    priority: str | None = None
    outcome: str | None = None
    outcome_note: str | None = None
    draft_message: str | None = None
    approve_draft: bool | None = None
    value_egp: float | None = None
    note: str | None = None


def _get(c: Ctx, action_id: str) -> Action:
    a = _scoped(c, c.db.query(Action)).filter(Action.id == action_id).first()
    if not a:
        raise HTTPException(404, "Action not found.")
    return a


@router.get("/actions/{action_id}")
def get_action(action_id: str, c: Ctx = Depends(ctx)):
    a = _get(c, action_id)
    users = {u.id: u.name for u in c.db.query(User).filter(User.id.in_({e.user_id for e in a.events if e.user_id}))}
    return action_row(a) | {"events": [{"kind": e.kind, "detail": e.detail, "at": e.at.isoformat(),
                                        "user": users.get(e.user_id, "Call analysis")} for e in a.events]}


@router.patch("/actions/{action_id}")
def patch_action(action_id: str, body: ActionPatch, c: Ctx = Depends(ctx)):
    a = _get(c, action_id)
    c.require("act", a.enterprise_id)
    ev = lambda kind, detail: a.events.append(ActionEvent(user_id=c.user.id, kind=kind, detail=detail))
    if body.status and body.status != a.status:
        if body.status not in ACTION_STATUS:
            raise HTTPException(400, "Unknown status.")
        ev("status", f"{a.status} → {body.status}")
        a.status = body.status
    if body.owner_id is not None and body.owner_id != a.owner_id:
        u = c.db.get(User, body.owner_id) if body.owner_id else None
        a.owner_id = u.id if u else None
        ev("assigned", f"assigned to {u.name}" if u else "unassigned")
        if a.status == "suggested":
            a.status = "open"
    if body.due is not None:
        a.due_date = body.due
    if body.priority:
        a.priority = body.priority
    if body.outcome is not None:
        if body.outcome and body.outcome not in ACTION_OUTCOME:
            raise HTTPException(400, "Unknown outcome.")
        a.outcome = body.outcome
        a.outcome_note = body.outcome_note or a.outcome_note
        ev("outcome", f"{body.outcome.replace('_', ' ')}" + (f": {body.outcome_note}" if body.outcome_note else ""))
        if body.outcome:
            a.status = "done"
    if body.value_egp is not None:
        a.value_egp = body.value_egp
    if body.draft_message is not None and body.draft_message != a.draft_message:
        a.draft_message, a.draft_approved_by = body.draft_message, None
        ev("draft", "message edited")
    if body.approve_draft:
        a.draft_approved_by = c.user.id
        ev("draft", f"message approved by {c.user.name}")
    if body.note:
        ev("note", body.note[:1000])
    c.db.commit()
    return get_action(action_id, c)


@router.post("/actions/{action_id}/draft")
def draft(action_id: str, tone: str = "warm", c: Ctx = Depends(ctx)):
    """Write (or rewrite) the customer message from the call. It is only a draft: a person approves it."""
    a = _get(c, action_id)
    c.require("act", a.enterprise_id)
    call = c.db.get(Call, a.call_id) if a.call_id else None
    if not call:
        raise HTTPException(400, "This action has no call to draft from.")
    ctx_text = "\n".join(f"{t.speaker}: {t.text}" for t in call.turns)[-6000:]
    msg = llm.chat([{"role": "system", "content":
                     "You write short customer messages (SMS/WhatsApp, max 70 words) in polite Egyptian Arabic for a "
                     "customer-service team. Use the customer's name if known. Never promise amounts, discounts or dates "
                     "that are not in the call: use placeholders like [القيمة] or [التاريخ]. Output only the message."},
                    {"role": "user", "content": f"Action: {a.title} ({a.type}). Why: {a.reason}. Tone: {tone}.\n"
                                                f"Customer: {call.customer.name if call.customer else ''}\n"
                                                f"Call summary: {call.summary}\nEnd of the call:\n{ctx_text}"}],
                   max_tokens=300, temperature=0.4)
    a.draft_message, a.draft_approved_by = (msg.get("content") or "").strip(), None
    a.events.append(ActionEvent(user_id=c.user.id, kind="draft", detail="message drafted by the assistant"))
    c.db.commit()
    return action_row(a)


# --------------------------------------------------------------------------------------------- promises
@router.get("/promises")
def promises(status: str = "open", c: Ctx = Depends(ctx)):
    q = c.db.query(Promise).filter(Promise.enterprise_id.in_(c.ents))
    if status != "all":
        q = q.filter(Promise.status == status)
    rows = q.order_by(Promise.due_date.asc().nulls_last()).limit(500).all()
    calls = {x.id: x for x in c.db.query(Call).options(joinedload(Call.customer), joinedload(Call.agent))
             .filter(Call.id.in_({p.call_id for p in rows}))}
    today = date.today()
    return [{"id": p.id, "text": p.text, "due": p.due_date.isoformat() if p.due_date else None, "status": p.status,
             "overdue": bool(p.due_date and p.due_date < today and p.status == "open"),
             "due_today": p.due_date == today, "call_id": p.call_id,
             "customer": customer_brief(calls[p.call_id].customer) if calls.get(p.call_id) and calls[p.call_id].customer else None,
             "agent": calls[p.call_id].agent.name if calls.get(p.call_id) and calls[p.call_id].agent else None,
             "enterprise": p.enterprise_id} for p in rows]


class PromisePatch(BaseModel):
    status: str


@router.patch("/promises/{pid}")
def patch_promise(pid: int, body: PromisePatch, c: Ctx = Depends(ctx)):
    p = c.db.get(Promise, pid)
    if not p or p.enterprise_id not in c.ents:
        raise HTTPException(404, "Promise not found.")
    c.require("act", p.enterprise_id)
    if body.status not in ("open", "kept", "broken"):
        raise HTTPException(400, "Unknown status.")
    p.status = body.status
    c.db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------------------------- alerts
@router.get("/alerts")
def alerts(status: str | None = None, c: Ctx = Depends(ctx)):
    q = c.db.query(Alert).filter(Alert.enterprise_id.in_(c.ents))
    if status:
        q = q.filter(Alert.status.in_(status.split(",")))
    rows = q.order_by(Alert.created_at.desc()).limit(300).all()
    return {"alerts": [{"id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "status": a.status,
                        "call_id": a.call_id, "enterprise": a.enterprise_id, "at": a.created_at.isoformat()} for a in rows],
            "new": sum(a.status == "new" for a in rows)}


class AlertPatch(BaseModel):
    status: str
    ids: list[int] = []


@router.post("/alerts/status")
def alert_status(body: AlertPatch, c: Ctx = Depends(ctx)):
    if body.status not in ("new", "seen", "resolved"):
        raise HTTPException(400, "Unknown status.")
    q = c.db.query(Alert).filter(Alert.enterprise_id.in_(c.ents))
    if body.ids:
        q = q.filter(Alert.id.in_(body.ids))
    elif body.status == "seen":
        q = q.filter(Alert.status == "new")
    n = 0
    for a in q:
        a.status = body.status
        n += 1
    c.db.commit()
    return {"updated": n, "at": datetime.now(timezone.utc).isoformat()}
