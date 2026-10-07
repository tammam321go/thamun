import json
import os
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from api.db import Database
from api.reports import ReportBook, normalise
from data.personas import DEMO_TODAY, MERCHANT_CATEGORY
from ml.bills import median
from ml.features import load_transactions
from ml.profile import CustomerProfile

DEMO_DIR = Path(__file__).resolve().parent / "demo_data"
START_TIME = datetime(DEMO_TODAY.year, DEMO_TODAY.month, DEMO_TODAY.day, 13, 10)
STEP = timedelta(minutes=37)
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "120"))
DEMO_NUMBERS = ("01077001234", "01055009876", "A9999")
STUDY = {"bill": "normal", "routine": "normal", "friend": "normal", "food": "overspending", "refund": "new_recipient",
         "prize": "new_recipient", "takeover": "unusual", "reported_small": "reported", "reported_usual": "reported",
         "reported_once": "reported", "bill_risk": "bill_risk"}

TYPE_COUNTERPARTY = {"send_money": "person", "cash_out": "agent", "merchant_payment": "merchant",
                     "bill_payment": "biller", "mobile_recharge": "operator"}


class CustomerSession:
    def __init__(self, info, rows):
        self.info = info
        self.profile = CustomerProfile.from_history(info["customer_id"], rows, info)
        self.now = START_TIME
        self.pending = {}
        self.log = []
        self.goal = None
        self.counter = 0
        self.protected = 0
        self.labels = {}

    def tick(self):
        self.now = self.now + STEP

    def next_id(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter:04d}"


