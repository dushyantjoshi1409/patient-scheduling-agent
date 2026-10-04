# Patient Scheduling Agent

A conversational AI agent that helps patients book, reschedule, and cancel appointments at City Health Clinic. Built with FastAPI, Google Gemini 2.0 Flash, and PostgreSQL.

Includes a full evaluation harness with simulated patients, LLM-based scoring, and an automated improvement loop that diagnoses failures and patches the system prompt.

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16 (or use Docker)
- Google Gemini API key (free tier — uses Gemini Flash models with automatic fallback)
- Groq API key (free tier — Llama 3.3 70B for eval)

### 1. Setup

```bash
# Clone and enter the project
cd patient-scheduling-agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start PostgreSQL

**Option A: Docker (recommended)**
```bash
docker compose up db -d
```

**Option B: Existing PostgreSQL**
Ensure a database `scheduling_agent` exists with user `admin` / password `admin123` on `localhost:5432`.

### 3. Run the Agent

```bash
# Start the server (auto-seeds the database with doctors and slots)
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000) to chat with the scheduling agent.

### 4. Run Evaluations

```bash
# Run all 8 test scenarios
python -m app.eval.cli

# Run specific scenarios
python -m app.eval.cli --scenarios simple_booking medical_emergency

# Run the full improvement loop (eval → analyze → patch prompt → re-eval)
python -m app.eval.cli --improve
```

### Docker Compose (full stack)

```bash
docker compose up --build
```

This starts PostgreSQL and the app together. The web UI is at [http://localhost:8000](http://localhost:8000).

## Architecture

```
Patient (Browser) → FastAPI → Gemini Flash (function calling) → PostgreSQL
                                    ↕
                              6 scheduling tools
                              (search, availability, book, cancel, reschedule, details)
```

### Three Agents
1. **Scheduling Agent** (Gemini Flash) — main brain, talks to patients, calls tools
2. **Simulated Patient** (Groq/Llama 3.3 70B) — plays patient personas during eval
3. **Eval Judge** (Groq/Llama 3.3 70B) — scores transcripts on 5 dimensions

### Eval Scoring (5 dimensions, 1-5 each)
- **Task Completion** — did the agent fulfill the request?
- **Safety** — emergencies redirected, no medical advice?
- **Conversation Quality** — natural, empathetic, well-paced?
- **Tool Use** — right tools, right order, no waste?
- **Guardrail Compliance** — stayed in scope?

### Improvement Loop
1. Run all 8 scenarios against current prompt
2. Score each transcript with the LLM judge
3. Analyze failures — identify root causes
4. Generate a surgical prompt patch
5. Re-run ALL scenarios with the new prompt
6. Check for regressions — report before/after scores

## Project Structure

```
app/
├── main.py              # FastAPI entry point
├── config.py            # Settings from .env
├── database.py          # SQLAlchemy async engine
├── seed.py              # Seed doctors + time slots
├── models/models.py     # ORM: doctors, patients, slots, appointments, conversations
├── schemas/schemas.py   # Pydantic request/response models
├── routers/             # API endpoints: chat, doctors, appointments, eval
├── agent/
│   ├── scheduling_agent.py  # Gemini integration with function calling loop
│   ├── tools.py             # 6 tool implementations
│   └── prompts.py           # System prompt (versioned)
└── eval/
    ├── scenarios.py         # 8 test scenarios with personas
    ├── simulated_patient.py # Groq-powered simulated patient
    ├── judge.py             # LLM judge with structured scoring
    ├── improver.py          # Failure analysis + prompt patching
    ├── runner.py            # Orchestrates eval suite + improvement loop
    └── cli.py               # CLI entry point
frontend/                    # Simple HTML/JS chat UI
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, get agent response |
| DELETE | `/api/chat/{session_id}` | Clear conversation history |
| GET | `/api/doctors` | List all doctors |
| GET | `/api/appointments/{session_id}` | List patient's appointments |
| POST | `/api/eval/run` | Run eval scenarios |
| POST | `/api/eval/improve` | Run improvement loop |
