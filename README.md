# ID TECH Suggestion Engine

The ID TECH Suggestion Engine is a web-based Product Finder for ID TECH payment hardware. A visitor describes a deployment or business use case in natural language, and the assistant searches the live product catalog to recommend suitable hardware.

The application also supports approved FAQ answers, product details, installation documentation, PDF recommendation downloads, sales escalation, and lead capture. Product recommendation correctness is the primary responsibility; the other capabilities support that workflow.

## What the software does

### Public customer experience

- Starts a conversation and preserves the session in Redis.
- Extracts product requirements such as use case, category, indoor/outdoor placement, power, host interface, standalone operation, and extra specifications.
- Searches the PostgreSQL catalog instead of inventing products or specifications.
- Returns recommendations with product links, highlights, compatible software, and key specifications.
- Streams progress and response text through Server-Sent Events in the web client.
- Answers approved FAQ topics such as pricing, shipping, warranty, returns, compatibility, security, support, PAE, RDM, RKI, and merchant services.
- Looks up detailed product specifications and installation documents.
- Captures volunteered contact information, submits qualified leads, and escalates requests to sales.
- Generates a PDF from a recommendation.

If the requested combination has no exact catalog match, the search tool reports which constraints were relaxed. The assistant must tell the visitor that the result is a closest fit or escalate to a specialist; it must not present a relaxed result as an exact match.

### Internal admin portal

The frontend admin area is available at `/admin` and currently supports:

- Lead list and funnel metrics.
- Hardware creation, editing, and soft deletion.
- Software management.
- Category and use-case management.
- Prompt and documentation management through their admin routes.

The catalog is database-backed. Categories and use cases shown to the assistant are read from the database so admin edits can be reflected in later conversations.

## Add the Product Finder to a website

This repository does not ship a single `<script>` widget. You can either host the included React frontend and embed it with an iframe, or build a native chat interface that calls the public API.

### Option 1: host the included frontend and embed it

This is the fastest path. Build and host `frontend/dist` at a dedicated URL, such as `https://finder.example.com`, then add this to the host website:

```html
<iframe
  src="https://finder.example.com/"
  title="ID TECH Product Finder"
  loading="lazy"
  style="width: 100%; min-height: 720px; border: 0;"
></iframe>
```

For production, serve the built frontend rather than the Vite development server:

```bash
cd frontend
npm ci
npm run build
```

Serve `frontend/dist` with a web server that sends unknown client-side routes to `index.html`. The simplest deployment proxies `/api/` on the same origin to the FastAPI backend, so the included frontend needs no API-base configuration:

```nginx
location / {
  try_files $uri $uri/ /index.html;
}

location /api/ {
  proxy_pass http://backend:8000;
  proxy_http_version 1.1;
  proxy_buffering off;
  proxy_read_timeout 300s;
}
```

`proxy_buffering off` matters: `/api/chat/stream` uses Server-Sent Events and must not be buffered before reaching the browser.

If the frontend and API use different origins, set the chat app's runtime API base before its JavaScript loads:

```html
<script>
  window.__VITE_API_BASE_URL__ = "https://api.example.com";
</script>
```

Also add the frontend origin to `CORS_ALLOW_ORIGINS` on the backend. The outer website that contains an iframe does not itself need CORS access to the API; the page inside the iframe does.

### Option 2: build a native chat interface

Use this when the site already has its own design system or you need a floating chat launcher. The browser should call only the public chat endpoints—never send `OPENAI_API_KEY`, `ADMIN_API_KEY`, `SESSION_SECRET_KEY`, or `REDIS_PASSWORD` to a visitor.

First create and retain a session:

```js
const API_BASE = "https://api.example.com";

const session = await fetch(`${API_BASE}/api/session`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
}).then((response) => response.json());

localStorage.setItem("idtech_session_id", session.session_id);
localStorage.setItem("idtech_session_token", session.session_token);
```

Then send customer messages to the streaming endpoint. Each event is a JSON object in a `data: ...\n\n` Server-Sent Event frame:

```js
async function sendMessage(message, onEvent) {
  const sessionId = localStorage.getItem("idtech_session_id");
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (frame.startsWith("data: ")) {
        onEvent(JSON.parse(frame.slice(6)));
      }
    }
  }
}
```

Handle these event types in the UI:

| Event | Meaning |
| --- | --- |
| `progress` | A catalog, FAQ, lead, or other tool action is in progress. |
| `token` | Append `delta` to the visible assistant response. |
| `done` | The final response is in `response`; store its `session_id` if supplied. |
| `error` | Show a recoverable error message. |

