from pathlib import Path

from data.personas import PURPOSES
from ml.bills import AFFORD_HORIZON, affordability
from ml.categorizer import Categorizer
from ml.risk import RiskModel

ASK_MIN = 500
MATERIAL_MIN = 300
SHORTFALL_MIN = 500
BILL_NUDGE_DAYS = 3
BEHAVIOUR_ORDER = ["amount_vs_usual", "new_recipient", "recent_recipient", "balance_share", "rapid_sequence",
                   "several_new_recipients", "unusual_time"]

MODEL_DIR = Path(__file__).resolve().parents[1] / "ml" / "models"


def needs_purpose(txn, feats, confident):
    if txn["type"] != "send_money" or txn["amount"] < ASK_MIN:
        return False
    recent = feats["cp_age_days"] < 1.0 and feats["cp_count"] <= 3
    return bool(feats["is_new_cp"] or recent or not confident)


def purpose_rules(txn, purpose, feats):
    if purpose == "refund_mistake":
        received = float(feats["in_cp_amount"])
        if received <= 0:
            return [{"code": "refund_no_incoming"}]
        if txn["amount"] > received * 1.05:
            return [{"code": "refund_exceeds_incoming", "received": int(received), "amount": int(txn["amount"])}]
        return []
    if purpose == "prize_fee":
        return [{"code": "prize_fee"}]
    if purpose == "agent_request":
        return [{"code": "agent_request"}]
    return []


def report_rule(report):
    if report and report.get("confidence") in ("medium", "high"):
        return [{"code": "reported_number", "count": int(report["reports"]), "pattern": report.get("pattern"),
                 "confidence": report["confidence"], "recent": int(report.get("recent_reports", 0))}]
    return []


def report_note(report):
    if report and report.get("confidence") == "low":
        return [{"code": "reported_unconfirmed", "count": int(report["reports"])}]
    return []


def is_unusual(feats):
    ratio = feats["amt_ratio_type"]
    return bool(ratio >= 3.0 or (feats["is_new_cp"] and ratio >= 1.5))


def decide(txn, risk, rules, afford, nudge, unusual=False, bill_nudge=True, notes=()):
    behaviour = bool(risk["high"]) and txn["amount"] >= MATERIAL_MIN
    shortfall = bool(afford and afford["caused"] and unusual and afford["days_left"] <= BILL_NUDGE_DAYS
                     and txn["type"] != "bill_payment" and txn["amount"] >= SHORTFALL_MIN)
    flags = {"behaviour": behaviour, "rules": bool(rules), "shortfall": shortfall}
    if behaviour or rules or shortfall:
        reasons = []
        if behaviour or rules:
            ranked = sorted(risk["reasons"], key=lambda r: BEHAVIOUR_ORDER.index(r["code"]))
            reasons.extend(ranked[:3] if behaviour else ranked[:2])
            if behaviour and not reasons:
                reasons.append({"code": "unusual_pattern"})
        reasons.extend(rules)
        reasons.extend(notes)
        if afford:
            reasons.append(afford)
        reasons.sort(key=lambda r: r["code"] != "reported_number")
        return "pause", reasons, flags
    reasons = list(notes)
    if afford and bill_nudge and afford["days_left"] <= BILL_NUDGE_DAYS:
        reasons.append(dict(afford, code="bill_due_soon"))
    if nudge:
        reasons.append(nudge)
    return ("nudge" if reasons else "silent"), reasons, flags


class Engine:
    def __init__(self, model_dir=MODEL_DIR):
        self.categorizer = Categorizer.load(model_dir)
        self.risk = RiskModel.load(model_dir)

    def check(self, profile, payment, now, purpose=None, report=None):
        txn = {
            "ts": now, "type": payment["type"], "direction": "out", "amount": float(payment["amount"]),
            "counterparty": payment["counterparty"], "counterparty_type": payment["counterparty_type"],
            "merchant_type": payment.get("merchant_type") or "none", "balance_before": profile.balance,
        }
        feats = profile.state.features(txn)
        label = self.categorizer.predict(feats)
        result = {"txn": txn, "features": feats, "label": label, "purpose": purpose}
        reported = report_rule(report)
        notes = report_note(report)
        if purpose is None and not reported and needs_purpose(txn, feats, label["confident"]):
            return dict(result, decision="ask_purpose", reasons=[], flags={}, risk=None, category=label["label"])
        category = label["label"]
        if purpose in PURPOSES and (not label["confident"] or feats["is_new_cp"] or PURPOSES[purpose]["scam_story"]):
            category = PURPOSES[purpose]["category"]
        risk = self.risk.score(feats)
        rules = reported + purpose_rules(txn, purpose, feats)
        upcoming = profile.bills.upcoming(now.date(), horizon=AFFORD_HORIZON)
        afford = affordability(profile.balance, txn["amount"], upcoming, paying=txn["counterparty"],
                               daily_inflow=profile.bills.daily_inflow(now.date()))
        nudge = profile.spend.check(category, txn["amount"], now)
        bill_nudge = bool(afford) and not profile.spend.bill_seen(afford)
        decision, reasons, flags = decide(txn, risk, rules, afford, nudge, is_unusual(feats), bill_nudge, notes)
        flags["reported"] = bool(reported)
        flags["reported_unconfirmed"] = bool(notes)
        return dict(result, decision=decision, reasons=reasons, flags=flags, risk=risk, category=category,
                    affordability=afford, nudge=nudge)
