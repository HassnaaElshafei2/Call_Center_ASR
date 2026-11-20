"""Database tables. Every business record carries enterprise_id; queries are always filtered by it."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


ROLES = ("admin", "manager", "qa", "retention", "agent", "executive")
CALL_STATUSES = ("queued", "waiting_asr", "transcribing", "analyzing", "done", "failed")
RESOLUTION = ("resolved", "partly_resolved", "not_resolved")
SENTIMENT = ("positive", "neutral", "negative", "mixed")
MOOD = ("calm", "happy", "confused", "worried", "frustrated", "angry")
LEVEL = ("low", "medium", "high")
ACTION_TYPES = ("callback", "offer", "apology", "escalate", "ticket", "technician", "refund_review",
                "coach_agent", "follow_up", "verify_info")
ACTION_STATUS = ("suggested", "open", "in_progress", "done", "dismissed")
ACTION_OUTCOME = ("recovered", "offer_accepted", "resolved_later", "no_answer", "not_recovered")


class Enterprise(Base):
    __tablename__ = "enterprises"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)          # "adib", "btech"
    name: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(32), default="bank")            # bank, retail, ...
    accent: Mapped[str] = mapped_column(String(16), default="#5516fb")
    # file-name rules: [{"pattern": regex, "phone_group": "phone"}] -> customer phone from the recording name
    filename_rules: Mapped[list] = mapped_column(JSON, default=list)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    memberships: Mapped[list[Membership]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Membership(Base):
    """A user's role in one enterprise (roles are per enterprise)."""
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "enterprise_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    user: Mapped[User] = relationship(back_populates="memberships")


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(64), default="")                 # employee id / extension
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    phone_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    phone_masked: Mapped[str] = mapped_column(String(32), default="")
    phone_full: Mapped[str] = mapped_column(String(32), default="")           # revealed only to permitted roles, audited
    identified_by: Mapped[str] = mapped_column(String(24), default="none")    # filename, transcript, manual, none
    vip: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Category(Base):
    """Call reasons, editable per enterprise."""
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("enterprise_id", "code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Scorecard(Base):
    """Versioned QA scorecard; a published version never changes (calls keep the version that scored them)."""
    __tablename__ = "scorecards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # [{"code","name","description","weight","critical"}]
    kpis: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (Index("ix_calls_ent_started", "enterprise_id", "started_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    external_ref: Mapped[str] = mapped_column(String(200), default="", index=True)   # recording name
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    queue: Mapped[str] = mapped_column(String(80), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    audio_path: Mapped[str] = mapped_column(String(400), default="")
    source: Mapped[str] = mapped_column(String(24), default="upload")          # upload, seed, api, folder
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    status_detail: Mapped[str] = mapped_column(Text, default="")
    transcript_quality: Mapped[float | None] = mapped_column(Float, nullable=True)

    # analysis results copied here for filtering and charts (full output in CallAnalysis.data)
    summary: Mapped[str] = mapped_column(Text, default="")
    summary_ar: Mapped[str] = mapped_column(Text, default="")
    reason_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    resolution: Mapped[str] = mapped_column(String(24), default="", index=True)
    satisfaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentiment: Mapped[str] = mapped_column(String(16), default="")
    mood_start: Mapped[str] = mapped_column(String(16), default="")
    mood_end: Mapped[str] = mapped_column(String(16), default="")
    churn_risk: Mapped[str] = mapped_column(String(8), default="")
    escalation_risk: Mapped[str] = mapped_column(String(8), default="")
    compliance_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    qa_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    critical_fail: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reason: Mapped[str] = mapped_column(String(200), default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repeat_of: Mapped[str | None] = mapped_column(String(32), nullable=True)    # earlier call by the same customer on the same reason
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)                  # measured behaviour (talk ratio, silence, ...)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    agent: Mapped[Agent | None] = relationship()
    customer: Mapped[Customer | None] = relationship()
    turns: Mapped[list[Turn]] = relationship(back_populates="call", cascade="all, delete-orphan", order_by="Turn.idx")


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (UniqueConstraint("call_id", "idx"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(16))          # agent, customer, ivr, unknown
    start: Mapped[float] = mapped_column(Float, default=0)
    end: Mapped[float] = mapped_column(Float, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    mood: Mapped[str] = mapped_column(String(16), default="")  # customer mood at this turn (from the analysis)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    call: Mapped[Call] = relationship(back_populates="turns")


class CallAnalysis(Base):
    """Every analysis run is kept (model + prompt version), the latest one is copied onto the call."""
    __tablename__ = "call_analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(32))
    scorecard_id: Mapped[int | None] = mapped_column(ForeignKey("scorecards.id", ondelete="SET NULL"), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    second_opinion: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    seconds: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Promise(Base):
    __tablename__ = "promises"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")          # open, kept, broken
    turn_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Action(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(240))
    reason: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(8), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="suggested", index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    outcome: Mapped[str] = mapped_column(String(24), default="")
    outcome_note: Mapped[str] = mapped_column(Text, default="")
    draft_message: Mapped[str] = mapped_column(Text, default="")
    draft_approved_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value_egp: Mapped[float | None] = mapped_column(Float, nullable=True)     # offer value / revenue kept, if known
    created_by: Mapped[str] = mapped_column(String(32), default="ai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    events: Mapped[list[ActionEvent]] = relationship(cascade="all, delete-orphan", order_by="ActionEvent.at")


class ActionEvent(Base):
    __tablename__ = "action_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))                             # created, status, assigned, note, outcome, draft
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id", ondelete="CASCADE"), index=True)
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))          # angry_customer, compliance, vip_unresolved, promise_due, topic_spike
    severity: Mapped[str] = mapped_column(String(8), default="medium")
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(12), default="new")             # new, seen, resolved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    """Work queue in the database (SELECT ... FOR UPDATE SKIP LOCKED): no extra service needed."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32))          # process_call, analyze_call, embed_call
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)   # pending, running, done, failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Correction(Base):
    """Human fixes to transcripts and labels; they become training data."""
    __tablename__ = "corrections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    target: Mapped[str] = mapped_column(String(32))        # turn, resolution, satisfaction, reason, ...
    turn_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[str] = mapped_column(String(32))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    enterprise_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(48))        # reveal_phone, label_change, user_change, ...
    target: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
