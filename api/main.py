import csv
import io
import json
import logging
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

load_dotenv()

from api import explain as ex
from api.db import Database, audit_logs, now_utc, scam_reports, ux_feedback
from api.engine import MODEL_DIR, Engine
from api.monitor import Monitor, evidence
from api.reports import DAILY_LIMIT, HIGH_SCORE, MEDIUM_SCORE, normalise
from api.schemas import (AskRequest, CheckRequest, FeedbackRequest, GoalRequest, LabelRequest, PayRequest, ReportRequest,
                         ResetRequest, SaveRequest, SessionRequest)
from api.security import (Principal, RateLimiter, admin, auth_required, authorise, bearer, hashed, issue_token, principal,
                          rate_limit, read_token)
from api.store import START_TIME, TYPE_COUNTERPARTY, Store
from data.personas import CATEGORIES, DISCRETIONARY
from ml import goals, review
from ml.bills import forecast
from ml.goals import month_key, previous_months

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("thamun")

if not (MODEL_DIR / "meta.json").exists():
    raise RuntimeError("Models not found. Run: python -m data.generate && python -m ml.train")

META = json.loads((MODEL_DIR / "meta.json").read_text())
FEATURE_LABELS = {
    "amt_ratio_type": "Amount vs usual for this payment type", "amt_pct": "Amount rank among past payments",
    "amt_pct_type": "Amount rank within this payment type", "amt_ratio_max": "Amount vs largest past payment",
    "balance_share": "Share of balance", "is_new_cp": "New recipient", "cp_count": "Times paid this recipient",
    "cp_age_days": "Days since first contact with recipient", "hour": "Hour of day",
    "hour_share": "How often the customer pays at this hour", "is_night": "Night-time payment",
    "n_1h": "Payments in the last hour", "n_24h": "Payments in the last 24 hours",
    "sum_1h_ratio": "Money out in the last hour vs usual", "sum_24h_ratio": "Money out in 24 hours vs usual",
    "new_cp_24h": "New recipients in 24 hours", "mins_since_last": "Minutes since last transaction",
    "in_cp_ratio": "Money received from this recipient", "in_1h_ratio": "Money received in the last hour",
    "n_out": "Length of payment history", "type_idx": "Payment type", "cp_type_idx": "Recipient type",
}
NUMBER_SHAPE = re.compile(r"^[A-Z0-9]{4,24}$")
NOT_REPORTABLE = {"biller", "operator", "merchant", "employer"}
API_VERSION = "2.0.0"
AUTH_LIMIT_PER_MINUTE = 30
RISK_LEVELS = {"silent": "low", "nudge": "medium", "pause": "high"}
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                    "Cache-Control": "no-store"}
db = Database()
store = Store(db=db)
engine = Engine()
limiter = RateLimiter()
monitor = Monitor()

app = FastAPI(title="Thamun API", version=API_VERSION)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


@app.middleware("http")
async def guard(request: Request, call_next):
    started = time.perf_counter()
    path = request.url.path
    if request.method != "OPTIONS":
        key = None
        token = bearer(request.headers.get("authorization"))
        if token:
            try:
                key = "s:" + read_token(token).sid
            except HTTPException:
                key = None
        elif not auth_required() and request.headers.get("x-session"):
            key = "s:" + request.headers["x-session"][:64]
        allowed, retry = limiter.allow(key or "ip:" + client_ip(request), rate_limit())
        if not allowed:
            monitor.record(path, 429, (time.perf_counter() - started) * 1000)
            return JSONResponse({"detail": "Too many requests. Try again in a moment."}, status_code=429,
                                headers={"Retry-After": str(retry)})
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error path=%s", path)
        monitor.record(path, 500, (time.perf_counter() - started) * 1000)
        return JSONResponse({"detail": "Something went wrong on our side."}, status_code=500)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    monitor.record(path, response.status_code, (time.perf_counter() - started) * 1000)
    return response


origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


