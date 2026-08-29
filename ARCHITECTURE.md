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
| Silent fallback to `"test-key"` if `OPENAI_API_KEY` unset | `agent/loop.py`, `agent/classifier.py`, `main.py` | Missing config failed cryptically mid-request instead of loudly at startup | ✅ Fixed (fail-fast startup check; the `"test-key"` fallback strings themselves were still present in both call sites and have now been removed too — see 2026-08-28 follow-up below) |
| No retry/timeout around the OpenAI call | `agent/loop.py` | A transient network blip or rate-limit crashed the whole turn | ✅ Fixed (`timeout=20s`, `max_retries=2`, graceful fallback on `OpenAIError`) |
| `get_product_details` silently fell back to `rows[0]` when no exact model-name match | `agent/tools/get_product_details.py` | Poka-yoke violation (Appendix 2) — the agent could confidently describe the *wrong* product to a customer | ✅ Fixed (returns an error with `did_you_mean` candidates so the agent disambiguates) |
| Conversation state lives only in a process-local dict | `engine/conversation_store.py` | Any restart/redeploy silently drops every in-progress conversation; doesn't work across >1 worker process | ✅ Fixed (2026-08-28) — Redis-backed store, see "Persistent conversation store" below |
| Hardcoded DB credentials as source default | `db/session.py` | Committed fallback connection string, should be `.env`-only | ✅ Fixed (2026-08-28) — `DATABASE_URL` is now required, fails fast like `OPENAI_API_KEY`; `echo=True` also turned off by default (`SQL_ECHO=1` to opt in) |
| Business logic bypasses FastAPI DI, calls `SessionLocal()` directly | `lead_service.py`, `search_products.py`, `get_product_details.py`, `product_matcher.py` | Couples tools to one global engine, harder to test/swap | ✅ Fixed (2026-08-28) — all four now go through `db/session.py::session_scope()`, a single injectable context manager, instead of importing `SessionLocal` at each call site |
| No conversion/resolution metric surfaced anywhere | `frontend/.../Dashboard.tsx` | `lead_submitted` / `recommendation_shown` are tracked per-session but never rolled up — per Appendix 1, agentic customer-support tools are judged by resolution rate, and right now there's no view that shows one | ✅ Fixed (2026-08-28) — see below |
| No auth on `/api/lead/*` and `/api/maintenance/*` | `routers/lead.py`, `routers/maintenance/*` | Any unauthenticated caller could read every captured lead's PII, or edit/delete the product catalog | ✅ Fixed (2026-08-28) — see "Security hardening" below |
| Session IDs act as unauthenticated bearer tokens | `routers/chat.py` (`GET /api/session/{id}`) | A session_id alone (logged in access logs, sitting in localStorage) was enough to read a transcript containing a prospect's name/email/phone | ✅ Fixed (2026-08-28) — see below |
| No rate limiting on `/api/chat` / `/api/session` | `routers/chat.py` | Unauthenticated, unbounded — a trivially scriptable way to run up an OpenAI bill or exhaust quota | ✅ Fixed (2026-08-28) — see below |

### 2026-08-28 follow-up

