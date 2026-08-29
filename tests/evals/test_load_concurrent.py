"""
Concurrent-conversation load test (H3).

Two things this repo had zero coverage of before this file:

1. Everything measured so far (unit tests, `test_latency_baseline*.py`,
   `test_agent_evals.py`) is single-request, sequential. Nothing exercised
   what happens when several conversations run through `process_message()`
   at the same time — the OpenAI SDK client, DB session-per-call
   (`session_scope()`), and Redis connection pool are all created and used
   per-request, so concurrent behavior isn't guaranteed by the sequential
   tests passing.
2. `agent/loop.py` catches `OpenAIError` (which `RateLimitError` is a
   subclass of) around every `client.chat.completions.create(...)` call and
   degrades to a safe fallback response (see `_safe_fallback()`) instead of
   raising — but nothing asserted that this holds up when several turns hit
   a 429 *concurrently*, not just one at a time.

This uses mocked OpenAI calls (fast, free, deterministic) run across real
OS threads via `ThreadPoolExecutor` against the real `process_message()`
+ real SQLite-backed tool calls (via the `seeded_catalog` fixture) — so
it's the actual agent-loop code path under real concurrency, just without
spending real OpenAI tokens or needing a live DB/Redis. It does not cover
the conversation-store (Redis) or HTTP layer — those are exercised by the
live, real-network run in `load_test_concurrent_chat.py` (same directory)
and its checked-in results report, which also covers real OpenAI-side
rate-limit headroom under concurrency.

Lives alongside the other eval files and is skipped the same way
(`tests/evals/conftest.py` skips everything in this directory unless
RUN_EVALS=1) purely for consistency of location — it doesn't actually need
a real OPENAI_API_KEY or spend real tokens, since OpenAI is mocked here.
Run with:  RUN_EVALS=1 pytest tests/evals/test_load_concurrent.py -q
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import httpx2
import pytest
from openai import RateLimitError
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from backend.agent.loop import process_message
from backend.engine.state_machine import ConversationSession


def _fake_completion(content: str) -> ChatCompletion:
    return ChatCompletion(
        id="chatcmpl-fake",
        object="chat.completion",
        created=0,
        model="gpt-4o",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=ChatCompletionMessage(role="assistant", content=content),
            )
        ],
    )


def _fake_rate_limit_error() -> RateLimitError:
    request = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx2.Response(status_code=429, request=request)
    return RateLimitError("Rate limit exceeded", response=response, body=None)


class TestConcurrentSessionsAgainstMockedOpenAI:
    """N simulated conversations, each in its own session, run
    concurrently through process_message(). No two sessions share state,
    so nothing here should fail, deadlock, or cross-contaminate."""

    N_CONCURRENT_SESSIONS = 20

    def test_concurrent_sessions_all_succeed(self, seeded_catalog, monkeypatch):
        call_count = {"n": 0}
        lock = threading.Lock()

        def fake_create(self, *args, **kwargs):
            with lock:
                call_count["n"] += 1
            return _fake_completion("Thanks! How can I help?")

        monkeypatch.setattr(
            "openai.resources.chat.completions.Completions.create", fake_create
        )

        def run_one(idx: int):
            session = ConversationSession(id=f"load-concurrent-{idx}")
            return process_message("What outdoor terminals do you have?", session)

        results = []
        with ThreadPoolExecutor(max_workers=self.N_CONCURRENT_SESSIONS) as pool:
            futures = [pool.submit(run_one, i) for i in range(self.N_CONCURRENT_SESSIONS)]
            for f in as_completed(futures):
                results.append(f.result())

        assert len(results) == self.N_CONCURRENT_SESSIONS
        assert all(r.text for r in results), "every concurrent turn should produce a non-empty response"
        assert call_count["n"] >= self.N_CONCURRENT_SESSIONS, (
            "expected at least one OpenAI call per concurrent session"
        )

    def test_concurrent_sessions_degrade_gracefully_under_openai_429(self, seeded_catalog, monkeypatch):
        """Half the concurrent turns get a simulated OpenAI 429. None of
        them should raise — agent/loop.py's `_safe_fallback()` path should
        catch it per-request, independent of what's happening on other
        threads at the same time."""

        def flaky_create(self, *args, **kwargs):
            # Every other call (across all threads) fails with 429.
            if flaky_create.counter % 2 == 0:
                flaky_create.counter += 1
                raise _fake_rate_limit_error()
            flaky_create.counter += 1
            return _fake_completion("Here's what I found.")

        flaky_create.counter = 0
        lock = threading.Lock()

        def locked_flaky_create(self, *args, **kwargs):
            with lock:
                return flaky_create(self, *args, **kwargs)

        monkeypatch.setattr(
            "openai.resources.chat.completions.Completions.create", locked_flaky_create
        )

        def run_one(idx: int):
            session = ConversationSession(id=f"load-429-{idx}")
            # A 429 should produce a fallback response, not an exception.
            return process_message("What outdoor terminals do you have?", session)

        results = []
        errors: List[BaseException] = []

        def safe_run(idx: int):
            try:
                results.append(run_one(idx))
            except BaseException as e:  # noqa: BLE001 - this IS the assertion
                errors.append(e)

        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(safe_run, range(20)))

        assert not errors, f"process_message() raised under concurrent 429s: {errors}"
        assert len(results) == 20
        assert all(r.text for r in results), "every turn should still get a non-empty response, even the 429'd ones"