class Store:
    def __init__(self, folder=DEMO_DIR, db=None):
        folder = Path(folder)
        self.db = db or Database()
        self.customers = {c["customer_id"]: c for c in json.loads((folder / "customers.json").read_text())}
        self.contacts = json.loads((folder / "contacts.json").read_text())
        frame = load_transactions(folder / "transactions.csv")
        self.history = {}
        self.directory = {}
        for customer_id, group in frame.sort_values("ts").groupby("customer_id"):
            rows = group.to_dict("records")
            for row in rows:
                row["ts"] = row["ts"].to_pydatetime()
                self.directory[row["counterparty"]] = {
                    "name": row["counterparty_name"], "type": row["counterparty_type"], "merchant_type": row["merchant_type"]}
            self.history[customer_id] = rows
        self.plain = {normalise(key): value for key, value in self.directory.items()}
        self.sessions = OrderedDict()
        self.reports = ReportBook(self.db, folder / "reported_numbers.json")
        self.reports.protected = (set(self.plain) | {normalise(n) for book in self.contacts.values() for n in book}
                                  | {normalise(n) for n in DEMO_NUMBERS})

    def key(self, session_id):
        return (session_id or "public")[:64]

    def session(self, session_id, customer_id):
        if customer_id not in self.customers:
            raise KeyError(customer_id)
        key = self.key(session_id)
        bucket = self.sessions.get(key)
        if bucket is None:
            bucket = {}
            self.sessions[key] = bucket
            while len(self.sessions) > MAX_SESSIONS:
                self.sessions.popitem(last=False)
        else:
            self.sessions.move_to_end(key)
        if customer_id not in bucket:
            bucket[customer_id] = CustomerSession(self.customers[customer_id], self.history[customer_id])
        return bucket[customer_id]

    def balance(self, session_id, customer_id):
        bucket = self.sessions.get(self.key(session_id), {})
        if customer_id in bucket:
            return bucket[customer_id].profile.balance
        return float(self.history[customer_id][-1]["balance_after"])

    def reset(self, session_id, customer_id=None, report_key=None):
        key = self.key(session_id)
        if customer_id is None:
            self.sessions.pop(key, None)
            if report_key:
                self.reports.clear(report_key)
        elif key in self.sessions:
            self.sessions[key].pop(customer_id, None)

    def lookup(self, customer_id, counterparty, payment_type):
        known = self.directory.get(counterparty)
        name = self.contacts.get(customer_id, {}).get(counterparty) or (known["name"] if known else "")
        return {
            "name": name,
            "type": known["type"] if known else TYPE_COUNTERPARTY[payment_type],
            "merchant_type": known["merchant_type"] if known else "none",
        }

    def dealings(self, state, number):
        paid, received = [], 0.0
        for txn in state.profile.txns:
            if normalise(txn["counterparty"]) != number:
                continue
            if txn["direction"] == "out":
                paid.append(txn)
            else:
                received += float(txn["amount"])
        return {
            "times_paid": len(paid), "total_paid": int(sum(float(t["amount"]) for t in paid)),
            "first_paid": paid[0]["ts"].date() if paid else None,
            "last_paid": paid[-1]["ts"].date() if paid else None, "total_received": int(received),
        }

    def payees(self, state):
        txns = state.profile.txns
        groups = {"send_money": Counter(), "merchant_payment": Counter(), "cash_out": Counter(), "mobile_recharge": Counter()}
        amounts = {}
        for txn in txns:
            if txn["direction"] == "out" and txn["type"] in groups:
                groups[txn["type"]][txn["counterparty"]] += 1
                amounts.setdefault(txn["counterparty"], []).append(float(txn["amount"]))
        out = {}
        for payment_type, counter in groups.items():
            items = []
            for cp, count in counter.most_common(8):
                info = self.lookup(state.info["customer_id"], cp, payment_type)
                items.append({"counterparty": cp, "name": info["name"] or cp, "merchant_type": info["merchant_type"],
                              "times_paid": count, "usual_amount": int(round(median(amounts[cp])))})
            out[payment_type] = items
        today = state.now.date()
        out["bill_payment"] = [
            {"counterparty": b["counterparty"], "name": b["name"], "merchant_type": "utility", "category": b["category"],
             "usual_amount": b["amount"], "due_date": b["due_date"], "days_left": b["days_left"]}
            for b in state.profile.bills.upcoming(today) if b["type"] == "bill_payment"]
        return out

    def scenarios(self, state, session=""):
        payees = self.payees(state)
        balance = state.profile.balance
        sends = sorted(float(t["amount"]) for t in state.profile.txns if t["direction"] == "out" and t["type"] == "send_money")
        usual = median(sends) if sends else 500.0
        items = []
        bill = next((b for b in payees["bill_payment"] if b["days_left"] <= 3), None)
        if bill:
            items.append({"id": "bill", "kind": "silent", "type": "bill_payment", "counterparty": bill["counterparty"],
                          "name": bill["name"], "amount": bill["usual_amount"], "merchant_type": "utility"})
        food = next((m for m in payees["merchant_payment"] if MERCHANT_CATEGORY.get(m["merchant_type"]) == "eating_out"), None)
        if food:
            scripted = state.info["customer_id"] == "D0001"
            amount = 450 if scripted else food["usual_amount"]
            items.append({"id": "food", "kind": "nudge" if scripted else "silent", "type": "merchant_payment", "counterparty": food["counterparty"],
                          "name": food["name"], "amount": amount, "merchant_type": food["merchant_type"]})
        elif payees["merchant_payment"]:
            shop = payees["merchant_payment"][0]
            items.append({"id": "routine", "kind": "silent", "type": "merchant_payment", "counterparty": shop["counterparty"],
                          "name": shop["name"], "amount": shop["usual_amount"], "merchant_type": shop["merchant_type"]})
        refund = 8000 if state.info["customer_id"] == "D0001" else int(max(500, min(balance * 0.8, usual * 4)) // 100 * 100)
        items.append({"id": "refund", "kind": "pause", "type": "send_money", "counterparty": "01077001234", "fresh": True,
                      "name": "New number", "amount": refund, "merchant_type": "none", "purpose_hint": "refund_mistake"})
        items.append({"id": "prize", "kind": "pause", "type": "send_money", "counterparty": "01055009876", "fresh": True,
                      "name": "New number", "amount": int(max(500, min(balance * 0.5, usual * 1.5)) // 50 * 50),
                      "merchant_type": "none", "purpose_hint": "prize_fee"})
        items.append({"id": "takeover", "kind": "pause", "type": "cash_out", "counterparty": "A9999", "fresh": True,
                      "name": "Unknown agent point", "amount": int(max(500, balance * 0.9) // 100 * 100), "merchant_type": "none"})
        listed = sorted(self.reports.seed, key=lambda r: -int(r["reports"]))
        normal = int(max(300, min(usual, balance * 0.4)) // 50 * 50)
        today = state.now.date()
        for name, row, amount in zip(("reported_small", "reported_usual"), listed, (50, normal)):
            if amount <= balance:
                status = self.reports.status(session, row["number"], today=today)
                items.append({"id": name, "kind": "pause", "type": "send_money", "counterparty": row["number"], "fresh": True,
                              "name": "Reported number", "amount": amount, "merchant_type": "none",
                              "reports": status["reports"], "confidence": status["confidence"]})
        single = next((r for r in reversed(listed) if self.reports.status(session, r["number"], today=today)["confidence"] == "low"), None)
        if single and 200 <= balance:
            status = self.reports.status(session, single["number"], today=today)
            items.append({"id": "reported_once", "kind": "nudge", "type": "send_money", "counterparty": single["number"],
                          "fresh": True, "name": "Number with one report", "amount": 200, "merchant_type": "none",
                          "reports": status["reports"], "confidence": status["confidence"]})
        if payees["send_money"]:
            friend = payees["send_money"][0]
            items.append({"id": "friend", "kind": "silent", "type": "send_money", "counterparty": friend["counterparty"],
                          "name": friend["name"], "amount": friend["usual_amount"], "merchant_type": "none"})
            if bill:
                items.append({"id": "bill_risk", "kind": "pause", "type": "send_money", "counterparty": friend["counterparty"],
                              "name": friend["name"], "amount": 0, "merchant_type": "none", "search": True})
        for item in items:
            item["study"] = STUDY.get(item["id"], "free")
        return items
