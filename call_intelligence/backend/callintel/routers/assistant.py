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
from ..models import Agent, Call, Category, Enterprise
from .common import scope
from ..services import llm

router = APIRouter(prefix="/api/e/{ent}")
MAX_ROUNDS = 8
LABELS = {"count_calls": "Counting calls", "list_calls": "Finding calls", "get_call": "Reading the call",
          "search_transcripts": "Searching what was said in calls", "find_customers": "Looking at customers",
          "agent_stats": "Comparing agents", "list_actions": "Checking follow-up actions",
          "unhappy_without_callback": "Finding unhappy customers without a callback",
          "propose_action": "Preparing an action for you to confirm"}
LABELS_AR = {"count_calls": "بعد المكالمات", "list_calls": "بدور على المكالمات", "get_call": "بقرا المكالمة",
             "search_transcripts": "بدور في كلام المكالمات", "find_customers": "ببص على العملاء",
             "agent_stats": "بقارن الموظفين", "list_actions": "ببص على المتابعات",
             "unhappy_without_callback": "بدور على العملاء الزعلانين اللي محدش كلمهم",
             "propose_action": "بجهز متابعة تأكدها"}

SYSTEM = """You are Sia AI, the assistant inside Sia Listen, a customer-service call analysis platform for {companies}.
Today is {today}. Users are call-centre managers, QA, retention staff and agents.

How to answer:
- Act, don't narrate: call the tools straight away (several if needed), then answer from their results. Never reply
  with a plan or with what you are "going to" check.
- Get every number, name and call from the tools.
- Never show internal field names or codes (not_resolved, open_actions, suggested, churn_risk…): say them in plain
  words. Copy call ids exactly as the tools give them. Never estimate or invent figures; if the tools don't cover a
  question, say so plainly.
- Reply in the user's language: Egyptian Arabic if they write Arabic, otherwise English (unless told below). Be short and concrete:
  lead with the answer, then 2-5 bullets. Use **bold** for key numbers.
- Refer to a specific call as [call:ID] (the id from the tools) so the app turns it into a link; at most 5 per answer.
- Satisfaction is predicted from the conversation (1-5), not a survey; resolution is resolved / partly resolved /
  not resolved. Say "predicted" when it matters.
- To suggest follow-ups (callbacks, offers...), use propose_action; the user confirms it. Never say an action was done.
- Periods are always in the past: the default is the last 30 days ("آخر 30 يوم"), unless the user says otherwise.
- If a count is zero, say so plainly and offer to look at a longer period or a related measure (e.g. partly
  resolved calls). In Arabic, write natural Egyptian Arabic: call the agent «الموظف» / «الموظفة» (or by name) and the
  customer «العميل» / «العميلة»; keep the wording plain and respectful.

- After your final answer (never before using the tools), add one last line: "FOLLOWUPS: <question> | <question>",
  two short questions the user might ask next, written as the user would type them, in the language of your answer.
  The app shows them as buttons and removes this line.
- In Arabic, don't assume the user's gender: avoid gendered forms like تحب/تحبي or عايز/عايزة; use neutral wording
  (e.g. "ممكن أجهز…" or a noun phrase).
{language}
Call reasons: {categories}
Agents: {agents}
{screen}"""


class Msg(BaseModel):
    role: str
    content: str


class AskBody(BaseModel):
    messages: list[Msg]
    lang: str = "en"                # the language the user picked in the panel (en / ar)
    screen: dict | None = None      # what the user is looking at: page, filters, call_id, customer_id, agent_id, title


def system_prompt(c: Ctx, screen: dict | None, lang: str = "en") -> str:
    ents = c.db.query(Enterprise).filter(Enterprise.id.in_(c.ents)).all()
    cats = c.db.query(Category).filter(Category.enterprise_id.in_(c.ents), Category.active.is_(True)).all()
    agents = c.db.query(Agent).filter(Agent.enterprise_id.in_(c.ents)).order_by(Agent.name).all()
    scr = ""
    if screen:
        scr = ("The user is looking at: " + json.dumps(screen, ensure_ascii=False)[:1500] +
               "\nWords like 'this call', 'this customer', 'these calls' or 'this agent' refer to it.")
    return SYSTEM.format(companies=", ".join(f"{e.name} ({e.kind}, id {e.id})" for e in ents), today=date.today(),
                         categories="; ".join(f"{x.code} = {x.name} ({x.enterprise_id})" for x in cats),
                         agents=", ".join(f"{a.name} ({a.enterprise_id})" for a in agents)[:2000], screen=scr,
                         language="- The user switched the panel to Arabic: answer in Egyptian Arabic, even if the question is in English."
                         if lang == "ar" else "")


def reply_arabic(body: "AskBody") -> bool:
    """Arabic when the panel is set to ع or the latest question is written in Arabic; English otherwise."""
    last = next((m.content for m in reversed(body.messages) if m.role == "user"), "")
    letters = re.findall(r"[A-Za-z\u0600-\u06FF]", last)
    arabic = sum("\u0600" <= ch <= "\u06FF" for ch in letters)
    return body.lang == "ar" or (bool(letters) and arabic / len(letters) > .5)


