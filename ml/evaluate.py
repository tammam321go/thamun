import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from api.engine import decide, is_unusual, needs_purpose, purpose_rules
from data.personas import CATEGORIES, TEST_START
from ml import categorizer, risk
from ml.bills import AFFORD_HORIZON, affordability, forecast
from ml.features import RISK_FEATURES, build_table, load_transactions
from ml.nudges import week_start
from ml.profile import CustomerProfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "out"
MODELS = ROOT / "ml" / "models"
DOCS = ROOT / "docs"
EVIDENCE = ROOT / "api" / "evidence"
SCORED = ["is_new_cp", "cp_age_days", "cp_count", "in_cp_amount", "amt_ratio_type", "confident", "high"]


def rate(numerator, denominator):
    return round(float(numerator) / float(denominator), 4) if denominator else None


def wilson(successes, total, z=1.96):
    if not total:
        return None
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / (1 + z * z / total)
    return [round(max(centre - half, 0.0), 4), round(min(centre + half, 1.0), 4)]


def replay(txns, scored, bill_events):
    due_checks = defaultdict(list)
    for event in bill_events.to_dict("records"):
        due_checks[(event["customer_id"], event["due_date"] - timedelta(days=3))].append(event)
    start = pd.Timestamp(TEST_START)
    decisions, nudges, flags = [], [], []
    detected = {}
    for customer_id, group in txns.groupby("customer_id", sort=False):
        profile = CustomerProfile(customer_id)
        balance = float(group["balance_before"].iloc[0])
        seen_days = set()
        for txn in group.to_dict("records"):
            ts = txn["ts"]
            day = ts.date()
            if ts >= start and customer_id not in detected:
                detected[customer_id] = profile.bills.recurring()
            if ts >= start and day not in seen_days:
                seen_days.add(day)
                for event in due_checks.get((customer_id, day), []):
                    upcoming = profile.bills.upcoming(day, horizon=10)
                    plan = forecast(balance, upcoming, profile.bills.daily_spend(day), profile.bills.income(day), day,
                                    profile.bills.daily_inflow(day))
                    row = next((b for b in plan["bills"] if b["counterparty"] == event["counterparty"]), None)
                    flags.append({"customer_id": customer_id, "counterparty": event["counterparty"],
                                  "known": row is not None, "flagged": bool(row and row["shortfall"] > 0),
                                  "truth": bool(event["short_on_due"]),
                                  "due_error": abs((row["due_date"] - event["due_date"]).days) if row else None,
                                  "amount_error": abs(row["amount"] - event["amount"]) / event["amount"] if row else None})
            if txn["direction"] == "out" and ts >= start:
                s = scored[txn["txn_id"]]
                feats = {"is_new_cp": s["is_new_cp"], "cp_age_days": s["cp_age_days"], "cp_count": s["cp_count"],
                         "in_cp_amount": s["in_cp_amount"], "amt_ratio_type": s["amt_ratio_type"]}
                asked = needs_purpose(txn, feats, s["confident"])
                rules = purpose_rules(txn, txn["purpose"], feats) if asked else []
                upcoming = profile.bills.upcoming(day, horizon=AFFORD_HORIZON)
                afford = affordability(balance, txn["amount"], upcoming, paying=txn["counterparty"],
                                       daily_inflow=profile.bills.daily_inflow(day))
                nudge = profile.spend.check(txn["category"], txn["amount"], ts)
                bill_nudge = bool(afford) and not profile.spend.bill_seen(afford)
                decision, reasons, why = decide(txn, {"high": s["high"], "reasons": []}, rules, afford, nudge,
                                                is_unusual(feats), bill_nudge)
                if decision == "nudge":
                    for reason in reasons:
                        if reason["code"] == "bill_due_soon":
                            profile.spend.register_bill(afford)
                            nudges.append({"customer_id": customer_id, "week": week_start(ts), "category": "bill"})
                        else:
                            profile.spend.register(txn["category"], ts)
                            nudges.append({"customer_id": customer_id, "week": week_start(ts), "category": txn["category"]})
                decisions.append({"txn_id": txn["txn_id"], "decision": decision, "asked": asked,
                                  "behaviour": why["behaviour"], "rules": why["rules"], "shortfall": why["shortfall"]})
            profile.add(txn)
            balance = float(txn["balance_after"])
    return pd.DataFrame(decisions), pd.DataFrame(nudges), pd.DataFrame(flags), detected


