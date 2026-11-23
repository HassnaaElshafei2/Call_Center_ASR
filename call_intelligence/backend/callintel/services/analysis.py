"""Call analysis with Qwen3.6-35B on the DGX gateway.

One strict-JSON answer per call: summary, reason, resolution, predicted satisfaction, mood journey, key moments,
customer identity hints, QA scorecard, promises, opportunities, risks and recommended actions. Every label points at
transcript turns ([n]) so the interface can show the evidence. Measured behaviour (talk ratio, silences...) is
computed from the turns, never asked of the model.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import (ACTION_TYPES, LEVEL, MOOD, RESOLUTION, SENTIMENT, Action, ActionEvent, Alert, Call,
                      CallAnalysis, Category, Enterprise, Promise, Scorecard)
from . import llm
from .identity import link_customer
from .metrics import measure

log = logging.getLogger(__name__)
PROMPT_VERSION = "2026-11-23.1"
MOMENTS = ("problem_stated", "frustration", "escalation_request", "hold", "solution_offered", "resolution",
           "promise", "gratitude", "upsell", "complaint", "compliance_issue", "confusion")
OPPORTUNITY = ("upsell", "cross_sell", "retention_offer", "loyalty", "referral")


def _arr(items: dict, max_items: int) -> dict:
    return {"type": "array", "items": {"type": "object", "properties": items, "required": list(items),
                                       "additionalProperties": False}, "maxItems": max_items}


def mistake_mode(kpis: list[dict]) -> bool:
    """A scorecard of mistakes (ADIB's scoresheet): each item has a severity and takes its points off 100."""
    return bool(kpis) and all("severity" in k for k in kpis)


def schema(categories: list[str], kpis: list[str], mistakes: bool = False) -> dict:
    s = lambda: {"type": "string"}
    turns = {"type": "array", "items": {"type": "integer"}, "maxItems": 4}
    nullable = lambda t: {"type": [t, "null"]}
    props = {
        "summary": s(), "summary_ar": s(),
        "reason_code": {"type": "string", "enum": categories + ["other"]}, "reason_detail": s(),
        "products": {"type": "array", "items": s(), "maxItems": 5},
        "resolution": {"type": "object", "additionalProperties": False, "required": ["status", "explanation", "evidence_turns"],
                       "properties": {"status": {"type": "string", "enum": list(RESOLUTION)}, "explanation": s(),
                                      "evidence_turns": turns}},
        "satisfaction": {"type": "object", "additionalProperties": False, "required": ["score", "signals", "evidence_turns"],
                         "properties": {"score": {"type": "integer", "minimum": 1, "maximum": 5},
                                        "signals": {"type": "array", "items": s(), "maxItems": 4}, "evidence_turns": turns}},
        "sentiment": {"type": "object", "additionalProperties": False,
                      "required": ["overall", "mood_start", "mood_middle", "mood_end"],
                      "properties": {"overall": {"type": "string", "enum": list(SENTIMENT)},
                                     "mood_start": {"type": "string", "enum": list(MOOD)},
                                     "mood_middle": {"type": "string", "enum": list(MOOD)},
                                     "mood_end": {"type": "string", "enum": list(MOOD)}}},
        "mood_changes": _arr({"turn": {"type": "integer"}, "mood": {"type": "string", "enum": list(MOOD)}}, 12),
        "moments": _arr({"turn": {"type": "integer"}, "type": {"type": "string", "enum": list(MOMENTS)}, "note": s()}, 10),
        "customer": {"type": "object", "additionalProperties": False, "required": ["name", "phone"],
                     "properties": {"name": nullable("string"), "phone": nullable("string")}},
        "agent_name": nullable("string"),
        **({"qa_mistakes": _arr({"code": {"type": "string", "enum": kpis}, "turn": nullable("integer"), "note": s()},
                                 len(kpis))} if mistakes else
           {"scorecard": _arr({"kpi": {"type": "string", "enum": kpis or ["none"]},
                               "result": {"type": "string", "enum": ["pass", "fail", "na"]},
                               "turn": nullable("integer"), "note": s()}, max(1, len(kpis)))}),
        "promises": _arr({"text": s(), "due_in_days": nullable("integer"), "turn": {"type": "integer"}}, 5),
        "opportunities": _arr({"type": {"type": "string", "enum": list(OPPORTUNITY)}, "note": s(),
                               "turn": {"type": "integer"}}, 4),
        "knowledge_gaps": {"type": "array", "items": s(), "maxItems": 4},
        "risks": {"type": "object", "additionalProperties": False, "required": ["churn", "escalation", "compliance_issues"],
                  "properties": {"churn": {"type": "string", "enum": list(LEVEL)},
                                 "escalation": {"type": "string", "enum": list(LEVEL)},
                                 "compliance_issues": {"type": "array", "items": s(), "maxItems": 4}}},
        "actions": _arr({"type": {"type": "string", "enum": list(ACTION_TYPES)}, "title": s(), "reason": s(),
                         "priority": {"type": "string", "enum": list(LEVEL)}, "draft_message": nullable("string")}, 4),
    }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SYSTEM = """You analyse customer-service phone calls for {company} ({kind}) in Egypt. Transcripts are Egyptian Arabic,
produced by speech recognition, so expect some wrong words: judge by meaning. Speakers are AGENT, CUSTOMER and IVR.

Rules:
- Base every label on the transcript only. Cite turn numbers [n] as evidence.
- resolution (be strict; a polite ending is not a resolution):
  "resolved" = the problem was actually fixed or the question fully answered DURING this call (card unblocked,
  information given, change made) and nothing is left waiting.
  "partly_resolved" = the customer still has to wait for something: a refund in X days, a technician visit, a new
  delivery date, an escalation, a complaint ticket, a callback, a document to send, a branch visit; or only part of
  the request was handled.
  "not_resolved" = the request was refused or impossible, the agent couldn't help, or the customer is left without a
  clear way forward. A repeat failure (e.g. technician didn't come again) that is only escalated is at best partly
  resolved.
- satisfaction is the customer's predicted satisfaction at the end of the call (1 very unhappy ... 5 very happy),
  from the customer's own words and tone, not the agent's politeness: thanks at the end is normal and doesn't make a
  5. A customer who was frustrated and is still waiting for a fix is usually 2-3. Give 5 only for clear delight.
- mood: judge the customer's real mood; an angry customer who calms down but still has the problem ends "worried" or
  "frustrated", not "calm".
- mood_changes: only customer turns where their mood clearly changes. moments: the turning points of the call.
- customer.name / customer.phone: only if the customer says them (phone as digits only, e.g. "01012345678"), else null.
{qa_rule}
- risks.churn: "high" if the customer threatens to leave, close the account or go to a competitor, or is angry about
  a repeated failure; "medium" if they are unhappy and still waiting for a fix.
- promises: commitments the agent or company made (callback, technician visit, refund), with days until due if said.
- actions: what the company should do next for this customer or this agent (none if nothing is needed). If a message
  to the customer helps (apology, offer, follow-up), write draft_message in polite Egyptian Arabic; never invent
  amounts or discounts that weren't mentioned, use "[القيمة]" placeholders instead.
- summary in English (2-4 sentences), summary_ar in Egyptian Arabic (1-2 sentences). Keep notes short.

Call reasons (reason_code): {categories}

{qa_title}: {kpis}"""

QA_KPI_RULE = """- scorecard: one entry per KPI listed below; "na" when the KPI doesn't apply to this call. Score like a strict QA
  auditor: "pass" only if the agent clearly did it; anything skipped, rushed, unclear or wrong is "fail" with the
  reason. Most real calls miss at least one item."""
QA_MISTAKE_RULE = """- qa_mistakes: the agent's mistakes in this call, from the QA mistake list below only, each at most once, with the
  turn where it happens (null if it is something missing from the whole call) and a short note saying what the agent
  did or didn't do. Audit like a strict QA reviewer, but only list a mistake the transcript clearly shows; speech
  recognition errors and garbled or repeated transcript text are not the agent's mistakes.
  An empty list is right for a clean call."""


def transcript_text(call: Call) -> str:
    return "\n".join(f"[{t.idx}] {t.speaker.upper()}: {t.text}" for t in call.turns if t.text.strip())


def analyze_call(db: Session, call: Call, second_opinion: bool = True) -> CallAnalysis:
    ent = db.get(Enterprise, call.enterprise_id)
    cats = db.query(Category).filter_by(enterprise_id=ent.id, active=True).order_by(Category.id).all()
    card = db.query(Scorecard).filter_by(enterprise_id=ent.id, active=True).order_by(Scorecard.version.desc()).first()
    kpis = card.kpis if card else []
    mistakes = mistake_mode(kpis)
    system = SYSTEM.format(
        company=ent.name, kind=ent.kind,
        categories="; ".join(f"{c.code} = {c.name}" + (f" ({c.description})" if c.description else "") for c in cats),
        kpis="; ".join(f"{k['code']} = {k['name']}: {k.get('description', '')}" for k in kpis) or "none",
        qa_rule=QA_MISTAKE_RULE if mistakes else QA_KPI_RULE,
        qa_title="QA mistake list (code = mistake: severity)" if mistakes else "QA scorecard KPIs")
    text = transcript_text(call)
    if not text:
        raise ValueError("the call has no transcript")
    t0 = time.time()
    data = llm.chat_json([{"role": "system", "content": system},
                          {"role": "user", "content": f"Transcript:\n{text}"}],
                         schema([c.code for c in cats], [k["code"] for k in kpis], mistakes), max_tokens=4000, temperature=0.1)
    seconds = time.time() - t0
    second = verify(call, data, text) if second_opinion and _high_impact(data) else None
    rec = CallAnalysis(call_id=call.id, model=llm.settings().llm_model, prompt_version=PROMPT_VERSION,
                       scorecard_id=card.id if card else None, data=data, second_opinion=second, seconds=seconds)
    db.add(rec)
    apply(db, call, data, kpis, second)
    return rec


def _high_impact(d: dict) -> bool:
    return (d["resolution"]["status"] == "not_resolved" or d["satisfaction"]["score"] <= 2
            or d["risks"]["churn"] == "high" or bool(d["risks"]["compliance_issues"]))


VERIFY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["resolution", "satisfaction", "agree", "why"],
                 "properties": {"resolution": {"type": "string", "enum": list(RESOLUTION)},
                                "satisfaction": {"type": "integer", "minimum": 1, "maximum": 5},
                                "agree": {"type": "boolean"}, "why": {"type": "string"}}}


