# IDTECH Suggestion Engine

An AI-powered and rule-based product recommendation chatbot for IDTECH payment terminals.

## Project Organization

The repository is organized into three main components:

- **`backend/`**: FastAPI server, database models, and recommendation logic.
- **`frontend/`**: React application built with Vite, TypeScript, and TailwindCSS.
- **`tests/`**: Comprehensive test suites for both backend and frontend.

## Data & Database Setup

The project uses PostgreSQL as its primary database. The root `docker-compose.yml` provisions it automatically:

```bash
docker compose up -d db
```

On first startup, Postgres automatically runs every SQL script in `backend/db_scripts/` (in alphabetical order) to create the schema and seed initial data — nothing else to run by hand. See [Getting Started](#getting-started) below for the full stack.

## CI/CD and Gitflow

### Gitflow
We follow a standard Gitflow workflow:
- **`master`**: The main branch containing production-ready code.
- **`release/**`**: Branches used for preparing and stabilizing releases.
- **Feature Branches**: All development should occur in feature branches, which are merged into `master` via Pull Requests.

### Continuous Integration (CI)
The CI pipeline is triggered on every Pull Request targeting `master` or `release/**` branches. It performs the following checks:
- **Backend**: Runs `pytest` to ensure logic and API integrity.
- **Frontend**: Performs TypeScript type-checking to ensure code quality.

## Tech Stack

- **Frontend**: React (Vite), TypeScript, TailwindCSS
- **Backend**: Python 3.11+, FastAPI
- **Database**: PostgreSQL
- **LLM**: OpenAI API (gpt-4o-mini)
- **Deployment**: Docker + Docker Compose

## Project Structure

```
├── docker-compose.yml       # Compose for the full application (db + backend + frontend)
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── db/                   # Database models and session management
│   ├── db_scripts/           # SQL initialization scripts provided by data team
│   ├── schemas/              # Pydantic request/response models
│   ├── routers/              # API endpoints (chat, compare, compatibility, pdf)
│   ├── engine/               # Rule engine & compatibility logic, solution engine(formatting solution)
│   ├── llm/                  # OpenAI client and the brain of solution
│   └── pdf/                  # PDF report generator
├── frontend/
│   └── src/
│       ├── api/              # Backend API client functions
│       ├── components/       # UI Components (Chat, ComparisonTable, etc.)
│       └── pages/            # Page layouts
└── tests/
    ├── backend/              # Pytest backend tests
    └── frontend/             # Jest/RTL frontend tests
```

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- An OpenAI API key

### 1. Set up environment variables

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and add your OpenAI API key. The default `DATABASE_URL` in the example file already points at the `db` service's hostname inside Docker's network — leave it as-is for step 2 below.

Also set `ADMIN_API_KEY` and `SESSION_SECRET_KEY` to random values (e.g. `openssl rand -hex 32` for each) — these gate `/admin` and session-transcript access respectively. To reach the admin portal at `/admin`, enter the same `ADMIN_API_KEY` value at its login prompt.

Also set `REDIS_PASSWORD` (`openssl rand -hex 32`) — the `redis` container requires it and won't start without it (see "Deploying" below for why).

The app now fails fast at startup if `OPENAI_API_KEY` (or `OPENAI_ADMIN_KEY`), `ADMIN_API_KEY`, or `SESSION_SECRET_KEY` is missing *or* still set to the placeholder value from `.env.example`, with a clear error — so if the backend container won't start, check `docker compose logs backend` first.

### 2. Run with Docker (Recommended — works the same on Windows, Mac, and Linux)

This is the only startup path you need. One command starts the database, backend, and frontend together:

```bash
docker compose up --build
```

- **Backend** at http://localhost:8000
- **Frontend** at http://localhost:5173
- **Database** at localhost:5432 (seeded automatically from `backend/db_scripts/` on first run)
- **Redis** — not published to the host; only reachable from the `backend` service on the Compose network (conversation sessions — see below)

Stop everything with `Ctrl+C`, or `docker compose down` to also remove the containers (add `-v` to also wipe the database volume and reseed from scratch next time).

Conversation sessions are stored in Redis so they survive a `docker compose restart backend` and are shared across multiple backend worker processes. If Redis is unreachable, the backend degrades to serving each chat turn with a fresh session rather than erroring — conversations just won't persist until Redis is back.

### 3. Running without Docker (optional, for local iteration)

Start Postgres however you like (or reuse the Docker one: `docker compose up -d db`). Redis is optional outside Docker — without a `REDIS_URL`, sessions fall back to an in-memory store (fine for local iteration, just won't survive a restart). If you do point `REDIS_URL` at a real Redis outside Docker, also set `REDIS_PASSWORD` if that Redis requires auth. Then:

**Backend:**
```bash
python -m venv backend/.venv
source backend/.venv/bin/activate  # or backend\.venv\Scripts\activate on Windows
pip install -r backend/requirements.txt
export DATABASE_URL=postgresql://admin:ics1802026@localhost:5432/product_db  # note: localhost, not `db`, outside Docker's network
export OPENAI_API_KEY=sk-your-actual-key
export ADMIN_API_KEY=$(openssl rand -hex 32)
export SESSION_SECRET_KEY=$(openssl rand -hex 32)
python -m uvicorn backend.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Deploying / embedding the chat widget

By default the API only accepts browser requests from `http://localhost:5173` (the Vite dev server). To serve the widget from another origin — e.g. embedding it on the live site — set `CORS_ALLOW_ORIGINS` to the origin(s) the page is served from, comma-separated:

```bash
CORS_ALLOW_ORIGINS=https://idtechproducts.com,https://www.idtechproducts.com
```

Include the scheme and omit any trailing slash. `www` and non-`www` are different origins, so list both if both are used. The allowed origins are logged at startup, so `docker compose logs backend` will confirm what the server actually loaded.

Things to set up before exposing this publicly:

- **`ADMIN_API_KEY` and `SESSION_SECRET_KEY` must be real random secrets**, not the placeholder value from `.env.example`. They gate lead PII (`/api/lead/*`) and catalog mutation (`/api/maintenance/*`). The app now refuses to start if either is unset *or* still set to the literal placeholder (`change-me-to-a-random-secret`) — generate real values with `openssl rand -hex 32`.
- **`REDIS_PASSWORD` is required.** `docker-compose.yml`'s `redis` service refuses to start without it (Redis holds prospect PII — names, emails, full chat transcripts — so it must not run unauthenticated). Generate one with `openssl rand -hex 32` and set it in `backend/.env`; the backend picks it up automatically. Redis has no host port published and isn't reachable from outside the Compose network — only the `backend` service talks to it. Session data is TTL'd (4h) and intentionally **not** persisted to disk (no AOF/RDB) — a Redis restart loses in-flight conversations by design, trading durability for not keeping prospect PII on disk longer than necessary; captured leads themselves live in Postgres, not Redis, so this doesn't risk losing a lead. Memory is capped at 256MB with `allkeys-lru` eviction, appropriate for ephemeral session data.
- **Rate limiting trusts nothing behind a proxy until you configure it.** Behind a reverse proxy or load balancer, the app otherwise sees the *proxy's* IP for every request — every real visitor would share one rate-limit bucket, since slowapi's default key function reads the raw TCP peer address. Set `TRUSTED_PROXY_IPS` (comma-separated IPs/CIDRs, e.g. `TRUSTED_PROXY_IPS=10.0.0.0/8`) to the IP(s) of the proxy/load balancer that sits directly in front of this backend — only then is `X-Forwarded-For` (or `X-Real-IP`) trusted, and only from that peer. Leave it unset for a direct-connection deploy (e.g. local dev, or a platform that terminates TLS *inside* the same container). Never set it to a wildcard/any-IP range in production — that lets any direct caller spoof their rate-limit identity via the header, which is worse than no rate limiting at all.
- **`GET /ready`** is a readiness probe for orchestrators (k8s, ECS, ...) — it actively checks Postgres and Redis reachability and returns `{"status": "ok", "checks": {"db": true, "redis": true}}` (200) or `{"status": "unhealthy", ...}` (503), never connection details. Point your orchestrator's readiness check at it instead of `/`, which only confirms the process is alive. It's unauthenticated by design (orchestrators can't present `X-Admin-Api-Key`).

## Running Tests

**Backend:**
```bash
pytest tests/backend
```

**Frontend:**
```bash
cd frontend
npm test
```

**Evals (real OpenAI calls, real cost, opt-in):**
```bash
RUN_EVALS=1 pytest tests/evals
```
See `tests/evals/` for the golden-case model-behavior suite, the general-turn/routing latency baseline (`test_latency_baseline.py`), the recommendation-focused tool-heavy latency baseline (`test_latency_baseline_tool_heavy.py`), and the mocked-OpenAI concurrency test (`test_load_concurrent.py`). Use the tool-heavy report when judging Product Finder latency; the general-turn report deliberately includes short-circuit turns and is not comparable to a real recommendation turn.

**Concurrent load test against a live stack:**
```bash
docker compose up -d db redis backend
python tests/evals/load_test_concurrent_chat.py --base-url http://localhost:8000 --sessions 10 --turns 2
```
Standalone script (no pytest, no new dependency — just `httpx`), reports p50/p95 chat-turn latency and error/rate-limit counts. See `tests/evals/load_test_results.json` for the last checked-in run.

## Architecture

For the agent's design (workflow pattern, tool structure) and the list of
known trade-offs and open issues, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Example Chat Interaction

A qualification flow that reaches a recommendation typically looks like:

```
Use case: Parking Payment Systems
Environment: Outdoor (-20C to 65C)
Card types: Contact (chip), Contactless (tap), Magstripe (swipe)
PIN: Yes, PIN required
Standalone: Host-controlled
Host interface: RS232 (or USB / Ethernet)
Display: Yes, display needed
```
