"""Administration: users and roles, enterprise settings, call categories, scorecard versions, audit log, system
status (models, transcription service, queue). Plus the weekly brief."""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from ..deps import Ctx, ctx
from ..models import ROLES, Agent, AuditLog, Call, Category, Enterprise, Job, Membership, Scorecard, Team, User
from ..security import hash_password
from ..services import asr_client, jobs, llm
from .analytics import overview
from .common import CallFilters

router = APIRouter(prefix="/api/e/{ent}/admin")
brief_router = APIRouter(prefix="/api/e/{ent}")


def _admin(c: Ctx, ent: str | None = None):
    c.require("admin", ent)


# --------------------------------------------------------------------------------------------- users
@router.get("/users")
def users(c: Ctx = Depends(ctx)):
    _admin(c)
    uids = {m.user_id for m in c.db.query(Membership).filter(Membership.enterprise_id.in_(c.ents))}
    rows = c.db.query(User).filter(User.id.in_(uids) | User.is_superadmin.is_(True)).order_by(User.name).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "active": u.active, "superadmin": u.is_superadmin,
             "roles": [{"enterprise": m.enterprise_id, "role": m.role, "agent_id": m.agent_id}
                       for m in u.memberships if m.enterprise_id in c.ents]} for u in rows]


class UserIn(BaseModel):
    name: str
    email: str
    password: str | None = None
    active: bool = True
    roles: list[dict] = []          # [{"enterprise", "role", "agent_id"}]


@router.post("/users")
def save_user(body: UserIn, user_id: str | None = None, c: Ctx = Depends(ctx)):
    _admin(c)
    u = c.db.get(User, user_id) if user_id else c.db.query(User).filter_by(email=body.email.lower()).first()
    if user_id and not u:
        raise HTTPException(404, "User not found.")
    if not u:
        if not body.password or len(body.password) < 8:
            raise HTTPException(400, "Give a password of at least 8 characters.")
        u = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password))
        c.db.add(u)
        c.db.flush()
    u.name, u.active = body.name, body.active
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "Passwords need at least 8 characters.")
        u.password_hash = hash_password(body.password)
    for r in body.roles:
        if r.get("enterprise") not in c.ents or r.get("role") not in ROLES + ("none",):
            raise HTTPException(400, "Unknown enterprise or role.")
    for m in list(u.memberships):
        if m.enterprise_id in c.ents:
            c.db.delete(m)
    c.db.flush()
    for r in body.roles:
        if r["role"] != "none":
            c.db.add(Membership(user_id=u.id, enterprise_id=r["enterprise"], role=r["role"], agent_id=r.get("agent_id")))
    c.audit("user_change", u.id, f"{u.email}: {[(r['enterprise'], r['role']) for r in body.roles]}")
    c.db.commit()
    return {"id": u.id}