def fix_refs(text: str, known: dict) -> str:
    """Repair or drop [call:…] references the model mangled (e.g. shortened ids), so every link the user sees works."""
    def repl(m):
        ref = m.group(1)
        if ref in known:
            return m.group(0)
        hit = [k for k in known if len(ref) >= 6 and (k.startswith(ref[:8]) or k.endswith(ref[-8:]))]
        return f"[call:{hit[0]}]" if len(hit) == 1 else ""
    return re.sub(r"\[call:([0-9a-fA-F]{4,40})\]", repl, text)


def unique_links(links: list[dict], n: int = 3) -> list[dict]:
    """The latest distinct page links (a tool called several times adds the same link each time)."""
    out, seen = [], set()
    for l in reversed(links):
        key = (l.get("label"), l.get("page"), json.dumps(l.get("filters") or {}, sort_keys=True), l.get("enterprise"))
        if key not in seen:
            seen.add(key)
            out.append(l)
    return list(reversed(out[:n]))


def collapse_loops(text: str) -> str:
    """Safety net for a model stuck in a loop: a word or short phrase repeated 3+ times in a row is kept once."""
    return re.sub(r"(\b[\w\u0600-\u06FF]+(?:\s+[\w\u0600-\u06FF]+){0,2})(?:\s+\1\b){2,}", r"\1", text)


def split_followups(text: str) -> tuple[str, list[str]]:
    """Take the model's closing "FOLLOWUPS: a | b" line off the answer."""
    m = re.search(r"(?:^|\n)[ \t*_]*FOLLOW-?UPS[ \t*_]*:[ \t*_]*(.+?)\s*$", text, flags=re.I | re.S)
    if not m:
        return text, []
    qs = [q.strip(" -*•\"'") for q in m.group(1).split("|")]
    return text[:m.start()].rstrip(), [q for q in qs if 3 < len(q) < 140][:2]


def _event(kind: str, **data) -> str:
    return "data: " + json.dumps({"type": kind, **data}, ensure_ascii=False, default=str) + "\n\n"


def run(c: Ctx, body: AskBody):
    tb = Toolbox(c)
    msgs = [{"role": "system", "content": system_prompt(c, body.screen, body.lang)}]
    labels = LABELS_AR if body.lang == "ar" else LABELS
    msgs += [{"role": m.role, "content": m.content[:4000]} for m in body.messages[-12:] if m.role in ("user", "assistant")]
    # a reminder on the latest question: instructions at the top of a long prompt fade after several tool rounds
    if msgs[-1]["role"] == "user":
        msgs[-1] = {"role": "user", "content": msgs[-1]["content"] + "\n\n[" + (
            "Reply in Egyptian Arabic, FOLLOWUPS in Arabic too." if reply_arabic(body)
            else "Reply in English (names may stay in Arabic), FOLLOWUPS in English too.") + "]"}
    tools = definitions(c)
    seen_ids: set[str] = set()          # every call id any tool returned, to repair the model's references
    try:
        for _ in range(MAX_ROUNDS):
            reply = llm.chat(msgs, tools=tools, max_tokens=1500, temperature=0.1, timeout=120, repetition_penalty=1.08)
            calls = reply.get("tool_calls") or []
            if not calls:
                text, follow = split_followups(collapse_loops((reply.get("content") or "").strip()))
                text = fix_refs(text, {**dict.fromkeys(seen_ids), **tb.calls})
                cited = [i for i in dict.fromkeys(re.findall(r"\[call:([0-9a-f]{32})\]", text))]
                for cid in cited:                   # cited from a customer list etc.: load the call so its link shows
                    if cid not in tb.calls:
                        x = scope(c, c.db.query(Call)).filter(Call.id == cid).first()
                        if x:
                            tb._brief(x)
                shown = [i for i in dict.fromkeys(cited + tb.featured) if i in tb.calls]
                yield _event("answer", text=text, calls=[tb.calls[i] for i in shown],
                             links=unique_links(tb.links), proposals=tb.proposals, chips=tb.chips[-1:] if tb.chips else [],
                             followups=follow)
                return
            msgs.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
            for tc in calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield _event("step", tool=name, label=labels.get(name, name))
                result = tb.run(name, args)
                seen_ids.update(re.findall(r"[0-9a-f]{32}", json.dumps(result, default=str)))
                if tb.chips and tb.chips[-1]["tool"] == name:
                    yield _event("chips", chips=tb.chips[-1]["chips"])
                msgs.append({"role": "tool", "tool_call_id": tc.get("id", name), "name": name,
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:12000]})
        # out of steps: answer from what the tools returned so far instead of giving up
        msgs.append({"role": "user", "content": "Stop using tools now and answer from the results you already have. "
                     "Say briefly if something is incomplete. End with the FOLLOWUPS line."})
        reply = llm.chat(msgs, max_tokens=1500, temperature=0.1, timeout=120, repetition_penalty=1.08)
        text, follow = split_followups(collapse_loops((reply.get("content") or "").strip()))
        text = fix_refs(text, {**dict.fromkeys(seen_ids), **tb.calls})
        cited = [i for i in dict.fromkeys(re.findall(r"\[call:([0-9a-f]{32})\]", text)) if i in tb.calls]
        yield _event("answer", text=text, calls=[tb.calls[i] for i in dict.fromkeys(cited + tb.featured) if i in tb.calls], links=unique_links(tb.links),
                     proposals=tb.proposals, chips=tb.chips[-1:] if tb.chips else [], followups=follow)
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
