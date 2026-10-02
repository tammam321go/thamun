import json
import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api import explain as ex
from api.engine import MODEL_DIR, Engine
from api.schemas import AskRequest, CheckRequest, GoalRequest, LabelRequest, PayRequest, ResetRequest, SaveRequest
from api.store import START_TIME, TYPE_COUNTERPARTY, Store
from data.personas import CATEGORIES
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
store = Store()
engine = Engine()

app = FastAPI(title="Thamun API", version="1.0.0")
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


def state_for(session, customer_id):
    try:
        return store.session(session, customer_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown customer")


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
    return {"status": "ok", "demo_date": START_TIME.date(), "trained_at": META["trained_at"], "llm": bool(ex.llm_settings())}


@app.get("/customers")
def customers(x_session: str = Header(default="public")):
    out = []
    for customer_id, info in store.customers.items():
        out.append({"customer_id": customer_id, "name": info["name"], "persona": info["persona"],
                    "language": info["language"], "balance": int(store.balance(x_session, customer_id))})
    return out


@app.get("/home")
def home(customer_id: str, lang: str = "en", x_session: str = Header(default="public")):
    state = state_for(x_session, customer_id)
    recent = [txn_view(t, lang) for t in reversed(state.profile.txns[-14:])]
    return {
        "customer": {k: state.info[k] for k in ("customer_id", "name", "persona", "language", "trusted_name")},
        "now": state.now, "balance": int(state.profile.balance), "recent": recent, "bills": bill_plan(state),
        "protected": int(state.protected), "goal": goal_view(state, lang),
    }


@app.get("/payees")
def payees(customer_id: str, lang: str = "en", x_session: str = Header(default="public")):
    state = state_for(x_session, customer_id)
    return {"payees": store.payees(state), "purposes": ex.purpose_options(lang),
            "categories": [{"code": c, "label": ex.category_name(c, lang)} for c in CATEGORIES],
            "custom_labels": sorted(set(state.labels.values()))}


@app.get("/demo/script")
def demo_script(customer_id: str, x_session: str = Header(default="public")):
    return store.scenarios(state_for(x_session, customer_id))


@app.post("/demo/reset")
def demo_reset(body: ResetRequest, x_session: str = Header(default="public")):
    store.reset(x_session, body.customer_id)
    return {"status": "reset"}


@app.post("/check")
def check(body: CheckRequest, x_session: str = Header(default="public")):
    state = state_for(x_session, body.customer_id)
    balance = state.profile.balance
    if body.amount > balance:
        text = "ব্যালেন্স যথেষ্ট নয়।" if body.lang == "bn" else "You do not have enough balance for this payment."
        return {"decision": "insufficient", "headline": text, "message": text, "balance_before": int(balance)}
    info = store.lookup(body.customer_id, body.counterparty, body.type)
    payment = {
        "type": body.type, "amount": body.amount, "counterparty": body.counterparty,
        "counterparty_type": TYPE_COUNTERPARTY[body.type],
        "merchant_type": body.merchant_type or info["merchant_type"],
    }
    result = engine.check(state.profile, payment, state.now, body.purpose)
    decision = result["decision"]
    label = result["label"]
    name = body.counterparty_name or info["name"] or body.counterparty
    if decision == "ask_purpose":
        return {
            "decision": decision, "headline": ex.HEADLINES[decision][ex.lang_index(body.lang)],
            "purpose_options": ex.purpose_options(body.lang), "amount": int(body.amount), "counterparty": body.counterparty,
            "counterparty_name": name, "balance_before": int(balance),
            "label": {"category": label["label"], "confidence": round(label["confidence"], 3)},
            "details": {"new_recipient": bool(result["features"]["is_new_cp"]), "label_confident": label["confident"]},
        }
    explanation = ex.explain(decision, result["reasons"], body.amount, body.lang, body.type)
    if decision in ("pause", "nudge"):
        explanation = ex.rephrase(explanation)
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
    log.info("check customer=%s type=%s amount=%s decision=%s risk=%.3f reasons=%s", body.customer_id, body.type,
             int(body.amount), decision, risk["probability"], [r["code"] for r in result["reasons"]])
    return {
        "check_id": check_id, "decision": decision, "headline": explanation["headline"],
        "message": explanation["message"], "reasons": explanation["reasons"], "advice": explanation["advice"],
        "explanation_source": explanation["source"], "amount": int(body.amount), "counterparty": body.counterparty,
        "counterparty_name": name, "balance_before": int(balance), "balance_after": int(balance - body.amount),
        "trusted_name": state.info.get("trusted_name"),
        "label": {"category": category, "name": ex.category_name(category, body.lang),
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
            "features": {"usual_amount": int(round(feats["usual_amount"])), "amount_ratio": round(feats["amt_ratio_type"], 2),
                         "new_recipient": bool(feats["is_new_cp"]), "times_paid_before": int(feats["cp_count"]),
                         "balance_share": round(feats["balance_share"], 2), "payments_last_hour": int(feats["n_1h"]),
                         "received_from_recipient_72h": int(feats["in_cp_amount"])},
        },
    }


@app.post("/pay")
def pay(body: PayRequest, x_session: str = Header(default="public")):
    state = state_for(x_session, body.customer_id)
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
def label(body: LabelRequest, x_session: str = Header(default="public")):
    state = state_for(x_session, body.customer_id)
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
def cash_in(body: SaveRequest, x_session: str = Header(default="public")):
    state = state_for(x_session, body.customer_id)
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
def bills(customer_id: str, x_session: str = Header(default="public")):
    state = state_for(x_session, customer_id)
    return dict(bill_plan(state), balance=int(state.profile.balance), today=state.now.date())


@app.get("/review")
def month_review(customer_id: str, month: str | None = None, lang: str = "en", x_session: str = Header(default="public")):
    state = state_for(x_session, customer_id)
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
def goal_get(customer_id: str, lang: str = "en", x_session: str = Header(default="public")):
    return {"goal": goal_view(state_for(x_session, customer_id), lang)}


@app.post("/goal")
def goal_set(body: GoalRequest, x_session: str = Header(default="public")):
    state = state_for(x_session, body.customer_id)
    today = state.now.date()
    plan = goals.plan(state.profile.txns, body.target, body.months, today, state.profile.bills.income(today))
    state.goal = dict(plan, created=today.isoformat())
    return {"goal": goal_view(state, body.lang)}


@app.post("/goal/save")
def goal_save(body: SaveRequest, x_session: str = Header(default="public")):
    state = state_for(x_session, body.customer_id)
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
def ask(body: AskRequest, x_session: str = Header(default="public")):
    state = state_for(x_session, body.customer_id)
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


@app.get("/decisions")
def decisions(customer_id: str, x_session: str = Header(default="public")):
    return list(reversed(state_for(x_session, customer_id).log))


@app.get("/metrics")
def metrics():
    path = MODEL_DIR / "metrics.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run python -m ml.evaluate first.")
    return json.loads(path.read_text())