# --------------------------------------------------------------------------------------------- enterprise settings
class EnterpriseIn(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    accent: str | None = None
    filename_rules: list[dict] | None = None


@router.patch("/enterprise/{eid}")
def save_enterprise(eid: str, body: EnterpriseIn, c: Ctx = Depends(ctx)):
    _admin(c, eid)
    e = c.db.get(Enterprise, eid)
    if not e or eid not in c.ents:
        raise HTTPException(404, "Unknown enterprise.")
    for r in body.filename_rules or []:
        try:
            if "phone" not in re.compile(r.get("pattern", "")).groupindex:
                raise HTTPException(400, "Each file-name rule needs a (?P<phone>...) group.")
        except re.error as err:
            raise HTTPException(400, f"Invalid pattern: {err}") from err
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(e, k, v)
    c.audit("enterprise_change", eid, json.dumps(body.model_dump(exclude_none=True), ensure_ascii=False)[:500], eid)
    c.db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------------------------- categories
class CategoryIn(BaseModel):
    enterprise: str
    code: str
    name: str
    name_ar: str = ""
    description: str = ""
    active: bool = True


@router.post("/categories")
def save_category(body: CategoryIn, c: Ctx = Depends(ctx)):
    _admin(c, body.enterprise)
    code = re.sub(r"[^a-z0-9_]+", "_", body.code.lower()).strip("_")
    if not code:
        raise HTTPException(400, "Give a code.")
    cat = c.db.query(Category).filter_by(enterprise_id=body.enterprise, code=code).first() or \
        Category(enterprise_id=body.enterprise, code=code)
    cat.name, cat.name_ar, cat.description, cat.active = body.name, body.name_ar, body.description, body.active
    c.db.add(cat)
    c.audit("category_change", code, body.name, body.enterprise)
    c.db.commit()
    return {"code": code}


# --------------------------------------------------------------------------------------------- scorecards
@router.get("/scorecards")
def scorecards(c: Ctx = Depends(ctx)):
    rows = c.db.query(Scorecard).filter(Scorecard.enterprise_id.in_(c.ents)).order_by(Scorecard.enterprise_id,
                                                                                         Scorecard.version.desc())
    return [{"id": s.id, "enterprise": s.enterprise_id, "version": s.version, "active": s.active, "kpis": s.kpis,
             "created_at": s.created_at.isoformat()} for s in rows]


class ScorecardIn(BaseModel):
    enterprise: str
    kpis: list[dict]


@router.post("/scorecards")
def publish_scorecard(body: ScorecardIn, c: Ctx = Depends(ctx)):
    """Publishing creates a new version; earlier calls keep the version that scored them."""
    _admin(c, body.enterprise)
    codes = set()
    for k in body.kpis:
        k["code"] = re.sub(r"[^a-z0-9_]+", "_", str(k.get("code", "")).lower()).strip("_")
        if not k["code"] or not k.get("name") or k["code"] in codes:
            raise HTTPException(400, "Every KPI needs a unique code and a name.")
        codes.add(k["code"])
        k["weight"] = float(k.get("weight", 1))
        k["critical"] = bool(k.get("critical", False))
    last = c.db.query(func.max(Scorecard.version)).filter_by(enterprise_id=body.enterprise).scalar() or 0
    c.db.query(Scorecard).filter_by(enterprise_id=body.enterprise).update({"active": False})
    s = Scorecard(enterprise_id=body.enterprise, version=last + 1, active=True, kpis=body.kpis)
    c.db.add(s)
    c.audit("scorecard_publish", f"v{last + 1}", f"{len(body.kpis)} KPIs", body.enterprise)
    c.db.commit()
    return {"version": s.version}


# --------------------------------------------------------------------------------------------- teams and agents
class AgentIn(BaseModel):
    enterprise: str
    name: str
    code: str = ""
    team: str = ""
    active: bool = True


@router.post("/agents")
def save_agent(body: AgentIn, agent_id: str | None = None, c: Ctx = Depends(ctx)):
    _admin(c, body.enterprise)
    a = c.db.get(Agent, agent_id) if agent_id else Agent(enterprise_id=body.enterprise)
    if not a or a.enterprise_id != body.enterprise:
        raise HTTPException(404, "Agent not found.")
    team = None
    if body.team:
        team = c.db.query(Team).filter_by(enterprise_id=body.enterprise, name=body.team).first() or \
            Team(enterprise_id=body.enterprise, name=body.team)
        c.db.add(team)
        c.db.flush()
    a.name, a.code, a.active, a.team_id = body.name, body.code, body.active, team.id if team else None
    c.db.add(a)
    c.db.commit()
    return {"id": a.id}


# --------------------------------------------------------------------------------------------- audit and status
@router.get("/audit")
def audit(limit: int = 200, c: Ctx = Depends(ctx)):
    _admin(c)
    rows = c.db.query(AuditLog).filter(AuditLog.enterprise_id.in_(c.ents) | AuditLog.enterprise_id.is_(None)) \
        .order_by(AuditLog.at.desc()).limit(min(limit, 1000)).all()
    names = {u.id: u.name for u in c.db.query(User).filter(User.id.in_({r.user_id for r in rows}))}
    return [{"at": r.at.isoformat(), "user": names.get(r.user_id, "system"), "action": r.action, "target": r.target,
             "detail": r.detail, "enterprise": r.enterprise_id} for r in rows]


@router.get("/status")
def status(c: Ctx = Depends(ctx)):
    _admin(c)
    counts = dict(c.db.query(Job.status, func.count()).group_by(Job.status).all())
    calls = dict(c.db.query(Call.status, func.count()).filter(Call.enterprise_id.in_(c.ents)).group_by(Call.status).all())
    failed = c.db.query(Job).filter(Job.status == "failed").order_by(Job.id.desc()).limit(10).all()
    return {"llm": {"configured": llm.available(), "model": llm.settings().llm_model,
                    "second_opinion": llm.settings().llm_second_opinion_model or "second Qwen pass",
                    "embedding": llm.settings().embedding_model},
            "asr": asr_client.health(), "jobs": counts, "calls": calls,
            "failed_jobs": [{"id": j.id, "kind": j.kind, "error": j.error[:300], "payload": j.payload} for j in failed]}


@router.post("/retry-waiting")
def retry_waiting(c: Ctx = Depends(ctx)):
    """Queue every call that waits for transcription or failed, e.g. after the ASR service was connected."""
    _admin(c)
    n = 0
    for call in c.db.query(Call).filter(Call.enterprise_id.in_(c.ents), Call.status.in_(["waiting_asr", "failed"])):
        jobs.enqueue(c.db, "process_call", {"call_id": call.id})
        call.status, call.status_detail = "queued", "Queued again"
        n += 1
    c.db.commit()
    return {"queued": n}


# --------------------------------------------------------------------------------------------- weekly brief
@brief_router.get("/brief")
def brief(period: str = "7d", c: Ctx = Depends(ctx)):
    """Management brief: the computed numbers, written up by the model (which may only use these numbers)."""
    ov = overview(c=c, f=CallFilters(period=period))
    facts = {"period": period, "kpis": ov["kpis"], "previous": ov["previous"], "top_reasons": ov["reasons"][:6],
             "agents": [{k: a[k] for k in ("name", "calls", "resolved", "satisfaction")} for a in ov["agents"][:10]],
             "work": ov["work"], "insights": [i["text"] for i in ov["insights"]],
             "enterprises": [{k: e[k] for k in ("name", "calls", "resolved", "satisfaction")} for e in ov["enterprises"]]}
    text = None
    if llm.available() and ov["kpis"]["calls"]:
        try:
            text = llm.chat([{"role": "system", "content":
                              "Write a one-page management brief in English (markdown) for a customer-service director "
                              "from the JSON facts: a one-line headline, then sections 'What changed', 'Biggest problems', "
                              "'People', 'Follow-ups'. Use only the numbers given; rates are fractions (0.42 = 42%); "
                              "satisfaction is predicted, 1-5. Max 250 words."},
                             {"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)}],
                            max_tokens=900, temperature=0.3).get("content")
        except llm.LLMError:
            text = None
    return {"facts": facts, "text": text, "overview": ov}
