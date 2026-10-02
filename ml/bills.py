import calendar
import math
from collections import defaultdict
from datetime import date, timedelta

MIN_PAYMENTS = 3
AFFORD_HORIZON = 7
REMIND_DAYS = 3


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return float(ordered[mid]) if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def on_day(year, month, day):
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_month(d):
    return (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)


class BillBook:
    def __init__(self):
        self.payments = defaultdict(list)
        self.incomes = defaultdict(list)
        self.info = {}
        self.weekly_other = defaultdict(float)
        self.cache = None
        self.daily_in = defaultdict(float)

    def update(self, txn):
        day = txn["ts"].date()
        cp = txn["counterparty"]
        amount = float(txn["amount"])
        if txn["direction"] == "out":
            if txn["type"] in ("bill_payment", "send_money"):
                self.cache = None
                self.payments[cp].append((day, amount, txn["type"], txn.get("category") or "other"))
                self.info[cp] = txn.get("counterparty_name") or cp
            self.weekly_other[(day - timedelta(days=day.weekday()), cp)] += amount
        elif txn["type"] in ("salary_in", "receive_money"):
            self.incomes[cp].append((day, amount))
            self.daily_in[day] += amount

    def monthly(self, events, strict_amount):
        if len(events) < MIN_PAYMENTS:
            return None
        recent = events[-6:]
        gaps = [(b[0] - a[0]).days for a, b in zip(recent, recent[1:])]
        if not gaps:
            return None
        ok = sum(1 for g in gaps if 24 <= g <= 38)
        if not (26 <= median(gaps) <= 35) or ok < math.ceil(len(gaps) * 0.6):
            return None
        last = [e[1] for e in recent[-3:]]
        amount = median(last)
        if strict_amount and (max(last) - min(last)) > 0.35 * max(amount, 1.0):
            return None
        return {"amount": amount, "day": int(round(median([e[0].day for e in recent[-4:]]))), "last": recent[-1][0]}

    def recurring(self):
        if self.cache is not None:
            return self.cache
        out = []
        for cp, events in self.payments.items():
            found = self.monthly(events, strict_amount=events[-1][2] == "send_money")
            if found:
                cats = [e[3] for e in events[-4:]]
                out.append(dict(found, counterparty=cp, name=self.info.get(cp, cp), type=events[-1][2],
                                category=max(set(cats), key=cats.count)))
        self.cache = out
        return out

    def next_due(self, bill, today):
        year, month = bill["last"].year, bill["last"].month
        due = on_day(year, month, bill["day"])
        while due <= bill["last"] + timedelta(days=14):
            year, month = next_month(due)
            due = on_day(year, month, bill["day"])
        return due

    def upcoming(self, today, horizon=35):
        out = []
        for bill in self.recurring():
            due = self.next_due(bill, today)
            if due > today + timedelta(days=horizon) or (today - due).days > 20:
                continue
            out.append({
                "counterparty": bill["counterparty"], "name": bill["name"], "category": bill["category"],
                "type": bill["type"], "amount": int(round(bill["amount"])), "due_date": due,
                "days_left": (due - today).days, "overdue": due < today,
            })
        return sorted(out, key=lambda b: b["due_date"])

    def income(self, today):
        best = None
        for cp, events in self.incomes.items():
            found = self.monthly([(d, a, "in", "income") for d, a in events], strict_amount=False)
            if found and (best is None or found["amount"] > best["amount"]):
                best = found
        if best is None:
            return None
        due = self.next_due(best, today)
        return {"amount": int(round(best["amount"])), "date": due, "days_left": (due - today).days}

    def daily_inflow(self, today, window=14):
        values = [self.daily_in.get(today - timedelta(days=i), 0.0) for i in range(1, window + 1)]
        return median(values)

    def daily_spend(self, today):
        recurring = {b["counterparty"] for b in self.recurring()}
        monday = today - timedelta(days=today.weekday())
        weeks = []
        for i in range(1, 9):
            week = monday - timedelta(weeks=i)
            total = sum(v for (w, cp), v in self.weekly_other.items() if w == week and cp not in recurring)
            weeks.append(total)
        active = [w for w in weeks if w > 0]
        if len(active) < 3:
            return 0.0
        return median(weeks) / 7.0


def affordability(balance_before, amount, upcoming, paying=None, horizon=AFFORD_HORIZON, daily_inflow=0.0):
    total = 0.0
    for bill in upcoming:
        if bill["counterparty"] == paying or bill["days_left"] > horizon:
            continue
        total += bill["amount"]
        expected = daily_inflow * max(bill["days_left"], 0)
        after = balance_before - amount + expected
        if total > after:
            return {
                "code": "bill_shortfall", "bill": bill["name"], "category": bill["category"],
                "bill_amount": bill["amount"], "due_date": bill["due_date"], "days_left": bill["days_left"],
                "shortfall": int(math.ceil(total - after)), "caused": balance_before + expected >= total,
            }
    return None


def forecast(balance, upcoming, daily_spend, income, today, daily_inflow=0.0):
    daily_spend = max(daily_spend - daily_inflow, 0.0)
    rows = []
    running = float(balance)
    cursor = today
    income_used = False
    first_short = None
    for bill in upcoming:
        due = max(bill["due_date"], today)
        if income and not income_used and income["date"] <= due:
            running += income["amount"]
            income_used = True
        running -= daily_spend * max((due - cursor).days, 0)
        cursor = due
        before = running
        running -= bill["amount"]
        short = max(0, int(math.ceil(bill["amount"] - before)))
        status = "short" if short > 0 else "tight" if running < daily_spend * 3 else "ready"
        row = dict(bill, projected_balance=int(round(before)), shortfall=short, status=status)
        rows.append(row)
        if short > 0 and first_short is None:
            first_short = row
    reminder = None
    if first_short is not None:
        by = max(today, first_short["due_date"] - timedelta(days=REMIND_DAYS))
        reminder = {
            "bill": first_short["name"], "category": first_short["category"], "due_date": first_short["due_date"],
            "bills": [first_short["name"]], "amount": int(math.ceil(first_short["shortfall"] / 100.0) * 100),
            "cash_in_by": by,
        }
    return {"bills": rows, "reminder": reminder, "daily_spend": int(round(daily_spend)), "income": income}
