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
    monkeypatch.setenv("LLM_DATA_RESIDENCY", "allow_external")
    monkeypatch.setattr(explain, "chat", lambda *a, **k: "This 9,000 transfer looks fine.")
    assert explain.rephrase(base)["source"] == "template"
    monkeypatch.setattr(explain, "chat", lambda *a, **k: "Careful: 8,000 is about 4 times your usual 2,000. Call 16247.")
    assert explain.rephrase(base)["source"] == "template"
    monkeypatch.setattr(explain, "chat", lambda *a, **k: "Careful: this 8,000 transfer is large.")
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


def test_confirmed_reports_pause_any_amount_and_lead_the_reasons():
    from api.engine import report_note, report_rule

    assert report_rule(None) == [] and report_note(None) == []
    assert report_rule({"reports": 0, "confidence": "none", "pattern": None}) == []
    rule = report_rule({"reports": 4, "recent_reports": 3, "confidence": "medium", "pattern": "prize_fee"})
    risk = {"high": False, "reasons": [{"code": "new_recipient"}]}
    decision, reasons, flags = decide({"type": "send_money", "amount": 20}, risk, rule, None, None)
    assert decision == "pause" and flags["rules"]
    assert reasons[0] == {"code": "reported_number", "count": 4, "pattern": "prize_fee", "confidence": "medium", "recent": 3}


def test_a_single_report_is_a_note_not_a_pause():
    from api.engine import report_note, report_rule

    one = {"reports": 1, "recent_reports": 1, "confidence": "low", "pattern": "refund"}
    assert report_rule(one) == []
    notes = report_note(one)
    decision, reasons, flags = decide({"type": "send_money", "amount": 5000}, quiet_risk(), [], None, None, notes=notes)
    assert decision == "nudge" and not flags["rules"]
    assert reasons == [{"code": "reported_unconfirmed", "count": 1}]


def test_report_confidence_needs_several_recent_reporters():
    from api.reports import reputation

    assert reputation([])["confidence"] == "none"
    assert reputation([1])["confidence"] == "low"
    assert reputation([1, 2])["confidence"] == "low"
    assert reputation([1, 2, 3])["confidence"] == "medium"
    assert reputation([200] * 10)["confidence"] == "low"
    assert reputation([40] * 6)["confidence"] == "medium"
    assert reputation([5] * 10)["confidence"] == "high"
    old = reputation([120, 130, 140])
    assert old["reports"] == 3 and old["recent_reports"] == 0 and old["score"] == 0.75


def test_report_book_counts_each_reporter_once(tmp_path):
    from api.db import Database
    from api.reports import DAILY_LIMIT, ReportBook, normalise
    from api.store import DEMO_DIR

    book = ReportBook(Database(f"sqlite:///{tmp_path / 'book.db'}"), DEMO_DIR / "reported_numbers.json")
    today = date(2026, 10, 8)
    number = "01012345678"
    assert normalise("+880 1012-345678") == number
    assert book.status("s1", number)["confidence"] == "none"
    assert book.add("s1", "r1", number, "pin_otp", today) == "added"
    assert book.add("s1", "r1", number, "pin_otp", today) == "duplicate"
    assert book.status("s1", number, "r1", today)["confidence"] == "low"
    assert book.add("s1", "r2", "+8801012345678", None, today) == "added"
    assert book.add("s1", "r3", number, "pin_otp", today) == "added"
    status = book.status("s1", number, "r1", today)
    assert status["reports"] == 3 and status["confidence"] == "medium"
    assert status["pattern"] == "pin_otp" and status["you_reported"] and status["from_session"] == 3
    seen_elsewhere = book.status("s2", number, "r9", today)
    assert seen_elsewhere["reports"] == 1 and seen_elsewhere["confidence"] == "low" and seen_elsewhere["from_community"] == 1
    assert not seen_elsewhere["you_reported"]
    for i in range(DAILY_LIMIT):
        assert book.add("s3", "busy", f"0105550000{i}", None, today) == "added"
    assert book.add("s3", "busy", "01055500009", None, today) == "limit"
    listed = book.seed[0]
    assert book.status("s2", listed["number"], today=today)["reports"] == listed["reports"]
    book.clear("s1")
    assert book.status("s1", number, today=today)["reports"] == 0
    assert book.status("s1", listed["number"], today=today)["reports"] == listed["reports"]


def test_demo_story_numbers_ignore_reports_from_other_visitors(tmp_path):
    from api.db import Database
    from api.reports import ReportBook
    from api.store import DEMO_DIR

    book = ReportBook(Database(f"sqlite:///{tmp_path / 'book.db'}"), DEMO_DIR / "reported_numbers.json")
    book.protected = {"01077001234"}
    today = date(2026, 10, 8)
    for session in ("a", "b", "c"):
        book.add(session, f"r-{session}", "01077001234", "refund", today)
        book.add(session, f"r-{session}", "01011112222", "refund", today)
    assert book.status("z", "01077001234", today=today)["confidence"] == "none"
    assert book.status("z", "01011112222", today=today)["confidence"] == "medium"
    assert book.status("a", "01077001234", today=today)["reports"] == 1


