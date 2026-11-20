"""Ask: the assistant. Streams progress (the tools it runs, the filters it applied) and then the answer, with
links to the calls it cites and any proposed actions for the user to confirm."""
import json
import re
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..assistant.tools import Toolbox, definitions
from ..db import session_scope
from ..deps import Ctx, ctx
from ..models import Agent, Category, Enterprise
from ..services import llm

router = APIRouter(prefix="/api/e/{ent}")
MAX_ROUNDS = 6
LABELS = {"count_calls": "Counting calls", "list_calls": "Finding calls", "get_call": "Reading the call",
          "search_transcripts": "Searching what was said in calls", "find_customers": "Looking at customers",
          "agent_stats": "Comparing agents", "list_actions": "Checking follow-up actions",
          "propose_action": "Preparing an action for you to confirm"}

SYSTEM = """You are Ask, the assistant of a customer-service call analysis platform for {companies}.
Today is {today}. Users are call-centre managers, QA, retention staff and agents.

How to answer:
- Get every number, name and call from the tools. Never estimate or invent figures; if the tools don't cover a
  question, say so plainly.
- Reply in the user's language: Egyptian Arabic if they write Arabic, otherwise English. Be short and concrete:
  lead with the answer, then 2-5 bullets. Use **bold** for key numbers.
- Refer to a specific call as [call:ID] (the id from the tools) so the app turns it into a link; at most 5 per answer.
- Satisfaction is predicted from the conversation (1-5), not a survey; resolution is resolved / partly resolved /
  not resolved. Say "predicted" when it matters.
- To suggest follow-ups (callbacks, offers...), use propose_action; the user confirms it. Never say an action was done.
- Periods are always in the past: the default is the last 30 days ("آخر 30 يوم"), unless the user says otherwise.
- If a count is zero, say so plainly and offer to look at a longer period or a related measure (e.g. partly
  resolved calls). In Arabic, write natural Egyptian Arabic: call the agent «الموظف» / «الموظفة» (or by name) and the
  customer «العميل» / «العميلة»; keep the wording plain and respectful.

Call reasons: {categories}
Agents: {agents}
{screen}"""


class Msg(BaseModel):
    role: str
    content: str


class AskBody(BaseModel):
    messages: list[Msg]
    screen: dict | None = None      # what the user is looking at: page, filters, call_id, customer_id, agent_id, title


def system_prompt(c: Ctx, screen: dict | None) -> str:
    ents = c.db.query(Enterprise).filter(Enterprise.id.in_(c.ents)).all()
    cats = c.db.query(Category).filter(Category.enterprise_id.in_(c.ents), Category.active.is_(True)).all()
    agents = c.db.query(Agent).filter(Agent.enterprise_id.in_(c.ents)).order_by(Agent.name).all()
    scr = ""
    if screen:
        scr = ("The user is looking at: " + json.dumps(screen, ensure_ascii=False)[:1500] +
               "\nWords like 'this call', 'this customer', 'these calls' or 'this agent' refer to it.")
    return SYSTEM.format(companies=", ".join(f"{e.name} ({e.kind}, id {e.id})" for e in ents), today=date.today(),
                         categories="; ".join(f"{x.code} = {x.name} ({x.enterprise_id})" for x in cats),
                         agents=", ".join(f"{a.name} ({a.enterprise_id})" for a in agents)[:2000], screen=scr)


def _event(kind: str, **data) -> str:
    return "data: " + json.dumps({"type": kind, **data}, ensure_ascii=False, default=str) + "\n\n"


def run(c: Ctx, body: AskBody):
    tb = Toolbox(c)
    msgs = [{"role": "system", "content": system_prompt(c, body.screen)}]
    msgs += [{"role": m.role, "content": m.content[:4000]} for m in body.messages[-12:] if m.role in ("user", "assistant")]
    tools = definitions(c)
    try:
        for _ in range(MAX_ROUNDS):
            reply = llm.chat(msgs, tools=tools, max_tokens=1500, temperature=0.1, timeout=120)
            calls = reply.get("tool_calls") or []
            if not calls:
                text = (reply.get("content") or "").strip()
                cited = [i for i in dict.fromkeys(re.findall(r"\[call:([0-9a-f]{32})\]", text))]
                yield _event("answer", text=text, calls=[tb.calls[i] for i in cited if i in tb.calls],
                             links=tb.links[-3:], proposals=tb.proposals, chips=tb.chips[-1:] if tb.chips else [])
                return
            msgs.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
            for tc in calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield _event("step", tool=name, label=LABELS.get(name, name))
                result = tb.run(name, args)
                if tb.chips and tb.chips[-1]["tool"] == name:
                    yield _event("chips", chips=tb.chips[-1]["chips"])
                msgs.append({"role": "tool", "tool_call_id": tc.get("id", name), "name": name,
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:12000]})
        yield _event("answer", text="I couldn't finish this in a few steps. Try a narrower question.",
                     calls=[], links=tb.links[-3:], proposals=tb.proposals, chips=[])
    except llm.LLMError as e:
        yield _event("error", message="The language model isn't available right now. " + str(e)[:200])


@router.post("/assistant")
def ask(body: AskBody, c: Ctx = Depends(ctx)):
    # the stream outlives the request's database session, so it opens its own with the same user and scope
    def stream():
        with session_scope() as db:
            own = Ctx(user=db.merge(c.user, load=False), db=db, slug=c.slug, roles=c.roles, agent_scope=c.agent_scope)
            yield from run(own, body)
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/assistant/suggestions")
def suggestions(c: Ctx = Depends(ctx)):
    return {"en": ["Which calls this week were not resolved, and why?",
                   "Which customers are unhappy and still have no callback?",
                   "Compare agents by resolution rate this month",
                   "Show calls where the customer asked to cancel",
                   "What are the top reasons for low satisfaction?"],
            "ar": ["إيه أكتر أسباب المكالمات اللي متحلتش الأسبوع ده؟", "مين العملاء اللي زعلانين ومحدش كلمهم؟",
                   "مين أحسن موظف في حل المشاكل الشهر ده؟"]}
