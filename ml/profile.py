from datetime import timedelta

from ml.bills import BillBook
from ml.features import CustomerState
from ml.nudges import SpendTracker


class CustomerProfile:
    def __init__(self, customer_id, info=None):
        self.customer_id = customer_id
        self.info = info or {}
        self.state = CustomerState()
        self.spend = SpendTracker()
        self.bills = BillBook()
        self.txns = []
        self.balance = 0.0

    def add(self, txn):
        self.state.update(txn)
        self.spend.update(txn)
        self.bills.update(txn)
        self.txns.append(txn)
        if txn.get("balance_after") is not None:
            self.balance = float(txn["balance_after"])

    @classmethod
    def from_history(cls, customer_id, rows, info=None):
        profile = cls(customer_id, info)
        for txn in rows:
            profile.add(txn)
        return profile

    def relabel(self, txn, category):
        old = txn.get("category") or "other"
        if old == category or txn["direction"] != "out":
            return
        amount = float(txn["amount"])
        monday = txn["ts"].date() - timedelta(days=txn["ts"].weekday())
        week = self.spend.weeks[monday]
        week[old][0] -= amount
        week[old][1] -= 1
        week[category][0] += amount
        week[category][1] += 1
        counts = self.state.cp_cats[txn["counterparty"]]
        counts[old] -= 1
        counts[category] += 1
        txn["category"] = category