def state_for(who: Principal, customer_id: str):
    authorise(who, customer_id)
    try:
        return store.session(who.sid, customer_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown customer")


def reporter_of(who: Principal, customer_id: str) -> str:
    return hashed(f"{who.sid}:{customer_id}")


def load_metrics() -> Optional[dict]:
    path = MODEL_DIR / "metrics.json"
    if path.exists():
        return json.loads(path.read_text())
    return evidence("metrics")


def protection_view(state) -> dict:
    pauses = [e for e in state.log if e["decision"] == "pause"]
    return {"checked": len(state.log), "pauses": len(pauses),
            "cancelled": sum(1 for e in pauses if e["outcome"] == "cancel"), "kept_safe": int(state.protected)}


def spending_view(state, lang: str) -> list:
    rows = []
    for category in DISCRETIONARY:
        base = state.profile.spend.baseline(category, state.now)
        total, count = state.profile.spend.week_total(category, state.now)
        if base and base["median"] > 0:
            rows.append({"category": category, "name": ex.category_name(category, lang), "week_total": int(round(total)),
                         "usual_week": int(round(base["median"])), "ratio": round(total / base["median"], 2),
                         "payments": count})
    return rows


def usage(session_key: Optional[str] = None) -> dict:
    query = select(audit_logs.c.event, audit_logs.c.decision, audit_logs.c.outcome, func.count().label("n"),
                   func.coalesce(func.sum(audit_logs.c.amount), 0).label("amount"))
    if session_key:
        query = query.where(audit_logs.c.session == session_key)
    rows = db.rows(query.group_by(audit_logs.c.event, audit_logs.c.decision, audit_logs.c.outcome))
    checks = {d: sum(r["n"] for r in rows if r["event"] == "check" and r["decision"] == d)
              for d in ("silent", "nudge", "pause", "ask_purpose", "insufficient")}
    final = checks["silent"] + checks["nudge"] + checks["pause"]

    def outcome(decision: str, action: str) -> int:
        return sum(r["n"] for r in rows if r["event"] == "pay" and r["decision"] == decision and r["outcome"] == action)

    def share(part: int, whole: int) -> Optional[float]:
        return round(part / whole, 4) if whole else None

    pause_cancel, pause_continue = outcome("pause", "cancel"), outcome("pause", "proceed")
    reports = select(func.count()).select_from(scam_reports).where(scam_reports.c.source == "app")
    if session_key:
        reports = reports.where(scam_reports.c.session == session_key)
    return {
        "source": "live use of this prototype with demo customers. Not real customers or real money",
        "payments_checked": final,
        "decisions": {k: checks[k] for k in ("silent", "nudge", "pause")},
        "decision_mix": {k: share(checks[k], final) for k in ("silent", "nudge", "pause")},
        "purpose_questions": checks["ask_purpose"],
        "purpose_question_rate": share(checks["ask_purpose"], final),
        "pauses_cancelled": pause_cancel,
        "pauses_continued": pause_continue,
        "cancellation_rate_after_pause": share(pause_cancel, pause_cancel + pause_continue),
        "override_rate_after_pause": share(pause_continue, pause_cancel + pause_continue),
        "nudges_continued": outcome("nudge", "proceed"),
        "nudges_cancelled": outcome("nudge", "cancel"),
        "amount_kept_after_pause": int(sum(r["amount"] for r in rows if r["event"] == "pay" and r["decision"] == "pause"
                                           and r["outcome"] == "cancel")),
        "scam_reports_filed": int(next(iter(db.rows(reports)[0].values()))),
    }


def feedback_summary() -> dict:
    rows = db.rows(select(ux_feedback))
    questions = ("understood_warning", "understood_reason", "intrusive", "understood_choice")
    return {
        "source": "answers typed by people who tried this prototype in user-testing mode. No real payments or accounts",
        "responses": len(rows),
        "questions": {q: {a: sum(1 for r in rows if r[q] == a) for a in ("yes", "partly", "no")} for q in questions},
        "preferred_language": {k: sum(1 for r in rows if r["preferred_lang"] == k) for k in ("bn", "en", "both")},
        "by_scenario": {k: sum(1 for r in rows if r["scenario"] == k) for k in sorted({r["scenario"] for r in rows})},
        "comments": len([r for r in rows if r["comment"]]),
    }


def explanations(decision, reasons, amount, lang, payment_type):
    out = {code: ex.explain(decision, reasons, amount, code, payment_type) for code in ex.LANGS}
    if decision in ("pause", "nudge"):
        out[lang] = ex.rephrase(out[lang])
    return out


def clean_number(raw):
    number = normalise(raw)
    if not NUMBER_SHAPE.match(number):
        raise HTTPException(status_code=400, detail="Enter the number using digits only.")
    return number


def number_view(state, who, customer_id, number, lang):
    status = store.reports.status(who.key, number, reporter_of(who, customer_id), state.now.date())
    known = store.plain.get(number)
    view = ex.number_check(status, store.dealings(state, number), lang)
    return dict(status, **view, name=store.lookup(customer_id, number, "send_money")["name"],
                can_report=not (known and known["type"] in NOT_REPORTABLE), report_options=ex.report_options(lang))


def txn_view(txn, lang="en"):
    return {
        "txn_id": txn["txn_id"], "ts": txn["ts"], "type": txn["type"], "direction": txn["direction"],
        "amount": int(txn["amount"]), "counterparty": txn["counterparty"],
        "name": txn.get("counterparty_name") or txn["counterparty"], "category": txn.get("category"),
        "category_name": ex.category_name(txn.get("category") or "other", lang), "label": txn.get("label"),
        "decision": txn.get("decision"),
    }


def bill_plan(state):
    today = state.now.date()
    books = state.profile.bills
    return forecast(state.profile.balance, books.upcoming(today), books.daily_spend(today), books.income(today), today,
                    books.daily_inflow(today))


def goal_view(state, lang="en"):
    if not state.goal:
        return None
    cuts = [dict(c, name=ex.category_name(c["category"], lang)) for c in state.goal["cuts"]]
    return dict(state.goal, cuts=cuts, progress=goals.progress(state.goal, state.profile.txns, state.now.date()))


def rewards(state, key):
    on_time, total = 0, 0
    for bill in state.profile.bills.recurring():
        if bill["type"] != "bill_payment":
            continue
        paid = [d for d, _, _, _ in state.profile.bills.payments[bill["counterparty"]] if month_key(d) == key]
        if paid:
            total += 1
            on_time += int(min(paid).day <= bill["day"] + 1)
    goal = goal_view(state)
    on_track = bool(goal and goal["progress"]["on_track"])
    return {"bills_paid": total, "bills_on_time": on_time, "goal_on_track": on_track,
            "points": on_time * 10 + (50 if on_track else 0), "simulated": True}


@app.get("/")
def root():
    return {"name": "Thamun API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"status": "ok", "version": API_VERSION, "demo_date": START_TIME.date(), "trained_at": META["trained_at"],
            "llm": bool(ex.llm_settings()), "database": db.backend, "database_ok": db.healthy(),
            "auth_required": auth_required()}


@app.post("/auth/session")
def auth_session(request: Request, body: Optional[SessionRequest] = None):
    allowed, retry = limiter.allow("auth:" + client_ip(request), int(os.getenv("AUTH_LIMIT_PER_MINUTE", AUTH_LIMIT_PER_MINUTE)))
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many new sessions. Try again in a moment.",
                            headers={"Retry-After": str(retry)})
    customer_id = body.customer_id if body else None
    if customer_id and customer_id not in store.customers:
        raise HTTPException(status_code=404, detail="Unknown customer")
    token = issue_token(customer_id)
    db.audit("auth", hashed(read_token(token["access_token"]).sid), customer_id or "")
    return token


