"""ADIB's own scoresheet: 100 minus the points of each mistake (once per call), never below 0; critical ones flag."""
from callintel import adib
from callintel.services.analysis import _qa, mistake_mode, mistakes_to_scorecard, schema


def _score(codes):
    kpis = adib.scorecard_items()
    d = {"qa_mistakes": [{"code": c, "turn": 3, "note": "x"} for c in codes]}
    mistakes_to_scorecard(d, kpis)
    return d, _qa(d["scorecard"], kpis)


def test_sheet_contents():
    assert len(adib.ERRORS) == 46 and len(adib.CATEGORIES) == 130
    assert len({c for c, _, _ in adib.ERRORS}) == 46 and len({c for c, _, _ in adib.CATEGORIES}) == 130
    assert mistake_mode(adib.scorecard_items())


def test_clean_call_scores_100():
    _, (score, crit) = _score([])
    assert score == 100 and not crit


def test_points_and_flag():
    d, (score, crit) = _score(["dead_air", "interrupting_the_customer", "dead_air"])  # 5 + 15, dead air once
    assert score == 80 and crit
    assert [m["code"] for m in d["qa_mistakes"]] == ["dead_air", "interrupting_the_customer"]
    assert {r["kpi"]: r["result"] for r in d["scorecard"]}["dead_air"] == "fail"
    _, (score, crit) = _score(["dead_air", "very_fast_unclear"])
    assert score == 90 and not crit


def test_floor_at_zero():
    _, (score, crit) = _score([c for c, _, _ in adib.ERRORS])
    assert score == 0 and crit


def test_schema_uses_mistakes():
    codes = [k["code"] for k in adib.scorecard_items()]
    s = schema(["a"], codes, mistakes=True)["properties"]
    assert "qa_mistakes" in s and "scorecard" not in s


def test_adib_upgraded_once_btech_untouched(app_db):
    from callintel import db as dbm
    from callintel.models import Category, Scorecard
    with dbm.session_scope() as db:
        card = db.query(Scorecard).filter_by(enterprise_id="adib", active=True).one()
        assert mistake_mode(card.kpis) and len(card.kpis) == 46
        assert db.query(Category).filter_by(enterprise_id="adib", active=True).count() == 130
        assert not mistake_mode(db.query(Scorecard).filter_by(enterprise_id="btech", active=True).one().kpis)
        assert adib.apply_scoresheet(db) is False  # second run changes nothing
