from types import SimpleNamespace

from callintel.services import metrics, roles


def test_roles_agent_customer_ivr():
    turns = [{"speaker": "S0", "text": "مكالمتك قد تكون مسجلة، للغة العربية اضغط واحد"},
             {"speaker": "S2", "text": "أنا عايز أعرف الطلب بتاعي فين"},
             {"speaker": "S1", "text": "أهلاً بك في بي تك، معاك أحمد، أقدر أساعد حضرتك إزاي؟"},
             {"speaker": "S2", "text": "الطلب اتأخر"},
             {"speaker": "S1", "text": "تمام يا فندم، ثواني أراجع"}]
    assert roles.assign(turns) == {"S0": "ivr", "S1": "agent", "S2": "customer"}


def test_measure_talk_share_and_silence():
    t = lambda sp, a, b: SimpleNamespace(speaker=sp, start=a, end=b, text="x")
    m = metrics.measure([t("agent", 0, 6), t("customer", 6.5, 8), t("agent", 15, 17)])
    assert 0.7 < m["agent_talk_share"] < 0.9
    assert m["longest_silence_s"] >= 7