To restore a transcript after a refresh, call `GET /api/session/{session_id}` with `X-Session-Token` set to the saved `session_token`. The token is required for transcript retrieval; keep it with the session ID in browser storage.

For either integration approach, set `CORS_ALLOW_ORIGINS` to the exact browser origin that calls the API. Do not expose the admin page or its shared key to ordinary visitors.

### Server-side behavior

`process_message()` and `process_message_stream()` classify the request, extract requirements, run the agent tool loop, and produce the final reply. Product searches flow through `search_products()` and `product_filtering()`. The filter tries all requested constraints first; if none match, it can relax category/use case, extra specifications, or interface requirements. It returns `constraints_applied` and `constraints_relaxed`, and the assistant must disclose a relaxed result instead of presenting it as an exact match.

`POST /api/session` creates a session ID and signed token. Redis stores conversation state with a sliding four-hour TTL; PostgreSQL stores the catalog, captured leads, and funnel events. `require_admin_key()` protects lead and maintenance routes using `X-Admin-Api-Key`, while `SESSION_SECRET_KEY` signs transcript tokens and `REDIS_PASSWORD` authenticates the Redis client.

`submit_lead()` and `escalate_to_sales()` save leads to PostgreSQL. They also call `EmailService.send_lead_notification()`: without SMTP credentials it logs a skipped notification, and with credentials it sends email.

## Quick start with Docker

Docker Compose is the supported local and deployment starting point.

### Prerequisites

