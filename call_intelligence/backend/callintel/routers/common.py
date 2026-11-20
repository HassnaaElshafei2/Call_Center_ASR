"""Filters and serializers shared by the routers. Every list and chart uses the same call filters, so a
filter in the URL means the same thing on every page and in the assistant."""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone

from fastapi import Query
from sqlalchemy import or_
from sqlalchemy.orm import Query as SAQuery

from ..deps import Ctx
from ..models import Agent, Call, Customer, Turn

PERIODS = {"today": 1, "7d": 7, "30d": 30, "90d": 90, "365d": 365}


@dataclass
class CallFilters:
    period: str = "30d"                 # today, 7d, 30d, 90d, 365d, all, custom
    date_from: str | None = None
    date_to: str | None = None
    agent: str | None = None            # agent id
    team: str | None = None
    reason: str | None = None           # comma-separated reason codes
    resolution: str | None = None       # comma-separated
    sentiment: str | None = None
    mood_end: str | None = None
    sat_max: int | None = None
    sat_min: int | None = None
    churn: str | None = None            # low/medium/high, comma-separated
    review: bool | None = None          # needs review
    compliance: bool | None = None
    repeat: bool | None = None
    customer: str | None = None
    status: str | None = None           # pipeline status; default: done only in analytics
    q: str | None = None                # words in summary or transcript

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) not in (None, "")}


def call_filters(period: str = "30d", date_from: str | None = None, date_to: str | None = None,
                 agent: str | None = None, team: str | None = None, reason: str | None = None,
                 resolution: str | None = None, sentiment: str | None = None, mood_end: str | None = None,
                 sat_max: int | None = Query(None, ge=1, le=5), sat_min: int | None = Query(None, ge=1, le=5),
                 churn: str | None = None, review: bool | None = None, compliance: bool | None = None,
                 repeat: bool | None = None, customer: str | None = None, status: str | None = None,
                 q: str | None = None) -> CallFilters:
    return CallFilters(period, date_from, date_to, agent, team, reason, resolution, sentiment, mood_end, sat_max,
                       sat_min, churn, review, compliance, repeat, customer, status, q)


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def window(f: CallFilters) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(timezone.utc)
    if f.period == "custom" or f.date_from or f.date_to:
        start = datetime.fromisoformat(f.date_from).replace(tzinfo=timezone.utc) if f.date_from else None
        end = (datetime.fromisoformat(f.date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)) if f.date_to else None
        return start, end
    if f.period in PERIODS:
        return now - timedelta(days=PERIODS[f.period]), None
    return None, None


def scope(c: Ctx, q: SAQuery) -> SAQuery:
    """Enterprise and role scope: the enterprises in the URL; agents see only their own calls."""
    q = q.filter(Call.enterprise_id.in_(c.ents))
    for ent, agent_id in c.agent_scope.items():
        q = q.filter(or_(Call.enterprise_id != ent, Call.agent_id == (agent_id or "-")))
    return q


def apply_filters(c: Ctx, q: SAQuery, f: CallFilters, done_only: bool = False, use_window: bool = True) -> SAQuery:
    q = scope(c, q)
    if use_window:
        start, end = window(f)
        if start:
            q = q.filter(Call.started_at >= start)
        if end:
            q = q.filter(Call.started_at < end)
    if f.agent:
        q = q.filter(Call.agent_id.in_(_csv(f.agent)))
    if f.team:
        q = q.filter(Call.agent_id.in_(c.db.query(Agent.id).filter(Agent.team_id.in_(_csv(f.team)))))
    if f.reason:
        q = q.filter(Call.reason_code.in_(_csv(f.reason)))
    if f.resolution:
        q = q.filter(Call.resolution.in_(_csv(f.resolution)))
    if f.sentiment:
        q = q.filter(Call.sentiment.in_(_csv(f.sentiment)))
    if f.mood_end:
        q = q.filter(Call.mood_end.in_(_csv(f.mood_end)))
    if f.sat_max is not None:
        q = q.filter(Call.satisfaction <= f.sat_max)
    if f.sat_min is not None:
        q = q.filter(Call.satisfaction >= f.sat_min)
    if f.churn:
        q = q.filter(Call.churn_risk.in_(_csv(f.churn)))
    if f.review is not None:
        q = q.filter(Call.needs_review.is_(f.review))
    if f.compliance is not None:
        q = q.filter(Call.compliance_issue.is_(f.compliance))
    if f.repeat is not None:
        q = q.filter(Call.repeat_of.isnot(None) if f.repeat else Call.repeat_of.is_(None))
    if f.customer:
        q = q.filter(Call.customer_id == f.customer)
    if f.status:
        q = q.filter(Call.status.in_(_csv(f.status)))
    elif done_only:
        q = q.filter(Call.status == "done")
    if f.q:
        like = f"%{f.q.strip()}%"
        q = q.filter(or_(Call.summary.ilike(like), Call.summary_ar.ilike(like), Call.external_ref.ilike(like),
                         Call.id.in_(c.db.query(Turn.call_id).filter(Turn.text.ilike(like)))))
    return q


def call_row(call: Call) -> dict:
    return {
        "id": call.id, "enterprise": call.enterprise_id, "ref": call.external_ref,
        "started_at": call.started_at.isoformat(), "duration_s": round(call.duration_s or 0),
        "agent": {"id": call.agent.id, "name": call.agent.name} if call.agent else None,
        "customer": customer_brief(call.customer) if call.customer else None,
        "queue": call.queue, "status": call.status, "status_detail": call.status_detail,
        "summary": call.summary, "summary_ar": call.summary_ar, "reason": call.reason_code,
        "resolution": call.resolution, "satisfaction": call.satisfaction, "sentiment": call.sentiment,
        "mood_start": call.mood_start, "mood_end": call.mood_end, "churn_risk": call.churn_risk,
        "escalation_risk": call.escalation_risk, "compliance_issue": call.compliance_issue,
        "qa_score": call.qa_score, "critical_fail": call.critical_fail, "needs_review": call.needs_review,
        "review_reason": call.review_reason, "repeat_of": call.repeat_of, "source": call.source,
    }


def customer_brief(c: Customer) -> dict:
    return {"id": c.id, "name": c.name or "Unnamed customer", "phone": c.phone_masked, "identified_by": c.identified_by,
            "vip": c.vip}
