"""The assistant's tools. They run on the same filters and numbers as the pages, inside the user's enterprise and
role scope. The model only chooses tools and arguments; every figure in an answer comes from a tool result."""
from __future__ import annotations

import difflib
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import joinedload

from ..deps import Ctx
from ..models import ACTION_TYPES, LEVEL, MOOD, RESOLUTION, SENTIMENT, Action, Agent, Call, CallAnalysis, Category
from ..routers.analytics import kpis
from ..routers.common import CallFilters, apply_filters
from ..services import search as semantic

PERIODS = ["today", "7d", "30d", "90d", "365d", "all"]
GROUPS = ["none", "reason", "agent", "day", "week", "resolution", "mood_end", "satisfaction", "enterprise"]


def filter_schema(c: Ctx, cats: list[str]) -> dict:
    p = {
        "period": {"type": "string", "enum": PERIODS, "description": "time window ending now; default 30d"},
        "date_from": {"type": "string", "description": "YYYY-MM-DD, instead of period"},
        "date_to": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
        "agent": {"type": "string", "description": "agent name"},
        "reason": {"type": "array", "items": {"type": "string", "enum": cats}, "description": "call reason codes"},
        "resolution": {"type": "array", "items": {"type": "string", "enum": list(RESOLUTION)}},
        "sentiment": {"type": "array", "items": {"type": "string", "enum": list(SENTIMENT)}},
        "mood_end": {"type": "array", "items": {"type": "string", "enum": list(MOOD)}, "description": "customer mood at the end"},
        "sat_max": {"type": "integer", "minimum": 1, "maximum": 5, "description": "predicted satisfaction at most"},
        "sat_min": {"type": "integer", "minimum": 1, "maximum": 5},
        "churn": {"type": "array", "items": {"type": "string", "enum": list(LEVEL)}},
        "needs_review": {"type": "boolean"}, "compliance_issue": {"type": "boolean"},
        "repeat_call": {"type": "boolean", "description": "customer called again about the same issue within 14 days"},
        "customer_id": {"type": "string"},
        "words": {"type": "string", "description": "exact words in the transcript or summary"},
    }
    if len(c.ents) > 1:
        p["enterprise"] = {"type": "string", "enum": c.ents}
    return {"type": "object", "properties": p}


