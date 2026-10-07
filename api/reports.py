import json
import logging
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from api.db import Database, now_utc, scam_reports

log = logging.getLogger("thamun.reports")
PATTERNS = ("refund", "prize_fee", "fake_agent", "pin_otp", "other")
RECENT_DAYS = 30
STALE_DAYS = 90
MEDIUM_SCORE = 3.0
HIGH_SCORE = 10.0
DAILY_LIMIT = 5
MAX_PER_SESSION = 40
SEED_SESSION = "seed"


def normalise(number: Any) -> str:
    text = "".join(ch for ch in str(number) if ch.isalnum()).upper()
    if text.startswith("880") and len(text) == 13:
        text = text[2:]
    return text


def weight(age_days: int) -> float:
    if age_days <= RECENT_DAYS:
        return 1.0
    if age_days <= STALE_DAYS:
        return 0.5
    return 0.25


def confidence(score: float) -> str:
    if score >= HIGH_SCORE:
        return "high"
    if score >= MEDIUM_SCORE:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def reputation(ages: list[int]) -> dict[str, Any]:
    score = sum(weight(max(age, 0)) for age in ages)
    return {"reports": len(ages), "recent_reports": sum(1 for age in ages if age <= RECENT_DAYS),
            "score": round(score, 2), "confidence": confidence(score)}


class ReportBook:
    def __init__(self, db: Database, seed_path: Path) -> None:
        self.db = db
        self.seed = json.loads(Path(seed_path).read_text())
        self.protected: set[str] = set()
        self.load_seed()

    def load_seed(self) -> None:
        present = self.db.rows(select(func.count()).select_from(scam_reports).where(scam_reports.c.source == "seed"))
        if present and next(iter(present[0].values())) > 0:
            return
        rows = []
        for item in self.seed:
            last = date.fromisoformat(item["last_reported"])
            for i in range(int(item["reports"])):
                rows.append({"number": normalise(item["number"]), "reporter": f"seed-{i:03d}", "session": SEED_SESSION,
                             "pattern": item["pattern"], "source": "seed",
                             "reported_on": (last - timedelta(days=i * int(item.get("spacing_days", 3)))).isoformat(),
                             "created_at": now_utc()})
        if rows:
            try:
                self.db.write(scam_reports.insert().values(rows))
                log.info("seeded %s dummy scam reports", len(rows))
            except IntegrityError:
                log.info("dummy scam reports were already seeded by another worker")

    def counted(self, session: str, number: str) -> list[dict[str, Any]]:
        rows = self.db.rows(select(scam_reports).where(scam_reports.c.number == number))
        kept, foreign = [], {}
        for row in rows:
            if row["source"] == "seed" or row["session"] == session:
                kept.append(row)
            elif number in self.protected:
                continue
            elif row["session"] not in foreign or row["reported_on"] > foreign[row["session"]]["reported_on"]:
                foreign[row["session"]] = row
        return kept + list(foreign.values())

    def status(self, session: str, number: Any, reporter: Optional[str] = None, today: Optional[date] = None) -> dict[str, Any]:
        key = normalise(number)
        today = today or date.today()
        rows = self.counted(session, key)
        ages = [(today - date.fromisoformat(row["reported_on"])).days for row in rows]
        patterns = Counter(row["pattern"] or "other" for row in rows)
        named = [(name, count) for name, count in patterns.most_common() if name != "other"]
        return dict(
            reputation(ages), number=key, pattern=named[0][0] if named else None,
            last_reported=max((row["reported_on"] for row in rows), default=None),
            you_reported=bool(reporter) and any(row["reporter"] == reporter for row in rows),
            from_list=sum(1 for row in rows if row["source"] == "seed"),
            from_session=sum(1 for row in rows if row["source"] != "seed" and row["session"] == session),
            from_community=sum(1 for row in rows if row["source"] != "seed" and row["session"] != session),
        )

    def add(self, session: str, reporter: str, number: Any, pattern: Optional[str], today: date) -> str:
        key = normalise(number)
        mine = self.db.rows(select(scam_reports.c.number, scam_reports.c.reported_on)
                            .where(scam_reports.c.session == session, scam_reports.c.source == "app"))
        if len({row["number"] for row in mine}) >= MAX_PER_SESSION:
            return "limit"
        same_day = self.db.rows(select(func.count()).select_from(scam_reports)
                                .where(scam_reports.c.reporter == reporter, scam_reports.c.reported_on == today.isoformat()))
        if next(iter(same_day[0].values())) >= DAILY_LIMIT:
            return "limit"
        try:
            self.db.write(scam_reports.insert().values(number=key, reporter=reporter, session=session,
                                                       pattern=pattern or "other", source="app",
                                                       reported_on=today.isoformat(), created_at=now_utc()))
        except IntegrityError:
            return "duplicate"
        return "added"

    def listing(self, session: str, today: Optional[date] = None, limit: int = 40) -> list[dict[str, Any]]:
        numbers = self.db.rows(select(scam_reports.c.number).distinct())
        rows = [self.status(session, row["number"], today=today) for row in numbers]
        rows = [row for row in rows if row["reports"] > 0]
        return sorted(rows, key=lambda r: (-r["score"], -r["reports"], r["number"]))[:limit]

    def clear(self, session: str) -> None:
        self.db.write(delete(scam_reports).where(scam_reports.c.session == session, scam_reports.c.source == "app"))

    def total(self) -> dict[str, int]:
        rows = self.db.rows(select(scam_reports.c.source, func.count().label("n")).group_by(scam_reports.c.source))
        return {row["source"]: int(row["n"]) for row in rows}