def verify(call: Call, d: dict, text: str) -> dict | None:
    """Second opinion on high-impact labels: another model if configured, else a second, independent Qwen pass."""
    model = llm.settings().llm_second_opinion_model or None
    try:
        return llm.chat_json([
            {"role": "system", "content": "You audit another analyst's labels for an Egyptian Arabic customer-service call "
                                          "(speech-recognition transcript, expect errors). Decide independently, then say "
                                          "whether you agree. Be strict: 'resolved' only if the problem was fully handled."},
            {"role": "user", "content": f"Transcript:\n{text}\n\nAnalyst said: resolution={d['resolution']['status']}, "
                                        f"satisfaction={d['satisfaction']['score']}/5, churn risk={d['risks']['churn']}, "
                                        f"compliance issues={d['risks']['compliance_issues']}."}],
            VERIFY_SCHEMA, model=model, max_tokens=400, temperature=0.0)
    except llm.LLMError as e:
        log.warning("second opinion failed for %s: %s", call.id, e)
        return None


def mistakes_to_scorecard(d: dict, kpis: list[dict]) -> None:
    """Score a mistake list: 100 minus the points of each mistake (once per call), never below 0. Also fills
    d["scorecard"] (fail = the mistake happened) so agent pages and coaching read it like any scorecard."""
    by = {k["code"]: k for k in kpis}
    seen, found = set(), []
    for m in d.get("qa_mistakes") or []:
        if m["code"] in by and m["code"] not in seen:
            seen.add(m["code"])
            found.append(m)
    d["qa_mistakes"] = found
    d["scorecard"] = [{"kpi": k["code"], "result": "fail" if k["code"] in seen else "pass",
                       "turn": next((m["turn"] for m in found if m["code"] == k["code"]), None),
                       "note": next((m["note"] for m in found if m["code"] == k["code"]), "")} for k in kpis]


