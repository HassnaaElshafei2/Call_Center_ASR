"""Facts worked out from the analysed calls, shared by the Home page, the Overview's insight cards and the Ask Sia
suggestions, so the three always agree. Everything here is counted, not generated: the language model is not called."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from ..deps import Ctx
from ..models import Action, Agent, Call, CallAnalysis, Category, Customer, Enterprise, Promise, Scorecard
from ..routers.common import scope

UNHAPPY = ("angry", "frustrated")
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar(s: str) -> str:
    return s.translate(AR_DIGITS)


def ar_count(n: int, one: str, two: str, few: str, many: str) -> str:
    """Arabic counting: 1 and 2 have their own forms, 3-10 take the plural, 11+ the singular."""
    if n == 1:
        return one
    if n == 2:
        return two
    return ar(f"{n} {few if 3 <= n <= 10 else many}")


def _done_calls(c: Ctx, days: int):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return scope(c, c.db.query(Call)).filter(Call.status == "done", Call.started_at >= since)


def _cats(c: Ctx) -> dict[tuple[str, str], Category]:
    return {(x.enterprise_id, x.code): x for x in c.db.query(Category).filter(Category.enterprise_id.in_(c.ents))}


def short(text: str | None, n: int = 170) -> str:
    """Cut at a word boundary, with an ellipsis."""
    text = (text or "").strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _who(call: Call) -> str:
    return (call.customer.name if call.customer and call.customer.name else "") or "A customer"


def followup_state(c: Ctx, call: Call) -> str:
    """What happened after a call: "done" (a follow-up was completed), "planned" (one is open or in progress),
    or "none" (nothing, or only a suggestion nobody accepted)."""
    q = c.db.query(Action.status).filter(Action.created_at >= call.started_at,
                                         (Action.customer_id == call.customer_id) if call.customer_id else (Action.call_id == call.id))
    states = {s for (s,) in q}
    return "done" if "done" in states else "planned" if states & {"open", "in_progress"} else "none"


def unhappy_calls(c: Ctx, days: int = 30) -> list[tuple[Call, str]]:
    """Each customer's latest unhappy call (very low satisfaction or an angry/frustrated ending) with its follow-up state."""
    calls = _done_calls(c, days).filter((Call.mood_end.in_(UNHAPPY)) | (Call.satisfaction <= 2)).order_by(Call.started_at.desc()).all()
    seen, out = set(), []
    for call in calls:
        key = call.customer_id or call.id
        if key not in seen:
            seen.add(key)
            out.append((call, followup_state(c, call)))
    return out


def unhappy_without_callback(c: Ctx, days: int = 30) -> list[Call]:
    """Unhappy customers with no follow-up accepted after their call (a merely suggested action doesn't count)."""
    return [call for call, state in unhappy_calls(c, days) if state == "none"]


def weakest_reason(c: Ctx, days: int = 30) -> dict | None:
    """The call reason that most often ends partly or not resolved (at least 3 calls)."""
    cats = _cats(c)
    agg: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for call in _done_calls(c, days).filter(Call.reason_code.isnot(None)):
        a = agg[(call.enterprise_id, call.reason_code)]
        a[0] += 1
        a[1] += call.resolution != "resolved"
    best = max(((k, v) for k, v in agg.items() if v[0] >= 3 and v[1] >= 2), key=lambda kv: (kv[1][1] / kv[1][0], kv[1][1]), default=None)
    if not best:
        return None
    (ent, code), (n, bad) = best
    cat = cats.get((ent, code))
    e = c.db.get(Enterprise, ent)
    return {"enterprise": ent, "enterprise_name": e.name if e else ent, "enterprise_ar": (e.name_ar if e else "") or ent,
            "code": code, "name": cat.name if cat else code, "name_ar": (cat.name_ar if cat else "") or (cat.name if cat else code),
            "calls": n, "unresolved": bad}


def strongest_reason(c: Ctx, days: int = 14) -> dict | None:
    """A reason with at least 3 calls that were all fully resolved, the best predicted satisfaction first."""
    cats = _cats(c)
    agg: dict[tuple[str, str], list] = defaultdict(list)
    for call in _done_calls(c, days).filter(Call.reason_code.isnot(None)):
        agg[(call.enterprise_id, call.reason_code)].append(call)
    good = [(k, v) for k, v in agg.items() if len(v) >= 3 and all(x.resolution == "resolved" for x in v)]
    if not good:
        return None
    (ent, code), calls = max(good, key=lambda kv: (sum(x.satisfaction or 0 for x in kv[1]) / len(kv[1]), len(kv[1])))
    cat = cats.get((ent, code))
    e = c.db.get(Enterprise, ent)
    sat = sum(x.satisfaction or 0 for x in calls) / len(calls)
    return {"enterprise": ent, "enterprise_name": e.name if e else ent, "code": code, "name": cat.name if cat else code,
            "calls": len(calls), "satisfaction": round(sat, 1), "latest": max(x.started_at for x in calls).isoformat()}


