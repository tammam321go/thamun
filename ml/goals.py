import math
from collections import defaultdict
from datetime import date

from data.personas import DISCRETIONARY


def month_key(d):
    return (d.year, d.month)


def previous_months(today, count):
    year, month = today.year, today.month
    out = []
    for _ in range(count):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        out.append((year, month))
    return out


def monthly_spend(txns, months):
    totals = defaultdict(lambda: defaultdict(float))
    for txn in txns:
        if txn["direction"] != "out":
            continue
        key = month_key(txn["ts"].date())
        if key in months:
            totals[txn.get("category") or "other"][key] += float(txn["amount"])
    out = {}
    for category, by_month in totals.items():
        values = sorted(by_month.get(m, 0.0) for m in months)
        out[category] = values[len(values) // 2]
    return out


def plan(txns, target, months, today, income=None):
    target = float(target)
    months = max(int(months), 1)
    per_month = int(math.ceil(target / months / 50.0) * 50)
    typical = monthly_spend(txns, previous_months(today, 3))
    flexible = {c: v for c, v in typical.items() if c in DISCRETIONARY and v > 0}
    total_flexible = sum(flexible.values())
    share = per_month / total_flexible if total_flexible else None
    if share is None:
        level = "unknown"
    elif share <= 0.25:
        level = "realistic"
    elif share <= 0.5:
        level = "stretch"
    else:
        level = "hard"
    cuts = []
    for category, value in sorted(flexible.items(), key=lambda kv: kv[1], reverse=True)[:3]:
        monthly_cut = per_month * value / total_flexible
        cuts.append({
            "category": category, "monthly_spend": int(round(value)),
            "weekly_cut": int(math.ceil(monthly_cut / 4.33 / 50.0) * 50),
            "percent_of_category": int(round(monthly_cut / value * 100)),
        })
    finish_year, finish_month = today.year, today.month + months
    while finish_month > 12:
        finish_year, finish_month = finish_year + 1, finish_month - 12
    return {
        "target": int(target), "months": months, "per_month": per_month,
        "per_week": int(math.ceil(per_month / 4.33 / 10.0) * 10),
        "flexible_monthly_spend": int(round(total_flexible)), "level": level, "cuts": cuts,
        "save_on_day": income["date"].day if income else None,
        "finish": date(finish_year, finish_month, 1).isoformat()[:7],
    }


def progress(goal, txns, today):
    start = date.fromisoformat(goal["created"])
    saved = sum(float(t["amount"]) for t in txns
                if t["direction"] == "out" and t.get("category") == "savings" and t["ts"].date() >= start
                and t.get("counterparty") == "GOAL")
    months_in = max((today.year - start.year) * 12 + today.month - start.month, 0)
    expected = min(goal["target"], goal["per_month"] * (months_in + 1))
    return {"saved": int(saved), "expected_by_now": int(expected), "on_track": saved >= expected,
            "percent": int(round(100 * saved / goal["target"])) if goal["target"] else 0}
