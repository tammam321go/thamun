from datetime import date, datetime, timedelta

import pytest

from api import explain
from api.engine import MODEL_DIR, decide, needs_purpose, purpose_rules
from ml.bills import BillBook, affordability, forecast
from ml.features import CustomerState
from ml.nudges import SpendTracker

trained = (MODEL_DIR / "meta.json").exists()


def txn(ts, amount, cp="0100000001", ttype="send_money", direction="out", category="personal_transfer", balance=20000):
    return {"ts": ts, "type": ttype, "direction": direction, "amount": amount, "counterparty": cp,
            "counterparty_type": "person", "merchant_type": "none", "category": category,
            "balance_before": balance, "counterparty_name": cp}


def quiet_risk():
    return {"high": False, "reasons": []}


def test_refund_without_incoming_is_flagged():
    feats = {"in_cp_amount": 0}
    hits = purpose_rules({"amount": 8000}, "refund_mistake", feats)
    assert hits and hits[0]["code"] == "refund_no_incoming"


def test_refund_matching_incoming_passes():
    assert purpose_rules({"amount": 2000}, "refund_mistake", {"in_cp_amount": 2000}) == []


def test_refund_larger_than_incoming_is_flagged():
    hits = purpose_rules({"amount": 5000}, "refund_mistake", {"in_cp_amount": 200})
    assert hits[0]["code"] == "refund_exceeds_incoming"


def test_scam_story_purposes_always_hit():
    assert purpose_rules({"amount": 500}, "prize_fee", {"in_cp_amount": 0})[0]["code"] == "prize_fee"
    assert purpose_rules({"amount": 500}, "agent_request", {"in_cp_amount": 0})[0]["code"] == "agent_request"
    assert purpose_rules({"amount": 500}, "family_support", {"in_cp_amount": 0}) == []


def test_purpose_asked_only_for_material_new_transfers():
    new = {"is_new_cp": 1, "cp_age_days": 0.0, "cp_count": 0}
    known = {"is_new_cp": 0, "cp_age_days": 90.0, "cp_count": 12}
    assert needs_purpose({"type": "send_money", "amount": 3000}, new, True)
    assert not needs_purpose({"type": "send_money", "amount": 200}, new, True)
    assert not needs_purpose({"type": "merchant_payment", "amount": 3000}, new, False)
    assert not needs_purpose({"type": "send_money", "amount": 3000}, known, True)
    assert needs_purpose({"type": "send_money", "amount": 3000}, known, False)


def test_decide_pause_on_rule_even_when_model_is_calm():
    decision, reasons, flags = decide({"type": "send_money", "amount": 900}, quiet_risk(), [{"code": "prize_fee"}], None, None)
    assert decision == "pause" and flags["rules"] and not flags["behaviour"]


def test_decide_ignores_tiny_high_risk_payments():
    decision, _, _ = decide({"type": "send_money", "amount": 50}, {"high": True, "reasons": []}, [], None, None)
    assert decision == "silent"


def test_decide_nudge_and_silent():
    nudge = {"code": "above_baseline", "category": "eating_out", "count": 5, "week_total": 2100, "baseline": 1500, "pct_above": 40}
    assert decide({"type": "merchant_payment", "amount": 450}, quiet_risk(), [], None, nudge)[0] == "nudge"
    assert decide({"type": "merchant_payment", "amount": 450}, quiet_risk(), [], None, None)[0] == "silent"


def test_shortfall_pauses_only_unusual_payments():
    afford = {"code": "bill_shortfall", "bill": "Electricity", "category": "electricity", "bill_amount": 2500,
              "due_date": date(2026, 10, 10), "days_left": 2, "shortfall": 1200, "caused": True}
    payment = {"type": "send_money", "amount": 8000}
    assert decide(payment, quiet_risk(), [], afford, None, unusual=True)[0] == "pause"
    assert decide(payment, quiet_risk(), [], afford, None, unusual=False)[0] == "nudge"
    assert decide(payment, quiet_risk(), [], afford, None, unusual=False, bill_nudge=False)[0] == "silent"