def guard_metrics(test, customers):
    scams = test[test.is_scam == 1]
    legit = test[test.is_scam == 0]
    safety = test.behaviour | test.rules
    first = scams.sort_values("ts").groupby("incident_id").head(1)
    stopped = scams[scams.decision == "pause"].groupby("incident_id").size()
    return {
        "scam_payments": int(len(scams)),
        "scam_incidents": int(scams.incident_id.nunique()),
        "recall_payments": rate((scams.decision == "pause").sum(), len(scams)),
        "recall_payments_interval": wilson(int((scams.decision == "pause").sum()), len(scams)),
        "recall_first_payment": rate((first.decision == "pause").sum(), len(first)),
        "recall_incidents_any": rate(len(stopped), scams.incident_id.nunique()),
        "recall_money": rate(scams[scams.decision == "pause"].amount.sum(), scams.amount.sum()),
        "recall_model_only": rate(scams.behaviour.sum(), len(scams)),
        "recall_rules_only": rate(scams.rules.sum(), len(scams)),
        "false_pauses_per_customer_month": rate((legit.decision.eq("pause") & safety[legit.index]).sum(), customers),
        "affordability_pauses_per_customer_month": rate((legit.decision.eq("pause") & ~safety[legit.index]).sum(), customers),
        "all_pauses_per_customer_month": rate(test.decision.eq("pause").sum(), customers),
        "pause_precision": rate(scams.decision.eq("pause").sum(), (test.decision.eq("pause") & safety).sum()),
    }


def friction(test):
    total = len(test)
    legit = test[test.is_scam == 0]
    return {
        "legit_paused": rate((legit.decision == "pause").sum(), len(legit)),
        "payments": int(total),
        "silent": rate((test.decision == "silent").sum(), total),
        "nudge": rate((test.decision == "nudge").sum(), total),
        "pause": rate((test.decision == "pause").sum(), total),
        "asked_purpose": rate(test.asked.sum(), total),
        "no_interruption": rate(((test.decision == "silent") & ~test.asked).sum(), total),
    }


def load_models(folder=MODELS):
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text())
    return {"meta": meta, "categorizer": lgb.Booster(model_file=str(folder / categorizer.MODEL_FILE)),
            "risk": lgb.Booster(model_file=str(folder / risk.MODEL_FILE)), "isolation": joblib.load(folder / risk.ISO_FILE)}


def score_table(table, models):
    meta = models["meta"]
    predicted, confidence = categorizer.predict_table(models["categorizer"], table)
    prob = models["risk"].predict(table[RISK_FEATURES])
    anomaly = risk.isolation_scores(models["isolation"], meta["risk"]["iso_scale"], table)
    return table.assign(
        predicted=[CATEGORIES[i] for i in predicted], confidence=confidence,
        confident=confidence >= meta["categorizer"]["threshold"], prob=prob, anomaly=anomaly,
        high=(prob >= meta["risk"]["threshold"]) | (anomaly >= meta["risk"]["iso_threshold"]))


def load_bill_events(folder=DATA):
    bill_events = pd.read_csv(Path(folder) / "bill_events.csv", parse_dates=["due_date", "paid_ts"])
    bill_events["due_date"] = bill_events["due_date"].dt.date
    return bill_events[bill_events["due_date"] >= TEST_START]


def run(txns, table, bill_events):
    scored = table.set_index("txn_id")[SCORED].to_dict("index")
    decisions, nudges, flags, detected = replay(txns.sort_values("ts"), scored, bill_events)
    test = table.merge(decisions, on="txn_id")
    test["amount"] = test["amount"].astype(float)
    return test, nudges, flags, detected