def coaching_need(c: Ctx, days: int = 30) -> dict | None:
    """The agent who most often misses one QA item (at least 3 misses, in at least half of their calls)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (scope(c, c.db.query(CallAnalysis, Call).join(Call, Call.id == CallAnalysis.call_id))
            .filter(Call.started_at >= since, Call.agent_id.isnot(None)).order_by(CallAnalysis.id).all())
    latest = {call.id: (an, call) for an, call in rows}                 # the newest analysis of each call
    fails: Counter = Counter()
    calls_of: Counter = Counter()
    for an, call in latest.values():
        calls_of[call.agent_id] += 1
        for item in (an.data or {}).get("scorecard", []):
            if item.get("result") == "fail":
                fails[(call.agent_id, call.enterprise_id, item.get("kpi"))] += 1
    cand = [(k, n) for k, n in fails.items() if n >= 3 and n / calls_of[k[0]] >= .5]
    if not cand:
        return None
    (agent_id, ent, kpi), n = max(cand, key=lambda kv: kv[1])
    agent = c.db.get(Agent, agent_id)
    card = c.db.query(Scorecard).filter_by(enterprise_id=ent, active=True).order_by(Scorecard.version.desc()).first()
    name = next((k["name"] for k in (card.kpis if card else []) if k["code"] == kpi), kpi)
    return {"agent_id": agent_id, "agent": agent.name if agent else "An agent", "item": name, "fails": n, "calls": calls_of[agent_id]}


def promises_due(c: Ctx, days_ahead: int = 7) -> list[Promise]:
    return (c.db.query(Promise).filter(Promise.enterprise_id.in_(c.ents), Promise.status == "open", Promise.due_date.isnot(None),
                                       Promise.due_date <= date.today() + timedelta(days=days_ahead))
            .order_by(Promise.due_date).all())


def review_count(c: Ctx) -> int:
    return scope(c, c.db.query(Call)).filter(Call.needs_review.is_(True)).count()


# --------------------------------------------------------------------------------------------- Ask Sia suggestions
def suggestions(c: Ctx, lang: str = "en") -> list[dict]:
    """Three questions picked from this user's data, each with the reason it is suggested."""
    out = []
    w = weakest_reason(c)
    if w:
        out.append({"icon": "tools", "tone": "warn", "topic": "calls",
                    "en": (f"Why do {w['enterprise_name']} {w['name'].lower()} calls stay unresolved?",
                           f"{w['unresolved']} of {w['calls']} were not fully resolved in the last 30 days"),
                    "ar": (f"ليه مكالمات {w['name_ar']} في {w['enterprise_ar']} مش بتتحل كلها؟",
                           ar(f"{w['unresolved']} من {w['calls']} متحلوش بالكامل آخر 30 يوم"))})
    u = unhappy_without_callback(c)
    if u:
        out.append({"icon": "unhappy", "tone": "bad", "topic": "customers",
                    "en": ("Which unhappy customers have no callback yet?", f"{len(u)} customers ended unhappy with no follow-up"),
                    "ar": ("مين العملاء الزعلانين اللي محدش كلمهم لسه؟",
                           ar_count(len(u), "عميل واحد خلص المكالمة متضايق", "عميلين خلصوا المكالمة متضايقين", "عملاء", "عميل")
                           + ("" if len(u) <= 2 else " خلصوا المكالمة متضايقين") + " ومن غير متابعة")})
    agents = scope(c, c.db.query(Call.agent_id)).filter(Call.agent_id.isnot(None)).distinct().count()
    out.append({"icon": "team", "tone": "info", "topic": "agents",
                "en": ("Who resolves the most issues this month?", f"Compare {agents} agents" + (" across both enterprises" if len(c.ents) > 1 else "")),
                "ar": ("مين أكتر موظف بيحل المشاكل الشهر ده؟", "مقارنة " + ar_count(agents, "موظف واحد", "موظفين اتنين", "موظفين", "موظف")
                       + (" في الشركتين" if len(c.ents) > 1 else ""))})
    if len(out) < 3:
        out.append({"icon": "report", "tone": "brand", "topic": "reports",
                    "en": ("What changed this week compared with last week?", "Calls, resolution and satisfaction"),
                    "ar": ("إيه اللي اتغير الأسبوع ده عن اللي قبله؟", "المكالمات والحل ورضا العملاء")})
    return [{"icon": s["icon"], "tone": s["tone"], "topic": s["topic"], "q": s[lang][0], "why": s[lang][1]} for s in out[:3]]


