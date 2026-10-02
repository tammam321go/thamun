from collections import defaultdict
from datetime import timedelta

from data.personas import DISCRETIONARY, EID_WINDOWS

LOOKBACK_WEEKS = 8
MIN_WEEKS = 4
RATIO = 1.25
FESTIVAL_RATIO = 1.5
SPREAD_FACTOR = 1.5
MIN_EXCESS = 200
WEEKLY_CAP = 2


def week_start(ts):
    d = ts.date() if hasattr(ts, "date") else ts
    return d - timedelta(days=d.weekday())


def is_festival_week(monday):
    sunday = monday + timedelta(days=6)
    return any(a <= sunday and monday <= b for a, b in EID_WINDOWS)


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return float(ordered[mid]) if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


class SpendTracker:
    def __init__(self):
        self.weeks = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
        self.income_weeks = set()
        self.incoming = []
        self.first_week = None
        self.nudges = defaultdict(int)
        self.nudged = set()
        self.bill_nudged = set()

    def update(self, txn):
        monday = week_start(txn["ts"])
        if self.first_week is None:
            self.first_week = monday
        amount = float(txn["amount"])
        if txn["direction"] == "out":
            cell = self.weeks[monday][txn.get("category") or "other"]
            cell[0] += amount
            cell[1] += 1
            return
        if txn["type"] == "cash_in":
            return
        typical = median(self.incoming[-60:]) if self.incoming else 0.0
        if txn["type"] == "salary_in" or (amount >= 3000 and amount >= 4 * typical and len(self.incoming) >= 5):
            self.income_weeks.add(monday)
        self.incoming.append(amount)

    def history(self, category, monday):
        totals = []
        for i in range(1, LOOKBACK_WEEKS + 5):
            week = monday - timedelta(weeks=i)
            if self.first_week is None or week <= self.first_week:
                break
            if is_festival_week(week):
                continue
            totals.append((week, self.weeks[week][category][0] if week in self.weeks else 0.0))
            if len(totals) >= LOOKBACK_WEEKS:
                break
        return totals

    def baseline(self, category, ts):
        monday = week_start(ts)
        totals = self.history(category, monday)
        if len(totals) < MIN_WEEKS:
            return None
        same_kind = [t for w, t in totals if (w in self.income_weeks) == (monday in self.income_weeks)]
        values = same_kind if len(same_kind) >= 3 else [t for _, t in totals]
        centre = median(values)
        spread = 1.4826 * median([abs(v - centre) for v in values])
        return {"median": centre, "spread": spread, "weeks": len(values)}

    def week_total(self, category, ts):
        monday = week_start(ts)
        cell = self.weeks[monday][category] if monday in self.weeks else [0.0, 0]
        return cell[0], cell[1]

    def check(self, category, amount, ts):
        if category not in DISCRETIONARY:
            return None
        base = self.baseline(category, ts)
        if base is None or base["median"] <= 0:
            return None
        total, count = self.week_total(category, ts)
        new_total = total + float(amount)
        monday = week_start(ts)
        ratio = FESTIVAL_RATIO if is_festival_week(monday) else RATIO
        limit = max(base["median"] * ratio, base["median"] + SPREAD_FACTOR * base["spread"])
        if new_total <= limit or new_total - base["median"] < MIN_EXCESS:
            return None
        if (monday, category) in self.nudged or self.nudges[monday] >= WEEKLY_CAP:
            return None
        return {
            "code": "above_baseline",
            "category": category,
            "count": count + 1,
            "week_total": round(new_total),
            "baseline": round(base["median"]),
            "pct_above": int(round((new_total / base["median"] - 1.0) * 100)),
        }

    def register(self, category, ts):
        monday = week_start(ts)
        self.nudges[monday] += 1
        self.nudged.add((monday, category))

    def bill_seen(self, afford):
        return (afford["bill"], afford["due_date"]) in self.bill_nudged

    def register_bill(self, afford):
        self.bill_nudged.add((afford["bill"], afford["due_date"]))
