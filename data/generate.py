import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from data import personas as P

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "out"
DEMO_DIR = ROOT / "api" / "demo_data"

AREAS = ["Mirpur", "Dhanmondi", "Uttara", "Mohammadpur", "Banani", "Savar", "Gazipur", "Narayanganj", "Chattogram", "Sylhet", "Khulna", "Rajshahi"]
RECHARGE_PACKS = [20, 30, 50, 100, 150, 200, 300, 500]

COLUMNS = [
    "txn_id", "customer_id", "persona", "ts", "type", "direction", "amount", "counterparty",
    "counterparty_name", "counterparty_type", "merchant_type", "category", "purpose",
    "balance_before", "balance_after", "is_scam", "scam_type", "incident_id", "unusual", "late_days",
]


def round_to(x, base):
    return int(max(base, round(x / base) * base))


def phone(rng):
    return "010" + "".join(str(int(d)) for d in rng.integers(0, 10, 8))


def pick_hour(rng, key):
    w = np.array(P.HOURS[key], dtype=float)
    return int(rng.choice(24, p=w / w.sum()))


def at(d, hour, rng):
    return datetime(d.year, d.month, d.day, hour, int(rng.integers(0, 60)), int(rng.integers(0, 60)))


def in_eid(d):
    return any(a <= d <= b for a, b in P.EID_WINDOWS)


def build_registry(rng):
    merchants = {}
    by_type = defaultdict(list)
    n = 0
    for mtype, names in P.MERCHANT_NAMES.items():
        for name in names:
            for area in AREAS:
                n += 1
                mid = f"M{n:04d}"
                merchants[mid] = {"type": mtype, "name": f"{name} ({area})"}
                by_type[mtype].append(mid)
    agents = [f"A{i:04d}" for i in range(1, 301)]
    return {"merchants": merchants, "by_type": dict(by_type), "agents": agents}


def weighted_pool(rng, items):
    w = np.array([1.0 / (i + 1) for i in range(len(items))])
    return list(items), w / w.sum()


def build_profile(rng, registry, cid, persona, name="", override=None):
    spec = P.PERSONAS[persona]
    o = override or {}
    income = o.get("income") or round_to(rng.uniform(*spec["income"]), 500)
    scale = (income / spec["income_ref"]) ** 0.7
    payday = o.get("payday") or int(rng.integers(spec["payday"][0], spec["payday"][1] + 1))
    hold = (o.get("hold") or rng.uniform(*spec["hold"])) * income

    names = list(rng.permutation(P.PERSON_NAMES))
    contacts = {}

    def person(label):
        number = phone(rng)
        contacts[number] = f"{names.pop()} ({label})" if names else label
        return number

    bills = {}
    if "bills" in o:
        bills = {k: dict(v) for k, v in o["bills"].items()}
    else:
        for cat, (prob, lo, hi) in spec["bills"].items():
            if rng.random() < prob:
                amount = rng.uniform(lo, hi) * (scale if cat in ("electricity", "savings") else 1.0)
                amount = round_to(amount, 500) if cat == "savings" else int(round(amount, -1))
                bills[cat] = {"day": int(rng.integers(5, 26)), "amount": amount, "variable": cat in ("electricity", "water")}

    recurring = {}
    if "recurring" in o:
        for cat, r in o["recurring"].items():
            recurring[cat] = dict(r, counterparty=person("landlord" if cat == "rent" else "family"))
    else:
        for cat, (prob, lo, hi) in spec["recurring"].items():
            if rng.random() < prob:
                recurring[cat] = {
                    "day": min(28, payday + int(rng.integers(1, 6))),
                    "amount": round_to(income * rng.uniform(lo, hi), 500),
                    "counterparty": person("landlord" if cat == "rent" else "family"),
                }

    family = [r["counterparty"] for c, r in recurring.items() if c == "family_support"] or [person("family")]
    friends = [person("friend") for _ in range(int(rng.integers(3, 8)))]
    sellers = [person("seller") for _ in range(2)]
    suppliers = [person("supplier") for _ in range(3)]
    agents = list(rng.choice(registry["agents"], size=int(rng.integers(1, 4)), replace=False))

    spend = []
    for item in o.get("spend") or spec["spend"]:
        cat, ttype, mtype, rate, median, sigma, hours = item[:7]
        days = item[7] if len(item) > 7 else None
        if "spend" in o:
            c_rate, c_median = rate, median
        else:
            c_rate = rate * float(rng.lognormal(0, 0.25))
            c_median = median * scale * float(rng.lognormal(0, 0.2))
        if ttype == "merchant_payment":
            pool = list(rng.choice(registry["by_type"][mtype], size=int(rng.integers(2, 6)), replace=False))
        elif ttype == "cash_out":
            pool = agents
        elif ttype == "mobile_recharge":
            pool = [f"OP-{int(rng.integers(1, 4))}"]
        elif cat == "family_support":
            pool = family
        elif cat == "shopping":
            pool = sellers
        elif cat == "business_supplies":
            pool = suppliers
        else:
            pool = friends
        items, weights = weighted_pool(rng, pool)
        spend.append({"category": cat, "type": ttype, "merchant_type": mtype, "rate": c_rate, "median": c_median,
                      "sigma": sigma, "hours": hours, "pool": items, "weights": weights, "days": days})

    return {
        "customer_id": cid, "name": name, "persona": persona, "income": income, "payday": payday, "hold": hold,
        "p_late": o.get("p_late", spec["p_late"]), "p_topup": o.get("p_topup", spec["p_topup"]),
        "new_cp": o.get("new_cp", spec["new_cp"]), "scam_rate": o.get("scam_rate", spec["scam_rate"]),
        "scam_mix": spec["scam_mix"], "unusual_rate": o.get("unusual_rate", spec["unusual_rate"]),
        "bills": bills, "recurring": recurring, "spend": spend, "contacts": contacts, "family": family,
        "friends": friends, "agents": agents, "employer": f"E{int(rng.integers(1, 400)):04d}",
        "parent": person("parent"), "payers": [person("client") for _ in range(4)],
        "regulars": [phone(rng) for _ in range(20)], "has_side_income": bool(rng.random() < 0.4),
        "side_day": int(rng.integers(8, 26)), "electricity_script": o.get("electricity_script", {}),
        "pay_jitter": "pay_jitter" in o or "bills" in o,
    }