TOPICS = {
    "en": {"calls": ["Which calls this week were not resolved, and why?", "Show calls where the customer asked to cancel",
                     "Find calls where the technician did not show up", "Which calls had a compliance issue?"],
           "customers": ["Which customers are at risk of leaving?", "Which customers called more than once about the same issue?",
                         "Propose callbacks for unhappy customers"],
           "agents": ["Compare agents by resolution rate this month", "Which agents need coaching, and on what?",
                      "Who has the best predicted satisfaction?"],
           "reports": ["What are the top reasons for low satisfaction?", "Summarise this week for management",
                       "How did satisfaction change over the last 30 days?"]},
    "ar": {"calls": ["إيه المكالمات اللي متحلتش الأسبوع ده وليه؟", "وريني المكالمات اللي العميل طلب فيها يلغي",
                     "لاقيلي المكالمات اللي الفني مجاش فيها", "فيه مكالمات فيها مشكلة امتثال؟"],
           "customers": ["مين العملاء اللي ممكن يسيبونا؟", "مين العملاء اللي اتصلوا أكتر من مرة على نفس المشكلة؟",
                         "اقترح مكالمات متابعة للعملاء الزعلانين"],
           "agents": ["قارن الموظفين في نسبة الحل الشهر ده", "مين الموظفين اللي محتاجين تدريب وفي إيه؟",
                      "مين أعلى موظف في رضا العملاء المتوقع؟"],
           "reports": ["إيه أكتر أسباب قلة رضا العملاء؟", "لخص الأسبوع ده للإدارة", "رضا العملاء اتغير إزاي آخر 30 يوم؟"]},
}


# --------------------------------------------------------------------------------------------- Home
def home(c: Ctx) -> dict:
    now = datetime.now(timezone.utc)
    window_days, label = 1, "since yesterday"
    if _done_calls(c, 1).count() < 3:
        window_days, label = 7, "this week"
    recent = _done_calls(c, window_days)
    n_new = recent.count()
    cats = _cats(c)

    def reason_name(call: Call) -> str:
        x = cats.get((call.enterprise_id, call.reason_code or ""))
        return x.name.lower() if x else "the same issue"

    events = []
    for call in recent.filter(Call.repeat_of.isnot(None)).order_by(Call.started_at.desc()).limit(3):
        mood = f" and ended {call.mood_end}" if call.mood_end in UNHAPPY or call.mood_end == "worried" else ""
        events.append({"tone": "bad", "kind": "repeat", "at": call.started_at.isoformat(), "call_id": call.id,
                       "enterprise": call.enterprise_id, "customer_id": call.customer_id,
                       "title": f"{_who(call)} called again about {reason_name(call)}",
                       "body": short(f"A repeat call within 14 days{mood}. {call.summary}"),
                       "tags": ["Repeat call"], "primary": "callback", "followup": followup_state(c, call)})
    for call in recent.filter(Call.mood_end.in_(UNHAPPY), Call.repeat_of.is_(None)).order_by(Call.started_at.desc()).limit(2):
        events.append({"tone": "bad", "kind": "unhappy", "at": call.started_at.isoformat(), "call_id": call.id,
                       "enterprise": call.enterprise_id, "customer_id": call.customer_id,
                       "title": f"{_who(call)} ended the call {call.mood_end}", "body": short(call.summary),
                       "tags": [call.mood_end.capitalize()], "primary": "callback", "followup": followup_state(c, call)})
    for p in promises_due(c, 1)[:2]:
        cust = c.db.get(Customer, p.customer_id) if p.customer_id else None
        when = "today" if p.due_date <= date.today() else "tomorrow"
        events.append({"tone": "warn", "kind": "promise", "at": datetime.combine(p.due_date, datetime.min.time(), timezone.utc).isoformat(),
                       "call_id": p.call_id, "enterprise": p.enterprise_id,
                       "title": f"A promise is due {when}" if p.due_date >= date.today() else "A promise is overdue",
                       "body": f"“{p.text}”" + (f" to {cust.name}" if cust and cust.name else ""), "tags": ["Promise"]})
    s = strongest_reason(c)
    if s:
        events.append({"tone": "good", "kind": "positive", "at": s["latest"], "enterprise": s["enterprise"],
                       "title": f"{s['enterprise_name']} resolved every {s['name'].lower()} call",
                       "body": f"{s['calls']} of {s['calls']} were resolved during the call, predicted satisfaction {s['satisfaction']}.",
                       "tags": ["Going well"], "link": {"reason": s["code"]}})
    rc = review_count(c)
    if rc:
        events.append({"tone": "info", "kind": "review", "at": now.isoformat(), "title": f"{rc} analys{'is waits' if rc == 1 else 'es wait'} for your review",
                       "body": "The second opinion disagreed, or the call needs a human check.", "tags": ["Review"]})
    events.sort(key=lambda e: e["at"], reverse=True)

    unhappy = [(call, st) for call, st in unhappy_calls(c) if st != "done"]       # until they are actually called back
    unplanned = sum(st == "none" for _, st in unhappy)
    due = promises_due(c, 7)
    coach = coaching_need(c)
    needs = [n for n in [
        {"kind": "callbacks", "count": len(unhappy), "unplanned": unplanned, "title": "Call back unhappy customers",
         "sub": (f"{unplanned} not planned yet · {len(unhappy) - unplanned} planned in the Action Center" if unplanned and unplanned < len(unhappy)
                 else "Planned in the Action Center, waiting to be done" if not unplanned
                 else "Ask Sia can draft the messages in Egyptian Arabic")} if unhappy else None,
        {"kind": "promises", "count": len(due), "title": "Keep promises due this week", "sub": "Technician visits, refunds, callbacks"} if due else None,
        {"kind": "review", "count": rc, "title": "Review analyses", "sub": "The analysis needs a human check"} if rc else None,
        {"kind": "coaching", "count": None, "agent_id": coach["agent_id"], "title": f"Coach {coach['agent']} on {coach['item'].lower()}",
         "sub": f"Missed in {coach['fails']} of their last {coach['calls']} calls"} if coach else None,
    ] if n]
    return {"window": label, "new_calls": n_new, "events": events[:5], "needs": needs,
            "attention": sum(1 for n in needs if n["kind"] != "coaching")}