@app.get("/customers")
def customers(who: Principal = Depends(principal)):
    out = []
    for customer_id, info in store.customers.items():
        out.append({"customer_id": customer_id, "name": info["name"], "persona": info["persona"],
                    "language": info["language"], "balance": int(store.balance(who.sid, customer_id))})
    return out


@app.get("/home")
def home(customer_id: str, lang: str = "en", who: Principal = Depends(principal)):
    state = state_for(who, customer_id)
    recent = [txn_view(t, lang) for t in reversed(state.profile.txns[-14:])]
    return {
        "customer": {k: state.info[k] for k in ("customer_id", "name", "persona", "language", "trusted_name")},
        "now": state.now, "balance": int(state.profile.balance), "recent": recent, "bills": bill_plan(state),
        "protected": int(state.protected), "goal": goal_view(state, lang),
        "protection": protection_view(state), "spending": spending_view(state, lang),
    }


@app.get("/payees")
def payees(customer_id: str, lang: str = "en", who: Principal = Depends(principal)):
    state = state_for(who, customer_id)
    return {"payees": store.payees(state), "purposes": ex.purpose_options(lang),
            "report_options": ex.report_options(lang),
            "categories": [{"code": c, "label": ex.category_name(c, lang)} for c in CATEGORIES],
            "custom_labels": sorted(set(state.labels.values()))}


