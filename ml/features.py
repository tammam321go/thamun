import math
from bisect import bisect_left, insort
from collections import Counter, defaultdict, deque
from datetime import timedelta

import pandas as pd

from data.personas import CATEGORIES, COUNTERPARTY_TYPES, MERCHANT_TYPES, OUT_TYPES

RISK_FEATURES = [
    "amt_ratio_type", "amt_pct", "amt_pct_type", "amt_ratio_max", "balance_share", "is_new_cp", "cp_count",
    "cp_age_days", "hour", "hour_share", "is_night", "n_1h", "n_24h", "sum_1h_ratio", "sum_24h_ratio",
    "new_cp_24h", "mins_since_last", "in_cp_ratio", "in_1h_ratio", "n_out", "type_idx", "cp_type_idx",
]

CAT_FEATURES = [
    "type_idx", "cp_type_idx", "merchant_idx", "log_amount", "hour", "dow", "dom", "cp_count", "is_new_cp",
    "prev_cat_idx", "amt_ratio_type", "amt_pct",
]

CAT_CATEGORICAL = ["type_idx", "cp_type_idx", "merchant_idx", "prev_cat_idx"]
RISK_CATEGORICAL = ["type_idx", "cp_type_idx"]


def index_of(items, value):
    try:
        return items.index(value)
    except ValueError:
        return -1


def median_sorted(values):
    n = len(values)
    if n == 0:
        return 0.0
    mid = n // 2
    return float(values[mid]) if n % 2 else (values[mid - 1] + values[mid]) / 2.0


class CustomerState:
    def __init__(self):
        self.out_sorted = []
        self.type_sorted = defaultdict(list)
        self.cp_count = Counter()
        self.cp_first = {}
        self.cp_cats = defaultdict(Counter)
        self.hours = [0] * 24
        self.n_out = 0
        self.max_out = 0
        self.recent = deque()
        self.incoming = deque()
        self.last_ts = None

    def prune(self, ts):
        day_ago = ts - timedelta(hours=24)
        while self.recent and self.recent[0][0] < day_ago:
            self.recent.popleft()
        three_days = ts - timedelta(hours=72)
        while self.incoming and self.incoming[0][0] < three_days:
            self.incoming.popleft()

    def features(self, txn):
        ts = txn["ts"]
        amount = float(txn["amount"])
        cp = txn["counterparty"]
        self.prune(ts)

        type_hist = self.type_sorted[txn["type"]]
        base = type_hist if len(type_hist) >= 3 else self.out_sorted
        usual = median_sorted(base) if base else amount
        usual_all = median_sorted(self.out_sorted) if self.out_sorted else amount

        hour_ago = ts - timedelta(hours=1)
        n_1h = sum(1 for t, _, _ in self.recent if t >= hour_ago)
        sum_1h = sum(a for t, a, _ in self.recent if t >= hour_ago)
        sum_24h = sum(a for _, a, _ in self.recent)
        new_24h = sum(1 for _, _, was_new in self.recent if was_new)
        in_cp = sum(a for _, a, c in self.incoming if c == cp)
        in_1h = sum(a for t, a, _ in self.incoming if t >= hour_ago)

        count = self.cp_count[cp]
        first = self.cp_first.get(cp)
        age = (ts - first).total_seconds() / 86400.0 if first is not None else 0.0
        cats = self.cp_cats.get(cp)
        prev_cat = cats.most_common(1)[0][0] if cats else None
        mins = (ts - self.last_ts).total_seconds() / 60.0 if self.last_ts is not None else 10080.0
        balance = float(txn.get("balance_before") or 0.0)

        return {
            "amount": amount,
            "usual_amount": usual,
            "log_amount": math.log1p(amount),
            "amt_ratio_type": min(amount / max(usual, 1.0), 50.0),
            "amt_pct": bisect_left(self.out_sorted, amount) / len(self.out_sorted) if self.out_sorted else 0.5,
            "amt_pct_type": bisect_left(type_hist, amount) / len(type_hist) if type_hist else 0.5,
            "amt_ratio_max": min(amount / max(self.max_out, 1.0), 10.0),
            "balance_share": min(amount / max(balance, 1.0), 1.5),
            "is_new_cp": int(count == 0),
            "cp_count": count,
            "cp_age_days": min(age, 365.0),
            "hour": ts.hour,
            "hour_share": (self.hours[ts.hour] + 1.0) / (self.n_out + 24.0),
            "is_night": int(ts.hour < 6),
            "n_1h": n_1h,
            "n_24h": len(self.recent),
            "sum_1h_ratio": min((sum_1h + amount) / max(usual_all, 1.0), 100.0),
            "sum_24h_ratio": min((sum_24h + amount) / max(usual_all, 1.0), 200.0),
            "new_cp_24h": new_24h,
            "mins_since_last": min(mins, 10080.0),
            "in_cp_amount": in_cp,
            "in_cp_ratio": min(in_cp / max(amount, 1.0), 5.0),
            "in_1h_ratio": min(in_1h / max(amount, 1.0), 5.0),
            "n_out": self.n_out,
            "type_idx": max(index_of(OUT_TYPES, txn["type"]), 0),
            "cp_type_idx": max(index_of(COUNTERPARTY_TYPES, txn["counterparty_type"]), 0),
            "merchant_idx": max(index_of(MERCHANT_TYPES, txn.get("merchant_type") or "none"), 0),
            "dow": ts.weekday(),
            "dom": ts.day,
            "prev_cat_idx": index_of(CATEGORIES, prev_cat) + 1 if prev_cat else 0,
        }

    def update(self, txn):
        ts = txn["ts"]
        amount = float(txn["amount"])
        cp = txn["counterparty"]
        if txn["direction"] == "out":
            was_new = self.cp_count[cp] == 0
            insort(self.out_sorted, amount)
            insort(self.type_sorted[txn["type"]], amount)
            self.cp_count[cp] += 1
            category = txn.get("category")
            if category:
                self.cp_cats[cp][category] += 1
            self.hours[ts.hour] += 1
            self.n_out += 1
            self.max_out = max(self.max_out, amount)
            self.recent.append((ts, amount, was_new))
        else:
            self.incoming.append((ts, amount, cp))
        self.cp_first.setdefault(cp, ts)
        self.last_ts = ts


def build_table(txns):
    rows = []
    keep = ["txn_id", "customer_id", "persona", "ts", "type", "category", "purpose", "is_scam", "scam_type", "incident_id", "unusual"]
    for _, group in txns.sort_values("ts").groupby("customer_id", sort=False):
        state = CustomerState()
        for txn in group.to_dict("records"):
            if txn["direction"] == "out":
                row = state.features(txn)
                for key in keep:
                    row[key] = txn[key]
                rows.append(row)
            state.update(txn)
    return pd.DataFrame(rows)


def load_transactions(path):
    df = pd.read_csv(path, parse_dates=["ts"], keep_default_na=False,
                     dtype={"counterparty": str, "incident_id": str, "unusual": str, "purpose": str})
    return df