def test_reported_reason_exists_in_both_languages():
    reason = {"code": "reported_number", "count": 37, "pattern": "prize_fee", "confidence": "high", "recent": 10}
    english = explain.explain("pause", [reason], 50, "en")
    bangla = explain.explain("pause", [reason], 50, "bn")
    assert "37 people" in english["reasons"][0]["text"] and "37 জন" in bangla["reasons"][0]["text"]
    assert "10" in english["reasons"][0]["text"] and "10" in bangla["reasons"][0]["text"]
    assert english["advice"] and bangla["advice"] and english["advice"] != bangla["advice"]
    assert explain.render_reason({"code": "reported_number", "count": 1, "pattern": None}, 0, "en").startswith("1 person")
    soft = {"code": "reported_unconfirmed", "count": 1}
    assert explain.render_reason(soft, 0, "en") != explain.render_reason(soft, 0, "bn")
    assert "not confirmation" in explain.render_reason(soft, 0, "en")
    for names in list(explain.REPORT_PATTERNS.values()) + list(explain.REPORT_DETAILS.values()) + list(explain.NUMBER_CHECK.values()):
        assert all(names)


@pytest.mark.skipif(not trained, reason="models not trained yet")
def test_scam_number_check_and_reporting_end_to_end():
    from fastapi.testclient import TestClient

    from api.main import app, store

    client = TestClient(app)
    headers = {"X-Session": "pytest-reports"}
    other_session = {"X-Session": "pytest-reports-other"}
    client.post("/demo/reset", json={}, headers=headers)
    client.post("/demo/reset", json={}, headers=other_session)
    script = {s["id"]: s for s in client.get("/demo/script", params={"customer_id": "D0001"}, headers=headers).json()}
    known = set(store.directory) | {n for book in store.contacts.values() for n in book}
    assert not known & {row["number"] for row in store.reports.seed}
    assert all(item["expected"] == item["kind"] for item in script.values())

    def check(customer, number, amount, session=headers, lang="en"):
        body = {"customer_id": customer, "type": "send_money", "counterparty": number, "amount": amount, "lang": lang}
        return client.post("/check", json=body, headers=session).json()

    def look(number, lang="en"):
        return client.get("/reports/check", params={"customer_id": "D0001", "number": number, "lang": lang}, headers=headers).json()

    def report(customer, number, session=headers):
        return client.post("/reports", json={"customer_id": customer, "number": number, "pattern": "pin_otp"}, headers=session)

    for name in ("reported_small", "reported_usual"):
        item = script[name]
        result = check("D0001", item["counterparty"], item["amount"], lang="bn")
        assert result["decision"] == "pause" and result["risk_level"] == "high"
        assert result["reasons"][0]["code"] == "reported_number"
        assert result["details"]["reported"]["reports"] == item["reports"]
        assert result["details"]["reported"]["confidence"] == "high"
        assert result["i18n"]["bn"]["reasons"][0]["text"] == result["reasons"][0]["text"]
        assert str(item["reports"]) in result["i18n"]["en"]["reasons"][0]["text"]
        assert result["i18n"]["en"]["headline"] != result["i18n"]["bn"]["headline"]
    assert script["reported_small"]["amount"] <= 50

    once = check("D0001", script["reported_once"]["counterparty"], script["reported_once"]["amount"])
    assert once["decision"] == "nudge" and once["reasons"][0]["code"] == "reported_unconfirmed"
    assert look(script["reported_once"]["counterparty"])["verdict"] == "unconfirmed"

    fresh = "01033221100"
    assert check("D0001", fresh, 100)["decision"] == "silent"
    assert look(fresh)["verdict"] == "unknown"
    first = report("D0001", "+880 1033-221100").json()
    assert first["added"] and first["result"] == "added" and first["reports"] == 1
    assert first["verdict"] == "unconfirmed" and first["confidence"] == "low" and first["you_reported"]
    again = report("D0001", fresh).json()
    assert not again["added"] and again["result"] == "duplicate" and again["reports"] == 1
    soft = check("D0002", fresh, 100)
    assert soft["decision"] == "nudge" and soft["reasons"][0]["code"] == "reported_unconfirmed"
    assert report("D0002", fresh).json()["confidence"] == "low"
    third = report("D0003", fresh).json()
    assert third["reports"] == 3 and third["confidence"] == "medium" and third["verdict"] == "reported"
    hard = check("D0004", fresh, 100)
    assert hard["decision"] == "pause" and hard["reasons"][0]["code"] == "reported_number"
    elsewhere = check("D0002", fresh, 100, other_session)
    assert elsewhere["decision"] == "nudge" and elsewhere["details"]["reported"]["from_community"] == 1
    assert fresh in [row["number"] for row in client.get("/reports", headers=headers).json()]
    assert "reporter" not in client.get("/reports", headers=headers).text

    options = client.get("/reports/options", params={"lang": "bn"}).json()
    assert [o["code"] for o in options] == list(explain.REPORT_PATTERNS) and options[0]["label"] == explain.REPORT_PATTERNS["refund"][1]
    trusted = store.customers["D0001"]["trusted_contact"]
    assert look(trusted)["verdict"] == "known" and look(trusted, "bn")["headline"] != look(trusted)["headline"]
    assert report("D0001", "B-ELEC").status_code == 400
    assert client.get("/reports/check", params={"customer_id": "D0001", "number": "!!"}, headers=headers).status_code == 400

    client.post("/demo/reset", json={}, headers=headers)
    assert check("D0002", fresh, 100)["decision"] == "silent"
    assert look(script["reported_small"]["counterparty"])["confidence"] == "high"