class Simulator:
    def __init__(self, rng, profile, registry, start, end, demo=False):
        self.rng = rng
        self.p = profile
        self.reg = registry
        self.start = start
        self.end = end
        self.demo = demo
        self.balance = float(round_to(rng.uniform(0.05, 0.25) * profile["income"], 100))
        self.rows = []
        self.bill_events = []
        self.splurges = []
        self.deferred = defaultdict(list)
        self.week_mult = {}
        self.last_income = None
        self.incident = 0
        self.month_plan = {}
        self.last_ts = None

    def name_of(self, cp, cp_type):
        if cp_type == "merchant":
            return self.reg["merchants"][cp]["name"]
        if cp_type == "biller":
            return next((n for c, n in P.BILLERS.values() if c == cp), cp)
        if cp_type == "agent":
            return f"Agent point {cp}"
        if cp_type == "operator":
            return P.OPERATORS[int(cp[-1]) - 1]
        if cp_type == "employer":
            return f"Employer {cp}"
        return self.p["contacts"].get(cp, "")

    def event(self, ts, ttype, amount, cp, cp_type, category, direction="out", merchant_type="none", purpose="", **extra):
        return dict({"ts": ts, "type": ttype, "direction": direction, "amount": amount, "counterparty": cp,
                     "counterparty_type": cp_type, "merchant_type": merchant_type, "category": category,
                     "purpose": purpose, "is_scam": 0, "scam_type": "none", "incident_id": "", "unusual": "",
                     "late_days": 0}, **extra)

    def record(self, e):
        if self.last_ts is not None and e["ts"] <= self.last_ts:
            e = dict(e, ts=self.last_ts + timedelta(seconds=int(self.rng.integers(20, 90))))
        self.last_ts = e["ts"]
        before = self.balance
        self.balance = before + e["amount"] if e["direction"] == "in" else before - e["amount"]
        self.rows.append({
            "customer_id": self.p["customer_id"], "persona": self.p["persona"], "ts": e["ts"], "type": e["type"],
            "direction": e["direction"], "amount": int(e["amount"]), "counterparty": e["counterparty"],
            "counterparty_name": self.name_of(e["counterparty"], e["counterparty_type"]),
            "counterparty_type": e["counterparty_type"], "merchant_type": e["merchant_type"],
            "category": e["category"], "purpose": e["purpose"], "balance_before": int(round(before)),
            "balance_after": int(round(self.balance)), "is_scam": e["is_scam"], "scam_type": e["scam_type"],
            "incident_id": e["incident_id"], "unusual": e["unusual"], "late_days": e["late_days"],
        })

    def cash_in(self, needed, ts):
        buffer = self.rng.uniform(0, 0.05) * self.p["income"]
        amount = int(math.ceil((needed - self.balance + buffer) / 500.0) * 500)
        agent = self.p["agents"][0] if self.rng.random() < 0.85 else str(self.rng.choice(self.reg["agents"]))
        when = ts - timedelta(minutes=int(self.rng.integers(5, 45)))
        if self.last_ts is not None and when <= self.last_ts:
            when = self.last_ts + timedelta(seconds=5)
        self.record(self.event(when, "cash_in", amount, agent, "agent", "cash_in", direction="in"))

    def apply(self, e):
        if e["direction"] == "in":
            self.record(e)
            if e["type"] in ("salary_in",) or e.get("main_income"):
                self.last_income = e["ts"].date()
            return
        amount = e["amount"]
        if e.get("frac"):
            amount = int(self.balance * e["frac"] // 10 * 10)
            if amount < 300:
                return
        if e.get("bill") and "short" not in e:
            e["short"] = int(amount > self.balance)
        if amount > self.balance:
            if e["is_scam"]:
                amount = int(self.balance * 0.95 // 10 * 10)
                if amount < 300:
                    return
            elif e.get("bill"):
                if not e["late_days"] and self.rng.random() < self.p["p_late"]:
                    days = int(self.rng.integers(1, 7))
                    later = dict(e, late_days=days, ts=e["ts"] + timedelta(days=days))
                    if later["ts"].date() <= self.end:
                        self.deferred[later["ts"].date()].append(later)
                    return
                self.cash_in(amount, e["ts"])
            elif e.get("force") or self.rng.random() < self.p["p_topup"]:
                self.cash_in(amount, e["ts"])
            else:
                return
        e = dict(e, amount=amount)
        self.record(e)
        if e.get("bill"):
            self.bill_events.append({
                "customer_id": self.p["customer_id"], "counterparty": e["counterparty"], "category": e["category"],
                "due_date": e["due"], "paid_ts": e["ts"], "amount": int(amount), "short_on_due": e["short"],
                "late_days": e["late_days"],
            })

    def roll_week(self, d):
        self.week_mult = {}
        monday = d - timedelta(days=d.weekday())
        for cat in ("eating_out", "shopping", "transport"):
            if self.rng.random() < 0.07:
                mult = float(self.rng.uniform(1.8, 2.6))
                self.week_mult[cat] = mult
                self.splurges.append({"customer_id": self.p["customer_id"], "week_start": monday, "category": cat, "multiplier": round(mult, 2)})

    def plan_month(self, d):
        plan = defaultdict(list)
        last_day = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        for cat, b in self.p["bills"].items():
            jitter = 0 if self.p["pay_jitter"] else int(self.rng.choice([-2, -1, 0, 0, 0, 1]))
            day = min(max(1, b["day"] + jitter), last_day.day)
            plan[d.replace(day=day)].append(("bill", cat, d.replace(day=min(b["day"], last_day.day))))
        for cat, r in self.p["recurring"].items():
            jitter = 0 if self.p["pay_jitter"] else int(self.rng.choice([-1, 0, 0, 1]))
            day = min(max(1, r["day"] + jitter), last_day.day)
            plan[d.replace(day=day)].append(("recurring", cat, d.replace(day=min(r["day"], last_day.day))))
        self.month_plan = plan

    def income(self, d):
        p, rng, out = self.p, self.rng, []
        persona = p["persona"]
        if persona == "salaried" and d.day == p["payday"]:
            out.append(self.event(at(d, int(rng.integers(9, 13)), rng), "salary_in", p["income"], p["employer"], "employer", "income", direction="in", main_income=True))
        elif persona == "student":
            if d.day == p["payday"]:
                amount = round_to(p["income"] * rng.uniform(0.9, 1.1), 500)
                out.append(self.event(at(d, pick_hour(rng, "day"), rng), "receive_money", amount, p["parent"], "person", "income", direction="in", main_income=True))
            if d.day == min(28, p["payday"] + 14) and rng.random() < 0.4:
                out.append(self.event(at(d, pick_hour(rng, "day"), rng), "receive_money", round_to(rng.uniform(1000, 3000), 500), p["parent"], "person", "income", direction="in"))
            if p["has_side_income"] and d.day == p["side_day"]:
                out.append(self.event(at(d, pick_hour(rng, "evening"), rng), "receive_money", round_to(rng.uniform(3000, 6000), 500), p["payers"][0], "person", "income", direction="in"))
        elif persona == "shop_owner":
            is_open = d.weekday() != 4 or rng.random() < 0.4
            if is_open:
                lam = p["income"] / (26 * 480)
                for _ in range(int(rng.poisson(lam))):
                    amount = max(20, int(rng.lognormal(math.log(380), 0.7)))
                    payer = str(rng.choice(p["regulars"])) if rng.random() < 0.3 else phone(rng)
                    out.append(self.event(at(d, pick_hour(rng, "shop"), rng), "receive_money", amount, payer, "person", "income", direction="in"))
        elif persona == "irregular" and rng.random() < 0.55:
            for _ in range(1 if rng.random() < 0.85 else 2):
                amount = round_to(p["income"] / 16.5 * rng.lognormal(0, 0.45), 50)
                payer = str(rng.choice(p["payers"])) if rng.random() < 0.7 else phone(rng)
                out.append(self.event(at(d, pick_hour(rng, "evening"), rng), "receive_money", amount, payer, "person", "income", direction="in", main_income=True))
        return out

    def commitments(self, d):
        p, rng, out = self.p, self.rng, []
        for kind, cat, due in self.month_plan.get(d, []):
            if self.demo and due >= P.DEMO_TODAY:
                continue
            if kind == "bill":
                b = p["bills"][cat]
                amount = b["amount"]
                if cat == "electricity" and d.month in p["electricity_script"]:
                    amount = p["electricity_script"][d.month]
                elif b["variable"]:
                    season = P.ELECTRICITY_SEASON.get(d.month, 1.0) if cat == "electricity" else 1.0
                    amount = int(round(b["amount"] * season * rng.normal(1, 0.06)))
                code = P.BILLERS[cat][0]
                mtype = "bank" if cat == "savings" else "utility"
                out.append(self.event(at(d, pick_hour(rng, "day"), rng), "bill_payment", amount, code, "biller", cat, merchant_type=mtype, purpose=cat, bill=True, due=due))
            else:
                r = p["recurring"][cat]
                out.append(self.event(at(d, pick_hour(rng, "day"), rng), "send_money", r["amount"], r["counterparty"], "person", cat, purpose=P.CATEGORY_PURPOSE[cat], bill=True, due=due))
        if in_eid(d) and d == P.EID_WINDOWS[0][0] + timedelta(days=3) and "family_support" in p["recurring"] and rng.random() < 0.6:
            r = p["recurring"]["family_support"]
            amount = round_to(r["amount"] * rng.uniform(0.5, 1.5), 500)
            out.append(self.event(at(d, pick_hour(rng, "day"), rng), "send_money", amount, r["counterparty"], "person", "family_support", purpose="family_support", force=True))
        return out

    def spend_amount(self, line):
        raw = float(self.rng.lognormal(math.log(line["median"]), line["sigma"]))
        ttype = line["type"]
        if ttype == "mobile_recharge":
            return min(RECHARGE_PACKS, key=lambda v: abs(v - raw))
        if ttype == "cash_out":
            return round_to(raw, 100 if raw < 1500 else 500)
        if ttype == "send_money":
            return round_to(raw, 50 if raw < 1000 else 100 if raw < 5000 else 500)
        return max(10, int(round(raw)))

    def choose_counterparty(self, line):
        rng = self.rng
        p_new = 0.75 if (line["type"] == "send_money" and line["category"] == "shopping") else self.p["new_cp"]
        if line["type"] in ("mobile_recharge",) or line["category"] == "family_support":
            p_new = 0.0
        if rng.random() < p_new:
            if line["type"] == "merchant_payment":
                return str(rng.choice(self.reg["by_type"][line["merchant_type"]]))
            if line["type"] == "cash_out":
                return str(rng.choice(self.reg["agents"]))
            return phone(rng)
        return str(rng.choice(line["pool"], p=line["weights"]))

    def spending(self, d):
        p, rng, out = self.p, self.rng, []
        post_income = self.last_income is not None and 0 <= (d - self.last_income).days <= 6
        for line in p["spend"]:
            cat = line["category"]
            mult = self.week_mult.get(cat, 1.0)
            if d.weekday() in (4, 5) and cat in ("eating_out", "shopping"):
                mult *= 1.3
            if d.weekday() == 4 and cat == "transport":
                mult *= 0.6
            if in_eid(d):
                mult *= P.EID_BOOST.get(cat, 1.0)
            if post_income and cat in P.DISCRETIONARY and p["persona"] in ("salaried", "student"):
                mult *= 1.25
            if p["persona"] == "irregular" and self.balance < 200 and line["type"] != "mobile_recharge":
                mult *= 0.2
            count = int(d.weekday() in line["days"]) if line["days"] else int(rng.poisson(line["rate"] / 7.0 * mult))
            for _ in range(count):
                amount = self.spend_amount(line)
                cp = self.choose_counterparty(line)
                label = "other" if rng.random() < 0.03 else cat
                cp_type = {"merchant_payment": "merchant", "cash_out": "agent", "mobile_recharge": "operator"}.get(line["type"], "person")
                purpose = P.CATEGORY_PURPOSE.get(cat, "other") if line["type"] == "send_money" else cat
                out.append(self.event(at(d, pick_hour(rng, line["hours"]), rng), line["type"], amount, cp, cp_type, label,
                                      merchant_type=line["merchant_type"], purpose=purpose))
        return out

    def unusual(self, d):
        p, rng = self.p, self.rng
        if self.demo and (P.DEMO_TODAY - d).days <= 14:
            return []
        if rng.random() >= p["unusual_rate"] / 30.0:
            return []
        kinds = ["big_purchase", "lend_friend", "emergency", "true_refund", "big_cashout"]
        weights = [0.3, 0.2, 0.2, 0.12, 0.18]
        if p["persona"] == "student":
            kinds.append("tuition")
            weights.append(0.25)
        w = np.array(weights) / sum(weights)
        kind = str(rng.choice(kinds, p=w))
        size = (p["income"] / 40000) ** 0.5
        out = []
        if kind == "big_purchase":
            amount = round_to(rng.uniform(4000, 28000) * size, 500)
            out.append(self.event(at(d, pick_hour(rng, "evening"), rng), "send_money", amount, phone(rng), "person", "shopping", purpose="purchase", unusual=kind, force=True))
        elif kind == "lend_friend":
            amount = round_to(rng.uniform(3000, 12000) * size, 500)
            out.append(self.event(at(d, pick_hour(rng, "evening"), rng), "send_money", amount, str(rng.choice(p["friends"])), "person", "personal_transfer", purpose="friend", unusual=kind, force=True))
        elif kind == "emergency":
            amount = round_to(rng.uniform(3000, 15000) * size, 500)
            hour = pick_hour(rng, "night") if rng.random() < 0.3 else pick_hour(rng, "day")
            cp = str(rng.choice(p["family"])) if rng.random() < 0.6 else phone(rng)
            out.append(self.event(at(d, hour, rng), "send_money", amount, cp, "person", "family_support", purpose="family_support", unusual=kind, force=True))
        elif kind == "true_refund":
            amount = round_to(rng.uniform(500, 5000), 100)
            sender = phone(rng)
            t = at(d, pick_hour(rng, "day"), rng)
            out.append(self.event(t, "receive_money", amount, sender, "person", "income", direction="in", unusual=kind))
            out.append(self.event(t + timedelta(minutes=int(rng.integers(20, 180))), "send_money", amount, sender, "person", "other", purpose="refund_mistake", unusual=kind))
        elif kind == "big_cashout":
            amount = round_to(rng.uniform(5000, 20000) * size, 500)
            out.append(self.event(at(d, pick_hour(rng, "day"), rng), "cash_out", amount, str(rng.choice(self.reg["agents"])), "agent", "cash_withdrawal", purpose="cash_withdrawal", unusual=kind, force=True))
        elif kind == "tuition":
            amount = round_to(rng.uniform(8000, 25000), 500)
            cp = str(rng.choice(self.reg["by_type"]["education"]))
            out.append(self.event(at(d, pick_hour(rng, "day"), rng), "merchant_payment", amount, cp, "merchant", "education", merchant_type="education", purpose="education", unusual=kind, force=True))
        return out

    def scam_purpose(self, scam_type):
        story, honesty = P.SCAM_PURPOSE[scam_type]
        if story and self.rng.random() < honesty * P.PURPOSE_HONESTY_SCALE:
            return story
        return str(self.rng.choice(["friend", "family_support", "purchase", "other"]))

    def scams(self, d):
        p, rng = self.p, self.rng
        if rng.random() >= p["scam_rate"] / 30.0:
            return []
        mix = p["scam_mix"]
        scam_type = str(rng.choice(list(mix), p=np.array(list(mix.values())) / sum(mix.values())))
        self.incident += 1
        tag = {"is_scam": 1, "scam_type": scam_type, "incident_id": f"{p['customer_id']}-S{self.incident:02d}"}
        small = p["persona"] in ("student", "irregular")
        scammer = phone(rng)
        typical = next((l["median"] for l in p["spend"] if l["type"] == "send_money"), 800.0)
        modest = rng.random() < P.MODEST_SCAM_SHARE
        out = []
        if scam_type == "refund_scam":
            t = at(d, int(rng.integers(9, 22)), rng)
            if rng.random() < 0.2:
                out.append(self.event(t - timedelta(minutes=int(rng.integers(5, 30))), "receive_money", int(rng.integers(20, 300)), scammer, "person", "income", direction="in", incident_id=tag["incident_id"]))
            lo, hi = (1000, 6000) if small else (2000, 15000)
            if modest:
                lo, hi = max(300, typical * 0.6), max(500, typical * 1.6)
            purpose = self.scam_purpose(scam_type)
            out.append(self.event(t, "send_money", round_to(rng.uniform(lo, hi), 100), scammer, "person", "other", purpose=purpose, **tag))
            if rng.random() < 0.25:
                out.append(self.event(t + timedelta(minutes=int(rng.integers(30, 90))), "send_money", round_to(rng.uniform(lo, hi), 100), scammer, "person", "other", purpose=purpose, **tag))
        elif scam_type == "prize_fee":
            t = at(d, int(rng.integers(9, 22)), rng)
            amount = rng.uniform(max(300, typical * 0.5), max(500, typical * 1.3)) if modest else rng.uniform(500, 3000)
            purpose = self.scam_purpose(scam_type)
            for _ in range(int(rng.integers(1, 4))):
                out.append(self.event(t, "send_money", round_to(amount, 50), scammer, "person", "other", purpose=purpose, **tag))
                t = t + timedelta(minutes=int(rng.integers(20, 120)))
                amount *= rng.uniform(1.5, 2.5)
        elif scam_type == "fake_agent_call":
            t = at(d, int(rng.integers(9, 21)), rng)
            out.append(self.event(t, "send_money", 0, scammer, "person", "other", purpose=self.scam_purpose(scam_type), frac=float(rng.uniform(0.5, 0.95)), **tag))
        elif scam_type == "impersonation":
            t = at(d, pick_hour(rng, "evening"), rng)
            known = str(rng.choice(p["friends"] + p["family"]))
            purpose = "family_support" if known in p["family"] else "friend"
            amount = round_to(typical * rng.uniform(1.5, 6.0), 100)
            for _ in range(1 if rng.random() < 0.7 else 2):
                out.append(self.event(t, "send_money", amount, known, "person", "other", purpose=purpose, **tag))
                t = t + timedelta(minutes=int(rng.integers(10, 60)))
                amount = round_to(amount * rng.uniform(0.6, 1.4), 100)
        elif modest:
            t = at(d, int(rng.integers(8, 22)), rng)
            purpose = str(rng.choice(["friend", "family_support", "other"]))
            out.append(self.event(t, "send_money", 0, phone(rng), "person", "other", purpose=purpose, frac=float(rng.uniform(0.35, 0.7)), **tag))
        else:
            hour = pick_hour(rng, "night") if rng.random() < 0.65 else int(rng.integers(0, 24))
            t = at(d, hour, rng)
            purpose = str(rng.choice(["friend", "family_support", "other"]))
            if rng.random() < 0.6:
                out.append(self.event(t, "cash_out", 0, str(rng.choice(self.reg["agents"])), "agent", "cash_withdrawal", purpose="cash_withdrawal", frac=float(rng.uniform(0.6, 0.9)), **tag))
                t = t + timedelta(minutes=int(rng.integers(1, 6)))
            for _ in range(int(rng.integers(1, 3))):
                out.append(self.event(t, "send_money", 0, phone(rng), "person", "other", purpose=purpose, frac=float(rng.uniform(0.7, 0.95)), **tag))
                t = t + timedelta(minutes=int(rng.integers(1, 6)))
        return out

    def sweep(self, d):
        if self.balance > self.p["hold"] and self.rng.random() < 0.35:
            amount = round_to(self.balance - self.p["hold"] * self.rng.uniform(0.3, 0.7), 500)
            if 0 < amount < self.balance:
                self.record(self.event(at(d, 21, self.rng), "cash_out", amount, self.p["agents"][0], "agent", "cash_withdrawal", purpose="cash_withdrawal"))

    def run(self):
        d = self.start
        self.plan_month(d)
        while d <= self.end:
            if d.day == 1 and d != self.start:
                self.plan_month(d)
            if d.weekday() == 0 or d == self.start:
                self.roll_week(d)
            events = self.deferred.pop(d, []) + self.income(d) + self.commitments(d) + self.spending(d) + self.unusual(d)
            if not self.demo:
                events += self.scams(d)
            events.sort(key=lambda e: e["ts"])
            for e in events:
                self.apply(e)
            self.sweep(d)
            d += timedelta(days=1)
        return self.rows


def rebalance(rows, start_balance):
    rows.sort(key=lambda r: r["ts"])
    balance = start_balance
    for r in rows:
        r["balance_before"] = int(round(balance))
        balance = balance + r["amount"] if r["direction"] == "in" else balance - r["amount"]
        r["balance_after"] = int(round(balance))
    return balance


def script_rina(sim, registry):
    rows = sim.rows
    first = rows[0]["balance_before"]
    cut = datetime(2026, 10, 5)
    rows[:] = [r for r in rows if not (r["ts"] >= cut and r["category"] == "eating_out")]
    line = next(s for s in sim.p["spend"] if s["category"] == "eating_out")
    template = dict(rows[-1])
    for i, (day, hour, amount) in enumerate(P.RINA["week_meals"]):
        cp = line["pool"][i % len(line["pool"])]
        rows.append(dict(template, ts=datetime(2026, 10, day, hour, 12 + 7 * i, 0), type="merchant_payment", direction="out",
                         amount=amount, counterparty=cp, counterparty_name=registry["merchants"][cp]["name"],
                         counterparty_type="merchant", merchant_type="restaurant", category="eating_out",
                         purpose="eating_out", is_scam=0, scam_type="none", incident_id="", unusual="", late_days=0))
    final = rebalance(rows, first)
    diff = int(round(final - P.RINA["start_balance"]))
    agent = sim.p["agents"][0]
    grocer = next(s for s in sim.p["spend"] if s["category"] == "groceries")["pool"][0]
    if diff != 0:
        block = int(math.floor(diff / 500.0) * 500) if diff > 0 else -int(math.ceil(-diff / 500.0) * 500)
        rest = diff - block
        if block:
            rows.append(dict(template, ts=datetime(2026, 10, 6, 18, 30, 0), type="cash_out" if block > 0 else "cash_in",
                             direction="out" if block > 0 else "in", amount=abs(block), counterparty=agent,
                             counterparty_name=f"Agent point {agent}", counterparty_type="agent", merchant_type="none",
                             category="cash_withdrawal" if block > 0 else "cash_in",
                             purpose="cash_withdrawal" if block > 0 else "", is_scam=0, scam_type="none", incident_id="", unusual="", late_days=0))
        rows.append(dict(template, ts=datetime(2026, 10, 7, 18, 5, 0), type="merchant_payment", direction="out",
                         amount=600 + rest, counterparty=grocer, counterparty_name=registry["merchants"][grocer]["name"],
                         counterparty_type="merchant", merchant_type="grocery", category="groceries", purpose="groceries",
                         is_scam=0, scam_type="none", incident_id="", unusual="", late_days=0))
        rows.append(dict(template, ts=datetime(2026, 10, 7, 17, 40, 0), type="cash_in", direction="in",
                         amount=600, counterparty=agent, counterparty_name=f"Agent point {agent}", counterparty_type="agent",
                         merchant_type="none", category="cash_in", purpose="", is_scam=0, scam_type="none", incident_id="", unusual="", late_days=0))
    final = rebalance(rows, first)
    if int(round(final)) != P.RINA["start_balance"] or min(r["balance_after"] for r in rows) < 0:
        raise RuntimeError(f"Rina balance script failed: final={final}")


def frame(rows):
    df = pd.DataFrame(rows)
    df = df.sort_values(["ts", "customer_id"]).reset_index(drop=True)
    df.insert(0, "txn_id", [f"T{i:07d}" for i in range(1, len(df) + 1)])
    return df[COLUMNS]


def generate(seed=P.SEED, scale=1.0, quiet=False, demo=False, out_dir=None):
    out_dir = Path(out_dir) if out_dir else OUT_DIR
    registry = build_registry(np.random.default_rng([seed, 0]))
    customers, rows, bill_events, splurges, truth, usual = [], [], [], [], [], []
    idx = 0
    for persona, spec in P.PERSONAS.items():
        for _ in range(max(1, int(round(spec["count"] * scale)))):
            idx += 1
            rng = np.random.default_rng([seed, idx])
            profile = build_profile(rng, registry, f"C{idx:04d}", persona)
            sim = Simulator(rng, profile, registry, P.START, P.END)
            rows.extend(sim.run())
            bill_events.extend(sim.bill_events)
            splurges.extend(sim.splurges)
            customers.append({"customer_id": profile["customer_id"], "persona": persona, "income": profile["income"], "payday": profile["payday"]})
            for cat, b in profile["bills"].items():
                truth.append({"customer_id": profile["customer_id"], "counterparty": P.BILLERS[cat][0], "category": cat, "day": b["day"], "amount": b["amount"]})
            for cat, r in profile["recurring"].items():
                truth.append({"customer_id": profile["customer_id"], "counterparty": r["counterparty"], "category": cat, "day": r["day"], "amount": r["amount"]})
            weekly = defaultdict(float)
            for line in profile["spend"]:
                weekly[line["category"]] += line["rate"] * line["median"] * math.exp(line["sigma"] ** 2 / 2.0)
            for cat, value in weekly.items():
                usual.append({"customer_id": profile["customer_id"], "category": cat, "weekly_mean": round(value, 1)})

    out_dir.mkdir(parents=True, exist_ok=True)
    txns = frame(rows)
    txns.to_csv(out_dir / "transactions.csv", index=False)
    pd.DataFrame(customers).to_csv(out_dir / "customers.csv", index=False)
    pd.DataFrame(bill_events).to_csv(out_dir / "bill_events.csv", index=False)
    pd.DataFrame(splurges).to_csv(out_dir / "splurges.csv", index=False)
    pd.DataFrame(truth).to_csv(out_dir / "recurring_truth.csv", index=False)
    pd.DataFrame(usual).to_csv(out_dir / "spend_truth.csv", index=False)

    if not quiet:
        out = txns[txns.direction == "out"]
        print(f"customers: {len(customers)}  transactions: {len(txns)}  outgoing: {len(out)}")
        print(f"scam transactions: {int(out.is_scam.sum())}  incidents: {out[out.is_scam == 1].incident_id.nunique()}")
        print(out.groupby("persona").agg(txns=("amount", "size"), scams=("is_scam", "sum")).to_string())
    if out_dir != OUT_DIR or (not demo and (DEMO_DIR / "transactions.csv").exists()):
        return txns

    demo_rows, demo_customers, demo_contacts = [], [], {}
    for i, c in enumerate(P.DEMO_CUSTOMERS):
        rng = np.random.default_rng([seed, 9000 + i])
        override = dict(P.RINA) if c["customer_id"] == "D0001" else {"scam_rate": 0.0}
        profile = build_profile(rng, registry, c["customer_id"], c["persona"], c["name"], override)
        sim = Simulator(rng, profile, registry, P.START, P.DEMO_TODAY, demo=True)
        sim.run()
        noon = datetime(P.DEMO_TODAY.year, P.DEMO_TODAY.month, P.DEMO_TODAY.day, 12, 0, 0)
        sim.rows[:] = [r for r in sim.rows if r["ts"] < noon]
        if c["customer_id"] == "D0001":
            script_rina(sim, registry)
        else:
            final = rebalance(sim.rows, sim.rows[0]["balance_before"])
            gap = c["start_balance"] - final
            if gap > 0:
                agent = profile["agents"][0]
                sim.rows.append(dict(sim.rows[-1], ts=noon - timedelta(minutes=25), type="cash_in", direction="in",
                                     amount=int(math.ceil(gap / 100.0) * 100), counterparty=agent,
                                     counterparty_name=f"Agent point {agent}", counterparty_type="agent", merchant_type="none",
                                     category="cash_in", purpose="", is_scam=0, scam_type="none", incident_id="", unusual="", late_days=0))
                rebalance(sim.rows, sim.rows[0]["balance_before"])
        demo_rows.extend(sim.rows)
        trusted = profile["family"][0]
        demo_customers.append(dict({k: v for k, v in c.items() if k != "start_balance"}, income=profile["income"], payday=profile["payday"], trusted_contact=trusted,
                                   trusted_name=profile["contacts"].get(trusted, "Family")))
        demo_contacts[c["customer_id"]] = profile["contacts"]

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    demo = frame(demo_rows)
    demo.to_csv(DEMO_DIR / "transactions.csv", index=False)
    (DEMO_DIR / "customers.json").write_text(json.dumps(demo_customers, indent=2))
    (DEMO_DIR / "contacts.json").write_text(json.dumps(demo_contacts, indent=2))

    if not quiet:
        print(f"demo transactions: {len(demo)}  written to {DEMO_DIR}")
    return txns


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=P.SEED)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    generate(args.seed, args.scale, demo=args.demo)


if __name__ == "__main__":
    main()