def test_affordability_reports_first_bill_that_cannot_be_paid():
    upcoming = [
        {"counterparty": "B-ELEC", "name": "Electricity", "category": "electricity", "amount": 2500,
         "due_date": date(2026, 10, 10), "days_left": 2},
        {"counterparty": "B-GAS", "name": "Gas", "category": "gas", "amount": 1080, "due_date": date(2026, 10, 15), "days_left": 7},
    ]
    result = affordability(9300, 8000, upcoming)
    assert result["bill"] == "Electricity" and result["shortfall"] == 1200 and result["caused"]
    assert affordability(9300, 450, upcoming) is None
    assert affordability(9300, 2500, upcoming, paying="B-ELEC") is None


def monthly_bills(book, cp, amount, months, day, ttype="bill_payment"):
    for month in months:
        book.update(txn(datetime(2026, month, day, 11, 0), amount, cp=cp, ttype=ttype, category="electricity"))


def test_bill_detection_and_next_due_date():
    book = BillBook()
    monthly_bills(book, "B-ELEC", 2500, [5, 6, 7, 8, 9], 10)
    found = book.recurring()
    assert len(found) == 1 and found[0]["day"] == 10 and found[0]["amount"] == 2500
    upcoming = book.upcoming(date(2026, 10, 8))
    assert upcoming[0]["due_date"] == date(2026, 10, 10) and upcoming[0]["days_left"] == 2


def test_irregular_payments_are_not_bills():
    book = BillBook()
    for day in (3, 9, 11, 20, 27):
        book.update(txn(datetime(2026, 9, day, 10, 0), 700, cp="0100000009"))
    assert book.recurring() == []


def test_forecast_reminds_three_days_before_a_shortfall():
    upcoming = [{"counterparty": "B-GAS", "name": "Gas", "category": "gas", "type": "bill_payment", "amount": 1080,
                 "due_date": date(2026, 10, 15), "days_left": 7, "overdue": False}]
    plan = forecast(3000, upcoming, 400, None, date(2026, 10, 8))
    assert plan["bills"][0]["status"] == "short"
    assert plan["reminder"]["cash_in_by"] == date(2026, 10, 12)
    assert forecast(30000, upcoming, 400, None, date(2026, 10, 8))["reminder"] is None


def test_features_know_new_and_known_recipients():
    state = CustomerState()
    start = datetime(2026, 9, 1, 12, 0)
    for i in range(10):
        state.update(txn(start + timedelta(days=i), 2000))
    known = state.features(txn(start + timedelta(days=11), 8000))
    fresh = state.features(txn(start + timedelta(days=11), 8000, cp="0109999999"))
    assert known["is_new_cp"] == 0 and fresh["is_new_cp"] == 1
    assert known["amt_ratio_type"] == pytest.approx(4.0)
    assert fresh["in_cp_amount"] == 0


def test_features_see_recent_incoming_from_recipient():
    state = CustomerState()
    now = datetime(2026, 9, 5, 12, 0)
    state.update(txn(now - timedelta(hours=2), 1500, cp="0105555555", ttype="receive_money", direction="in"))
    feats = state.features(txn(now, 1500, cp="0105555555"))
    assert feats["in_cp_amount"] == 1500 and feats["in_cp_ratio"] == pytest.approx(1.0)


def test_nudge_fires_once_when_week_runs_above_baseline():
    tracker = SpendTracker()
    monday = datetime(2026, 7, 6, 13, 0)
    for week in range(8):
        for day in (0, 2, 4, 5):
            tracker.update(txn(monday + timedelta(weeks=week, days=day), 375, cp="M1", ttype="merchant_payment", category="eating_out"))
    this_week = monday + timedelta(weeks=8)
    for day in (0, 1, 2, 3):
        tracker.update(txn(this_week + timedelta(days=day), 412, cp="M1", ttype="merchant_payment", category="eating_out"))
    when = this_week + timedelta(days=3, hours=1)
    found = tracker.check("eating_out", 450, when)
    assert found and found["count"] == 5 and found["baseline"] == 1500 and found["pct_above"] > 30
    tracker.register("eating_out", when)
    assert tracker.check("eating_out", 450, when) is None
    assert tracker.check("groceries", 5000, when) is None