def dry_run(state, who: Principal, customer_id: str, item: dict) -> dict:
    if item["amount"] > state.profile.balance:
        return {"expected": "insufficient", "asks_purpose": False}
    info = store.lookup(customer_id, item["counterparty"], item["type"])
    payment = {"type": item["type"], "amount": item["amount"], "counterparty": item["counterparty"],
               "counterparty_type": TYPE_COUNTERPARTY[item["type"]],
               "merchant_type": item.get("merchant_type") or info["merchant_type"]}
    report = store.reports.status(who.key, item["counterparty"], reporter_of(who, customer_id), state.now.date())
    first = engine.check(state.profile, payment, state.now, None, report)
    if first["decision"] != "ask_purpose":
        return {"expected": first["decision"], "asks_purpose": False}
    final = engine.check(state.profile, payment, state.now, item.get("purpose_hint") or "friend", report)
    return {"expected": final["decision"], "asks_purpose": True}


@app.get("/demo/script")
def demo_script(customer_id: str, who: Principal = Depends(principal)):
    state = state_for(who, customer_id)
    return [dict(item, **dry_run(state, who, customer_id, item)) for item in store.scenarios(state, who.key)]


@app.post("/demo/reset")
def demo_reset(body: ResetRequest, who: Principal = Depends(principal)):
    store.reset(who.sid, body.customer_id, who.key)
    return {"status": "reset"}


