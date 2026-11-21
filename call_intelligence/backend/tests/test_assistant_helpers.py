from callintel.routers.assistant import AskBody, fix_refs, reply_arabic, split_followups
from callintel.services.insights import ar_count

ID = "1b937e7dd21548228e8d96442e86f9d4"


def test_followups_are_split_off():
    text, f = split_followups("**2** customers.\n\nFOLLOWUPS: Draft the messages | Why were they unhappy?")
    assert text == "**2** customers." and f == ["Draft the messages", "Why were they unhappy?"]
    assert split_followups("no followups here") == ("no followups here", [])


def test_call_refs_repaired_or_dropped():
    assert fix_refs("see [call:1b937e7dd21548228e86f9d4]", {ID: {}}) == f"see [call:{ID}]"
    assert fix_refs("see [call:deadbeef00]", {ID: {}}) == "see "


def test_reply_language():
    body = lambda lang, q: AskBody(lang=lang, messages=[{"role": "user", "content": q}])
    assert reply_arabic(body("ar", "Which customers?"))
    assert reply_arabic(body("en", "مين العملاء الزعلانين؟"))
    assert not reply_arabic(body("en", "Show calls for سعاد محمد please"))


def test_arabic_counting():
    assert [ar_count(n, "عميل واحد", "عميلين", "عملاء", "عميل") for n in (1, 2, 3, 11)] == ["عميل واحد", "عميلين", "٣ عملاء", "١١ عميل"]