def definitions(c: Ctx) -> list[dict]:
    cats = [x.code for x in c.db.query(Category).filter(Category.enterprise_id.in_(c.ents))] + ["other"]
    fs = filter_schema(c, sorted(set(cats)))
    fn = lambda name, desc, props, req=(): {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": list(req)}}}
    return [
        fn("count_calls", "Counts and rates for calls matching filters, optionally grouped (resolution rate, "
                          "average predicted satisfaction, negative share, repeat rate, QA score...).",
           {"filters": fs, "group_by": {"type": "string", "enum": GROUPS}}),
        fn("list_calls", "Calls matching filters, with summary, labels, agent and customer.",
           {"filters": fs, "sort": {"type": "string", "enum": ["newest", "lowest_satisfaction", "highest_satisfaction",
                                                                "lowest_qa"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 25}}),
        fn("get_call", "One call in detail: summary, labels with evidence, key moments, promises, actions, transcript.",
           {"call_id": {"type": "string"}}, ["call_id"]),
        fn("search_transcripts", "Find calls by meaning (e.g. 'customer wants to cancel', 'technician didn't come'). "
                                 "Returns the best matching moment per call.",
           {"query": {"type": "string"}, "filters": fs, "limit": {"type": "integer", "minimum": 1, "maximum": 15}},
           ["query"]),
        fn("find_customers", "Customers with their risk (high = unhappy and unresolved, or likely to leave), "
                             "calls, satisfaction, open actions.",
           {"risk": {"type": "array", "items": {"type": "string", "enum": list(LEVEL)}},
            "name": {"type": "string"}, "filters": fs, "limit": {"type": "integer", "minimum": 1, "maximum": 25}}),
        fn("agent_stats", "Per-agent performance (calls, resolution rate, satisfaction, QA) for the filters; "
                          "or one agent by name.", {"agent": {"type": "string"}, "filters": fs}),
        fn("list_actions", "Follow-up actions (callbacks, offers, escalations...) and their status and outcome.",
           {"status": {"type": "array", "items": {"type": "string",
                                                  "enum": ["suggested", "open", "in_progress", "done", "dismissed"]}},
            "type": {"type": "array", "items": {"type": "string", "enum": list(ACTION_TYPES)}},
            "overdue": {"type": "boolean"}}),
        fn("propose_action", "Propose a follow-up for one or more calls. It is NOT created: the user confirms it with "
                             "a button.",
           {"call_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 50},
            "type": {"type": "string", "enum": list(ACTION_TYPES)}, "title": {"type": "string"},
            "reason": {"type": "string"}, "priority": {"type": "string", "enum": list(LEVEL)}},
           ["call_ids", "type", "title"]),
    ]


class Toolbox:
    """Runs tool calls; remembers the filters applied (shown as chips) and the calls mentioned (for citations)."""

    def __init__(self, c: Ctx):
        self.c = c
        self.chips: list[dict] = []
        self.calls: dict[str, dict] = {}
        self.links: list[dict] = []
        self.proposals: list[dict] = []
        self.agents = {a.name: a.id for a in c.db.query(Agent).filter(Agent.enterprise_id.in_(c.ents))}
        self.cat_names = {x.code: x.name for x in c.db.query(Category).filter(Category.enterprise_id.in_(c.ents))}

    # ---------------------------------------------------------------- filters
    def _agent_id(self, name: str | None) -> str | None:
        if not name:
            return None
        if name in self.agents.values():
            return name
        hit = difflib.get_close_matches(name, list(self.agents), n=1, cutoff=0.5) or \
            [n for n in self.agents if name in n or n in name]
        return self.agents[hit[0]] if hit else "-"

    def filters(self, raw: dict | None, label: str = "") -> CallFilters:
        raw = raw or {}
        j = lambda v: ",".join(v) if isinstance(v, list) else v
        f = CallFilters(period=raw.get("period") or ("custom" if raw.get("date_from") or raw.get("date_to") else "30d"),
                        date_from=raw.get("date_from"), date_to=raw.get("date_to"),
                        agent=self._agent_id(raw.get("agent")), reason=j(raw.get("reason")),
                        resolution=j(raw.get("resolution")), sentiment=j(raw.get("sentiment")),
                        mood_end=j(raw.get("mood_end")), sat_max=raw.get("sat_max"), sat_min=raw.get("sat_min"),
                        churn=j(raw.get("churn")), review=raw.get("needs_review"),
                        compliance=raw.get("compliance_issue"), repeat=raw.get("repeat_call"),
                        customer=raw.get("customer_id"), q=raw.get("words"))
        self._ent = raw.get("enterprise") if raw.get("enterprise") in self.c.ents else None
        chips = [{"key": k, "label": self._chip(k, v)} for k, v in f.to_dict().items() if not (k == "period" and v == "30d")]
        if self._ent:
            chips.append({"key": "enterprise", "label": self._ent.upper()})
        self.chips.append({"tool": label, "chips": chips, "filters": f.to_dict(), "enterprise": self._ent})
        return f

    def _chip(self, k, v):
        names = {"7d": "last 7 days", "30d": "last 30 days", "90d": "last 90 days", "today": "today",
                 "365d": "last year", "all": "all time"}
        if k == "period":
            return names.get(v, v)
        if k == "agent":
            return "agent: " + next((n for n, i in self.agents.items() if i == v), "unknown")
        if k == "reason":
            return ", ".join(self.cat_names.get(x, x) for x in v.split(","))
        if k in ("resolution", "sentiment", "mood_end", "churn"):
            return f"{k.replace('_', ' ')}: " + v.replace("_", " ")
        return {"sat_max": f"satisfaction ≤ {v}", "sat_min": f"satisfaction ≥ {v}", "review": "needs review",
                "compliance": "compliance issue", "repeat": "repeat calls", "q": f'"{v}"',
                "date_from": f"from {v}", "date_to": f"to {v}", "customer": "one customer"}.get(k, f"{k}: {v}")

    def _query(self, f: CallFilters):
        q = apply_filters(self.c, self.c.db.query(Call), f, done_only=True)
        return q.filter(Call.enterprise_id == self._ent) if self._ent else q

    def _brief(self, x: Call) -> dict:
        d = {"id": x.id, "enterprise": x.enterprise_id, "date": x.started_at.strftime("%Y-%m-%d %H:%M"),
             "agent": x.agent.name if x.agent else None, "customer": x.customer.name if x.customer else None,
             "reason": self.cat_names.get(x.reason_code, x.reason_code), "resolution": x.resolution,
             "satisfaction": x.satisfaction, "mood_end": x.mood_end, "summary": x.summary}
        self.calls[x.id] = {"id": x.id, "summary": x.summary, "date": d["date"], "customer": d["customer"],
                            "resolution": x.resolution, "satisfaction": x.satisfaction, "mood_end": x.mood_end,
                            "reason": d["reason"], "enterprise": x.enterprise_id}
        return d

    def _link(self, f: CallFilters, label: str, n: int):
        if n:
            self.links.append({"label": label, "page": "calls", "filters": f.to_dict(), "enterprise": self._ent, "count": n})

    # ---------------------------------------------------------------- tools
    def count_calls(self, filters=None, group_by="none"):
        f = self.filters(filters, "count_calls")
        calls = self._query(f).options(joinedload(Call.agent)).all()
        self._link(f, f"Open these {len(calls)} calls", len(calls))
        out = {"total": kpis(calls)}
        if group_by and group_by != "none":
            g = defaultdict(list)
            for x in calls:
                key = {"reason": lambda: self.cat_names.get(x.reason_code, x.reason_code),
                       "agent": lambda: x.agent.name if x.agent else "no agent",
                       "day": lambda: x.started_at.date().isoformat(),
                       "week": lambda: (x.started_at.date().isocalendar()[1]),
                       "resolution": lambda: x.resolution, "mood_end": lambda: x.mood_end,
                       "satisfaction": lambda: x.satisfaction, "enterprise": lambda: x.enterprise_id}[group_by]()
                g[str(key)].append(x)
            out["groups"] = sorted(({"group": k, **kpis(v)} for k, v in g.items()), key=lambda r: -r["calls"])[:30]
        return out

    def list_calls(self, filters=None, sort="newest", limit=10):
        f = self.filters(filters, "list_calls")
        q = self._query(f).options(joinedload(Call.agent), joinedload(Call.customer))
        order = {"newest": Call.started_at.desc(), "lowest_satisfaction": Call.satisfaction.asc(),
                 "highest_satisfaction": Call.satisfaction.desc(), "lowest_qa": Call.qa_score.asc()}[sort or "newest"]
        total = q.count()
        rows = q.order_by(order.nulls_last()).limit(min(limit or 10, 25)).all()
        self._link(f, f"Open all {total} calls", total)
        return {"total": total, "calls": [self._brief(x) for x in rows]}

    def get_call(self, call_id):
        x = apply_filters(self.c, self.c.db.query(Call), CallFilters(period="all"), use_window=False) \
            .filter(Call.id == call_id).first()
        if not x:
            return {"error": "call not found"}
        an = self.c.db.query(CallAnalysis).filter_by(call_id=x.id).order_by(CallAnalysis.id.desc()).first()
        d = an.data if an else {}
        turns = [f"[{t.idx}] {t.speaker}: {t.text}" for t in x.turns][:80]
        return self._brief(x) | {
            "resolution_why": d.get("resolution", {}).get("explanation"),
            "satisfaction_signals": d.get("satisfaction", {}).get("signals"), "moments": d.get("moments"),
            "promises": d.get("promises"), "risks": d.get("risks"), "recommended_actions": d.get("actions"),
            "qa_score": x.qa_score, "transcript": "\n".join(turns)[:7000]}

    def search_transcripts(self, query, filters=None, limit=8):
        f = self.filters(filters, "search_transcripts")
        ids = {r[0] for r in self._query(f).with_entities(Call.id)}
        hits = semantic.search(self.c.db, [self._ent] if self._ent else self.c.ents, query, limit=min(limit or 8, 15),
                               call_ids=ids)
        calls = {x.id: x for x in self.c.db.query(Call).options(joinedload(Call.agent), joinedload(Call.customer))
                 .filter(Call.id.in_([h["call_id"] for h in hits]))}
        return {"matches": [self._brief(calls[h["call_id"]]) | {"moment": f"[{h['turn']}] {h['speaker']}: {h['text']}",
                                                               "match": h["score"]} for h in hits if h["call_id"] in calls]}

    def find_customers(self, risk=None, name=None, filters=None, limit=10):
        from ..routers.people import customers
        f = self.filters(filters, "find_customers")
        res = customers(risk=",".join(risk) if risk else None, name=name, c=self.c, f=f)
        rows = res["customers"][: min(limit or 10, 25)]
        if rows:
            self.links.append({"label": "Open customers", "page": "customers",
                               "filters": {"risk": ",".join(risk)} if risk else {}, "count": res["total"]})
        return {"total": res["total"], "customers": [{k: r[k] for k in ("id", "name", "calls", "last_call",
                "last_resolution", "last_satisfaction", "risk", "risk_why", "open_actions", "last_call_id")} for r in rows]}

    def agent_stats(self, agent=None, filters=None):
        from ..routers.people import agents
        f = self.filters(filters, "agent_stats")
        res = agents(c=self.c, f=f)
        rows = [r for r in res["agents"] if r["calls"]]
        if agent:
            aid = self._agent_id(agent)
            rows = [r for r in rows if r["id"] == aid]
        keep = ("name", "enterprise", "calls", "resolved", "not_resolved", "satisfaction", "qa", "negative", "turnaround")
        return {"team": res["team"], "agents": [{k: r.get(k) for k in keep} for r in rows]}

    def list_actions(self, status=None, type=None, overdue=None):
        q = self.c.db.query(Action).filter(Action.enterprise_id.in_(self.c.ents))
        if status:
            q = q.filter(Action.status.in_(status))
        if type:
            q = q.filter(Action.type.in_(type))
        rows = q.order_by(Action.created_at.desc()).limit(200).all()
        if overdue:
            rows = [a for a in rows if a.due_date and a.due_date < date.today() and a.status in ("suggested", "open", "in_progress")]
        self.links.append({"label": "Open the Action Center", "page": "actions", "filters": {}, "count": len(rows)})
        return {"total": len(rows), "actions": [{"title": a.title, "type": a.type, "status": a.status,
                                                 "priority": a.priority, "due": str(a.due_date) if a.due_date else None,
                                                 "outcome": a.outcome, "call_id": a.call_id} for a in rows[:25]]}

    def propose_action(self, call_ids, type, title, reason="", priority="medium"):
        ok = [r[0] for r in apply_filters(self.c, self.c.db.query(Call.id), CallFilters(period="all"),
                                          use_window=False).filter(Call.id.in_(call_ids))]
        p = {"call_ids": ok, "type": type, "title": title, "reason": reason, "priority": priority}
        self.proposals.append(p)
        return {"proposed": True, "calls": len(ok), "note": "shown to the user with a confirm button; not created yet"}

    def run(self, name: str, args: dict):
        fn = getattr(self, name, None)
        if not fn or name.startswith("_") or name in ("run", "filters"):
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}