@app.post("/check")
def check(body: CheckRequest, background: BackgroundTasks, who: Principal = Depends(principal)):
    state = state_for(who, body.customer_id)
    balance = state.profile.balance
    if body.amount > balance:
        text = "ব্যালেন্স যথেষ্ট নয়।" if body.lang == "bn" else "You do not have enough balance for this payment."
        background.add_task(db.audit, "check", who.key, body.customer_id, payment_type=body.type, amount=int(body.amount),
                            decision="insufficient")
        return {"decision": "insufficient", "headline": text, "message": text, "balance_before": int(balance)}
    info = store.lookup(body.customer_id, body.counterparty, body.type)
    payment = {
        "type": body.type, "amount": body.amount, "counterparty": body.counterparty,
        "counterparty_type": TYPE_COUNTERPARTY[body.type],
        "merchant_type": body.merchant_type or info["merchant_type"],
    }
    report = store.reports.status(who.key, body.counterparty, reporter_of(who, body.customer_id), state.now.date())
    result = engine.check(state.profile, payment, state.now, body.purpose, report)
    decision = result["decision"]
    label = result["label"]
    name = body.counterparty_name or info["name"] or body.counterparty
    if decision == "ask_purpose":
        monitor.record_check(decision, None, None)
        background.add_task(db.audit, "check", who.key, body.customer_id, payment_type=body.type, amount=int(body.amount),
                            decision=decision)
        return {
            "decision": decision, "headline": ex.HEADLINES[decision][ex.lang_index(body.lang)],
            "purpose_options": ex.purpose_options(body.lang), "amount": int(body.amount), "counterparty": body.counterparty,
            "counterparty_name": name, "balance_before": int(balance),
            "label": {"category": label["label"], "confidence": round(label["confidence"], 3)},
            "details": {"new_recipient": bool(result["features"]["is_new_cp"]), "label_confident": label["confident"]},
        }
    texts = explanations(decision, result["reasons"], body.amount, body.lang, body.type)
    explanation = texts[body.lang]
    check_id = state.next_id("K")
    category = result["category"]
    state.pending[check_id] = {
        "payment": payment, "name": name, "purpose": body.purpose, "custom_label": body.custom_label,
        "category": category, "decision": decision, "reasons": result["reasons"],
        "risk": round(result["risk"]["probability"], 4), "lang": body.lang,
    }
    for stale in list(state.pending)[:-20]:
        state.pending.pop(stale, None)
    feats, risk = result["features"], result["risk"]
    codes = [r["code"] for r in result["reasons"]]
    log.info("check customer=%s type=%s amount=%s decision=%s risk=%.3f reasons=%s", body.customer_id, body.type,
             int(body.amount), decision, risk["probability"], codes)
    monitor.record_check(decision, risk["probability"], risk["high"])
    background.add_task(db.audit, "check", who.key, body.customer_id, payment_type=body.type, amount=int(body.amount),
                        decision=decision, risk=round(risk["probability"], 4), reasons=",".join(codes))
    return {
        "check_id": check_id, "decision": decision, "risk_level": RISK_LEVELS[decision],
        "headline": explanation["headline"],
        "message": explanation["message"], "reasons": explanation["reasons"], "advice": explanation["advice"],
        "explanation_source": explanation["source"],
        "i18n": {code: {k: text[k] for k in ("headline", "message", "reasons", "advice", "source")}
                 for code, text in texts.items()},
        "amount": int(body.amount), "counterparty": body.counterparty,
        "counterparty_name": name, "balance_before": int(balance), "balance_after": int(balance - body.amount),
        "trusted_name": state.info.get("trusted_name"),
        "label": {"category": category, "name": ex.category_name(category, body.lang),
                  "names": {code: ex.category_name(category, code) for code in ex.LANGS},
                  "confidence": round(label["confidence"], 3), "auto": body.purpose is None,
                  "custom": body.custom_label,
                  "alternatives": [{"label": a["label"], "confidence": round(a["confidence"], 3)} for a in label["alternatives"]]},
        "details": {
            "risk": {"probability": round(risk["probability"], 4), "threshold": round(engine.risk.threshold, 4),
                     "anomaly": round(risk["anomaly"], 3), "anomaly_threshold": round(engine.risk.iso_threshold, 3),
                     "high": risk["high"],
                     "contributions": [dict(c, label=FEATURE_LABELS.get(c["feature"], c["feature"])) for c in risk["contributions"]]},
            "rules": [r["code"] for r in result["reasons"] if r["code"] in ex.SCAM_CODES],
            "affordability": result["affordability"], "nudge": result["nudge"], "flags": result["flags"],
            "purpose": body.purpose,
            "reported": {k: report[k] for k in ("reports", "recent_reports", "score", "confidence", "pattern", "you_reported",
                                                "from_list", "from_session", "from_community")},
            "llm": dict(ex.llm_status(), used=explanation["source"] == "llm"),
            "features": {"usual_amount": int(round(feats["usual_amount"])), "amount_ratio": round(feats["amt_ratio_type"], 2),
                         "new_recipient": bool(feats["is_new_cp"]), "times_paid_before": int(feats["cp_count"]),
                         "balance_share": round(feats["balance_share"], 2), "payments_last_hour": int(feats["n_1h"]),
                         "received_from_recipient_72h": int(feats["in_cp_amount"])},
        },
    }


