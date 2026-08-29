"""
General-turn latency baseline for the agentic loop (backend/agent/loop.py).

Measures wall-clock time spent in each phase of a turn — the gpt-4o-mini
classify_intent/extract_slots calls and the gpt-4o agent round(s) — across a
set of representative messages, so future streaming/parallelization work
has a real "before" number instead of a guess. Package F1 (parallelizing
classify_intent + extract_slots) already
landed, so this baseline reflects that — its own README/report should be
diffed against a *second* run after any future latency change, not against
memory of "how it used to feel".

Run with:  RUN_EVALS=1 pytest tests/evals/test_latency_baseline.py -s
Requires a real OPENAI_API_KEY (real cost per run — small, but not free).
Skipped automatically otherwise (see conftest.py).

This intentionally includes short-circuit and qualification turns, so it is
the routing/general-turn baseline, not the recommendation-latency baseline.
For product-finder latency, use test_latency_baseline_tool_heavy.py and its
latency_baseline_tool_heavy_report.json; that suite exercises actual tool
calls and a multi-turn recommendation flow.

Writes a JSON report to tests/evals/latency_baseline_report.json so a later
run can be diffed against this one.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from openai.resources.chat.completions import Completions

from backend.agent.loop import process_message
from backend.engine.state_machine import ConversationSession

# Representative single-turn messages cover the main conversation paths.
MESSAGES: List[str] = [
    "Hi, what can you help me with?",
    "What do you have for outdoor parking payment terminals?",
    "We're a parking operator looking for hardware.",
    "It's for outdoor use, no host computer nearby.",
    "We need PIN entry and contactless.",
    "About 5000 transactions a month.",
    "Does the VP6300 support WiFi and Cellular?",
    "What's the operating temperature range on the VP7200?",
    "How much does the VP3300 cost?",
    "What's your shipping time?",
    "What's your warranty policy?",
    "Can I return a device if it doesn't work out?",
    "Is the VP7200 PCI compliant?",
    "Do you support ACH payments?",
    "My name is Jane Smith, jane@example.com, at Acme Parking.",
    "Yes, connect me with sales.",
    "I need to speak to a person right now.",
    "Tell me a joke.",
    "What do you think about the weather today?",
    "We're a retail store needing an indoor USB reader for card-present transactions.",
]

REPORT_PATH = Path(__file__).parent / "latency_baseline_report.json"


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def _summarize(label: str, values: List[float]) -> Dict[str, Any]:
    return {
        "label": label,
        "count": len(values),
        "p50_ms": round(_percentile(values, 50) * 1000, 1),
        "p95_ms": round(_percentile(values, 95) * 1000, 1),
        "mean_ms": round(statistics.mean(values) * 1000, 1) if values else 0.0,
        "max_ms": round(max(values) * 1000, 1) if values else 0.0,
    }


class TestLatencyBaseline:
    def test_per_turn_latency_by_phase(self, seeded_catalog, monkeypatch):
        # Patch the SDK method so every model call is timed and tagged.
        original_create = Completions.create
        call_records: List[Dict[str, Any]] = []

        def timed_create(self, *args, **kwargs):
            start = time.perf_counter()
            result = original_create(self, *args, **kwargs)
            elapsed = time.perf_counter() - start
            call_records.append({"model": kwargs.get("model", "unknown"), "elapsed_s": elapsed})
            return result

        monkeypatch.setattr(Completions, "create", timed_create)

        turn_totals: List[float] = []
        rounds_per_turn: List[int] = []
        per_turn_records: List[Dict[str, Any]] = []

        for idx, message in enumerate(MESSAGES):
            session = ConversationSession(id=f"latency-baseline-{idx}")
            call_records.clear()

            turn_start = time.perf_counter()
            process_message(message, session)
            turn_elapsed = time.perf_counter() - turn_start

            turn_totals.append(turn_elapsed)
            gpt4o_calls = [r for r in call_records if r["model"] == "gpt-4o"]
            rounds_per_turn.append(len(gpt4o_calls))
            per_turn_records.append({
                "message": message,
                "total_ms": round(turn_elapsed * 1000, 1),
                "calls": call_records.copy(),
            })

        mini_call_times = [
            r["elapsed_s"] for rec in per_turn_records for r in rec["calls"] if r["model"] == "gpt-4o-mini"
        ]
        agent_round_times = [
            r["elapsed_s"] for rec in per_turn_records for r in rec["calls"] if r["model"] == "gpt-4o"
        ]

        report = {
            "n_messages": len(MESSAGES),
            "turn_total": _summarize("turn_total (full process_message call)", turn_totals),
            "classify_extract_calls": _summarize(
                "gpt-4o-mini calls (classify_intent + extract_slots, run concurrently as of F1)",
                mini_call_times,
            ),
            "agent_round_calls": _summarize("gpt-4o calls (one per agent round)", agent_round_times),
            "rounds_per_turn": {
                "mean": round(statistics.mean(rounds_per_turn), 2) if rounds_per_turn else 0,
                "max": max(rounds_per_turn) if rounds_per_turn else 0,
            },
            "per_turn": per_turn_records,
        }

        REPORT_PATH.write_text(json.dumps(report, indent=2))

        print("\n=== Latency baseline ===")
        for key in ("turn_total", "classify_extract_calls", "agent_round_calls"):
            s = report[key]
            print(f"{s['label']}: p50={s['p50_ms']}ms p95={s['p95_ms']}ms mean={s['mean_ms']}ms max={s['max_ms']}ms (n={s['count']})")
        print(f"rounds/turn: mean={report['rounds_per_turn']['mean']} max={report['rounds_per_turn']['max']}")
        print(f"Full report written to {REPORT_PATH}")

        assert len(turn_totals) == len(MESSAGES)
