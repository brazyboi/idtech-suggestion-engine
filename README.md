# IDTECH Suggestion Engine

An AI-powered and rule-based product recommendation chatbot for IDTECH payment terminals.

## Project Organization

The repository is organized into three main components:

- **`backend/`**: FastAPI server, database models, and recommendation logic.
- **`frontend/`**: React application built with Vite, TypeScript, and TailwindCSS.
- **`tests/`**: Comprehensive test suites for both backend and frontend.

## Data & Database Setup

The project uses PostgreSQL as its primary database. To simplify local development, the data team provides a Docker-based setup:

1. **SQL Scripts**: Pre-configured schema and initial data are located in `backend/db_scripts/`.
2. **Docker Compose**: A dedicated `docker-compose.yml` (located in `backend/`) allows for quick database provisioning.

To set up the database:
```bash
cd backend
docker-compose up -d db
```
This will automatically execute the SQL scripts in `backend/db_scripts/` to initialize your local database instance.

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
├── docker-compose.yml       # Root compose for full application
├── backend/
│   ├── docker-compose.yml   # Database-focused compose
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

Open `backend/.env` and add your OpenAI API key and update the `DATABASE_URL` if needed:

```
OPENAI_API_KEY=sk-your-actual-key
DATABASE_URL=postgresql://admin:ics1802026@localhost:5432/product_db
```

### 2. Run with Docker (Recommended)

To start the full stack (Frontend, Backend, and Database):

```bash
docker-compose up --build
```

- **Backend** at http://localhost:8000
- **Frontend** at http://localhost:5173

### 3. Quick Backend Startup (One Command)

From the repo root:

```bash
./start-backend.ps1
```

On Windows Command Prompt:

```bash
start-backend.cmd
```

What this does:
- Starts the backend DB container (`docker compose up -d db`) unless you pass `-NoDb`
- Creates `backend/.venv` if it does not exist
- Installs backend dependencies
- Runs FastAPI with reload at `http://localhost:8000`

Optional flags:
- `-SkipInstall` to skip `pip install`
- `-NoDb` to skip starting Docker DB

### 4. Running without Docker

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cd ..
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
cd backend
pytest ../tests/backend
```

**Frontend:**
```bash
cd frontend
npm test
```
