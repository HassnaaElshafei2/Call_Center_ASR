"""Request context: the signed-in user and the enterprises they may see.

The enterprise comes from the URL (`/api/e/{ent}/...`); "all" means every enterprise the user belongs to.
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, Membership, User
from .security import read_token

# what each role may do (admins and superadmins may do everything)
CAN = {
    "view": {"admin", "manager", "qa", "retention", "agent", "executive"},
    "review": {"admin", "manager", "qa"},
    "act": {"admin", "manager", "qa", "retention"},
    "upload": {"admin", "manager", "qa"},
    "reveal_phone": {"admin", "manager", "retention"},
    "admin": {"admin"},
}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get("ci_token", "")
    uid = read_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if not user or not user.active:
        raise HTTPException(401, "Sign in first.")
    return user


@dataclass
class Ctx:
    user: User
    db: Session
    slug: str                      # the enterprise in the URL ("all" allowed)
    roles: dict[str, str]          # enterprise id -> role, for the enterprises in scope
    agent_scope: dict[str, str | None]   # enterprise id -> agent id when the role is "agent" (own calls only)

    @property
    def ents(self) -> list[str]:
        return list(self.roles)

    def can(self, what: str, ent: str | None = None) -> bool:
        if self.user.is_superadmin:
            return True
        targets = [ent] if ent else self.ents
        return bool(targets) and all(self.roles.get(e) in CAN[what] for e in targets)

    def require(self, what: str, ent: str | None = None):
        if not self.can(what, ent):
            raise HTTPException(403, "Your role doesn't allow this.")

    def audit(self, action: str, target: str = "", detail: str = "", ent: str | None = None):
        self.db.add(AuditLog(user_id=self.user.id, enterprise_id=ent or (self.ents[0] if len(self.ents) == 1 else None),
                             action=action, target=target, detail=detail))


def memberships(db: Session, user: User) -> dict[str, Membership]:
    return {m.enterprise_id: m for m in db.query(Membership).filter(Membership.user_id == user.id)}


def ctx(ent: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Ctx:
    from .models import Enterprise
    ms = memberships(db, user)
    if user.is_superadmin:
        allowed = {e.id: "admin" for e in db.query(Enterprise)}
        agents = {}
    else:
        allowed = {k: m.role for k, m in ms.items()}
        agents = {k: m.agent_id for k, m in ms.items() if m.role == "agent"}
    if ent == "all":
        roles = allowed
    elif ent in allowed:
        roles = {ent: allowed[ent]}
    else:
        raise HTTPException(404, "Unknown enterprise, or you don't have access to it.")
    if not roles:
        raise HTTPException(403, "You don't have access to any enterprise yet.")
    return Ctx(user=user, db=db, slug=ent, roles=roles, agent_scope={k: v for k, v in agents.items() if k in roles})
