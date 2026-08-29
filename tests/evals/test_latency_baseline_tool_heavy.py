"""
Supplementary latency baseline (H3) using tool-heavy prompts.

`test_latency_baseline.py`'s committed report
(`latency_baseline_report.json`) reports p50=1.77s but averages only 0.9
gpt-4o agent rounds per turn — most of its MESSAGES list are single,
isolated fresh-session messages (short qualification answers, FAQ
questions) that the router short-circuits or answers in one round, so the
baseline mostly measures the *cheap* paths through `process_message()`
rather than the multi-round tool-calling agent loop that a real product
search or spec lookup exercises.

This file measures the paths that DO drive the agent loop through
multiple `gpt-4o` rounds:

  - Named-product spec questions (the get_product_details bypass) — these
    already showed 2 rounds / 3-5s in the original baseline's own data,
    the highest-latency rows in that report.
  - Single messages carrying enough qualification info at once to let the
    agent call search_products (and often follow up with
    get_solution_content) in the same turn, instead of asking a
    clarifying question back.
  - A full multi-turn conversation run in ONE session (qualification ->
    recommendation -> lead capture, the flow documented in the README's
    "Example Chat Interaction") — the shape a real prospect's session
    actually takes, where accumulated context from prior turns is what
    lets a later turn's tool calls actually resolve.

Run with:  RUN_EVALS=1 pytest tests/evals/test_latency_baseline_tool_heavy.py -s
Requires a real OPENAI_API_KEY (real cost per run — small, but not free).

Writes tests/evals/latency_baseline_tool_heavy_report.json.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from openai.resources.chat.completions import Completions

from backend.agent.loop import process_message
from backend.engine.state_machine import ConversationSession

# Each of these is sent as the FIRST message of its own fresh session, but
# carries enough information (or names a real product) that the agent
# should be able to act — call a tool — rather than ask a clarifying
# question back. Contrast with test_latency_baseline.py's MESSAGES, most of
# which are deliberately partial/isolated qualification answers.
SINGLE_TURN_TOOL_HEAVY_MESSAGES: List[str] = [
    "Does the VP6300 support WiFi and Cellular?",
    "What's the operating temperature range on the VP7200?",
    "How much does the VP3300 cost?",
    "Is the VP7200 PCI compliant?",
    "Compare the VP3300 and the VP7200 for me.",
    "We're a parking operator looking for an outdoor payment terminal, "
    "no host computer nearby, PIN entry and contactless required, about "
    "5000 transactions a month — what do you recommend?",
    "We're a retail store needing an indoor USB reader for card-present "
    "transactions. Can you recommend something and tell me more about it?",
    "Show me your outdoor terminals that support cellular connectivity.",
]

# A single realistic multi-turn conversation, run in ONE session so later
# turns build on earlier ones' collected_info — the qualification ->
# recommendation -> lead-capture flow from the README's "Example Chat
# Interaction". Real conversations accumulate context across turns; a
# fresh-session-per-message baseline structurally can't reach the
# search_products / get_solution_content / submit_lead calls this flow
# exercises.
MULTI_TURN_CONVERSATION: List[str] = [
    "Hi, we need a payment terminal for our parking lots.",
    "It's for outdoor use, no host computer nearby.",
    "We need PIN entry, and support for contact, contactless, and magstripe cards.",
    "About 5000 transactions a month, and yes we need a display.",
    "That looks good — what's next?",
    "My name is Jane Smith, jane@example.com, Acme Parking Co.",
]

REPORT_PATH = Path(__file__).parent / "latency_baseline_tool_heavy_report.json"


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


class TestToolHeavyLatencyBaseline:
    def test_tool_heavy_latency(self, seeded_catalog, monkeypatch):
        original_create = Completions.create
        call_records: List[Dict[str, Any]] = []

        def timed_create(self, *args, **kwargs):
            start = time.perf_counter()
            result = original_create(self, *args, **kwargs)
            elapsed = time.perf_counter() - start
            call_records.append({"model": kwargs.get("model", "unknown"), "elapsed_s": elapsed})
            return result

        monkeypatch.setattr(Completions, "create", timed_create)

        # ── Part 1: single-turn tool-heavy messages, fresh session each ──
        single_turn_totals: List[float] = []
        single_turn_rounds: List[int] = []
        single_turn_records: List[Dict[str, Any]] = []

        for idx, message in enumerate(SINGLE_TURN_TOOL_HEAVY_MESSAGES):
            session = ConversationSession(id=f"latency-tool-heavy-{idx}")
            call_records.clear()

            start = time.perf_counter()
            process_message(message, session)
            elapsed = time.perf_counter() - start

            single_turn_totals.append(elapsed)
            gpt4o_calls = [r for r in call_records if r["model"] == "gpt-4o"]
            single_turn_rounds.append(len(gpt4o_calls))
            single_turn_records.append({
                "message": message,
                "total_ms": round(elapsed * 1000, 1),
                "rounds": len(gpt4o_calls),
                "calls": call_records.copy(),
            })

        # ── Part 2: one multi-turn conversation in a single session ──
        convo_session = ConversationSession(id="latency-tool-heavy-multiturn")
        multiturn_totals: List[float] = []
        multiturn_rounds: List[int] = []
        multiturn_records: List[Dict[str, Any]] = []

        convo_start = time.perf_counter()
        for message in MULTI_TURN_CONVERSATION:
            call_records.clear()
            start = time.perf_counter()
            process_message(message, convo_session)
            elapsed = time.perf_counter() - start

            multiturn_totals.append(elapsed)
            gpt4o_calls = [r for r in call_records if r["model"] == "gpt-4o"]
            multiturn_rounds.append(len(gpt4o_calls))
            multiturn_records.append({
                "message": message,
                "total_ms": round(elapsed * 1000, 1),
                "rounds": len(gpt4o_calls),
                "calls": call_records.copy(),
            })
        convo_total_elapsed = time.perf_counter() - convo_start

        all_totals = single_turn_totals + multiturn_totals
        all_rounds = single_turn_rounds + multiturn_rounds

        report = {
            "note": (
                "Supplementary to latency_baseline_report.json (H3) — that "
                "report's messages average 0.9 gpt-4o rounds/turn (mostly "
                "short-circuits); this one targets messages that actually "
                "drive the multi-round tool-calling agent loop."
            ),
            "combined_turn_total": _summarize(
                "turn_total, all tool-heavy turns (single-turn messages + multi-turn conversation)",
                all_totals,
            ),
            "combined_rounds_per_turn": {
                "mean": round(statistics.mean(all_rounds), 2) if all_rounds else 0,
                "max": max(all_rounds) if all_rounds else 0,
            },
            "single_turn": {
                "turn_total": _summarize("turn_total (fresh session per message)", single_turn_totals),
                "rounds_per_turn": {
                    "mean": round(statistics.mean(single_turn_rounds), 2) if single_turn_rounds else 0,
                    "max": max(single_turn_rounds) if single_turn_rounds else 0,
                },
                "per_turn": single_turn_records,
            },
            "multi_turn_conversation": {
                "n_turns": len(MULTI_TURN_CONVERSATION),
                "conversation_wall_clock_s": round(convo_total_elapsed, 2),
                "turn_total": _summarize("turn_total (same session, accumulating context)", multiturn_totals),
                "rounds_per_turn": {
                    "mean": round(statistics.mean(multiturn_rounds), 2) if multiturn_rounds else 0,
                    "max": max(multiturn_rounds) if multiturn_rounds else 0,
                },
                "per_turn": multiturn_records,
            },
        }

        REPORT_PATH.write_text(json.dumps(report, indent=2))

        print("\n=== Tool-heavy latency baseline ===")
        s = report["combined_turn_total"]
        print(f"combined turn_total: p50={s['p50_ms']}ms p95={s['p95_ms']}ms mean={s['mean_ms']}ms max={s['max_ms']}ms (n={s['count']})")
        print(f"combined rounds/turn: mean={report['combined_rounds_per_turn']['mean']} max={report['combined_rounds_per_turn']['max']}")
        print(f"multi-turn conversation wall clock: {report['multi_turn_conversation']['conversation_wall_clock_s']}s over {len(MULTI_TURN_CONVERSATION)} turns")
        print(f"Full report written to {REPORT_PATH}")

        assert len(single_turn_totals) == len(SINGLE_TURN_TOOL_HEAVY_MESSAGES)
        assert len(multiturn_totals) == len(MULTI_TURN_CONVERSATION)