@app.post("/pay")
def pay(body: PayRequest, background: BackgroundTasks, who: Principal = Depends(principal)):
    state = state_for(who, body.customer_id)
    pending = state.pending.pop(body.check_id, None)
    if pending is None:
        raise HTTPException(status_code=404, detail="This check has expired. Start the payment again.")
    payment = pending["payment"]
    amount = float(payment["amount"])
    for reason in pending["reasons"]:
        if reason["code"] == "above_baseline":
            state.profile.spend.register(reason["category"], state.now)
        elif reason["code"] == "bill_due_soon":
            state.profile.spend.register_bill(reason)
    entry = {"ts": state.now, "type": payment["type"], "amount": int(amount), "name": pending["name"],
             "decision": pending["decision"], "risk": pending["risk"],
             "reasons": [r["code"] for r in pending["reasons"]], "outcome": body.action}
    background.add_task(db.audit, "pay", who.key, body.customer_id, payment_type=payment["type"], amount=int(amount),
                        decision=pending["decision"], risk=pending["risk"], outcome=body.action,
                        reasons=",".join(entry["reasons"]))
    if body.action == "cancel":
        if pending["decision"] == "pause":
            state.protected += amount
        state.log.append(entry)
        state.tick()
        return {"status": "cancelled", "balance": int(state.profile.balance), "protected": int(state.protected)}
    if not body.otp:
        raise HTTPException(status_code=400, detail="Enter the 4-digit demo OTP.")
    if amount > state.profile.balance:
        raise HTTPException(status_code=400, detail="Not enough balance.")
    before = state.profile.balance
    txn = {
        "txn_id": state.next_id("N"), "customer_id": body.customer_id, "ts": state.now, "type": payment["type"],
        "direction": "out", "amount": int(amount), "counterparty": payment["counterparty"],
        "counterparty_name": pending["name"], "counterparty_type": payment["counterparty_type"],
        "merchant_type": payment["merchant_type"], "category": pending["category"], "purpose": pending["purpose"] or "",
        "balance_before": int(before), "balance_after": int(before - amount), "decision": pending["decision"],
        "label": pending["custom_label"],
    }
    state.profile.add(txn)
    if pending["custom_label"]:
        state.labels[txn["txn_id"]] = pending["custom_label"]
    state.log.append(entry)
    state.tick()
    return {"status": "paid", "txn": txn_view(txn, pending["lang"]), "balance": int(state.profile.balance)}


@app.post("/label")
def label(body: LabelRequest, who: Principal = Depends(principal)):
    state = state_for(who, body.customer_id)
    txn = next((t for t in reversed(state.profile.txns) if t["txn_id"] == body.txn_id), None)
    if txn is None:
        raise HTTPException(status_code=404, detail="Unknown transaction")
    if body.category:
        state.profile.relabel(txn, body.category)
    if body.custom_label:
        txn["label"] = body.custom_label
        state.labels[txn["txn_id"]] = body.custom_label
    return {"status": "saved", "txn": txn_view(txn)}


@app.post("/cashin")
def cash_in(body: SaveRequest, who: Principal = Depends(principal)):
    state = state_for(who, body.customer_id)
    before = state.profile.balance
    state.profile.add({
        "txn_id": state.next_id("N"), "customer_id": body.customer_id, "ts": state.now, "type": "cash_in",
        "direction": "in", "amount": int(body.amount), "counterparty": "A-DEMO", "counterparty_name": "Agent point (demo)",
        "counterparty_type": "agent", "merchant_type": "none", "category": "cash_in", "purpose": "",
        "balance_before": int(before), "balance_after": int(before + body.amount),
    })
    state.tick()
    return {"status": "added", "balance": int(state.profile.balance)}


@app.get("/bills")
def bills(customer_id: str, who: Principal = Depends(principal)):
    state = state_for(who, customer_id)
    return dict(bill_plan(state), balance=int(state.profile.balance), today=state.now.date())


