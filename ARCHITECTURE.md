# Architecture Notes

Design assessment of the conversational agent, evaluated against Anthropic's
[Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents).
This document is for maintainers reasoning about the agent's design and its
open trade-offs; for setup and usage see the [README](./README.md).

## Workflow pattern: Routing gating an Agent

The core loop (`backend/agent/loop.py`) is a **Routing** workflow in front of
an **Agent**:

- `classify_intent()` deterministically routes each turn to either a fixed
  short-circuit response (pure FAQ, chitchat, escalation) **or** into a
  bounded, model-driven tool-calling loop (`MAX_TOOL_ROUNDS = 5`).
- Inside that loop, the model itself decides how many rounds to run and which
  tools to call. This is **not** prompt chaining — the number and order of
  tool calls is decided by the model turn-to-turn, not by a fixed sequence of
  prompts.

So the system is a hybrid: a cheap, predictable **Routing** gate protecting a
flexible **Agent** for the genuinely open-ended cases — the "compose patterns,
don't over-engineer" approach the article recommends.

## What the design already gets right

- **Routing** narrows the tool surface per intent
  (`agent/tools/registry.py::get_tools_for_intent`) — fewer irrelevant tools in
  context, less hallucination risk.
- **Stopping condition** — `MAX_TOOL_ROUNDS` bounds the loop instead of letting
  it run unbounded.
- **Transparency** — `ReasoningTrace` (`services/logger.py`) logs intent, tool
  calls, and results per turn.
- **Tool descriptions read like good docstrings** — e.g. `search_products`'s
  `use_case` param enumerates valid verticals directly in its description,
  which is exactly Appendix 2's "write it like a docstring for a junior
  developer" advice.

## Findings

| Issue | File | Risk | Status |
|---|---|---|---|
| Blanket `except Exception` returned raw `str(e)` as the HTTP body | `routers/chat.py` | Leaked internal errors straight to the customer-facing chat widget | ✅ Fixed |
| Silent fallback to `"test-key"` if `OPENAI_API_KEY` unset | `agent/loop.py`, `main.py` | Missing config failed cryptically mid-request instead of loudly at startup | ✅ Fixed (fail-fast startup check) |
| No retry/timeout around the OpenAI call | `agent/loop.py` | A transient network blip or rate-limit crashed the whole turn | ✅ Fixed (`timeout=20s`, `max_retries=2`, graceful fallback on `OpenAIError`) |
| `get_product_details` silently fell back to `rows[0]` when no exact model-name match | `agent/tools/get_product_details.py` | Poka-yoke violation (Appendix 2) — the agent could confidently describe the *wrong* product to a customer | ✅ Fixed (returns an error with `did_you_mean` candidates so the agent disambiguates) |
| Conversation state lives only in a process-local dict | `engine/conversation_store.py` | Any restart/redeploy silently drops every in-progress conversation; doesn't work across >1 worker process | ⚠️ Open |
| Hardcoded DB credentials as source default | `db/session.py` | Committed fallback connection string, should be `.env`-only | ⚠️ Open |
| Business logic bypasses FastAPI DI, calls `SessionLocal()` directly | `lead_service.py`, `search_products.py`, `get_product_details.py` | Couples tools to one global engine, harder to test/swap | ⚠️ Open |
| No conversion/resolution metric surfaced anywhere | `frontend/.../Dashboard.tsx` | `lead_submitted` / `recommendation_shown` are tracked per-session but never rolled up — per Appendix 1, agentic customer-support tools are judged by resolution rate, and right now there's no view that shows one | ⚠️ Open |