def test_explanations_exist_in_both_languages():
    reasons = [{"code": "amount_vs_usual", "ratio": 4.0, "usual": 2000}, {"code": "new_recipient"},
               {"code": "refund_no_incoming"},
               {"code": "bill_shortfall", "bill": "Electricity", "bill_amount": 2500, "due_date": date(2026, 10, 10), "shortfall": 1200}]
    english = explain.explain("pause", reasons, 8000, "en")
    bangla = explain.explain("pause", reasons, 8000, "bn")
    assert "4×" in english["message"] and "1,200" in english["message"] and "10 Oct" in english["message"]
    assert "1,200" in bangla["message"] and "অক্টোবর" in bangla["message"]
    assert len(english["reasons"]) == len(bangla["reasons"]) == 4
    for code in explain.TEMPLATES:
        assert all(explain.TEMPLATES[code])


def test_llm_output_is_rejected_when_numbers_change(monkeypatch):
    base = explain.explain("pause", [{"code": "amount_vs_usual", "ratio": 4.0, "usual": 2000}], 8000, "en")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "x")
    monkeypatch.setattr(explain, "chat", lambda *a, **k: "This 9,000 transfer looks fine.")
    assert explain.rephrase(base)["source"] == "template"
    monkeypatch.setattr(explain, "chat", lambda *a, **k: "Careful: 8,000 is about 4 times your usual 2,000.")
    assert explain.rephrase(base)["source"] == "llm"


@pytest.mark.skipif(not trained, reason="models not trained yet")
def test_demo_story_end_to_end():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    headers = {"X-Session": "pytest"}
    client.post("/demo/reset", json={}, headers=headers)
    script = {s["id"]: s for s in client.get("/demo/script", params={"customer_id": "D0001"}, headers=headers).json()}

    def check(item, purpose=None):
        body = {"customer_id": "D0001", "type": item["type"], "counterparty": item["counterparty"], "amount": item["amount"]}
        if purpose:
            body["purpose"] = purpose
        return client.post("/check", json=body, headers=headers).json()

    def finish(result, action="proceed"):
        return client.post("/pay", json={"customer_id": "D0001", "check_id": result["check_id"], "action": action, "otp": "1234"}, headers=headers).json()

    bill = check(script["bill"])
    assert bill["decision"] == "silent"
    assert finish(bill)["balance"] == 9750

    food = check(script["food"])
    assert food["decision"] == "nudge" and food["reasons"][0]["code"] == "above_baseline"
    assert finish(food)["balance"] == 9300

    first = check(script["refund"])
    assert first["decision"] == "ask_purpose"
    scam = check(script["refund"], "refund_mistake")
    codes = [r["code"] for r in scam["reasons"]]
    assert scam["decision"] == "pause"
    assert "refund_no_incoming" in codes and "new_recipient" in codes and "bill_shortfall" in codes
    assert scam["details"]["affordability"]["shortfall"] == 1200
    assert finish(scam, "cancel")["balance"] == 9300

    plan = client.get("/bills", params={"customer_id": "D0001"}, headers=headers).json()
    assert plan["reminder"] is not None
    review = client.get("/review", params={"customer_id": "D0001"}, headers=headers).json()
    assert review["guard"]["cancelled"] == 1 and review["categories"]
    goal = client.post("/goal", json={"customer_id": "D0001", "target": 30000, "months": 6}, headers=headers).json()
    assert goal["goal"]["per_month"] == 5000
    answer = client.post("/ask", json={"customer_id": "D0001", "question": "Why do I run short before month-end?"}, headers=headers).json()
    assert answer["intent"] == "month_end" and answer["answer"]


@pytest.mark.skipif(not trained, reason="models not trained yet")
def test_sessions_do_not_share_state():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    a, b = {"X-Session": "pytest-a"}, {"X-Session": "pytest-b"}
    client.post("/cashin", json={"customer_id": "D0001", "amount": 500}, headers=a)
    one = client.get("/home", params={"customer_id": "D0001"}, headers=a).json()["balance"]
    two = client.get("/home", params={"customer_id": "D0001"}, headers=b).json()["balance"]
    assert one == two + 500


@pytest.mark.skipif(not trained, reason="models not trained yet")
def test_bad_input_is_rejected():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    bad = client.post("/check", json={"customer_id": "D0001", "type": "send_money", "counterparty": "x'; DROP", "amount": 100})
    assert bad.status_code == 422
    negative = client.post("/check", json={"customer_id": "D0001", "type": "send_money", "counterparty": "0101234567", "amount": -5})
    assert negative.status_code == 422
    unknown = client.get("/home", params={"customer_id": "Z9999"})
    assert unknown.status_code == 404