- **Conversation persistence (fixed, 2026-08-28 — see "Persistent conversation store" below for the full Redis fix).** `ConversationStore` now evicts sessions idle longer than `SESSION_TTL_SECONDS` (default 4h), so the process no longer grows unbounded. The frontend now persists `session_id` in `localStorage` and rehydrates the transcript via a new `GET /api/session/{id}` endpoint on page load/refresh, so a refresh no longer silently starts a new conversation. At the time this note was first written the store was still a single process-local dict — a restart or a second worker process would still lose/fragment sessions; that gap is what the Redis-backed store closes.
- **Resolution-rate metric (fixed).** Added a `conversation_events` table (`session_started` / `recommendation_shown` / `lead_submitted`) logged best-effort from `routers/chat.py` on each turn, a `GET /api/lead/metrics` aggregation endpoint, and a funnel summary on the admin Dashboard (conversations started → reached a recommendation → converted to a lead, with rates). Event logging failures are caught and logged, never allowed to break a chat turn.
- **`"test-key"` fallback removed.** `agent/loop.py` and `agent/classifier.py` both still had `or "test-key"` as an OpenAI API key fallback, contradicting the fail-fast startup check added earlier — if `SKIP_STARTUP_CHECKS` was ever set, a request would silently authenticate with a fake key instead of failing clearly. Removed; a missing key now surfaces as an `OpenAIError` (loop.py, caught → graceful fallback response) or an import-time failure (classifier.py singleton).
- **Dead code removed.** `tools=tools if tool_names_used else tools` in `loop.py` was a no-op (both branches identical) — simplified to `tools=tools`.
- **Human-contact link added.** The escalation strip in `ChatWindow.tsx` and any bot message with `ui_actions: ["offer_booking"]` now link to `https://idtechproducts.com/contact/` (the latter was previously only `console.log`'d, never rendered — the booking CTA never actually reached the user).
- **DebugPanel was unconditionally rendered on the customer-facing page**, including in a production build — a floating "Debug" button exposing `collectedInfo`/session state to any visitor. Gated behind `import.meta.env.DEV` (`App.tsx`), so it only appears in `npm run dev`, never in the built app.
- **Heading font mismatch (false alarm, but one real gap).** idtechproducts.com's actual stylesheet uses Inter for body text, matching what this app already used — but layers in **Inter Tight** for headings, which this app didn't. Added.
- **Live-tested a real prospect message and found a routing bug**: "does the VP6300 support WiFi and Cellular?" was answered with generic support-hours boilerplate instead of the real spec. Root cause: the FAQ short-circuit (`_has_only_faq_intent` / `_detect_faq_topic` in `loop.py`) keyword-matched the word "support" used as a verb ("does X **support** Y") to the customer-support FAQ topic, before the question ever reached the tool-calling agent that could call `get_product_details`. Fixed with (1) a product-name-aware bypass — a message naming a known model shape (`VP\d+`, `AP\d+`, `Kiosk IV`, ...) always goes to the full agent loop instead of the FAQ shortcut, and (2) a "support-as-verb" guard in `_detect_faq_topic` so `support` + a connectivity/spec term (wifi, NFC, PIN, ...) routes to `compatibility` instead of `support`. Covered by new unit tests in `test_loop.py` and verified live against the running app.
- **Added a golden-case eval suite** (`tests/evals/`, opt-in via `RUN_EVALS=1 pytest tests/evals`, real OpenAI calls) — the gap the VP6300 bug above exposed: 283 unit tests all mock the LLM, so nothing previously checked actual model *behavior* (right tool picked, answer grounded in real product data, price never fabricated even when a system-prompt-only guardrail is the only thing stopping it, escalation actually reaches handoff). 6 cases today, all passing against the real API on a seeded SQLite catalog; sibling to `tests/backend/` (not under it) so it's never swept up by CI's `pytest tests/backend` or run without the explicit opt-in.
- **`get_product_details`'s exact-match gate replaced with a similarity-ranked match** (`difflib.SequenceMatcher`, no new dependency). It used to require literal string equality — case-insensitive, but a stray space ("VP 3300") or single-char typo ("VP63OO") failed it entirely, and its `ILIKE`-based candidate search couldn't even find a typo'd name that isn't a literal substring of the real one. Now: auto-resolve above a confident-match threshold (0.82 — chosen so a 1-word-off partial like "VP33" against both VP3300/VP3350, tied at 0.8, still correctly refuses to auto-guess between them, matching the tool's original "don't confidently show the wrong product" purpose), suggest via `did_you_mean` between 0.82 and a suggestion floor (0.3), plain not-found below the floor so an unrelated query doesn't surface noise. Falls back to the full active catalog as candidates when the `ILIKE` search returns nothing, so a real near-miss is still found. Covered by 7 tests (4 original + 3 new), all passing.
- **System prompt now includes the real catalog's model names** (`prompts.py::_build_model_names_section`, queried fresh per turn — not cached, since the catalog is admin-editable live). Previously the model had a valid-values list for `use_case`/`category` but nothing for product names, so a user-typo'd model name in a cold ask (not a `search_products` follow-up) had no ground truth to self-correct against before calling `get_product_details`. This is the first line of defense; the `difflib` fix above is the backstop for whatever still slips through.
- **Found a second, narrower instance of the same routing gap while verifying the fix above**: `_PRODUCT_NAME_PATTERN` (added for the VP6300 bug) required digits immediately after the model prefix — "vp 6300" (with a space) wasn't recognized as naming a product and fell back through to the FAQ shortcut. Fixed with `\s?` between prefix and digits; regression-tested.
- **Root cause was misdiagnosed, then found and fixed for real.** The write-up above initially chalked the remaining "does the vp 6300 support wifi?" failure up to LLM tool-choice non-determinism and shipped it as a tracked `xfail`. That diagnosis was wrong. Direct instrumentation of `process_message()` (tracing every `_dispatch_tool` call) showed the model wasn't choosing badly — it was structurally unable to call `get_product_details` at all: `get_tools_for_intent("faq")` (`agent/tools/registry.py`) never included that tool in its list, and both phrasings classified as intent `"faq"`. The "verified working" answer shown earlier in this doc's history for "Does the VP6300 support WiFi and Cellular?" was not tool-grounded — it was the model answering from its own guess with the real tool unavailable, and re-running it showed it isn't even reliably right: **the actual catalog VP6300 does not support WiFi/Cellular** (RS232 & USB HID only), contradicting what was reported as a passing verification.
  - Fixed in `loop.py`: after `tools = get_tools_for_intent(intent)`, `GET_PRODUCT_DETAILS_TOOL` is added whenever the message matches `_PRODUCT_NAME_PATTERN`, regardless of classified intent — deterministic, not a prompt nudge. Verified live and via direct tool-call tracing that `get_product_details` is now invoked on every run for both phrasings, returning the same correct, DB-grounded answer each time.
  - The `xfail` eval case was converted to a normal passing assertion (`test_short_ambiguous_compatibility_phrasing_uses_real_spec`) and re-run for real — 7/7 eval cases pass.
  - Lesson for future debugging in this codebase: when a tool-calling agent gives a plausible-sounding wrong or inconsistent answer, check `get_tools_for_intent()` for the classified intent before assuming it's a prompt-wording or model-non-determinism problem — a tool that was never offered will always look like "the model chose not to use it."

### Systematic tool-surface audit (2026-08-28)

The VP6300 bug above was one instance of a root-cause class — a tool that
was never offered for an intent, which always *looks* like a model
tool-choice mistake. Rather than wait to find the next instance by luck,
every `get_tools_for_intent()` entry was audited against a concrete
justifying user message before changing anything, per the guiding principle
that widening the tool surface undermines the Routing design's whole point
(fewer tools per intent = less hallucination risk) — a tool is added to an
intent only when a realistic message classifies into it and genuinely needs
that tool, never "give every intent every tool."

| Intent | Gap | Confirmed how | Fix |
|---|---|---|---|
| `qualification` | No `answer_faq` — the classifier defaults short/ambiguous messages here (`classifier.py`'s own fallback on invalid/errored output), so a mid-qualification pricing question could land in `qualification` with no way to reach the pricing guardrail | Live: "Roughly 500 units across our lots, what would that run us?" after a qualification opener classified as `qualification` and, pre-fix, had no `answer_faq` tool available. New eval `test_pricing_question_phrased_as_qualification_answer_never_states_a_price` reproduces this against the real API and passes post-fix; re-verified live (see below) — no price fabricated, deflects via the approved pricing answer. | Added `ANSWER_FAQ_TOOL` and `GET_PRODUCT_DETAILS_TOOL` to `qualification` in `registry.py` |
| `lead_capture` | Only `submit_lead` — no way to escalate ("just have someone call me"), re-look-up a product ("what was that model again?"), or answer a last FAQ before contact info is captured | Confirmed by code inspection of `intent_tools["lead_capture"]` | Added `escalate_to_sales`, `get_product_details`, `answer_faq` |
| `faq` | No `escalate_to_sales`, even though the approved pricing answer itself offers to connect the customer to a specialist | Confirmed by code inspection — the model had the offer text but no tool to act on "yes, connect me" | Added `escalate_to_sales` |
| `greeting` | No `get_solution_content` | Confirmed by code inspection | Added `get_solution_content` |
| `escalate`, `chitchat` | Suspected dead code | **Confirmed dead**: `process_message()` early-returns for both intents (lines ~203 and ~225 in `loop.py`) *before* `get_tools_for_intent()` is ever called (line ~255), so `intent_tools["escalate"]` / `["chitchat"]` are never read. Left in place (harmless, and `test_registry.py` exercises `get_tools_for_intent()` directly as a unit of its own), documented here rather than removed, since removing them wouldn't change runtime behavior and would just delete otherwise-correct-looking config a future refactor might rely on if the early-return is ever removed. | Not a problem — documented, not fixed |

**`capture_lead_info` garbage-extraction bug (real, found in trace, unrelated
to the audit above but found during the same investigation):** live trace of
"Does the VP6300 support WiFi and Cellular?" showed the model calling
`capture_lead_info(company="WiFi and Cellular")` — the spec answer itself
got written into the lead record's company field. Confirmed the bad value
was reachable (re-ran the exact trigger message twice against the live
Postgres-backed stack and inspected the `leads` table). `CAPTURE_LEAD_INFO_TOOL`
stays in the always-on `base` tool list (passive capture is intentional
across every intent), so the fix is in the tool itself
(`agent/tools/capture_lead_info.py`): reject a `name`/`company` value that
contains a `?` or a connectivity/spec term (`wifi`, `bluetooth`, `rs232`,
...), and require `email`/`phone` to match a basic plausible format before
writing them to the session. Regression-tested in `test_capture_lead_info.py`
and re-verified live post-fix — the same trigger message no longer writes to
`company`.

Eval coverage was also expanded (`tests/evals/test_agent_evals.py`) along the
phrasing-variety axis that hid these bugs in the first place — short/
lowercase/terse variants of the same underlying question, not just one
phrasing per feature. 9/9 eval cases pass against the real API.

### Recognize-and-hand-off for PAE / RDM / RKI / merchant services (2026-08-28)

Four new FAQ topics (`payment_integration`, `device_management`,
`key_injection`, `merchant_services`) added to `backend/knowledge/faq.json`
following the existing "approved copy, presented verbatim, never
paraphrased" pattern — no new tool, no deep Q&A, deliberately shallow. Each
answer ends with an explicit handoff offer.

**Accuracy constraint enforced**: ID TECH's approved merchant-services copy
covers P2PE encryption, low-ticket interchange, reporting, and
onboarding/account support — it does not claim eCheck, ACH, virtual
terminal, invoicing, or payment-link capability (those terms came from an
inbound prospect question, not ID TECH's own material). The
`merchant_services` answer names only the approved capabilities and routes
anything else to a specialist without asserting or denying it. Verified live
against the real prospect message ("Does your merchant services platform
support eCheck, ACH, virtual terminal, invoicing, and payment links?") — the
response never states any of those five terms as a capability.

**Keyword-precedence bug found and fixed while wiring this up**: adding
`merchant_services`' keyword list to `_FAQ_KEYWORDS` (`loop.py`) surfaced two
real collisions with the routing logic, not just the "one topic shadows
another" kind:
1. Plain substring matching meant the `"ach"` keyword matched inside
   `"reach"`, `"each"`, `"coach"`, etc. — any support question mentioning
   "reach" would misroute to `merchant_services`. Fixed by switching
   `_detect_faq_topic`'s matching to word-boundary regex (`_kw_in()`) for
   every keyword, old and new — also incidentally fixes a latent bug where
   the `security` topic's `"PCI"` keyword (stored uppercase) never matched
   because the message is lowercased before comparison but the keyword
   wasn't.
2. Even with word-boundary matching, `"do you support ACH?"` matched the
   generic `support` topic's own `"support"` keyword before ever reaching
   `merchant_services`, since `support` is earlier in `_FAQ_KEYWORDS`'
   insertion order. Fixed the same way the existing "support-as-verb"
   compatibility guard works: a dedicated check before the generic loop —
   `"support" in message` + any merchant-services term present routes to
   `merchant_services` first. Both fixes are regression-tested in
   `test_loop.py` (`test_merchant_services_ach_does_not_collide_with_support`,
   `test_new_topics_do_not_collide_with_existing_eight`).

### Persistent conversation store (2026-08-28)

`ConversationStore` (`backend/engine/conversation_store.py`) is now an ABC
with two implementations, selected by `get_conversation_store()` based on
whether `REDIS_URL` is set:

- **`InMemoryConversationStore`** — the original process-local dict, kept
  for local dev/test and as the no-Redis fallback. Behavior unchanged
  (lazy TTL eviction, returns a deep copy on read so a caller mutating the
  returned session before `save_session()` can't corrupt the stored copy).
- **`RedisConversationStore`** — new. Key `session:{id}`, value
  `ConversationSession.model_dump_json()`. TTL is native Redis expiry
  (`SET ... EX` on write, `EXPIRE` on read) instead of the manual sweep —
  sliding expiry, same semantics as the in-memory store's
  `_last_accessed`. Redis already hands back a fresh deserialized object
  per read, so no explicit deep-copy is needed there.

`routers/chat.py` is untouched — `ensure_session` / `has_session` /
`get_session` / `save_session` kept the exact same signatures, so the
swap is invisible to callers.

**Design choice: Redis over a DB-backed table.** `ConversationSession` is
already a Pydantic model, so `model_dump_json()` / `model_validate_json()`
is the entire serialization story — no schema/migration needed. This data
is inherently ephemeral and TTL'd, which is a much more natural fit for
Redis's native expiry than a Postgres table that would need its own sweep
job and adds a write on every turn for data nobody needs after a few hours.

**Verified explicitly: `Set[str]` fields round-trip through JSON as sets.**
`asked_slots` / `answered_slots` are `Set[str]`, and JSON has no native set
type — this was the single most likely place for the Redis path to
silently downgrade a set to a list. `pydantic`'s validation on
`model_validate_json()` coerces the deserialized JSON array back to a
`set` because the field is typed `Set[str]`, confirmed by a dedicated test
(`test_set_fields_round_trip_as_sets_not_lists` in
`tests/backend/test_conversation_store.py`) asserting both value equality
and `isinstance(..., set)`.

**Redis-down handling: degraded-but-up, not hard-down.** Every
`RedisConversationStore` method catches `redis.RedisError` and falls back
to serving the turn with a fresh, unpersisted session rather than raising
— a dead Redis must not turn into a 500 on every chat turn for a sales
widget. This means a Redis outage silently degrades every conversation to
"forgets everything each turn" rather than failing loudly; that tradeoff
is deliberate (availability over consistency for this specific data), but
worth knowing if debugging a report of the bot "not remembering anything."

**`get_conversation_store()` does not fail fast on a missing `REDIS_URL`**
— unlike `OPENAI_API_KEY`/`ADMIN_API_KEY`/`DATABASE_URL`, in-memory is a
legitimate dev/test mode, not a misconfiguration. It does log loudly
(`logger.warning`, visible at default log levels) when falling back to
in-memory, specifically so a production deploy can't end up running that
way silently.

**Infra:** `docker-compose.yml` adds a `redis:7-alpine` service with a
healthcheck; `backend` now depends on it being healthy and gets
`REDIS_URL=redis://redis:6379/0` injected via `environment:` (overriding
anything in `.env`, same pattern as `DATABASE_URL`). Running the backend
outside Docker without a local Redis simply falls back to in-memory — no
extra setup required for that path.

**Test coverage:** `tests/backend/test_conversation_store.py` runs the same
interface tests against both implementations via a parametrized fixture
(the Redis side uses `fakeredis`, so no real Redis server is needed to run
the suite) — session creation/reuse, save/get round-trips, the `Set[str]`
round-trip above, and TTL expiry (real short sleep against a monkeypatched
`SESSION_TTL_SECONDS=1`). Separate classes cover the in-memory-specific
deep-copy behavior, the Redis-down degradation paths (a stub client that
raises `redis.ConnectionError` on every call), and `_build_store()`'s
selection logic. 342/342 backend tests passing (321 prior + 21 new).

**Live-verified, not just unit-tested:** `docker compose up -d --build db
redis backend`, created a session and sent a real chat turn through the
live OpenAI-backed agent, `docker compose restart backend`, then fetched
the same session — transcript and stage survived the restart intact. Then
ran `uvicorn backend.main:app --workers 3` directly inside the backend
container, created 6 sessions and read all 6 back over the same shared
listen socket (any of the 3 worker processes, confirmed distinct PIDs in
the logs, could have served either the write or the read) — every session
was readable regardless of which worker handled which request, confirming
cross-worker sharing via the shared Redis backend.

### Security hardening (2026-08-28)

Before this pass, there was no auth anywhere in this backend — no `Depends`,
no bearer/API-key scheme, no login gate client- or server-side. `/admin` in
the React app was a plain route with no gate at all, and `GET
/api/lead/leads` returned every captured lead's PII to any caller.

- **Admin/lead auth (`backend/auth.py`, `backend/main.py`).** Added a
  shared-secret `ADMIN_API_KEY` gate (`X-Admin-Api-Key` header,
  `hmac.compare_digest` comparison) applied at `include_router(...,
  dependencies=[Depends(require_admin_key)])` for `/api/lead/*` and every
  `/api/maintenance/*` router — one dependency at the mount point rather than
  touching each route function. `/api/chat` and `/api/session` stay public,
  as they must. `ADMIN_API_KEY` is a required env var — missing it fails
  fast at startup, same pattern as `OPENAI_API_KEY`/`DATABASE_URL`, so it
  can't be silently deployed without the gate active.
  Minimum viable gate for an internal admin tool — no user table, swap for
  real SSO at handoff. The React `/admin` route (`AdminLayout.tsx`) now has
  a matching login gate (key entered at runtime, kept in `sessionStorage`
  via `api/adminAuth.ts`, never baked into the JS bundle) so the UI doesn't
  render before a key is present — but that's UX only; the actual boundary
  is the backend check, since a client-side route guard is not security.
  Every admin page's `fetch()` call was swapped for `adminFetch()` (same
  helper) so the UI keeps working now that the API requires the header.
- **Session-token auth on transcripts (`backend/auth.py`, `routers/chat.py`,
  `App.tsx`, `api/client.ts`).** `POST /api/session` now also returns a
  `session_token` — an HMAC-SHA256 of the session_id keyed by
  `SESSION_SECRET_KEY` (also required, fails fast if unset). `GET
  /api/session/{id}` now requires a matching `X-Session-Token` header
  (`hmac.compare_digest`) and returns 403 without one; a nonexistent
  session_id still returns `exists: false` regardless of token (doesn't leak
  which IDs are live). The frontend stores the token alongside `session_id`
  in `localStorage` and only attempts to resume a session when both are
  present. Chosen over "accept and document the risk" since the transcript
  can contain the prospect's name/email/phone. Scope is deliberately just
  this endpoint — `POST /api/chat` continuing an existing session_id was a
  pre-existing risk this pass didn't extend to.
- **Rate limiting (`backend/rate_limit.py`, `routers/chat.py`).** Added
  `slowapi`, a shared per-IP `Limiter` (`get_remote_address`) applied to
  `POST /api/session` (10/minute) and `POST /api/chat` (20/minute). Also
  added a per-session turn cap (`MAX_SESSION_TURNS`, default 60,
  `session.turn_count`) so a scripted client reusing one session_id can't
  keep running up OpenAI calls indefinitely even under the per-IP limit.
  Both return 429. (`slowapi`'s in-memory limiter is a process-global
  singleton — the test suite resets it between tests via an autouse
  fixture in `conftest.py`, or request counts would accumulate across the
  whole run and fail unrelated tests.)
- **CORS (`main.py`).** `allow_credentials=True` dropped — nothing in this
  app uses cookies (auth is header-based), and leaving it `True` would have
  blocked a wildcard origin if staging ever needs one. This is what
  unblocks safely opening CORS to a public origin (a separate, still-open
  item).
- **Verified, not fixed (already correct):** SQL injection — SQLAlchemy is
  parameterized throughout, including the `ILIKE` paths, no raw/interpolated
  SQL anywhere. XSS — `ReactMarkdown` has no `rehype-raw` plugin and nothing
  uses `dangerouslySetInnerHTML`, so it never renders raw HTML from a
  message. `backend/.env` is gitignored (`**/.env`) and was never committed
  historically (`git log --all --full-history` for it is empty).
- **Test coverage:** `tests/backend/test_api.py` — `TestAdminAuthGate` (401
  without/with-wrong key, 200 with the right one, chat/session confirmed
  still public), `TestSessionTokenAuth` (token issuance, 403
  without/with-wrong token, 200 with the right one, missing-session still
  reports `exists: false`), `TestRateLimiting` (429 after the session-create
  limit, 429 after the turn cap). `conftest.py`'s `api_client` fixture now
  carries the admin key by default so existing lead/maintenance tests didn't
  need per-test changes; `unauthed_api_client` is the auth-gate-specific
  variant. 321/321 passing (308 baseline + 13 new).
## "Shop by Solution" chip → category/use_case mapping

The site's "Shop by Solution" entry points are meant to deep-link into the
Product Finder chat with prefilled text, which the agent then resolves into
a `search_products` call. Four of the five chips map directly onto existing
DB categories:

| Chip          | DB category                     |
|---------------|----------------------------------|
| Countertop    | `Countertop Solution`            |
| Unattended    | `Unattended Payment Solutions`   |
| Mobile        | `Mobile Payment Devices`         |
| OEM           | `OEM Payment Products`           |

**Point of Sale** has no matching DB category. Prior to this change,
`backend/knowledge/vertical_map.json`'s `retail` entry listed `pos`,
`point of sale`, and `countertop` as *use_case* aliases (resolving to the
`retail` → `Loyalty Program Contactless Readers` use case). That meant a
"Point of Sale" chip would have filtered by industry/vertical instead of by
product category — inconsistent with the other four chips, which are all
category filters, and confusing since "Point of Sale" is a product/category
concept, not an industry.

**Decision: alias "Point of Sale" to the `Countertop Solution` category**
(option a), not a new DB category and not a use_case alias.

Reasoning:
- The four sibling chips are all category filters. Treating "Point of Sale"
  as a use_case would make it behave differently from every other chip for
  no product reason a customer would understand.
- "Point of Sale" and "Countertop" describe the same class of hardware —
  attended, counter-mounted terminals — so a real, separate DB category
  would just duplicate `Countertop Solution` with no distinguishing
  products (this package's scope explicitly excludes adding new
  categories/products to the catalog).
- Aliasing keeps the fix data-only: `vertical_map.json`'s `retail` entry no
  longer claims `pos`/`point of sale`/`countertop` as industry aliases (see
  the `retail` mapping), and `_build_valid_values_section()` in
  `backend/agent/prompts.py` now tells the model the real DB category list
  each turn, so the model is expected to resolve "Point of Sale" text to
  `category="Countertop Solution"` the same way it resolves "Countertop" —
  i.e. via the tool's `category` parameter, not `use_case`.

There is currently no chip UI in `frontend/` that deep-links into the finder
(no "Shop by Solution" component exists yet), so there is no literal
click-handler to update. This section documents the intended mapping so
that whoever builds that UI wires "Point of Sale" to
`search_products(category="Countertop Solution")` rather than to a
use_case.
## Deployment readiness (Package H, 2026-08-28)

Closing the gap between "passes its own tests" and "safe to put behind a
public URL." Each item below was live-verified against a real Docker stack
(`docker compose up -d db redis backend`), not just unit-tested, except
where noted.

**H1 — Rate limiting behind a proxy.** `get_remote_address` (slowapi's
default `key_func`) reads `request.client.host` — behind any reverse proxy
or load balancer that's the *proxy's* IP, so every real visitor shared one
bucket and `/api/chat`'s rate limit was effectively void for any deploy
fronted by a proxy. `backend/rate_limit.py` now has `get_client_ip()`: the
raw connecting peer's IP is used UNLESS that peer is in a configured
`TRUSTED_PROXY_IPS` set (comma-separated IPs/CIDRs, env var, empty by
default), in which case `X-Forwarded-For`'s left-most entry (or
`X-Real-IP`) is trusted instead. Unconfigured = identical behavior to
before (safe by default, no header ever trusted); this is a strict
widening, not a behavior change, until an operator opts in. Live-verified:
with `TRUSTED_PROXY_IPS=0.0.0.0/0` set, two different `X-Forwarded-For`
values got independent rate-limit buckets (10 requests each, 429 only
after the 10th); with it unset, requests from the same peer shared one
bucket exactly as before regardless of what `X-Forwarded-For` claimed.

**H2 — Redis production config.** `docker-compose.yml`'s `redis` service
previously ran with no auth, a published host port, default (RDB
snapshot) persistence, and no memory bound — for a store holding prospect
PII (names, emails, full transcripts). Now:
- **Auth**: `--requirepass "${REDIS_PASSWORD:?...}"` — fails to start
  without a real `REDIS_PASSWORD` (env var, see `backend/.env.example`),
  not a hardcoded default. The backend passes it to `redis.from_url(...,
  password=REDIS_PASSWORD)` (`backend/engine/conversation_store.py`)
  rather than embedding it in `REDIS_URL` itself — one fewer place a
  secret ends up in a log line (`REDIS_URL` is logged at startup) and
  avoids URL-escaping whatever characters land in a generated password.
- **Persistence decision: accept loss on restart, no AOF.** Considered
  enabling AOF for durability across restarts, but decided against it:
  (1) session data already has a 4-hour TTL and the store's own documented
  failure mode for a *live* Redis outage is "degrade to serving a fresh,
  unpersisted session" (see "Persistent conversation store" above) — a
  restart losing the same data is a consistent, already-accepted
  tradeoff, not a new one; (2) this data is prospect PII (names, emails,
  transcripts) — an AOF file is that same PII, in full, sitting on disk
  indefinitely (or until the volume is cleaned up), which is a durability
  win bought with a real exposure surface for data nobody needs after a
  few hours anyway; (3) no migration/backfill of anything valuable is at
  risk — the worst case of a Redis restart is prospects who were
  mid-conversation have to restart it, not lost leads (leads are written
  to Postgres via `submit_lead`, not Redis). `--save ""
  --appendonly no` makes this explicit rather than relying on the image's
  default RDB save points.
- **Eviction policy**: `--maxmemory 256mb --maxmemory-policy allkeys-lru`
  — every key in this store is ephemeral session data, so evicting the
  least-recently-used key under memory pressure is safe (worse case: that
  session's user has to repeat themselves), unlike `noeviction`'s default
  of refusing writes once full.
- **No host port publish**: `ports: ["6379:6379"]` removed. Nothing
  outside the Docker Compose network needs to reach Redis directly — only
  the `backend` service does, via the `redis` hostname on the compose
  network — so publishing it to the host was pure attack surface for a
  PII-holding store. (Left DB's `5432:5432` alone — pre-existing, out of
  scope for this pass, and worth revisiting for the same reason.)
- **Live-verified**: unauthenticated `redis-cli ping` against the
  container returned `NOAUTH Authentication required`; authenticated
  `ping` (via the container's own `$REDIS_PASSWORD`) returned `PONG`;
  `CONFIG GET` confirmed `maxmemory=268435456`, `maxmemory-policy
  allkeys-lru`, `appendonly no`, `save` empty; `docker port` showed no
  host binding. Created a session, sent a real chat turn through the live
  OpenAI-backed agent, `docker restart` on just the backend container,
  then re-fetched the same session with its token — transcript survived
  intact (Redis itself wasn't restarted, consistent with the persistence
  decision above).

**H3 — Load testing + an honest latency baseline.**
- **The old baseline understated real latency.** `latency_baseline_report.json`
  (p50=1.77s) averages only 0.9 `gpt-4o` rounds/turn because most of its
  `MESSAGES` are short, isolated, fresh-session qualification answers —
  the router mostly short-circuits or answers in one round; it barely
  exercises the multi-round tool-calling loop a real product search or
  spec lookup drives. Added `test_latency_baseline_tool_heavy.py`
  (`latency_baseline_tool_heavy_report.json`), targeting messages that
  actually get 2 tool-calling rounds (named-product spec questions,
  richer single-message qualification, and one full multi-turn
  conversation run in one session so later turns have accumulated
  context). Result: **p50=2.19s, p95=5.49s, mean=3.33s** (mean 1.57
  rounds/turn, n=14, real API) — the old baseline's own highest-latency
  rows (VP6300/VP7200/VP3300 spec questions, 3.1-5.4s) were already
  hinting at this; the new run confirms it's the common case for a
  tool-heavy turn, not an outlier, and roughly matches an independently
  observed 7.3s live tool-calling turn.
- **Found and fixed a real concurrency bug while load testing.**
  `POST /api/chat` (`routers/chat.py`) is an `async def` endpoint that
  called the synchronous, network-blocking `process_message()` directly —
  unlike `POST /api/chat/stream`, which already wraps its (also
  synchronous) generator in `run_in_threadpool` for exactly this reason.
  An `async def` route is never offloaded to a worker thread by
  Starlette, so every OpenAI/DB call inside `process_message()` blocked
  the single asyncio event-loop thread — serializing *all* concurrent
  `/api/chat` requests, regardless of session. A 10-concurrent-session
  load test against a live stack (`docker compose up`, real OpenAI calls)
  measured **p50=28.4s, p95=42.8s, and 14/30 requests timing out**
  before the fix; wrapping the same call in `run_in_threadpool`
  (`routers/chat.py`) brought the same test to **p50=6.0s, p95=10.4s,
  30/30 succeeding** — an order of magnitude, and the difference between
  "broken under any real concurrency" and "works." Full before/after
  detail lives in the load-test results file below.
- **Concurrent load test added**: `tests/evals/load_test_concurrent_chat.py`
  — a standalone `httpx`+`asyncio` script (no new dependency; `httpx` was
  already present) that runs N concurrent conversations against a live
  server and reports p50/p95/error counts. Checked-in results
  (`tests/evals/load_test_results.json`) are the post-fix run: 10
  sessions x 2 turns, p50=6.0s / p95=10.4s / mean=6.7s, 30/30 succeeded,
  against an isolated stack (own Postgres/Redis containers, not the
  dev stack) with a real `OPENAI_API_KEY`. A follow-up 20-session burst
  (all from one IP, as a load-test script naturally is) got 10/30
  requests correctly 429'd by the per-IP `/api/chat` limit (20/minute,
  see D3) rather than 500ing or exhausting the DB connection pool — the
  rate limiter engaging under real concurrent burst traffic is the
  intended behavior, not a bug, and no pool-exhaustion errors surfaced up
  to that concurrency.
- **OpenAI 429 behavior under concurrency**: already handled per-request
  (`agent/loop.py` catches `OpenAIError`, which `RateLimitError`
  subclasses, around every `chat.completions.create(...)` call and
  degrades to a safe fallback response — see the "No retry/timeout around
  the OpenAI call" finding in the table above), but nothing had verified
  this holds under *concurrent* 429s specifically.
  `tests/evals/test_load_concurrent.py` (mocked OpenAI, no real API cost)
  runs 20 concurrent `process_message()` calls via real OS threads with
  every other call raising a simulated `RateLimitError` — all 20 return a
  valid response, none raise. A second test in the same file runs 20
  fully-successful concurrent calls as a baseline thread-safety check.
- **Redis connection-pool behavior under load**: not separately stressed
  beyond the load test above — at 10-20 concurrent sessions no pool
  errors surfaced (each `RedisConversationStore` call goes through
  `redis-py`'s default connection pool, sized generously relative to this
  concurrency). Worth a dedicated stress test before a deploy expecting
  triple-digit concurrent sessions; out of scope for this pass.

**H4 — Readiness endpoint.** Added `GET /ready` (`backend/main.py`):
executes `SELECT 1` against Postgres (via the existing `session_scope()`)
and pings the active `ConversationStore` (new `ping()` method on both
implementations — always `True` for the in-memory store, since there's
nothing external to fail; a real Redis `PING` for the Redis-backed one).
Returns `{"status": "ok"|"unhealthy", "checks": {"db": bool, "redis":
bool}}` — `200` when both pass, `503` otherwise; never a connection
string, hostname, or credential in the body. Deliberately unauthenticated
(an orchestrator's health checker can't present `X-Admin-Api-Key`).
Live-verified: `ok`/`200` against the healthy stack; stopping the `redis`
container flipped it to `{"status": "unhealthy", "checks": {"db": true,
"redis": false}}` / `503` within one request, and it recovered to `ok`
immediately after restarting Redis.

**H5 — Secret hygiene.** The existing startup check only verified
`ADMIN_API_KEY` / `SESSION_SECRET_KEY` were non-empty — copying
`backend/.env.example` to `.env` without editing those two lines passed
that check and booted with the literal, publicly-known placeholder value
(`change-me-to-a-random-secret`) gating lead PII and session transcripts.
`backend/main.py` now also rejects that exact placeholder value for both
vars with a dedicated error message, in addition to the existing
non-empty check.
