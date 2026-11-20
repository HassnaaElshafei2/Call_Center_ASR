from conftest import login


def test_login_and_meta(client):
    h = login(client, "manager@demo.sia")
    me = client.get("/api/me", headers=h).json()
    assert {e["id"] for e in me["enterprises"]} == {"adib", "btech"}
    assert client.get("/api/e/all/meta", headers=h).status_code == 200


def test_bad_password(client):
    assert client.post("/api/auth/login", json={"email": "manager@demo.sia", "password": "nope"}).status_code == 401


def test_enterprise_switching_and_isolation(client):
    h = login(client, "manager@demo.sia")
    assert client.get("/api/e/all/calls", headers=h).json()["total"] == 4
    assert client.get("/api/e/adib/calls", headers=h).json()["total"] == 2
    # a B.TECH-only user sees B.TECH only, even under "all", and can't open ADIB
    hb = login(client, "btech.qa@demo.sia")
    rows = client.get("/api/e/all/calls", headers=hb).json()["calls"]
    assert rows and all(r["enterprise"] == "btech" for r in rows)
    assert client.get("/api/e/adib/calls", headers=hb).status_code == 404


def test_filters(client):
    h = login(client, "manager@demo.sia")
    r = client.get("/api/e/all/calls?resolution=not_resolved", headers=h).json()
    assert r["total"] == 1 and r["calls"][0]["resolution"] == "not_resolved"
    assert client.get("/api/e/all/calls?sat_min=4", headers=h).json()["total"] == 2


def test_agent_sees_only_own_calls(client):
    h = login(client, "agent@test", "pw")
    rows = client.get("/api/e/btech/calls", headers=h).json()["calls"]
    assert len(rows) == 1 and rows[0]["resolution"] == "resolved"


def test_customer_from_recording_name_and_phone_reveal(client):
    h = login(client, "manager@demo.sia")
    custs = client.get("/api/e/btech/customers?period=all", headers=h).json()["customers"]
    masked = {c["phone"] for c in custs}
    assert "+20 10 •••• 3344" in masked and "+20 12 •••• 6666" in masked
    cid = next(c["id"] for c in custs if c["phone"] == "+20 10 •••• 3344")
    assert client.post(f"/api/e/btech/customers/{cid}/reveal-phone", headers=h).json()["phone"].replace(" ", "") == "+201011223344"
    # QA may not reveal full numbers
    assert client.post(f"/api/e/btech/customers/{cid}/reveal-phone", headers=login(client, "qa@demo.sia")).status_code == 403


def test_executive_cannot_act_or_review(client):
    h = login(client, "exec@demo.sia")
    call = client.get("/api/e/adib/calls", headers=h).json()["calls"][0]
    r = client.post(f"/api/e/adib/calls/{call['id']}/review", headers=h, json={"resolution": "resolved"})
    assert r.status_code == 403
    assert client.get("/api/e/all/admin/users", headers=h).status_code == 403


def test_overview(client):
    h = login(client, "manager@demo.sia")
    o = client.get("/api/e/all/overview?period=all", headers=h)
    assert o.status_code == 200, o.text