def main():
    models = load_models()
    meta = models["meta"]
    txns = load_transactions(DATA / "transactions.csv")
    table = score_table(build_table(txns), models)
    test, nudges, flags, detected = run(txns, table, load_bill_events())
    customers = txns["customer_id"].nunique()
    personas = txns.drop_duplicates("customer_id").set_index("customer_id")["persona"]

    correct = test.predicted == test.category
    labels = {
        "test_payments": int(len(test)),
        "accuracy": rate(correct.sum(), len(test)),
        "auto_label_share": rate(test.confident.sum(), len(test)),
        "auto_label_accuracy": rate(correct[test.confident].sum(), test.confident.sum()),
        "asked_share": rate(test.asked.sum(), len(test)),
        "not_asked_share": rate((~test.asked).sum(), len(test)),
    }

    guard = guard_metrics(test, customers)
    by_type = {t: {"payments": int(len(g)), "paused": rate((g.decision == "pause").sum(), len(g))}
               for t, g in test[test.is_scam == 1].groupby("scam_type")}
    unusual = test[(test.is_scam == 0) & (test.unusual != "")]
    by_persona = {}
    for persona, group in test.groupby("persona"):
        by_persona[persona] = guard_metrics(group, int((personas == persona).sum()))

    truth = pd.read_csv(DATA / "recurring_truth.csv", dtype={"counterparty": str})
    truth_set = set(zip(truth.customer_id, truth.counterparty))
    found_set = {(c, b["counterparty"]) for c, items in detected.items() for b in items}
    known = flags[flags.known] if len(flags) else flags
    bills = {
        "recurring_truth": len(truth_set),
        "detection_recall": rate(len(truth_set & found_set), len(truth_set)),
        "detection_precision": rate(len(truth_set & found_set), len(found_set)),
        "test_bills": int(len(flags)),
        "due_date_mae_days": round(float(known.due_error.mean()), 2) if len(known) else None,
        "amount_mape": round(float(known.amount_error.mean()), 4) if len(known) else None,
        "shortfalls": int(flags.truth.sum()),
        "shortfall_recall_3_days_ahead": rate((flags.truth & flags.flagged).sum(), flags.truth.sum()),
        "shortfall_precision": rate((flags.truth & flags.flagged).sum(), flags.flagged.sum()),
    }

    usual = pd.read_csv(DATA / "spend_truth.csv").set_index(["customer_id", "category"])["weekly_mean"].to_dict()
    out = txns[(txns.direction == "out") & (txns.ts >= pd.Timestamp(TEST_START))].copy()
    out["week"] = out.ts.map(week_start)
    totals = out.groupby(["customer_id", "week", "category"]).amount.sum().to_dict()
    spend_nudges = nudges[nudges.category != "bill"] if len(nudges) else nudges
    bill_nudges = nudges[nudges.category == "bill"] if len(nudges) else nudges
    above = 0
    nudged = set()
    for n in spend_nudges.to_dict("records"):
        key = (n["customer_id"], n["week"], n["category"])
        nudged.add(key)
        mean = usual.get((n["customer_id"], n["category"]), 0.0)
        above += int(mean > 0 and totals.get(key, 0.0) >= 1.25 * mean)
    clear = {k for k, total in totals.items()
             if usual.get((k[0], k[2]), 0.0) > 0 and k[2] in ("eating_out", "shopping", "transport")
             and total >= 1.5 * usual[(k[0], k[2])] and total - usual[(k[0], k[2])] >= 200}
    per_week = spend_nudges.groupby(["customer_id", "week"]).size() if len(spend_nudges) else pd.Series(dtype=int)
    nudge = {
        "spending_nudges": int(len(spend_nudges)),
        "spending_nudges_per_customer_month": rate(len(spend_nudges), customers),
        "bill_nudges_per_customer_month": rate(len(bill_nudges), customers),
        "precision_truly_above_usual": rate(above, len(spend_nudges)),
        "clear_overspend_weeks": len(clear),
        "clear_overspend_weeks_nudged": rate(len(clear & nudged), len(clear)),
        "max_per_customer_week": int(per_week.max()) if len(per_week) else 0,
    }

    metrics = {
        "test_month": str(TEST_START)[:7], "customers": int(customers), "labels": labels, "guard": guard,
        "friction": friction(test),
        "guard_by_scam_type": by_type, "guard_by_persona": by_persona,
        "unusual_legit_paused_share": rate((unusual.decision.eq("pause") & (unusual.behaviour | unusual.rules)).sum(), len(unusual)),
        "bills": bills, "nudges": nudge, "thresholds": {"risk": meta["risk"]["threshold"],
        "isolation": meta["risk"]["iso_threshold"], "label_confidence": meta["categorizer"]["threshold"]},
    }
    (MODELS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "metrics.json").write_text(json.dumps(metrics, indent=2))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "evaluation.md").write_text(report(metrics))
    print(report(metrics))


