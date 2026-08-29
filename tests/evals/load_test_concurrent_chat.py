"""
Concurrent-conversation load test against a LIVE backend (H3).

Everything else measured in this repo (test_latency_baseline*.py,
test_agent_evals.py, test_load_concurrent.py) is either single-request or
runs concurrency against mocked OpenAI calls in-process. This script is
the missing piece: real concurrent HTTP traffic against a running server
(`docker compose up`, real Postgres, real Redis, real OpenAI calls), which
is the only way to see:

  - p95 turn latency under N concurrent conversations (not just 1)
  - Redis connection-pool / DB session-per-request behavior under
    concurrent load (connection exhaustion would show up as request
    errors or a latency cliff, not as a clean failure)
  - Real OpenAI rate-limit headroom for this account/tier under load
    (agent/loop.py degrades gracefully on a 429 — see
    test_load_concurrent.py — but this is the only way to see whether a
    real deploy's expected concurrency actually risks hitting one)

Requires only `httpx` (already a dependency; no locust/new dependency
needed) and a running backend. Does NOT require pytest — this is a
standalone script, run manually against a real stack:

    docker compose up -d db redis backend
    python tests/evals/load_test_concurrent_chat.py \\
        --base-url http://localhost:8000 --sessions 10 --turns 2

Writes a JSON report to tests/evals/load_test_results.json (overwritten
each run — see that file's own "generated_at" for when it was last
captured, and the checked-in copy's own note for the run this repo ships).

Costs real OpenAI tokens (one classify+extract call and 1-2 agent rounds
per turn) — sessions * turns_per_session turns total. Keep --sessions and
--turns modest for a sanity run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx

REPORT_PATH = Path(__file__).parent / "load_test_results.json"

# A handful of tool-heavy messages (see test_latency_baseline_tool_heavy.py)
# so concurrent turns actually drive the multi-round agent loop instead of
# a cheap FAQ short-circuit — the realistic worst case for concurrent load.
TURN_MESSAGES = [
    "We're a parking operator looking for an outdoor payment terminal, "
    "no host computer nearby, PIN entry and contactless required, about "
    "5000 transactions a month.",
    "Does the VP6300 support WiFi and Cellular?",
    "What's the operating temperature range on the VP7200?",
    "How much does the VP3300 cost?",
]


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


async def _run_one_session(
    client: httpx.AsyncClient, session_idx: int, turns_per_session: int, timeout_s: float
) -> Dict[str, Any]:
    """One simulated conversation: create a session, then send
    turns_per_session chat messages sequentially (a real user's turns
    within one conversation are sequential; concurrency comes from
    running many *sessions* like this one at once)."""
    turn_results: List[Dict[str, Any]] = []

    try:
        start = time.perf_counter()
        resp = await client.post("/api/session", timeout=timeout_s)
        elapsed = time.perf_counter() - start
        turn_results.append({"endpoint": "POST /api/session", "status": resp.status_code, "elapsed_s": elapsed})
        if resp.status_code != 200:
            return {"session": session_idx, "turns": turn_results, "ok": False}
        session_id = resp.json()["session_id"]
    except Exception as e:  # noqa: BLE001 - recorded, not raised
        return {"session": session_idx, "turns": [{"endpoint": "POST /api/session", "error": str(e)}], "ok": False}

    for i in range(turns_per_session):
        message = TURN_MESSAGES[i % len(TURN_MESSAGES)]
        try:
            start = time.perf_counter()
            resp = await client.post(
                "/api/chat",
                json={"message": message, "session_id": session_id},
                timeout=timeout_s,
            )
            elapsed = time.perf_counter() - start
            turn_results.append({
                "endpoint": "POST /api/chat",
                "status": resp.status_code,
                "elapsed_s": elapsed,
                "message": message,
            })
        except Exception as e:  # noqa: BLE001 - recorded, not raised
            turn_results.append({"endpoint": "POST /api/chat", "error": str(e), "message": message})

    return {"session": session_idx, "turns": turn_results, "ok": True}


async def run_load_test(base_url: str, n_sessions: int, turns_per_session: int, timeout_s: float) -> Dict[str, Any]:
    limits = httpx.Limits(max_connections=n_sessions, max_keepalive_connections=n_sessions)
    async with httpx.AsyncClient(base_url=base_url, limits=limits) as client:
        wall_start = time.perf_counter()
        session_results = await asyncio.gather(*[
            _run_one_session(client, i, turns_per_session, timeout_s) for i in range(n_sessions)
        ])
        wall_elapsed = time.perf_counter() - wall_start

    chat_latencies: List[float] = []
    status_counts: Dict[str, int] = {}
    errors: List[str] = []

    for sr in session_results:
        for turn in sr["turns"]:
            if "error" in turn:
                errors.append(f"session {sr['session']} {turn['endpoint']}: {turn['error']}")
                continue
            status_counts[str(turn["status"])] = status_counts.get(str(turn["status"]), 0) + 1
            if turn["endpoint"] == "POST /api/chat" and turn["status"] == 200:
                chat_latencies.append(turn["elapsed_s"])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "n_sessions": n_sessions,
        "turns_per_session": turns_per_session,
        "wall_clock_s": round(wall_elapsed, 2),
        "chat_turn_latency": {
            "count": len(chat_latencies),
            "p50_ms": round(_percentile(chat_latencies, 50) * 1000, 1),
            "p95_ms": round(_percentile(chat_latencies, 95) * 1000, 1),
            "mean_ms": round(statistics.mean(chat_latencies) * 1000, 1) if chat_latencies else 0.0,
            "max_ms": round(max(chat_latencies) * 1000, 1) if chat_latencies else 0.0,
        },
        "status_counts": status_counts,
        "errors": errors,
        "session_results": session_results,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--sessions", type=int, default=10, help="Number of concurrent conversations")
    parser.add_argument("--turns", type=int, default=2, help="Chat turns per session (sequential within a session)")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    report = asyncio.run(run_load_test(args.base_url, args.sessions, args.turns, args.timeout))

    REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(f"\n=== Concurrent load test: {args.sessions} sessions x {args.turns} turns ===")
    print(f"wall clock: {report['wall_clock_s']}s")
    lat = report["chat_turn_latency"]
    print(f"POST /api/chat latency: p50={lat['p50_ms']}ms p95={lat['p95_ms']}ms mean={lat['mean_ms']}ms max={lat['max_ms']}ms (n={lat['count']})")
    print(f"status counts: {report['status_counts']}")
    if report["errors"]:
        print(f"{len(report['errors'])} request(s) errored:")
        for e in report["errors"][:10]:
            print(f"  - {e}")
    print(f"Full report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
