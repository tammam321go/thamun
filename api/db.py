import logging
import os
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, String, Table, Text, UniqueConstraint,
                        create_engine, text)
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("thamun.db")
metadata = MetaData()

scam_reports = Table(
    "scam_reports", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("number", String(24), nullable=False, index=True),
    Column("reporter", String(64), nullable=False),
    Column("session", String(64), nullable=False, index=True),
    Column("pattern", String(24), nullable=False),
    Column("source", String(8), nullable=False),
    Column("reported_on", String(10), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("number", "reporter", name="uq_report_once"),
)

audit_logs = Table(
    "audit_logs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("event", String(16), nullable=False, index=True),
    Column("session", String(64), nullable=False, index=True),
    Column("customer_id", String(8), nullable=False),
    Column("payment_type", String(20), nullable=False, default=""),
    Column("amount", Integer, nullable=False, default=0),
    Column("decision", String(16), nullable=False, default=""),
    Column("risk", Float, nullable=True),
    Column("reasons", Text, nullable=False, default=""),
    Column("outcome", String(16), nullable=False, default=""),
)

ux_feedback = Table(
    "ux_feedback", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("session", String(64), nullable=False),
    Column("scenario", String(24), nullable=False),
    Column("decision", String(16), nullable=False, default=""),
    Column("lang", String(2), nullable=False),
    Column("understood_warning", String(8), nullable=False),
    Column("understood_reason", String(8), nullable=False),
    Column("intrusive", String(8), nullable=False),
    Column("understood_choice", String(8), nullable=False),
    Column("preferred_lang", String(8), nullable=False),
    Column("comment", String(200), nullable=False, default=""),
)


AUDIT_FIELDS = ("payment_type", "amount", "decision", "risk", "reasons", "outcome")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        path = Path(os.getenv("THAMUN_DB_PATH") or ROOT / "data" / "thamun.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+pg8000://" + url[len("postgresql://"):]
    return url


class Database:
    def __init__(self, url: Optional[str] = None) -> None:
        raw = url or database_url()
        args: dict[str, Any] = {}
        if raw.startswith("sqlite"):
            args["check_same_thread"] = False
        elif "pg8000" in raw:
            wants_ssl = "sslmode=require" in raw or os.getenv("DATABASE_SSL", "").lower() == "true"
            raw = raw.split("?")[0]
            if wants_ssl:
                args["ssl_context"] = ssl.create_default_context()
        self.engine: Engine = create_engine(raw, connect_args=args, pool_pre_ping=True)
        self.backend = "postgresql" if raw.startswith("postgresql") else "sqlite"
        metadata.create_all(self.engine)
        log.info("database ready backend=%s", self.backend)

    def healthy(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def write(self, statement: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(statement)

    def rows(self, statement: Any) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(statement)]

    def audit(self, event: str, session: str, customer_id: str, **fields: Any) -> None:
        try:
            known = {k: v for k, v in fields.items() if k in AUDIT_FIELDS and v is not None}
            self.write(audit_logs.insert().values(created_at=now_utc(), event=event, session=session,
                                                  customer_id=customer_id, **known))
        except Exception:
            log.exception("audit write failed event=%s", event)
