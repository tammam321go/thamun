import time

import pytest

from api import explain
from api.engine import MODEL_DIR

trained = (MODEL_DIR / "meta.json").exists()
needs_models = pytest.mark.skipif(not trained, reason="models not trained yet")


def test_database_keeps_reports_after_a_restart(tmp_path):
    from datetime import date

    from api.db import Database
    from api.reports import ReportBook
    from api.store import DEMO_DIR

    url = f"sqlite:///{tmp_path / 'thamun.db'}"
    today = date(2026, 10, 8)
    first = ReportBook(Database(url), DEMO_DIR / "reported_numbers.json")
    assert first.add("s1", "r1", "01012345678", "refund", today) == "added"
    seeded = first.total()["seed"]
    second = ReportBook(Database(url), DEMO_DIR / "reported_numbers.json")
    assert second.status("s1", "01012345678", "r1", today)["reports"] == 1
    assert second.total() == {"seed": seeded, "app": 1}


def test_audit_log_never_stores_the_recipient(tmp_path):
    from sqlalchemy import select

    from api.db import Database, audit_logs

    db = Database(f"sqlite:///{tmp_path / 'audit.db'}")
    db.audit("check", "session-hash", "D0001", payment_type="send_money", amount=500, decision="pause", risk=0.4,
             reasons="new_recipient")
    db.audit("check", "session-hash", "D0001", not_a_column="ignored")
    rows = db.rows(select(audit_logs))
    assert len(rows) == 2 and rows[0]["decision"] == "pause"
    assert not {"counterparty", "number", "otp", "recipient"} & set(rows[0])


def test_tokens_are_signed_and_expire(monkeypatch):
    import jwt
    from fastapi import HTTPException

    from api import security

    token = security.issue_token("D0001")["access_token"]
    who = security.read_token(token)
    assert who.customer_id == "D0001" and who.sid and who.key != who.sid
    with pytest.raises(HTTPException) as bad:
        security.read_token(token[:-3] + "abc")
    assert bad.value.status_code == 401
    forged = jwt.encode({"sid": "x", "exp": int(time.time()) + 60}, "another-secret", algorithm="HS256")
    with pytest.raises(HTTPException):
        security.read_token(forged)
    expired = jwt.encode({"sid": "x", "exp": int(time.time()) - 5}, security.SECRET, algorithm="HS256")
    with pytest.raises(HTTPException):
        security.read_token(expired)
    with pytest.raises(HTTPException) as wrong:
        security.authorise(who, "D0002")
    assert wrong.value.status_code == 403
    security.authorise(who, "D0001")


def test_rate_limiter_blocks_and_recovers():
    from api.security import RateLimiter

    limiter = RateLimiter()
    assert all(limiter.allow("k", 3, window=1)[0] for _ in range(3))
    ok, retry = limiter.allow("k", 3, window=1)
    assert not ok and retry >= 1
    assert limiter.allow("other", 3, window=1)[0]
    time.sleep(1.05)
    assert limiter.allow("k", 3, window=1)[0]


def test_external_llm_is_off_unless_explicitly_allowed(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "x")
    monkeypatch.delenv("LLM_DATA_RESIDENCY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    assert explain.llm_settings() is None and explain.llm_status()["configured"]
    monkeypatch.setenv("LLM_BASE_URL", "http://10.20.0.5:8000/v1")
    assert explain.llm_settings() and explain.llm_status()["host_internal"]
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    assert explain.llm_settings()
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.wallet.example/v1")
    assert explain.llm_settings() is None
    monkeypatch.setenv("LLM_INTERNAL_HOSTS", "llm.wallet.example")
    assert explain.llm_settings()
    monkeypatch.delenv("LLM_INTERNAL_HOSTS")
    monkeypatch.setenv("LLM_DATA_RESIDENCY", "allow_external")
    assert explain.llm_settings()


def test_llm_cannot_change_numbers_in_bangla_or_add_links(monkeypatch):
    base = explain.explain("pause", [{"code": "amount_vs_usual", "ratio": 4.0, "usual": 2000}], 8000, "bn")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "x")
    monkeypatch.setenv("LLM_DATA_RESIDENCY", "allow_external")
    assert explain.numbers_in("৳৮,০০০ এবং 4×") == {"8000", "4"}
    monkeypatch.setattr(explain, "chat", lambda *a, **k: "এই ৳৯,০০০ লেনদেন ঠিক আছে।")
    assert explain.rephrase(base)["source"] == "template"
    monkeypatch.setattr(explain, "chat", lambda *a, **k: base["message"] + " http://bad.example")
    assert explain.rephrase(base)["source"] == "template"
    monkeypatch.setattr(explain, "chat", lambda *a, **k: None)
    assert explain.rephrase(base) == base


