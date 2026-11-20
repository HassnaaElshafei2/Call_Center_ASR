"""Customers (Customer 360, at-risk list, merge, audited phone reveal) and agents (performance, coaching)."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import joinedload

from ..deps import Ctx, ctx
from ..models import Action, Agent, Call, CallAnalysis, Customer, Promise, Team
from ..services import llm, phones
from .actions import action_row
from .analytics import kpis
from .common import CallFilters, apply_filters, call_filters, call_row, customer_brief

router = APIRouter(prefix="/api/e/{ent}")
OPEN = ("suggested", "open", "in_progress")


def _risk(calls: list[Call]) -> tuple[str, list[str]]:
    """Customer risk from their latest calls: what a retention team would look at."""
    if not calls:
        return "low", []
    last = calls[0]
    why = []
    if last.resolution != "resolved":
        why.append("last issue " + last.resolution.replace("_", " "))
    if (last.satisfaction or 5) <= 2:
        why.append(f"last call satisfaction {last.satisfaction}/5")
    if last.churn_risk == "high":
        why.append("said things that suggest leaving")
    recent = [x for x in calls if x.started_at >= last.started_at - timedelta(days=14)]
    if len(recent) >= 2 and any(x.repeat_of for x in recent):
        why.append(f"called {len(recent)} times in 2 weeks about the same issue")
    level = "high" if last.churn_risk == "high" or ((last.satisfaction or 5) <= 2 and last.resolution != "resolved") \
        else "medium" if why else "low"
    return level, why


@router.get("/customers")
def customers(risk: str | None = None, name: str | None = None, c: Ctx = Depends(ctx), f: CallFilters = Depends(call_filters)):
    calls = apply_filters(c, c.db.query(Call), f, done_only=True).filter(Call.customer_id.isnot(None)) \
        .options(joinedload(Call.customer)).order_by(Call.started_at.desc()).all()
    by = defaultdict(list)
    for x in calls:
        by[x.customer_id].append(x)
    acts = defaultdict(int)
    for a in c.db.query(Action).filter(Action.customer_id.in_(list(by)), Action.status.in_(OPEN)):
        acts[a.customer_id] += 1
    out = []
    for cid, cs in by.items():
        cu = cs[0].customer
        if name and name.lower() not in (cu.name or "").lower() and name not in (cu.phone_masked or ""):
            continue
        level, why = _risk(cs)
        if risk and level not in risk.split(","):
            continue
        sats = [x.satisfaction for x in cs if x.satisfaction]
        out.append(customer_brief(cu) | {
            "enterprise": cu.enterprise_id, "calls": len(cs), "last_call": cs[0].started_at.isoformat(),
            "last_call_id": cs[0].id, "last_reason": cs[0].reason_code, "last_resolution": cs[0].resolution,
            "satisfaction": round(mean(sats), 1) if sats else None, "last_satisfaction": cs[0].satisfaction,
            "open_actions": acts[cid], "risk": level, "risk_why": why})
    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda r: r["last_call"], reverse=True)          # newest first within each risk level
    out.sort(key=lambda r: order[r["risk"]])
    return {"customers": out[:1000], "total": len(out),
            "at_risk": sum(r["risk"] == "high" for r in out)}


def _customer(c: Ctx, cid: str) -> Customer:
    cu = c.db.get(Customer, cid)
    if not cu or cu.enterprise_id not in c.ents:
        raise HTTPException(404, "Customer not found.")
    return cu


@router.get("/customers/{cid}")
def customer_detail(cid: str, c: Ctx = Depends(ctx)):
    cu = _customer(c, cid)
    calls = apply_filters(c, c.db.query(Call), CallFilters(period="all"), use_window=False) \
        .filter(Call.customer_id == cid).options(joinedload(Call.agent)).order_by(Call.started_at.desc()).all()
    level, why = _risk([x for x in calls if x.status == "done"])
    return customer_brief(cu) | {
        "enterprise": cu.enterprise_id, "notes": cu.notes, "created_at": cu.created_at.isoformat(),
        "risk": level, "risk_why": why, "calls": [call_row(x) for x in calls],
        "satisfaction_trend": [{"date": x.started_at.isoformat(), "satisfaction": x.satisfaction, "call_id": x.id}
                               for x in reversed(calls) if x.satisfaction],
        "actions": [action_row(a) for a in c.db.query(Action).filter_by(customer_id=cid).order_by(Action.created_at.desc())],
        "promises": [{"id": p.id, "text": p.text, "due": p.due_date.isoformat() if p.due_date else None, "status": p.status,
                      "call_id": p.call_id} for p in c.db.query(Promise).filter_by(customer_id=cid)],
        "can_reveal": c.can("reveal_phone", cu.enterprise_id) and bool(cu.phone_full)}


@router.post("/customers/{cid}/reveal-phone")
def reveal_phone(cid: str, c: Ctx = Depends(ctx)):
    cu = _customer(c, cid)
    c.require("reveal_phone", cu.enterprise_id)
    if not cu.phone_full:
        raise HTTPException(404, "No phone number on file.")
    c.audit("reveal_phone", cu.id, "", cu.enterprise_id)
    c.db.commit()
    return {"phone": phones.pretty(cu.phone_full)}


class CustomerPatch(BaseModel):
    name: str | None = None
    vip: bool | None = None
    notes: str | None = None


@router.patch("/customers/{cid}")
def patch_customer(cid: str, body: CustomerPatch, c: Ctx = Depends(ctx)):
    cu = _customer(c, cid)
    c.require("act", cu.enterprise_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(cu, k, v)
    c.audit("customer_change", cu.id, str(body.model_dump(exclude_none=True))[:300], cu.enterprise_id)
    c.db.commit()
    return customer_brief(cu)


class Merge(BaseModel):
    into: str


@router.post("/customers/{cid}/merge")
def merge(cid: str, body: Merge, c: Ctx = Depends(ctx)):
    """Move every call, action and promise of customer `cid` to customer `into` (e.g. a confirmed name match)."""
    src, dst = _customer(c, cid), _customer(c, body.into)
    if src.id == dst.id or src.enterprise_id != dst.enterprise_id:
        raise HTTPException(400, "Choose another customer of the same enterprise.")
    c.require("act", src.enterprise_id)
    for model in (Call, Action, Promise):
        c.db.query(model).filter(model.customer_id == src.id).update({"customer_id": dst.id})
    if not dst.name:
        dst.name = src.name
    if not dst.phone_hash and src.phone_hash:
        dst.phone_hash, dst.phone_masked, dst.phone_full, dst.identified_by = \
            src.phone_hash, src.phone_masked, src.phone_full, src.identified_by
        src.phone_hash = None
    c.audit("customer_merge", dst.id, f"merged {src.id}", src.enterprise_id)
    c.db.delete(src)
    c.db.commit()
    return {"ok": True, "customer": dst.id}


# --------------------------------------------------------------------------------------------- agents
def _kpi_rates(db, calls: list[Call]) -> dict[str, dict]:
    """Pass rate per scorecard KPI, with one failing example each (for coaching)."""
    an = {a.call_id: a for a in db.query(CallAnalysis).filter(CallAnalysis.call_id.in_([x.id for x in calls]))
          .order_by(CallAnalysis.id)}
    rates = defaultdict(lambda: {"pass": 0, "fail": 0, "examples": []})
    for x in calls:
        a = an.get(x.id)
        for r in (a.data.get("scorecard", []) if a else []):
            if r["result"] == "na":
                continue
            rates[r["kpi"]][r["result"]] += 1
            if r["result"] == "fail" and len(rates[r["kpi"]]["examples"]) < 3:
                rates[r["kpi"]]["examples"].append({"call_id": x.id, "turn": r.get("turn"), "note": r["note"]})
    return {k: v | {"rate": round(v["pass"] / (v["pass"] + v["fail"]), 3)} for k, v in rates.items() if v["pass"] + v["fail"]}


@router.get("/agents")
def agents(c: Ctx = Depends(ctx), f: CallFilters = Depends(call_filters)):
    calls = apply_filters(c, c.db.query(Call), f, done_only=True).all()
    by = defaultdict(list)
    for x in calls:
        by[x.agent_id].append(x)
    teams = {t.id: t.name for t in c.db.query(Team).filter(Team.enterprise_id.in_(c.ents))}
    q = c.db.query(Agent).filter(Agent.enterprise_id.in_(c.ents))
    for ent, aid in c.agent_scope.items():
        q = q.filter((Agent.enterprise_id != ent) | (Agent.id == (aid or "-")))
    out = []
    for a in q.order_by(Agent.name):
        cs = by.get(a.id, [])
        k = kpis(cs)
        talk = [x.metrics.get("agent_talk_share") for x in cs if x.metrics and x.metrics.get("agent_talk_share")]
        turned = [x for x in cs if x.mood_start in ("angry", "frustrated", "worried") and x.mood_end in ("calm", "happy")]
        hard = [x for x in cs if x.mood_start in ("angry", "frustrated", "worried")]
        out.append({"id": a.id, "name": a.name, "enterprise": a.enterprise_id, "team": teams.get(a.team_id, ""),
                    "active": a.active, **k, "talk_share": round(mean(talk), 3) if talk else None,
                    "turnaround": round(len(turned) / len(hard), 3) if hard else None})
    team = kpis(calls)
    return {"agents": out, "team": team}


@router.get("/agents/{aid}")
def agent_detail(aid: str, c: Ctx = Depends(ctx), f: CallFilters = Depends(call_filters)):
    a = c.db.get(Agent, aid)
    if not a or a.enterprise_id not in c.ents:
        raise HTTPException(404, "Agent not found.")
    if c.agent_scope.get(a.enterprise_id) not in (None, aid):
        raise HTTPException(403, "Agents see only their own page.")
    f.agent = aid
    calls = apply_filters(c, c.db.query(Call), f, done_only=True).order_by(Call.started_at.desc()).all()
    f.agent = None
    team_calls = [x for x in apply_filters(c, c.db.query(Call), f, done_only=True).all() if x.enterprise_id == a.enterprise_id]
    weekly = defaultdict(list)
    for x in calls:
        weekly[(x.started_at - timedelta(days=x.started_at.weekday())).date().isoformat()].append(x)
    mine, team = _kpi_rates(c.db, calls), _kpi_rates(c.db, team_calls)
    metric = lambda cs, key: (round(mean(v), 3) if (v := [x.metrics.get(key) for x in cs if x.metrics and x.metrics.get(key) is not None]) else None)
    return {"id": a.id, "name": a.name, "enterprise": a.enterprise_id, "kpis": kpis(calls), "team_kpis": kpis(team_calls),
            "trend": [{"week": w, **{k: v for k, v in kpis(cs).items() if k in ("calls", "resolved", "satisfaction", "qa")}}
                      for w, cs in sorted(weekly.items())],
            "scorecard": [{"kpi": k, "rate": v["rate"], "team_rate": team.get(k, {}).get("rate"), "examples": v["examples"]}
                          for k, v in sorted(mine.items(), key=lambda kv: kv[1]["rate"])],
            "behaviour": {k: {"agent": metric(calls, k), "team": metric(team_calls, k)}
                          for k in ("agent_talk_share", "longest_silence_s", "silences_over_5s", "overlaps")},
            "calls": [call_row(x) for x in calls[:50]]}


@router.post("/agents/{aid}/coaching")
def coaching(aid: str, c: Ctx = Depends(ctx), f: CallFilters = Depends(call_filters)):
    """Three coaching points written from the agent's computed numbers and failing examples."""
    d = agent_detail(aid, c, f)
    if not d["kpis"]["calls"]:
        raise HTTPException(400, "No analysed calls in this period.")
    weak = [s for s in d["scorecard"] if s["team_rate"] is not None and s["rate"] < s["team_rate"]][:4]
    facts = {"agent": d["name"], "agent_kpis": d["kpis"], "team_kpis": d["team_kpis"],
             "weakest_scorecard_items": weak, "behaviour": d["behaviour"]}
    out = llm.chat_json([{"role": "system", "content":
                          "You are a call-centre coach. From the facts (JSON) write exactly 3 short coaching points in "
                          "English for the supervisor: each a title (max 8 words) and one sentence on what to do "
                          "differently, citing the numbers given (rates are fractions: 0.42 = 42%). Also one sentence on "
                          "what the agent does well. Use only the given numbers."},
                         {"role": "user", "content": str(facts)}],
                        {"type": "object", "additionalProperties": False, "required": ["strength", "points"],
                         "properties": {"strength": {"type": "string"}, "points": {"type": "array", "maxItems": 3, "items": {
                             "type": "object", "additionalProperties": False, "required": ["title", "detail", "kpi"],
                             "properties": {"title": {"type": "string"}, "detail": {"type": "string"},
                                            "kpi": {"type": ["string", "null"]}}}}}},
                        max_tokens=800)
    ex = {s["kpi"]: s["examples"] for s in d["scorecard"]}
    for p in out.get("points", []):
        p["examples"] = ex.get(p.get("kpi"), [])
    return out | {"generated_at": datetime.now(timezone.utc).isoformat()}
