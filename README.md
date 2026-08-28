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

The app now fails fast at startup if `OPENAI_API_KEY` (or `OPENAI_ADMIN_KEY`) is missing, with a clear error — so if the backend container won't start, check `docker compose logs backend` first.

### 2. Run with Docker (Recommended — works the same on Windows, Mac, and Linux)

This is the only startup path you need. One command starts the database, backend, and frontend together:

```bash
docker compose up --build
```

- **Backend** at http://localhost:8000
- **Frontend** at http://localhost:5173
- **Database** at localhost:5432 (seeded automatically from `backend/db_scripts/` on first run)

Stop everything with `Ctrl+C`, or `docker compose down` to also remove the containers (add `-v` to also wipe the database volume and reseed from scratch next time).

### 3. Running without Docker (optional, for local iteration)

Start Postgres however you like (or reuse the Docker one: `docker compose up -d db`), then:

**Backend:**
```bash
python -m venv backend/.venv
source backend/.venv/bin/activate  # or backend\.venv\Scripts\activate on Windows
pip install -r backend/requirements.txt
export DATABASE_URL=postgresql://admin:ics1802026@localhost:5432/product_db  # note: localhost, not `db`, outside Docker's network
export OPENAI_API_KEY=sk-your-actual-key
python -m uvicorn backend.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

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