@app.get("/review")
def month_review(customer_id: str, month: str | None = None, lang: str = "en", who: Principal = Depends(principal)):
    state = state_for(who, customer_id)
    today = state.now.date()
    options = [month_key(today)] + previous_months(today, 2)
    key = options[1]
    if month:
        try:
            key = (int(month[:4]), int(month[5:7]))
        except ValueError:
            raise HTTPException(status_code=400, detail="Use month=YYYY-MM")
    data = review.summary(state.profile.txns, key, today)
    for item in data["categories"] + data["increases"] + data["decreases"]:
        item["name"] = ex.category_name(item["category"], lang)
    pauses = [e for e in state.log if e["decision"] == "pause"]
    data.update({
        "months": [f"{y}-{m:02d}" for y, m in options],
        "pattern": review.cashflow_pattern(state.profile.txns, today, state.profile.bills.income(today)),
        "rewards": rewards(state, key),
        "guard": {"pauses": len(pauses), "cancelled": sum(1 for e in pauses if e["outcome"] == "cancel"),
                  "protected": int(state.protected)},
        "nudges": sum(1 for e in state.log if e["decision"] == "nudge"),
        "goal": goal_view(state, lang),
    })
    return data


@app.get("/goal")
def goal_get(customer_id: str, lang: str = "en", who: Principal = Depends(principal)):
    return {"goal": goal_view(state_for(who, customer_id), lang)}


@app.post("/goal")
def goal_set(body: GoalRequest, who: Principal = Depends(principal)):
    state = state_for(who, body.customer_id)
    today = state.now.date()
    plan = goals.plan(state.profile.txns, body.target, body.months, today, state.profile.bills.income(today))
    state.goal = dict(plan, created=today.isoformat())
    return {"goal": goal_view(state, body.lang)}


@app.post("/goal/save")
def goal_save(body: SaveRequest, who: Principal = Depends(principal)):
    state = state_for(who, body.customer_id)
    if not state.goal:
        raise HTTPException(status_code=400, detail="Set a goal first.")
    if body.amount > state.profile.balance:
        raise HTTPException(status_code=400, detail="Not enough balance.")
    before = state.profile.balance
    state.profile.add({
        "txn_id": state.next_id("N"), "customer_id": body.customer_id, "ts": state.now, "type": "bill_payment",
        "direction": "out", "amount": int(body.amount), "counterparty": "GOAL", "counterparty_name": "Savings goal",
        "counterparty_type": "biller", "merchant_type": "bank", "category": "savings", "purpose": "savings",
        "balance_before": int(before), "balance_after": int(before - body.amount), "decision": "silent",
    })
    state.tick()
    return {"goal": goal_view(state, body.lang), "balance": int(state.profile.balance)}


@app.post("/ask")
def ask(body: AskRequest, who: Principal = Depends(principal)):
    state = state_for(who, body.customer_id)
    today = state.now.date()
    last_month = previous_months(today, 1)[0]
    summary = review.summary(state.profile.txns, last_month, today)
    facts = {
        "today": today, "balance": int(state.profile.balance),
        "review": {"month": summary["month"], "total_out": summary["total_out"], "total_in": summary["total_in"],
                   "categories": summary["categories"][:8]},
        "pattern": review.cashflow_pattern(state.profile.txns, today, state.profile.bills.income(today)),
        "bills": bill_plan(state), "goal": goal_view(state),
    }
    return ex.answer(body.question, facts, body.lang)


@app.get("/reports")
def reports_list(who: Principal = Depends(principal)):
    return store.reports.listing(who.key, START_TIME.date())


@app.get("/reports/options")
def reports_options(lang: str = "en"):
    return ex.report_options(lang)


@app.get("/reports/check")
def reports_check(customer_id: str, number: str, lang: str = "en", who: Principal = Depends(principal)):
    state = state_for(who, customer_id)
    return number_view(state, who, customer_id, clean_number(number), lang)