def pct(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


def report(m):
    g, l, b, n, f = m["guard"], m["labels"], m["bills"], m["nudges"], m["friction"]
    lines = [
        "# Evaluation on the held-out month",
        "",
        f"Test month: {m['test_month']} (never used for training or threshold selection). Customers: {m['customers']}.",
        "All data is synthetic. Scam attempts are oversampled, so precision would be lower at real-world rates.",
        "",
        "## Guard",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Scam payments in test month | {g['scam_payments']} in {g['scam_incidents']} incidents |",
        f"| Scam payments paused | {pct(g['recall_payments'])} (95% interval {pct(g['recall_payments_interval'][0])} to {pct(g['recall_payments_interval'][1])}) |",
        f"| Incidents paused at the first payment | {pct(g['recall_first_payment'])} |",
        f"| Scam money paused | {pct(g['recall_money'])} |",
        f"| Caught by the behaviour model alone | {pct(g['recall_model_only'])} |",
        f"| Caught by purpose rules alone | {pct(g['recall_rules_only'])} |",
        f"| False pauses per customer per month | {g['false_pauses_per_customer_month']} |",
        f"| Affordability pauses per customer per month | {g['affordability_pauses_per_customer_month']} |",
        f"| Unusual but legitimate payments paused | {pct(m['unusual_legit_paused_share'])} |",
        "",
        "### By scam type",
        "",
        "| Scam type | Payments in test month | Payments paused |",
        "|---|---|---|",
    ]
    lines += [f"| {k} | {v['payments']} | {pct(v['paused'])} |" for k, v in m["guard_by_scam_type"].items()]
    lines += ["", "### Fairness by persona", "",
              "| Persona | Scam payments paused | False pauses per customer-month | All pauses per customer-month |", "|---|---|---|---|"]
    lines += [f"| {k} | {pct(v['recall_payments'])} | {v['false_pauses_per_customer_month']} | {v['all_pauses_per_customer_month']} |"
              for k, v in m["guard_by_persona"].items()]
    lines += [
        "", "## Customer experience (alert fatigue)", "", "| Metric | Value |", "|---|---|",
        f"| Outgoing payments in the test month | {f['payments']} |",
        f"| Went straight to OTP with no question and no message | {pct(f['no_interruption'])} |",
        f"| Silent decisions | {pct(f['silent'])} |",
        f"| Nudges (one line, payment continues) | {pct(f['nudge'])} |",
        f"| Pauses (full screen, customer still decides) | {pct(f['pause'])} |",
        f"| Genuine payments that were paused | {pct(f['legit_paused'])} |",
        f"| Asked \"what is this payment for?\" | {pct(f['asked_purpose'])} |",
        "", "## Labels", "", "| Metric | Value |", "|---|---|",
        f"| Category accuracy | {pct(l['accuracy'])} |",
        f"| Auto-labelled with confidence | {pct(l['auto_label_share'])} |",
        f"| Accuracy of auto-labels | {pct(l['auto_label_accuracy'])} |",
        f"| Payments completed without asking the purpose | {pct(l['not_asked_share'])} |",
        "", "## Bills", "", "| Metric | Value |", "|---|---|",
        f"| Recurring bills found (recall) | {pct(b['detection_recall'])} |",
        f"| Detected bills that are real (precision) | {pct(b['detection_precision'])} |",
        f"| Due date error | {b['due_date_mae_days']} days |",
        f"| Amount error | {pct(b['amount_mape'])} |",
        f"| Shortfalls flagged 3 days ahead (recall) | {pct(b['shortfall_recall_3_days_ahead'])} |",
        f"| Shortfall flags that were right (precision) | {pct(b['shortfall_precision'])} |",
        "", "## Nudges", "", "| Metric | Value |", "|---|---|",
        f"| Spending nudges per customer per month | {n['spending_nudges_per_customer_month']} |",
        f"| Bill-due nudges per customer per month | {n['bill_nudges_per_customer_month']} |",
        f"| Nudges in weeks truly above the customer's usual | {pct(n['precision_truly_above_usual'])} |",
        f"| Clear overspending weeks (50% above usual) that got a nudge | {pct(n['clear_overspend_weeks_nudged'])} of {n['clear_overspend_weeks']} |",
        f"| Most spending nudges for one customer in one week | {n['max_per_customer_week']} |",
        "",
        "## Limits of this evaluation",
        "",
        "- The models are trained and tested on data from the same simulator, so these numbers are optimistic. Real scams will differ from the injected ones.",
        "- The test month holds few scam payments, which is why the interval above is wide.",
        "- A scam where a known contact's account is used (impersonation) looks like a normal transfer to a friend, and most of those are missed.",
        "- Scam attempts are injected far more often than they happen in reality. False pauses per customer per month do not depend on that rate, so that figure is the one to compare.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
