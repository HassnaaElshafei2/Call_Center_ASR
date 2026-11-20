"""Which diarized speaker is the agent, which the customer, which the IVR."""
import re
from collections import defaultdict

IVR_HINTS = re.compile(r"(اضغط|للغة|مكالمتك (قد|سوف)|سيتم تسجيل|press|لخدمة العملاء|برجاء الانتظار|للتحدث مع)")
AGENT_HINTS = re.compile(r"(أهلا(ً)? (بك|بحضرتك)|مع حضرتك|أتشرف|اتشرف|أقدر أساعد|اقدر اساعد|أي خدمة تانية|"
                         r"شكرا لاتصال|لاتصالك|تقييم المكالمة|يا فندم|حضرتك)")


def assign(turns: list[dict]) -> dict[str, str]:
    """turns: [{"speaker", "text"}] in time order -> {speaker label: agent|customer|ivr}."""
    by = defaultdict(list)
    for t in turns:
        by[t["speaker"]].append(t["text"])
    labels = {}
    for spk, texts in by.items():
        joined = " ".join(texts)
        if IVR_HINTS.search(joined) and len(texts) <= 3:
            labels[spk] = "ivr"
    rest = [s for s in by if s not in labels]
    if not rest:
        return labels
    score = {s: len(AGENT_HINTS.findall(" ".join(by[s]))) / max(1, len(by[s])) for s in rest}
    first = next((t["speaker"] for t in turns if t["speaker"] in rest), rest[0])
    score[first] += 0.5                      # the agent usually speaks first after the IVR
    agent = max(score, key=score.get)
    for s in rest:
        labels[s] = "agent" if s == agent else "customer"
    return labels