@app.post("/reports")
def reports_add(body: ReportRequest, who: Principal = Depends(principal)):
    state = state_for(who, body.customer_id)
    number = clean_number(body.number)
    known = store.plain.get(number)
    if known and known["type"] in NOT_REPORTABLE:
        raise HTTPException(status_code=400, detail="Only personal and agent numbers can be reported.")
    result = store.reports.add(who.key, reporter_of(who, body.customer_id), number, body.pattern, state.now.date())
    if result == "limit":
        raise HTTPException(status_code=429, detail=f"Report limit reached. A customer can file {DAILY_LIMIT} reports a day.")
    log.info("report customer=%s pattern=%s result=%s", body.customer_id, body.pattern, result)
    db.audit("report", who.key, body.customer_id, outcome=result)
    return dict(number_view(state, who, body.customer_id, number, body.lang), added=result == "added", result=result)


@app.get("/decisions")
def decisions(customer_id: str, who: Principal = Depends(principal)):
    return list(reversed(state_for(who, customer_id).log))


@app.get("/metrics")
def metrics():
    data = load_metrics()
    if data is None:
        raise HTTPException(status_code=404, detail="Run python -m ml.evaluate first.")
    return data


@app.get("/evidence")
def evidence_files():
    return {"label": "Synthetic evaluation. Every number comes from scripts in this repository, run on simulated data",
            "metrics": load_metrics(), "experiments": evidence("experiments"), "load_test": evidence("load_test"),
            "report_rule": {"medium_score": MEDIUM_SCORE, "high_score": HIGH_SCORE, "daily_limit": DAILY_LIMIT}}


@app.get("/analytics")
def analytics(scope: str = "session", who: Principal = Depends(principal)):
    return dict(usage(who.key if scope != "all" else None), scope="session" if scope != "all" else "all")


@app.post("/feedback")
def feedback_add(body: FeedbackRequest, request: Request, who: Principal = Depends(principal)):
    allowed, retry = limiter.allow("feedback:" + who.key, 20, 3600)
    if not allowed:
        raise HTTPException(status_code=429, detail="Feedback limit reached for now.", headers={"Retry-After": str(retry)})
    db.write(ux_feedback.insert().values(
        created_at=now_utc(), session=who.key, scenario=body.scenario, decision=body.decision or "", lang=body.lang,
        understood_warning=body.understood_warning, understood_reason=body.understood_reason, intrusive=body.intrusive,
        understood_choice=body.understood_choice, preferred_lang=body.preferred_lang, comment=body.comment or ""))
    return dict(feedback_summary(), status="saved")


@app.get("/feedback/summary")
def feedback_get():
    return feedback_summary()


@app.get("/admin/feedback/export", dependencies=[Depends(admin)])
def feedback_export():
    rows = db.rows(select(ux_feedback).order_by(ux_feedback.c.id))
    fields = ["id", "created_at", "scenario", "decision", "lang", "understood_warning", "understood_reason", "intrusive",
              "understood_choice", "preferred_lang", "comment"]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=thamun_user_testing.csv"})


@app.get("/admin/audit", dependencies=[Depends(admin)])
def audit_recent(limit: int = 200):
    rows = db.rows(select(audit_logs).order_by(audit_logs.c.id.desc()).limit(max(1, min(limit, 1000))))
    return rows


@app.get("/monitoring")
def monitoring():
    return dict(
        monitor.snapshot(), version=API_VERSION,
        model={"trained_at": META["trained_at"], "versions": META["versions"], "risk_threshold": round(engine.risk.threshold, 4),
               "anomaly_threshold": round(engine.risk.iso_threshold, 3), "label_threshold": engine.categorizer.threshold},
        database={"backend": db.backend, "ok": db.healthy(), "reports": store.reports.total()},
        security={"auth_required": auth_required(), "rate_limit_per_minute": rate_limit(), "cors_origins": origins},
        llm=ex.llm_status(), sessions_in_memory=len(store.sessions))
