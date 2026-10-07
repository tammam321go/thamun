import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import jwt
from fastapi import Header, HTTPException

log = logging.getLogger("thamun.security")
ALGORITHM = "HS256"
TOKEN_HOURS = 12
SECRET = os.getenv("THAMUN_SECRET", "").strip()
if not SECRET:
    SECRET = secrets.token_urlsafe(32)
    log.warning("THAMUN_SECRET is not set. Using a temporary secret, so tokens stop working when the API restarts.")


@dataclass(frozen=True)
class Principal:
    sid: str
    customer_id: Optional[str] = None
    role: str = "demo"

    @property
    def key(self) -> str:
        return hashed(self.sid)


def auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "true").strip().lower() != "false"


def hashed(value: str) -> str:
    return hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()[:24]


def issue_token(customer_id: Optional[str] = None) -> dict:
    now = int(time.time())
    payload = {"sid": uuid.uuid4().hex, "role": "demo", "iat": now, "exp": now + TOKEN_HOURS * 3600}
    if customer_id:
        payload["cid"] = customer_id
    return {"access_token": jwt.encode(payload, SECRET, algorithm=ALGORITHM), "token_type": "bearer",
            "expires_in": TOKEN_HOURS * 3600, "customer_id": customer_id}


def read_token(token: str) -> Principal:
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM], options={"require": ["sid", "exp"]})
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Start a new session.",
                            headers={"WWW-Authenticate": "Bearer"})
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid session token.", headers={"WWW-Authenticate": "Bearer"})
    return Principal(sid=str(payload["sid"])[:64], customer_id=payload.get("cid"), role=str(payload.get("role", "demo")))


def bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def principal(authorization: Optional[str] = Header(default=None),
              x_session: Optional[str] = Header(default=None)) -> Principal:
    token = bearer(authorization)
    if token:
        return read_token(token)
    if not auth_required():
        return Principal(sid=(x_session or "public")[:64])
    raise HTTPException(status_code=401, detail="Start a session first with POST /auth/session.",
                        headers={"WWW-Authenticate": "Bearer"})


def authorise(who: Principal, customer_id: str) -> None:
    if who.customer_id and who.customer_id != customer_id:
        raise HTTPException(status_code=403, detail="This session cannot act for that customer.")


def admin(x_admin_key: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("ADMIN_KEY", "").strip()
    if not expected or not hmac.compare_digest((x_admin_key or "").encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Admin key required.")


def internal_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    listed = {h.strip().lower() for h in os.getenv("LLM_INTERNAL_HOSTS", "").split(",") if h.strip()}
    if host in listed or host == "localhost" or host.endswith((".internal", ".local", ".lan")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback


class RateLimiter:
    def __init__(self) -> None:
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float = 60.0) -> tuple[bool, int]:
        now = time.monotonic()
        bucket = self.hits[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False, max(1, int(window - (now - bucket[0])) + 1)
        bucket.append(now)
        if len(self.hits) > 20000:
            for stale in [k for k, v in self.hits.items() if not v or v[-1] <= now - window]:
                self.hits.pop(stale, None)
        return True, 0


def rate_limit() -> int:
    try:
        return max(1, int(os.getenv("RATE_LIMIT_PER_MINUTE", "240")))
    except ValueError:
        return 240