def _qa(scorecard: list[dict], kpis: list[dict]) -> tuple[float | None, bool]:
    if mistake_mode(kpis):
        failed = {r["kpi"] for r in scorecard if r["result"] == "fail"}
        items = [k for k in kpis if k["code"] in failed]
        return max(0.0, 100.0 - sum(float(k["weight"]) for k in items)), any(k.get("critical") for k in items)
    weights = {k["code"]: float(k.get("weight", 1)) for k in kpis}
    critical = {k["code"] for k in kpis if k.get("critical")}
    got = tot = 0.0
    crit_fail = False
    for r in scorecard:
        if r["kpi"] not in weights or r["result"] == "na":
            continue
        tot += weights[r["kpi"]]
        got += weights[r["kpi"]] if r["result"] == "pass" else 0
        crit_fail |= r["result"] == "fail" and r["kpi"] in critical
    return (round(100 * got / tot, 1) if tot else None), crit_fail


def apply(db: Session, call: Call, d: dict, kpis: list[dict], second: dict | None = None):
    """Copy an analysis onto the call and create its promises, suggested actions and alerts."""
    call.summary, call.summary_ar = d["summary"], d["summary_ar"]
    call.reason_code = d["reason_code"]
    call.resolution = d["resolution"]["status"]
    call.satisfaction = d["satisfaction"]["score"]
    call.sentiment = d["sentiment"]["overall"]
    call.mood_start, call.mood_end = d["sentiment"]["mood_start"], d["sentiment"]["mood_end"]
    call.churn_risk, call.escalation_risk = d["risks"]["churn"], d["risks"]["escalation"]
    call.compliance_issue = bool(d["risks"]["compliance_issues"])
    if mistake_mode(kpis) and "qa_mistakes" in d:
        mistakes_to_scorecard(d, kpis)
    call.qa_score, call.critical_fail = _qa(d["scorecard"], kpis)
    call.metrics = measure(call.turns)

    # customer mood per turn: start mood, then the changes, carried forward over customer turns
    changes = {c["turn"]: c["mood"] for c in d.get("mood_changes", [])}
    mood = d["sentiment"]["mood_start"]
    for t in call.turns:
        if t.idx in changes:
            mood = changes[t.idx]
        t.mood = mood if t.speaker == "customer" else ""

    reasons = []
    if call.transcript_quality is not None and call.transcript_quality < 0.5:
        reasons.append("low transcript confidence")
    if call.compliance_issue:
        reasons.append("compliance issue")
    if second and not second.get("agree", True):
        reasons.append(f"second opinion disagrees ({second.get('resolution')}, {second.get('satisfaction')}/5)")
    if call.critical_fail:
        reasons.append("critical mistake" if mistake_mode(kpis) else "critical KPI failed")
    call.needs_review = bool(reasons) and call.reviewed_at is None
    call.review_reason = "; ".join(reasons)[:200]

    link_customer(db, call, d.get("customer") or {})

    # replace what an earlier analysis of this call created (but keep actions people already worked on)
    db.query(Promise).filter_by(call_id=call.id).delete()
    db.query(Alert).filter_by(call_id=call.id, status="new").delete()
    for a in db.query(Action).filter_by(call_id=call.id, status="suggested", created_by="ai"):
        db.delete(a)
    for p in d.get("promises", []):
        due = (call.started_at + timedelta(days=p["due_in_days"])).date() if p.get("due_in_days") is not None else None
        db.add(Promise(enterprise_id=call.enterprise_id, call_id=call.id, customer_id=call.customer_id,
                       text=p["text"], due_date=due, turn_idx=p.get("turn")))
    for a in d.get("actions", []):
        act = Action(enterprise_id=call.enterprise_id, call_id=call.id, customer_id=call.customer_id,
                     agent_id=call.agent_id, type=a["type"], title=a["title"][:240], reason=a["reason"],
                     priority=a["priority"], draft_message=a.get("draft_message") or "", status="suggested",
                     due_date=(call.started_at + timedelta(days=2 if a["priority"] == "high" else 5)).date())
        act.events.append(ActionEvent(kind="created", detail="suggested by the call analysis"))
        db.add(act)
    for kind, sev, title in _alerts(call, d):
        db.add(Alert(enterprise_id=call.enterprise_id, call_id=call.id, kind=kind, severity=sev, title=title))
    _mark_repeat(db, call)


