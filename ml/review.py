from collections import defaultdict

from data.personas import DISCRETIONARY
from ml.goals import month_key, previous_months


def month_totals(txns, key):
    totals = defaultdict(float)
    counts = defaultdict(int)
    money_in = 0.0
    for txn in txns:
        if month_key(txn["ts"].date()) != key:
            continue
        if txn["direction"] == "out":
            category = txn.get("category") or "other"
            totals[category] += float(txn["amount"])
            counts[category] += 1
        else:
            money_in += float(txn["amount"])
    return totals, counts, money_in


def summary(txns, key, today):
    previous = previous_months(type(today)(key[0], key[1], 1), 1)[0]
    now, counts, money_in = month_totals(txns, key)
    before, _, _ = month_totals(txns, previous)
    partial = key == month_key(today)
    scale = 1.0
    if partial:
        scale = today.day / 30.0
    categories = []
    for category, value in sorted(now.items(), key=lambda kv: kv[1], reverse=True):
        base = before.get(category, 0.0) * scale
        change = (value - base) / base if base > 0 else None
        categories.append({
            "category": category, "amount": int(round(value)), "count": counts[category],
            "previous": int(round(before.get(category, 0.0))),
            "change_pct": int(round(change * 100)) if change is not None else None,
            "flexible": category in DISCRETIONARY,
        })
    total = sum(now.values())
    movers = [c for c in categories if c["change_pct"] is not None and abs(c["amount"] - c["previous"] * scale) >= 300]
    movers.sort(key=lambda c: c["amount"] - c["previous"] * scale, reverse=True)
    return {
        "month": f"{key[0]}-{key[1]:02d}", "previous_month": f"{previous[0]}-{previous[1]:02d}", "partial": partial,
        "total_out": int(round(total)), "previous_total_out": int(round(sum(before.values()))),
        "total_in": int(round(money_in)), "categories": categories,
        "increases": [c for c in movers if c["amount"] > c["previous"] * scale][:3],
        "decreases": [c for c in reversed(movers) if c["amount"] < c["previous"] * scale][:2],
    }


def cashflow_pattern(txns, today, income):
    if not income:
        return None
    payday = income["date"].day
    months = previous_months(today, 3)
    early, total, topups = 0.0, 0.0, 0
    for txn in txns:
        d = txn["ts"].date()
        if month_key(d) not in months:
            continue
        offset = (d.day - payday) % 31
        if txn["direction"] == "out":
            total += float(txn["amount"])
            if offset < 10:
                early += float(txn["amount"])
        elif txn["type"] == "cash_in" and offset >= 20:
            topups += 1
    if total <= 0:
        return None
    return {"payday": payday, "share_first_10_days": int(round(100 * early / total)),
            "late_month_topups": topups, "months": len(months)}
