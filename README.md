# MedAssist AI — Medication Management System

[![CI Pipeline](https://github.com/12hurricane/MedicalAssistant/actions/workflows/ci.yml/badge.svg)](https://github.com/12hurricane/MedicalAssistant/actions/workflows/ci.yml)

MedAssist AI is an intelligent, safety-first clinical medication adherence and management platform. It assists patients in understanding verified prescriptions, managing real-time medication schedules, and surfacing adherence barriers for authoritative human clinical review.

---

## Architecture & System Invariants

The platform maintains strict separation between **authoritative deterministic clinical logic** and **generative patient assistance**:

1. **Deterministic Clinical Engine (Zero-LLM):** Prescription validation, dosage allocation, drug-drug interaction detection, adherence score calculation, and clinician overrides are 100% deterministic and reproducible.
2. **4-Tier Resilient LLM Router:** Patient conversational chat routes through ultra-low-latency Groq LPU (`qwen/qwen3.8-27b`), falling back gracefully to HuggingFace Inference API, Google Gemini 2.5 Flash, and local Ollama (`qwen2.5:7b-instruct`) for complete offline air-gapped resilience.
3. **Strict Safety Boundary:** Patient free text is treated as untrusted input. Adversarial attempts to override clinical recommendations or fabricate quotations are filtered and discarded before clinician escalation.
4. **Immutable Audit Trail:** All clinician overrides and corrections are logged to `event_corrections` with clinical justification and timestamps.

| Layer | Component | Status |
|---|---|---|
| **Auth & RBAC** | JWT authentication, role separation (Patient / Clinician) | ✅ Built & Verified |
| **Prescriptions** | Capture, verification, and deterministic daily slot generation | ✅ Built & Verified |
| **Safety Engine** | Contraindications, interactions, duplicate therapy rules | ✅ Built & Verified |
| **Evidence Retrieval** | BM25 + TF-IDF cosine ranking over clinical drug corpus | ✅ Built & Verified |
| **Adherence Metrics** | Rolling compliance score, streaks, and risk classification | ✅ Built & Verified |
| **4-Tier LLM Router** | Groq LPU → HF Router → Gemini 2.5 Flash → Ollama | ✅ Built & Verified |
| **Adherence Boundary** | Untrusted text fencing, quote grounding, risk locking | ✅ Built & Verified |
| **Frontend Client** | Flutter Web SPA (Patient Chat & Clinician Dashboard) | ✅ Built & Verified |
| **CI/CD Pipeline** | GitHub Actions 3-job parallel quality gates & tests | ✅ Built & Verified |
| **Production Packaging** | Multi-stage Docker Compose with Nginx reverse proxy | ✅ Built & Verified |

---

## Quick Start (Docker Compose)

The entire production stack (Nginx + compiled Flutter Web + FastAPI backend + SQLite/Postgres) can be launched with Docker:

```bash
# 1. Clone the repository
git clone https://github.com/12hurricane/MedicalAssistant.git
cd MedicalAssistant

# 2. Provision local environment
cp backend/.env.production.example backend/.env

# 3. Launch the containerized application
docker compose up -d --build

# 4. Access the web applications
# Frontend: http://localhost/
# Patient Chat: http://localhost/#/patient/chat
# Clinician Portal: http://localhost/#/clinician
# Backend API Docs: http://localhost:8000/docs
```

---

## Local Development Setup

### 1. Backend Setup (FastAPI)
```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup (Flutter Web)
```bash
cd flutter
flutter pub get
flutter run -d chrome --web-port 3000
```

---

## Automated Verification Suite

Run the full automated test suite locally:

```bash
cd backend

# 1. Unit & Boundary Safety Tests (27 tests)
pytest test_llm_router.py test_agent_endpoint.py test_merge_boundary.py -v

# 2. End-to-End Adherence Lifecycle Verification (8 stages)
python test_e2e_adherence_lifecycle.py
```

---

## Project Structure

```
├── .github/workflows/
│   └── ci.yml               # Parallel CI/CD pipeline (Backend, Flutter, Docker)
├── backend/
│   ├── app/
│   │   ├── agents/          # LLM router (Groq, HF, Gemini, Ollama)
│   │   ├── analysis/        # Constrained Adherence Intelligence & prompts
│   │   ├── api/             # FastAPI REST routes (v1)
│   │   ├── core/            # Configuration, security, database session
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── rag/             # Clinical evidence retrieval corpus
│   │   ├── rules/           # Deterministic safety rules engine
│   │   └── schemas/         # Pydantic data schemas
│   ├── alembic/             # Database migrations
│   ├── Dockerfile           # Backend container specification
│   ├── requirements.txt     # Python dependencies
│   └── test_*.py            # Comprehensive test suite
├── flutter/
│   ├── lib/                 # Flutter UI screens, providers, and models
│   ├── Dockerfile           # Multi-stage Flutter build & Nginx container
│   └── pubspec.yaml         # Flutter dependencies
├── nginx/
│   └── nginx.conf           # Reverse proxy configuration
└── docker-compose.yml       # Production container orchestration
```

---

## Demo Day Walkthrough

1. **Patient Fast-Path Interaction (`/#/patient/chat`):**
   - Inquire: *"I missed my morning Metformin dose. Should I double up tonight?"*
   - Verify: Latency under ~2 seconds with clear warning against double-dosing.
2. **Clinician Human-in-the-Loop Override (`/#/clinician`):**
   - Inspect Patient adherence record and trigger a dose correction.
   - Confirm adherence recalculation and immutable audit trail persistence.
