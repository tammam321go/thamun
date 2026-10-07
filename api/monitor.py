import json
import math
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any, Optional

EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"
MIN_DRIFT_SAMPLE = 200


def percentile(values: list[float], share: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(share * len(ordered)) - 1))
    return round(ordered[index], 2)


def evidence(name: str) -> Optional[Any]:
    path = EVIDENCE_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None


def psi(expected: list[float], observed: list[float]) -> float:
    total = 0.0
    for e, o in zip(expected, observed):
        e, o = max(e, 1e-4), max(o, 1e-4)
        total += (o - e) * math.log(o / e)
    return round(total, 4)


class Monitor:
    def __init__(self) -> None:
        self.started = time.time()
        self.requests = 0
        self.server_errors = 0
        self.client_errors = 0
        self.rate_limited = 0
        self.recent: deque = deque(maxlen=5000)
        self.decisions: Counter = Counter()
        self.scores: deque = deque(maxlen=5000)

    def record(self, path: str, status: int, ms: float) -> None:
        self.requests += 1
        if status >= 500:
            self.server_errors += 1
        elif status == 429:
            self.rate_limited += 1
        elif status >= 400:
            self.client_errors += 1
        self.recent.append((time.time(), path, status, ms))

    def record_check(self, decision: str, probability: Optional[float], high: Optional[bool]) -> None:
        self.decisions[decision] += 1
        if probability is not None:
            self.scores.append((float(probability), bool(high)))

    def latency(self, prefix: Optional[str] = None) -> dict[str, Any]:
        values = [ms for _, path, _, ms in self.recent if prefix is None or path.startswith(prefix)]
        return {"count": len(values), "avg_ms": round(sum(values) / len(values), 2) if values else None,
                "p50_ms": percentile(values, 0.5), "p95_ms": percentile(values, 0.95)}

    def drift(self) -> dict[str, Any]:
        reference = evidence("reference")
        live = len(self.scores)
        out: dict[str, Any] = {"live_checks": live, "minimum_sample": MIN_DRIFT_SAMPLE,
                               "reference": "validation month, synthetic data" if reference else None}
        if not reference:
            return dict(out, status="no reference file", score_psi=None, high_risk_share=None)
        edges = reference["score_edges"]
        counts = [0] * (len(edges) + 1)
        for probability, _ in self.scores:
            counts[sum(1 for edge in edges if probability >= edge)] += 1
        share_high = sum(1 for _, high in self.scores if high) / live if live else None
        out.update(reference_high_risk_share=reference["high_risk_share"],
                   high_risk_share=round(share_high, 4) if share_high is not None else None)
        if live < MIN_DRIFT_SAMPLE:
            return dict(out, status="not enough live checks yet", score_psi=None)
        value = psi(reference["score_shares"], [c / live for c in counts])
        status = "stable" if value < 0.1 else "watch" if value < 0.25 else "investigate before retraining"
        return dict(out, status=status, score_psi=value)

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        last_minute = sum(1 for ts, _, _, _ in self.recent if ts >= now - 60)
        handled = max(self.requests, 1)
        checks = sum(v for k, v in self.decisions.items() if k in ("silent", "nudge", "pause"))
        return {
            "source": "live counters of this API process since it started (demo traffic)",
            "uptime_seconds": int(now - self.started),
            "requests": self.requests,
            "requests_last_minute": last_minute,
            "error_rate": round(self.server_errors / handled, 4),
            "client_error_rate": round(self.client_errors / handled, 4),
            "rate_limited": self.rate_limited,
            "latency_all": self.latency(),
            "latency_check": self.latency("/check"),
            "decisions": dict(self.decisions),
            "decision_mix": {k: round(self.decisions[k] / checks, 4) for k in ("silent", "nudge", "pause")} if checks else None,
            "drift": self.drift(),
        }