def _alerts(call: Call, d: dict):
    who = call.customer.name if call.customer and call.customer.name else "A customer"
    if call.mood_end == "angry" or call.satisfaction == 1:
        yield "angry_customer", "high", f"{who} ended the call very unhappy ({d['reason_detail'][:80]})"
    if call.compliance_issue:
        yield "compliance", "high", "Compliance: " + "; ".join(d["risks"]["compliance_issues"])[:200]
    if call.churn_risk == "high":
        yield "churn_risk", "high", f"{who} may leave: {d['resolution']['explanation'][:120]}"
    if call.customer and call.customer.vip and call.resolution != "resolved":
        yield "vip_unresolved", "high", f"VIP customer {who}: issue {call.resolution.replace('_', ' ')}"


def _mark_repeat(db: Session, call: Call):
    """The same customer called within the 14 days before this call, about the same reason or after a call that
    wasn't fully resolved -> a repeat call (first-call resolution failed)."""
    call.repeat_of = None
    if not call.customer_id:
        return
    prevs = (db.query(Call).filter(Call.customer_id == call.customer_id, Call.id != call.id,
                                   Call.started_at < call.started_at,
                                   Call.started_at >= call.started_at - timedelta(days=14))
             .order_by(Call.started_at.desc()).all())
    prev = next((p for p in prevs if (call.reason_code and p.reason_code == call.reason_code)
                 or (p.resolution and p.resolution != "resolved")), None)
    if prev:
        call.repeat_of = prev.id