@needs_models
def test_coach_answer_rejects_invented_numbers(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    headers = {"X-Session": "pytest-coach"}
    question = {"customer_id": "D0001", "question": "Where does my money go?"}
    plain = client.post("/ask", json=question, headers=headers).json()
    assert plain["source"] == "template" and plain["answer"]
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "x")
    monkeypatch.setenv("LLM_DATA_RESIDENCY", "allow_external")
    monkeypatch.setattr(explain, "chat", lambda *a, **k: "You could save 987654 every month.")
    invented = client.post("/ask", json=question, headers=headers).json()
    assert invented["source"] == "template" and invented["answer"] == plain["answer"]
    monkeypatch.setattr(explain, "chat", lambda *a, **k: "Most of your money goes to regular costs.")
    assert client.post("/ask", json=question, headers=headers).json()["source"] == "llm"


@needs_models
def test_api_needs_a_token_when_auth_is_on(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    assert client.get("/health").status_code == 200
    assert client.get("/home", params={"customer_id": "D0001"}).status_code == 401
    assert client.get("/home", params={"customer_id": "D0001"}, headers={"X-Session": "no-token"}).status_code == 401
    assert client.get("/home", params={"customer_id": "D0001"}, headers={"Authorization": "Bearer junk"}).status_code == 401
    token = client.post("/auth/session").json()
    assert token["token_type"] == "bearer" and token["expires_in"] > 0
    headers = {"Authorization": "Bearer " + token["access_token"]}
    home = client.get("/home", params={"customer_id": "D0001"}, headers=headers)
    assert home.status_code == 200 and "protection" in home.json() and "spending" in home.json()
    bound = client.post("/auth/session", json={"customer_id": "D0002"}).json()
    locked = {"Authorization": "Bearer " + bound["access_token"]}
    assert client.get("/home", params={"customer_id": "D0002"}, headers=locked).status_code == 200
    assert client.get("/home", params={"customer_id": "D0001"}, headers=locked).status_code == 403
    assert client.post("/auth/session", json={"customer_id": "Z9999"}).status_code == 404
    assert client.get("/admin/audit").status_code == 403


@needs_models
def test_admin_routes_need_the_admin_key(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    monkeypatch.delenv("ADMIN_KEY", raising=False)
    assert client.get("/admin/feedback/export").status_code == 403
    assert client.get("/admin/feedback/export", headers={"X-Admin-Key": ""}).status_code == 403
    monkeypatch.setenv("ADMIN_KEY", "s3cret-admin")
    assert client.get("/admin/feedback/export").status_code == 403
    assert client.get("/admin/feedback/export", headers={"X-Admin-Key": "wrong"}).status_code == 403
    ok = client.get("/admin/feedback/export", headers={"X-Admin-Key": "s3cret-admin"})
    assert ok.status_code == 200 and ok.text.startswith("id,created_at,scenario")
    assert "session" not in ok.text.splitlines()[0]
    assert client.get("/admin/audit", headers={"X-Admin-Key": "s3cret-admin"}).status_code == 200


@needs_models
def test_requests_are_rate_limited(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "5")
    headers = {"X-Session": "pytest-flood"}
    codes = [client.get("/health", headers=headers).status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429] * 3
    blocked = client.get("/health", headers=headers)
    assert blocked.headers["Retry-After"] and "detail" in blocked.json()
    assert client.get("/health", headers={"X-Session": "pytest-calm"}).status_code == 200


@needs_models
def test_responses_carry_security_headers_and_hide_errors(monkeypatch):
    from fastapi.testclient import TestClient

    from api import main

    client = TestClient(main.app, raise_server_exceptions=False)
    ok = client.get("/health")
    assert ok.headers["X-Content-Type-Options"] == "nosniff" and ok.headers["X-Frame-Options"] == "DENY"

    def boom(*args, **kwargs):
        raise RuntimeError("secret database password")

    monkeypatch.setattr(main.store, "home_facts", boom, raising=False)
    monkeypatch.setattr(main, "protection_view", boom)
    broken = client.get("/home", params={"customer_id": "D0001"}, headers={"X-Session": "pytest-err"})
    assert broken.status_code == 500 and "secret" not in broken.text and broken.json()["detail"]


@needs_models
def test_feedback_analytics_and_monitoring_use_real_counts():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    headers = {"X-Session": "pytest-insight"}
    client.post("/demo/reset", json={}, headers=headers)
    before = client.get("/analytics", headers=headers).json()
    assert before["scope"] == "session" and "Not real customers" in before["source"]
    script = {s["id"]: s for s in client.get("/demo/script", params={"customer_id": "D0001"}, headers=headers).json()}
    item = script["reported_small"]
    body = {"customer_id": "D0001", "type": item["type"], "counterparty": item["counterparty"], "amount": item["amount"]}
    result = client.post("/check", json=body, headers=headers).json()
    client.post("/pay", json={"customer_id": "D0001", "check_id": result["check_id"], "action": "cancel"}, headers=headers)
    bill = script["bill"]
    body = {"customer_id": "D0001", "type": bill["type"], "counterparty": bill["counterparty"], "amount": bill["amount"]}
    quiet = client.post("/check", json=body, headers=headers).json()
    client.post("/pay", json={"customer_id": "D0001", "check_id": quiet["check_id"], "action": "proceed", "otp": "1234"}, headers=headers)
    after = client.get("/analytics", headers=headers).json()
    assert after["decisions"]["pause"] == before["decisions"]["pause"] + 1
    assert after["decisions"]["silent"] == before["decisions"]["silent"] + 1
    assert after["pauses_cancelled"] == before["pauses_cancelled"] + 1
    assert after["amount_kept_after_pause"] == before["amount_kept_after_pause"] + item["amount"]
    assert 0 < after["cancellation_rate_after_pause"] <= 1

    count = client.get("/feedback/summary").json()["responses"]
    answer = {"scenario": "reported", "decision": "pause", "lang": "bn", "understood_warning": "yes", "understood_reason": "partly",
              "intrusive": "no", "understood_choice": "yes", "preferred_lang": "bn", "comment": "clear <b>enough</b>"}
    saved = client.post("/feedback", json=answer, headers=headers).json()
    assert saved["status"] == "saved" and saved["responses"] == count + 1
    assert saved["questions"]["understood_reason"]["partly"] >= 1 and saved["preferred_language"]["bn"] >= 1
    assert client.post("/feedback", json=dict(answer, intrusive="maybe"), headers=headers).status_code == 422
    assert client.post("/feedback", json=dict(answer, scenario="made_up"), headers=headers).status_code == 422

    live = client.get("/monitoring").json()
    assert live["requests"] > 0 and live["decisions"]["pause"] >= 1 and live["latency_check"]["count"] >= 2
    assert live["database"]["backend"] == "sqlite" and live["database"]["ok"]
    assert live["drift"]["status"] and live["drift"]["live_checks"] >= 2
    health = client.get("/health").json()
    assert health["version"] == "2.0.0" and health["database"] == "sqlite" and health["database_ok"]
    assert "label" in client.get("/evidence").json()
