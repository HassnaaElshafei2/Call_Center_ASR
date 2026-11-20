"""Tests run against a separate Postgres database (TEST_DATABASE_URL, default callintel_test on localhost)."""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("PHONE_HASH_KEY", "test-key")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ["LLM_API_KEY"] = ""          # tests never call the language models
os.environ["ASR_SERVICE_URL"] = ""
TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql+psycopg://callintel:callintel-local@localhost:5432/callintel_test")


@pytest.fixture(scope="session")
def app_db():
    from callintel import db as dbm, models  # noqa: F401 - registers the tables
    from callintel.config import settings
    settings.cache_clear()
    dbm.reset_engine(TEST_DB)
    assert dbm.engine().url.database.endswith("_test"), "refusing to reset a database whose name doesn't end in _test"
    dbm.Base.metadata.drop_all(dbm.engine())
    dbm.Base.metadata.create_all(dbm.engine())
    from callintel.models import Agent, Call, Membership, User
    from callintel.security import hash_password
    from callintel.seed import seed_base
    from callintel.services import identity
    with dbm.session_scope() as db:
        seed_base(db, demo_users=True)
        now = datetime.now(timezone.utc)
        a1 = Agent(enterprise_id="adib", name="Agent A", code="A1")
        b1 = Agent(enterprise_id="btech", name="Agent B", code="B1")
        b2 = Agent(enterprise_id="btech", name="Agent C", code="B2")
        db.add_all([a1, b1, b2])
        db.flush()
        rows = [("adib", a1, "resolved", 5, "demo:1"), ("adib", a1, "partly_resolved", 3, "demo:2"),
                ("btech", b1, "not_resolved", 1, "btech_01011223344"), ("btech", b2, "resolved", 4, "btech_201255556666")]
        for i, (ent, ag, res, sat, ref) in enumerate(rows):
            c = Call(enterprise_id=ent, agent_id=ag.id, external_ref=ref, started_at=now - timedelta(days=i + 1),
                     status="done", resolution=res, satisfaction=sat, source="test", duration_s=60)
            db.add(c)
            db.flush()
            cu = identity.from_recording_name(db, c)
            c.customer_id = cu.id if cu else None
        agent_user = User(email="agent@test", name="Agent C user", password_hash=hash_password("pw"))
        db.add(agent_user)
        db.flush()
        db.add(Membership(user_id=agent_user.id, enterprise_id="btech", role="agent", agent_id=b2.id))
    yield
    dbm.reset_engine(settings().database_url)


@pytest.fixture(scope="session")
def client(app_db):
    from fastapi.testclient import TestClient
    from callintel.main import app
    return TestClient(app)


def login(client, email, password=None):
    r = client.post("/api/auth/login", json={"email": email, "password": password or os.environ.get("DEMO_PASSWORD", "demo-change-me")})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}