- [Docker Desktop](https://docs.docker.com/get-docker/) or another Docker Engine with Compose.
- An OpenAI API key.
- `openssl` for generating secrets.

### 1. Create the environment file

Run this from the repository root:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and set `OPENAI_API_KEY` to a real key. Replace all three security placeholders with three different random values:

```bash
openssl rand -hex 32   # ADMIN_API_KEY
openssl rand -hex 32   # SESSION_SECRET_KEY
openssl rand -hex 32   # REDIS_PASSWORD
```

Paste the outputs into the corresponding entries:

```dotenv
OPENAI_API_KEY=sk-your-real-key
ADMIN_API_KEY=first-generated-value
SESSION_SECRET_KEY=second-generated-value
REDIS_PASSWORD=third-generated-value
```

Do not commit `backend/.env`. It is gitignored. The backend refuses to start when `ADMIN_API_KEY` or `SESSION_SECRET_KEY` is missing or still equal to `change-me-to-a-random-secret`. Redis also refuses to start without `REDIS_PASSWORD`.

### 2. Start the application

```bash
docker compose up --build -d
docker compose ps
```

Open:

- Customer frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- Admin portal: <http://localhost:5173/admin>
- Readiness check: <http://localhost:8000/ready>

Check startup failures with:

```bash
docker compose logs backend
docker compose logs redis
```

The readiness endpoint returns HTTP 200 only when PostgreSQL and Redis are reachable:

```json
{"status":"ok","checks":{"db":true,"redis":true}}
```

If either dependency is unavailable, it returns HTTP 503 and only exposes boolean check results.

Stop the application with:

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intend to delete the PostgreSQL volume and reseed the database from scratch. Database initialization scripts run automatically only when PostgreSQL creates a new, empty data volume.

## Environment variables and authorization

### The three security values

These values are deliberately separate:

| Variable | Used by | Purpose |
| --- | --- | --- |
| `ADMIN_API_KEY` | Administrators and the backend | Shared key for the `/admin` portal and protected lead/catalog API requests. The browser sends it as `X-Admin-Api-Key`. |
| `SESSION_SECRET_KEY` | Backend only | Signs and verifies per-conversation session tokens. It is never entered by an administrator or visitor. |
| `REDIS_PASSWORD` | Backend and Redis | Authenticates the backend's connection to Redis. It is never entered in the admin portal. |

### How admin authorization works

There are currently no admin usernames, individual accounts, roles, or SSO integration. `/admin` uses one shared API key:

1. Open `/admin`.
2. Enter the value of `ADMIN_API_KEY` from the server's `backend/.env`.
3. The frontend verifies it by requesting the protected metrics endpoint.
4. If valid, the key is kept in browser `sessionStorage` and attached to later admin requests as `X-Admin-Api-Key`.

The backend remains the real authorization boundary. The protected API surfaces are:

- `/api/lead/*` — lead PII and funnel metrics.
- `/api/maintenance/*` — hardware, software, category, use-case, prompt, and documentation changes.

The customer chat endpoints remain public so the embedded widget can work without an admin credential. Existing conversation transcripts require the signed `X-Session-Token` issued when the session is created.

Changing `ADMIN_API_KEY` invalidates the old admin key. Changing `SESSION_SECRET_KEY` invalidates existing session tokens. After changing either value, recreate the backend:

```bash
docker compose up -d --force-recreate backend
```

If changing `REDIS_PASSWORD`, recreate both services so Redis and the backend receive the same value:

```bash
docker compose up -d --force-recreate redis backend
```

### Important `backend/.env` and Compose detail

The root `docker-compose.yml` contains:

```yaml
env_file: ./backend/.env
```

for both the `redis` and `backend` services. This path is relative to the directory containing `docker-compose.yml`, not to the directory from which you happen to run the command. In this repository, the file must therefore be exactly:

```text
<repository root>/backend/.env
```

Redis uses the loaded `REDIS_PASSWORD` to start with `--requirepass`. The backend uses the same value as a separate Redis client password; it is not embedded in `REDIS_URL`. Compose also overrides the Docker-internal database and Redis URLs for the backend:

```text
DATABASE_URL=postgresql://admin:...@db:5432/product_db
REDIS_URL=redis://redis:6379/0
```

If you move the Compose file or rename the environment file, update both `env_file` references and the Redis command together. If `backend/.env` is absent or does not contain `REDIS_PASSWORD`, the Redis service will fail its startup check.

## Configuration for deployment

Before exposing the application publicly:

### Browser origin

Set the frontend's real origin in `CORS_ALLOW_ORIGINS`, including the scheme and without a trailing slash. List multiple origins with commas:

```dotenv
CORS_ALLOW_ORIGINS=https://idtechproducts.com,https://www.idtechproducts.com
```

`www` and non-`www` are different origins.

### Reverse proxy and rate limiting

The API limits session creation to 10 requests per minute per client and chat turns to 20 requests per minute per client. There is also a 60-turn default cap per conversation.

When a reverse proxy or load balancer sits directly in front of the backend, set `TRUSTED_PROXY_IPS` to the proxy's actual IP addresses or CIDR ranges:

```dotenv
TRUSTED_PROXY_IPS=10.0.0.8,10.0.0.0/24
```

Only requests arriving from those peers may use `X-Forwarded-For` or `X-Real-IP` to identify the visitor. Leave it unset for a direct connection. Never use a wildcard range in production: an untrusted caller could spoof its rate-limit identity.

Point the orchestrator's readiness probe at `/ready`, not `/`. `/` only confirms that the process is running; `/ready` checks PostgreSQL and Redis.

### PostgreSQL

The Compose database settings are development defaults. The repository currently uses the `admin` user and a sample password in `docker-compose.yml`, and publishes PostgreSQL on host port `5432` for local access. Before a public deployment, replace the database credentials with deployment-managed secrets, update both the `db` environment and the backend's `DATABASE_URL`, and remove the host port publish unless an approved operator workflow genuinely needs it. Do not expose PostgreSQL directly to the public internet.

### Redis policy

Redis stores short-lived conversation sessions and may contain names, emails, and transcripts. The current policy is:

- Password authentication required.
- Redis port is not published to the host; only the backend can reach it on the Compose network.
- Four-hour session TTL by default.
- No AOF or RDB persistence. A Redis restart loses in-flight sessions by design; captured leads are stored in PostgreSQL.
- 256 MB maximum memory with `allkeys-lru` eviction.

This policy favors limiting PII retained on disk over preserving abandoned conversations. Change it deliberately if your deployment requires durable transcripts.

## Lead handling

Captured leads are stored in PostgreSQL and are reviewable at `/admin/leads`. SMTP support is still implemented, but it is disabled by default because `SMTP_USER` and `SMTP_PASS` are unset. Without those credentials, someone must monitor the admin portal.

The customer is also directed to the existing ID TECH contact page when appropriate: <https://idtechproducts.com/contact/>.

To enable SMTP notifications, configure `SMTP_USER` and `SMTP_PASS` in `backend/.env`; optional host, port, and recipient settings are in `backend/.env.example`. Test delivery before relying on it operationally.

## Known limitations and operational issues

- **Shared admin credential:** authorization is one shared `ADMIN_API_KEY`; there is no per-user audit identity, role management, SSO, or password reset flow.
- **Admin frontend deployment:** some maintenance screens still contain development-oriented `http://localhost:8000` API URLs. Verify and update those screens before serving the admin portal from a non-localhost deployment.
- **Development frontend server:** Docker Compose currently serves the Vite development server. A public deployment should build and serve the frontend with a production web server or CDN rather than treating the Vite dev server as the final public asset server.
- **Development database settings:** the checked-in Compose file contains local bootstrap credentials and publishes PostgreSQL for development convenience. Treat them as non-production defaults and harden them before deployment.
- **Redis failure behavior:** the chat service can continue a turn with a fresh, unpersisted session when Redis is unavailable, so a request may succeed without conversation continuity. `/ready` still reports the instance unhealthy.
- **Database initialization:** SQL files in `backend/db_scripts/` are seed/initialization scripts, not a general migration system. Existing database volumes are not automatically updated when those files change.
- **No exact product match:** the finder may relax constraints and disclose a closest fit, or the assistant may escalate instead. This is intentional; it is safer than claiming unsupported compatibility.
- **Latency:** the simple sequential/general-turn baseline includes many short-circuit turns and understates recommendation latency. Use the tool-heavy report and concurrent load test when evaluating Product Finder performance.
- **Sales follow-up promise:** the assistant's follow-up timing is only accurate if someone monitors `/admin/leads` or SMTP notifications are configured and working.

## API and user flows

The main public endpoints are:

| Endpoint | Function | Auth |
| --- | --- | --- |
| `POST /api/session` | Create a session and receive a session token | Public; rate limited |
| `GET /api/session/{id}` | Resume an existing conversation | Session token |
| `POST /api/chat` | Process a chat turn as JSON | Public; rate limited |
| `POST /api/chat/stream` | Process a chat turn as SSE | Public; rate limited |
| `POST /api/pdf/generate` | Generate a recommendation PDF | Public |
| `GET /ready` | Check DB and Redis readiness | Public |
| `GET /api/lead/leads` | Review captured leads | Admin API key |
| `GET /api/lead/metrics` | View funnel metrics | Admin API key |
| `/api/maintenance/*` | Manage catalog and admin content | Admin API key |

## Running without Docker

This is useful for local development, but Docker is the supported full-stack path.

1. Start PostgreSQL separately, or start only the Compose database:

   ```bash
   docker compose up -d db
   ```

2. Create a Python environment and install dependencies:

   ```bash
   python -m venv backend/.venv
   source backend/.venv/bin/activate       # Windows: backend\\.venv\\Scripts\\activate
   pip install -r backend/requirements.txt
   ```

3. Set local connection values. Outside Docker, use `localhost`, not the Compose hostname `db`:

   ```bash
   export DATABASE_URL=postgresql://admin:ics1802026@localhost:5432/product_db
   export OPENAI_API_KEY=sk-your-real-key
   export ADMIN_API_KEY=$(openssl rand -hex 32)
   export SESSION_SECRET_KEY=$(openssl rand -hex 32)
   ```

   Redis is optional for local iteration. Without `REDIS_URL`, sessions use in-memory storage and do not survive a backend restart. If using an external Redis, set `REDIS_URL` and its `REDIS_PASSWORD`.

4. Start the backend:

   ```bash
   python -m uvicorn backend.main:app --reload --port 8000
   ```

5. In another terminal, start the frontend:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Tests and evaluation

Run the deterministic backend suite:

```bash
source backend/.venv/bin/activate
python -m pytest tests/backend -q
```

Run the frontend suite:

```bash
cd frontend
npm test -- --runInBand
```

The evaluation suite makes real OpenAI calls and costs money. Run it only deliberately:

```bash
RUN_EVALS=1 pytest tests/evals
```

The latency files have different purposes:

- `test_latency_baseline.py` measures general routing and short-circuit turns.
- `test_latency_baseline_tool_heavy.py` measures actual product-finder/tool-calling turns and a multi-turn recommendation flow.
- `load_test_concurrent_chat.py` measures concurrent live chat sessions.

Example concurrent load test:

```bash
docker compose up -d db redis backend
python tests/evals/load_test_concurrent_chat.py \
  --base-url http://localhost:8000 \
  --sessions 10 \
  --turns 2
```

## Repository layout

```text
├── docker-compose.yml       # PostgreSQL, Redis, backend, and frontend services
├── backend/
│   ├── main.py              # FastAPI application and readiness checks
│   ├── agent/               # Classification, prompting, agent loop, and tools
│   ├── db/                  # SQLAlchemy models, repositories, and sessions
│   ├── db_scripts/          # Initial schema and seed data
│   ├── engine/              # Session, filtering, matching, and recommendation logic
│   ├── routers/             # Chat, PDF, lead, and maintenance APIs
│   └── services/            # Lead email and event logging services
├── frontend/                # React/Vite customer and admin interfaces
├── tests/backend/            # Deterministic pytest suite
├── tests/evals/              # Opt-in model, latency, and load evaluations
└── ARCHITECTURE.md           # Architecture decisions and implementation rationale
```
