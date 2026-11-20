"""Sign-in, the current user, and enterprise metadata (categories, KPIs, agents, teams, users)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CAN, Ctx, ctx, current_user, memberships
from ..models import ACTION_TYPES, Agent, Category, Enterprise, Membership, Scorecard, Team, User
from ..security import check_password, make_token
from ..services import asr_client, llm

router = APIRouter(prefix="/api")


class Login(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: Login, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or not user.active or not check_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password.")
    token = make_token(user.id)
    response.set_cookie("ci_token", token, httponly=True, samesite="lax", max_age=12 * 3600)
    return {"token": token, "user": me_payload(db, user)}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("ci_token")
    return {"ok": True}


def me_payload(db: Session, user: User) -> dict:
    ents = {e.id: e for e in db.query(Enterprise).order_by(Enterprise.name)}
    if user.is_superadmin:
        roles = {k: "admin" for k in ents}
    else:
        roles = {k: m.role for k, m in memberships(db, user).items() if k in ents}
    return {"id": user.id, "email": user.email, "name": user.name, "superadmin": user.is_superadmin,
            "enterprises": [{"id": k, "name": ents[k].name, "name_ar": ents[k].name_ar, "accent": ents[k].accent,
                             "kind": ents[k].kind, "role": r} for k, r in roles.items()],
            "permissions": {what: sorted(k for k, r in roles.items() if user.is_superadmin or r in who)
                            for what, who in CAN.items()}}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return me_payload(db, user)


@router.get("/e/{ent}/meta")
def meta(c: Ctx = Depends(ctx)):
    db = c.db
    ents = db.query(Enterprise).filter(Enterprise.id.in_(c.ents)).all()
    out = {"enterprises": [{"id": e.id, "name": e.name, "name_ar": e.name_ar, "accent": e.accent, "kind": e.kind,
                            "role": c.roles[e.id], "filename_rules": e.filename_rules} for e in ents],
           "categories": [], "kpis": [], "agents": [], "teams": [], "users": [],
           "action_types": list(ACTION_TYPES),
           "services": {"llm": llm.available(), "asr": asr_client.configured()}}
    for cat in db.query(Category).filter(Category.enterprise_id.in_(c.ents)).order_by(Category.id):
        out["categories"].append({"code": cat.code, "name": cat.name, "name_ar": cat.name_ar,
                                  "enterprise": cat.enterprise_id, "active": cat.active})
    for sc in db.query(Scorecard).filter(Scorecard.enterprise_id.in_(c.ents), Scorecard.active.is_(True)):
        out["kpis"] += [k | {"enterprise": sc.enterprise_id} for k in sc.kpis]
    for a in db.query(Agent).filter(Agent.enterprise_id.in_(c.ents)).order_by(Agent.name):
        out["agents"].append({"id": a.id, "name": a.name, "enterprise": a.enterprise_id, "team": a.team_id,
                              "active": a.active})
    for t in db.query(Team).filter(Team.enterprise_id.in_(c.ents)).order_by(Team.name):
        out["teams"].append({"id": t.id, "name": t.name, "enterprise": t.enterprise_id})
    uids = {m.user_id for m in db.query(Membership).filter(Membership.enterprise_id.in_(c.ents),
                                                          Membership.role.in_(["admin", "manager", "qa", "retention"]))}
    for u in db.query(User).filter(User.id.in_(uids), User.active.is_(True)).order_by(User.name):
        out["users"].append({"id": u.id, "name": u.name})
    return out
