"""Overview numbers, charts and the "What we see" insights. Everything here is computed from the data;
the insight sentences are templates filled with computed facts, so no figure is ever invented."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import joinedload

from ..deps import Ctx, ctx
from ..models import Action, Agent, Call, Category, Enterprise, Promise
from .common import CallFilters, apply_filters, call_filters, scope, window

router = APIRouter(prefix="/api/e/{ent}")
CAIRO = ZoneInfo("Africa/Cairo")
NEGATIVE_MOODS = {"angry", "frustrated"}


def _calls(c: Ctx, f: CallFilters, start=None, end=None, use_window=True):
    q = apply_filters(c, c.db.query(Call), f, done_only=True, use_window=use_window)
    if start:
        q = q.filter(Call.started_at >= start)
    if end:
        q = q.filter(Call.started_at < end)
    return q.options(joinedload(Call.agent), joinedload(Call.customer)).all()


def kpis(calls: list[Call]) -> dict:
    n = len(calls)
    sats = [x.satisfaction for x in calls if x.satisfaction]
    res = Counter(x.resolution for x in calls)
    pct = lambda k: round(res[k] / n, 4) if n else None
    return {
        "calls": n,
        "resolved": pct("resolved"), "partly_resolved": pct("partly_resolved"), "not_resolved": pct("not_resolved"),
        "satisfaction": round(mean(sats), 2) if sats else None,
        "negative": round(sum(x.mood_end in NEGATIVE_MOODS or x.sentiment == "negative" for x in calls) / n, 4) if n else None,
        "avg_duration_s": round(mean(x.duration_s for x in calls)) if n else None,
        "repeat": round(sum(bool(x.repeat_of) for x in calls) / n, 4) if n else None,
        "qa": round(mean(q), 1) if (q := [x.qa_score for x in calls if x.qa_score is not None]) else None,
        "needs_review": sum(x.needs_review for x in calls),
        "compliance": sum(x.compliance_issue for x in calls),
        "churn_high": sum(x.churn_risk == "high" for x in calls),
    }


@router.get("/overview")
def overview(c: Ctx = Depends(ctx), f: CallFilters = Depends(call_filters)):
    calls = _calls(c, f)
    start, end = window(f)
    prev = []
    if start:
        span = (end or datetime.now(timezone.utc)) - start
        prev = _calls(c, f, start - span, start, use_window=False)
    cats = {(x.enterprise_id, x.code): x.name for x in c.db.query(Category).filter(Category.enterprise_id.in_(c.ents))}
    name = lambda call: cats.get((call.enterprise_id, call.reason_code), call.reason_code.replace("_", " ").title())

    # trend per day (Cairo time)
    day = defaultdict(list)
    for x in calls:
        day[x.started_at.astimezone(CAIRO).date()].append(x)
    trend = []
    if calls:
        d0, d1 = min(day), max(day)
        d = d0
        while d <= d1:
            k = kpis(day.get(d, []))
            trend.append({"date": d.isoformat(), "calls": k["calls"], "resolved": k["resolved"],
                          "satisfaction": k["satisfaction"], "negative": k["negative"]})
            d += timedelta(days=1)

    by_reason = defaultdict(list)
    for x in calls:
        by_reason[(x.reason_code, name(x))].append(x)
    reasons = sorted(({"code": code, "name": nm, **{k: v for k, v in kpis(v).items()
                                                     if k in ("calls", "resolved", "not_resolved", "satisfaction", "repeat")}}
                      for (code, nm), v in by_reason.items()), key=lambda r: -r["calls"])

    heat = [[0] * 24 for _ in range(7)]
    for x in calls:
        t = x.started_at.astimezone(CAIRO)
        heat[(t.weekday() + 2) % 7][t.hour] += 1          # rows start on Saturday (Egyptian week)

    flow = Counter((x.mood_start, x.mood_end) for x in calls if x.mood_start and x.mood_end)
    by_agent = defaultdict(list)
    for x in calls:
        if x.agent:
            by_agent[(x.agent.id, x.agent.name, x.enterprise_id)].append(x)
    agents = sorted(({"id": a, "name": nm, "enterprise": e, **kpis(v)} for (a, nm, e), v in by_agent.items()),
                    key=lambda r: (-(r["resolved"] or 0), -(r["satisfaction"] or 0)))
    by_ent = []
    if len(c.ents) > 1:
        for e in c.db.query(Enterprise).filter(Enterprise.id.in_(c.ents)):
            by_ent.append({"id": e.id, "name": e.name, "accent": e.accent,
                           **kpis([x for x in calls if x.enterprise_id == e.id])})

    today = date.today()
    open_actions = scope(c, c.db.query(Action).join(Call, Action.call_id == Call.id)) \
        .filter(Action.status.in_(["suggested", "open", "in_progress"])).count()
    promises_due = scope(c, c.db.query(Promise).join(Call, Promise.call_id == Call.id)) \
        .filter(Promise.status == "open", Promise.due_date <= today).count()
    recovered = scope(c, c.db.query(Action).join(Call, Action.call_id == Call.id)) \
        .filter(Action.outcome.in_(["recovered", "offer_accepted", "resolved_later"])).count()
    return {
        "kpis": kpis(calls), "previous": kpis(prev) if prev else None,
        "trend": trend, "reasons": reasons,
        "resolution": Counter(x.resolution for x in calls),
        "satisfaction_dist": [sum(x.satisfaction == s for x in calls) for s in range(1, 6)],
        "mood_flow": [{"from": a, "to": b, "calls": n} for (a, b), n in flow.most_common()],
        "heatmap": heat, "agents": agents, "enterprises": by_ent,
        "work": {"open_actions": open_actions, "promises_due": promises_due, "recovered": recovered},
        "insights": insights(calls, prev, reasons, agents, open_actions, promises_due),
    }


def _pct(v):
    return f"{round(100 * v)}%"


def insights(calls, prev, reasons, agents, open_actions, promises_due) -> list[dict]:
    """Facts worth a manager's attention, most important first. Each carries the filter that shows its calls."""
    out = []
    n = len(calls)
    if not n:
        return out
    k, p = kpis(calls), kpis(prev) if prev else None
    big = [r for r in reasons if r["calls"] >= max(3, n * 0.05)]
    if big:
        worst = max(big, key=lambda r: r["not_resolved"] or 0)
        if worst["not_resolved"]:
            out.append({"severity": "high" if worst["not_resolved"] >= 0.4 else "medium",
                        "text": f"**{_pct(worst['not_resolved'])}** of **{worst['name']}** calls were not resolved, "
                                f"the highest of any frequent reason ({worst['calls']} calls).",
                        "filter": {"reason": worst["code"], "resolution": "not_resolved"}})
    unhappy = [x for x in calls if (x.satisfaction or 5) <= 2]
    if unhappy:
        out.append({"severity": "high" if len(unhappy) / n > 0.15 else "medium",
                    "text": f"**{len(unhappy)}** customers ended the call unhappy (satisfaction 1–2 of 5).",
                    "filter": {"sat_max": 2}})
    if p and p["satisfaction"] and k["satisfaction"]:
        d = k["satisfaction"] - p["satisfaction"]
        if abs(d) >= 0.2:
            out.append({"severity": "medium" if d < 0 else "good",
                        "text": f"Average satisfaction {'fell' if d < 0 else 'rose'} from **{p['satisfaction']:.1f}** to "
                                f"**{k['satisfaction']:.1f}** compared with the previous period.", "filter": {}})
    rep = [x for x in calls if x.repeat_of]
    if rep:
        out.append({"severity": "medium",
                    "text": f"**{len(rep)}** calls were repeat calls: the same customer calling again about the same "
                            f"issue within 14 days.", "filter": {"repeat": True}})
    ag = [a for a in agents if a["calls"] >= 3]
    if len(ag) >= 3 and k["resolved"]:
        best = ag[0]
        if best["resolved"] and best["resolved"] - k["resolved"] >= 0.1:
            out.append({"severity": "good",
                        "text": f"**{best['name']}** resolves **{_pct(best['resolved'])}** of calls, against "
                                f"**{_pct(k['resolved'])}** overall: a model for coaching.", "filter": {"agent": best["id"]}})
    if k["compliance"]:
        out.append({"severity": "high", "text": f"**{k['compliance']}** calls have a possible compliance issue.",
                    "filter": {"compliance": True}})
    if promises_due:
        out.append({"severity": "medium", "text": f"**{promises_due}** promises made to customers are due or overdue.",
                    "filter": {}, "link": "actions?tab=promises"})
    if open_actions:
        out.append({"severity": "info", "text": f"**{open_actions}** follow-up actions are waiting.", "filter": {},
                    "link": "actions"})
    return out[:6]
