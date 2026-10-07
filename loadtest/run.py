import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "api" / "evidence"


def read_stats(prefix: Path) -> dict[str, dict[str, Any]]:
    with open(f"{prefix}_stats.csv", newline="") as handle:
        return {row["Name"]: row for row in csv.DictReader(handle)}


def summary(row: dict[str, Any]) -> dict[str, Any]:
    return {"requests": int(row["Request Count"]), "failures": int(row["Failure Count"]),
            "p50_ms": int(float(row["50%"])), "p95_ms": int(float(row["95%"])), "p99_ms": int(float(row["99%"])),
            "average_ms": round(float(row["Average Response Time"]), 1), "max_ms": int(float(row["Max Response Time"]))}


def run_stage(host: str, users: int, seconds: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as folder:
        prefix = Path(folder) / "run"
        command = [sys.executable, "-m", "locust", "-f", str(ROOT / "loadtest" / "locustfile.py"), "--headless",
                   "-u", str(users), "-r", str(max(1, users // 5)), "-t", f"{seconds}s", "--host", host,
                   "--csv", str(prefix), "--only-summary"]
        subprocess.run(command, check=False, capture_output=True, text=True)
        stats = read_stats(prefix)
    total = stats["Aggregated"]
    requests, failures = int(total["Request Count"]), int(total["Failure Count"])
    return {"users": users, "duration_seconds": seconds, "requests": requests, "failures": failures,
            "failure_rate": round(failures / requests, 5) if requests else None,
            "requests_per_second": round(float(total["Requests/s"]), 1),
            "all": summary(total), "check": summary(stats["/check"]),
            "by_route": {name: summary(row) for name, row in stats.items() if name != "Aggregated"}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--users", default="25,100,200")
    parser.add_argument("--seconds", type=int, default=40)
    parser.add_argument("--workers", type=int, default=1, help="uvicorn workers the API was started with")
    parser.add_argument("--note", default="")
    parser.add_argument("--observation", default="")
    args = parser.parse_args()
    stages = []
    for users in [int(u) for u in args.users.split(",")]:
        stage = run_stage(args.host, users, args.seconds)
        stages.append(stage)
        print(f"{users} users: {stage['requests_per_second']} req/s, failures {stage['failures']}, "
              f"/check p50 {stage['check']['p50_ms']} ms p95 {stage['check']['p95_ms']} ms p99 {stage['check']['p99_ms']} ms")
    clean = [s for s in stages if s["failure_rate"] is not None and s["failure_rate"] < 0.01 and s["check"]["p95_ms"] <= 500]
    largest = clean[-1] if clean else stages[0]
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "tool": "Locust",
        "environment": (f"Measured on one machine with {os.cpu_count()} CPU cores ({platform.system()}), API and load "
                        f"generator on the same machine, {args.workers} API worker, SQLite. {args.note}").strip(),
        "scenario": "Each simulated user opens a session, then repeats: risk check and cancel (60%), home (20%), "
                    "number check (10%), health (10%), with 0.5 to 1.5 seconds between actions.",
        "headline": "Largest stage with under 1% failures and a 95th percentile risk check under 500 ms.",
        "users": largest["users"], "duration_seconds": largest["duration_seconds"], "requests": largest["requests"],
        "failures": largest["failures"], "failure_rate": largest["failure_rate"],
        "requests_per_second": largest["requests_per_second"], "check": largest["check"], "stages": stages,
        "rate_limit_observation": args.observation or None,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "load_test.json").write_text(json.dumps(result, indent=2))
    print(f"saved {EVIDENCE / 'load_test.json'}")


if __name__ == "__main__":
    main()
