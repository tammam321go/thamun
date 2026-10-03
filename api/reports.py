import json
from collections import Counter
from pathlib import Path

PATTERNS = ("refund", "prize_fee", "fake_agent", "pin_otp", "other")
MAX_PER_SESSION = 40


def normalise(number):
    text = "".join(ch for ch in str(number) if ch.isalnum()).upper()
    if text.startswith("880") and len(text) == 13:
        text = text[2:]
    return text


class ReportBook:
    def __init__(self, path):
        rows = json.loads(Path(path).read_text())
        self.seed = {normalise(row["number"]): row for row in rows}
        self.added = {}

    def status(self, session, number, customer_id=None):
        key = normalise(number)
        seed = self.seed.get(key)
        own = self.added.get(session, {}).get(key, {})
        patterns = Counter()
        dates = []
        if seed:
            patterns[seed["pattern"]] += int(seed["reports"])
            dates.append(seed["last_reported"])
        for entry in own.values():
            patterns[entry["pattern"] or "other"] += 1
            dates.append(entry["date"])
        named = [(name, count) for name, count in patterns.most_common() if name != "other"]
        return {
            "number": key,
            "reports": (int(seed["reports"]) if seed else 0) + len(own),
            "pattern": named[0][0] if named else None,
            "last_reported": max(dates) if dates else None,
            "you_reported": customer_id in own,
            "from_list": int(seed["reports"]) if seed else 0,
            "from_session": len(own),
        }

    def add(self, session, customer_id, number, pattern, today):
        key = normalise(number)
        bucket = self.added.setdefault(session, {})
        if key not in bucket and len(bucket) >= MAX_PER_SESSION:
            return False
        entries = bucket.setdefault(key, {})
        if customer_id in entries:
            return False
        entries[customer_id] = {"pattern": pattern, "date": today.isoformat()}
        return True

    def listing(self, session):
        numbers = list(self.seed) + [n for n in self.added.get(session, {}) if n not in self.seed]
        rows = [self.status(session, number) for number in numbers]
        return sorted(rows, key=lambda r: (-r["reports"], r["number"]))

    def clear(self, session):
        self.added.pop(session, None)