# --------------------------------------------------------------------------------------------- Overview: Sia AI's read
def read(c: Ctx, days: int = 30) -> list[dict]:
    """Up to three insight cards (guidelines: Attention / Positive, a bold lead, a body and one action)."""
    cards = []
    w = weakest_reason(c, days)
    if w:
        cards.append({"kind": "attention", "lead": f"{w['enterprise_name']} {w['name'].lower()} calls are often left open.",
                      "body": f"{w['unresolved']} of {w['calls']} ended partly or not resolved, so these customers are still waiting.",
                      "action": {"label": f"See the {w['unresolved']} calls", "enterprise": w["enterprise"],
                                 "filters": {"reason": w["code"], "resolution": "partly_resolved,not_resolved"}}})
    u = unhappy_without_callback(c, days)
    if u:
        names = [n for n in dict.fromkeys(_who(x) for x in u) if n != "A customer"][:2]
        cards.append({"kind": "attention", "lead": f"{len(u)} unhappy customer{'s have' if len(u) > 1 else ' has'} no callback yet.",
                      "body": ("They ended the call frustrated or angry and nobody has followed up"
                               + (f", including {' and '.join(names)}." if names else ".")),
                      "action": {"label": "Plan callbacks", "primary": True,
                                 "ask": "Which unhappy customers have no callback yet? Propose callbacks for them."}})
    s = strongest_reason(c, min(days, 30))
    if s:
        cards.append({"kind": "positive", "lead": f"{s['enterprise_name']} resolves {s['name'].lower()} calls on the spot.",
                      "body": f"{s['calls']} of {s['calls']} were fully resolved during the call, predicted satisfaction {s['satisfaction']}.",
                      "action": {"label": "See what works", "enterprise": s["enterprise"], "filters": {"reason": s["code"], "resolution": "resolved"}}})
    if len(cards) < 3:
        rep = _done_calls(c, days).filter(Call.repeat_of.isnot(None)).count()
        if rep:
            cards.append({"kind": "attention", "lead": f"{rep} customer{'s' if rep > 1 else ''} had to call again.",
                          "body": "The same customer called within 14 days about the same or an unfinished issue.",
                          "action": {"label": "See repeat calls", "filters": {"repeat": "true"}}})
    if len(cards) < 3:
        comp = _done_calls(c, days).filter(Call.compliance_issue.is_(True)).count()
        if comp:
            cards.append({"kind": "attention", "lead": f"{comp} call{'s' if comp > 1 else ''} may have a compliance issue.",
                          "body": "Check what was said before the customer escalates or regulators ask.",
                          "action": {"label": "Review them", "filters": {"compliance": "true"}}})
    if not any(x["action"].get("primary") for x in cards) and cards:
        cards[0]["action"]["primary"] = True                       # one primary button per area
    return cards[:3]
