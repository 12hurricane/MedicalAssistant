# MedAssist AI — Medication Management System

Helps patients understand verified prescriptions, manage medication schedules, and
surfaces adherence problems for human clinical follow-up.

## What actually exists today

The system is deterministic end to end. **There is no model call anywhere in this
codebase** — no LLM, no agents, no orchestration graph, no embeddings. Everything below
is reproducible: identical inputs produce identical output.

| Layer | Status |
|---|---|
| Auth (JWT), registration, role separation | built |
| Prescription capture, correction and verification | built |
| Schedule calculation, reminders, dose logging | built (timezone-local, DST tested) |
| Safety rules engine — contraindications, interactions, duplicate therapy | built |
| Clinical evidence retrieval (BM25 + TF-IDF cosine over a fixed corpus) | built |
| Adherence metrics, streaks, time-of-day and day-of-week patterns, escalation | built |
| Adherence Analysis Service — the Constrained Adherence Intelligence Layer | built |
| Prompt trust contract for a future generative layer (`app/analysis/prompts.py`) | built, unused |
| Generative layer (LLM), multi-agent orchestration, OCR, vector store | **not built** |

### The Adherence Analysis Service is not AI

`app/analysis/` composes patient explanations and clinician briefs like this:

```
SafetyAssessment + AdherenceMetrics + RAG Evidence
        ↓
Deterministic template/composition logic
        ↓
Barrier classification → Response validator → Structured output
```

It cannot hallucinate because it cannot generate. Calling it an agent or an LLM would
be false, so nothing in the code, the docstrings, the OpenAPI descriptions or this file
does. The generative phase is a later box in the build order.

### Trust tiers are explicit and must stay that way

Clinician-facing output keeps three sources visibly separate:

```
🚫 DETERMINISTIC SAFETY FINDING   — rules engine, authoritative
📄 VERIFIED CLINICAL EVIDENCE     — retrieved, cited
✦  AI-ASSISTED SUMMARY            — not present yet; will be clearly labelled
```

Patient free text (`MedicationEvent.skip_reason`) is **untrusted data**. It is quoted to
the clinician in `BarrierItem.patient_reported_text` and never merged into
system-authored prose. `app/analysis/prompts.py` defines the four-tier prompt contract a
future model must be fed through — untrusted content last, fenced, passed as structured
JSON, with the deterministic verdict re-applied after generation regardless.

Structured skip reasons (`MedicationEvent.skip_reason_code`) are a closed vocabulary the
patient selects from, so they are trusted: `OBSERVED` / `HIGH` confidence. Keyword
matching on free text is a guess and is labelled one: `INFERRED` / `LOW`.

## Tech stack

- **Backend**: FastAPI, SQLAlchemy 2 (async), Alembic, APScheduler
- **Database**: SQLite in development (`sqlite+aiosqlite`), PostgreSQL supported via `asyncpg`
- **Frontend**: Flutter (in progress)
- **Planned**: LangGraph + Ollama for the generative layer. The packages are in
  `requirements.txt`, but nothing imports them yet.

## Quick Start

### Prerequisites
- Python 3.11+
- Flutter 3.24+ (frontend only)
- Docker & Docker Compose (only needed for PostgreSQL; SQLite needs nothing)

### 1. Setup backend
```bash
cd backend && python -m venv venv && venv/Scripts/python -m pip install -r requirements.txt
```

### 2. Configure
Create `backend/.env`:
```
DATABASE_URL="sqlite+aiosqlite:///./medication.db"
SECRET_KEY="change-this-for-local-development-only"
```
`SECRET_KEY` above is acceptable **only** for local development. Generate a proper
random secret before deployment.

### 3. Run migrations
```bash
cd backend && venv/Scripts/python -m alembic upgrade head
```

### 4. Start the backend
```bash
cd backend && venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

### 5. Run the tests
```bash
cd backend && venv/Scripts/python -m pytest -q
```
Tests run against an isolated database. `medication.db` holds real data kept for manual
verification; `conftest.py` fails any test that opens it.

## API Documentation
With the backend running: http://localhost:8000/docs

## Project Structure
```
├── backend/
│   ├── app/
│   │   ├── analysis/     # Adherence Analysis Service (deterministic, not an LLM)
│   │   ├── api/          # REST endpoints (v1)
│   │   ├── core/         # Config, security
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── notifications/
│   │   ├── rag/          # Clinical evidence corpus, index, retriever
│   │   ├── rules/        # Safety rules engine
│   │   ├── schemas/      # Pydantic DTOs
│   │   ├── services/     # Business logic
│   │   ├── agents/       # EMPTY — reserved for the future generative layer
│   │   └── graph/        # EMPTY — reserved for future orchestration
│   ├── alembic/          # Migrations
│   └── test_*.py         # Test suite (pytest, at the backend root)
├── flutter/              # Flutter app
└── docker-compose.yml
```
