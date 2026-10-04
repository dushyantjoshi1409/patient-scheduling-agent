# Patient Scheduling Agent

A conversational AI agent that helps patients book, reschedule, and cancel appointments at City Health Clinic. Built with FastAPI, Groq (Qwen 3.8 27B with native function calling), and PostgreSQL.

Includes a full evaluation harness with simulated patients, LLM-based scoring, and an automated self-improvement loop that diagnoses failures, patches the system prompt, and validates against regressions.

**Live demo:** https://patient-scheduling-agent-production.up.railway.app

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16 (or use Docker)
- Groq API key (free tier)
- Langfuse account (free tier, optional — for observability)

### 1. Setup

```bash
cd patient-scheduling-agent

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys
```

### 2. Environment Variables

```env
GROQ_API_KEY=gsk_...
DATABASE_URL=postgresql+asyncpg://admin:admin123@localhost:5432/scheduling_agent
LANGFUSE_SECRET_KEY=sk-lf-...    # optional
LANGFUSE_PUBLIC_KEY=pk-lf-...    # optional
LANGFUSE_HOST=https://us.cloud.langfuse.com  # optional
```

### 3. Start PostgreSQL

**Option A: Docker (recommended)**
```bash
docker compose up db -d
```

**Option B: Existing PostgreSQL**
Ensure a database `scheduling_agent` exists with user `admin` / password `admin123` on `localhost:5432`.

### 4. Run the Agent

```bash
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000) to chat with the scheduling agent.
Admin dashboard at [http://localhost:8000/admin.html](http://localhost:8000/admin.html).

### 5. Run Evaluations

```bash
# Run all 8 test scenarios
python -m app.eval.cli

# Run specific scenarios
python -m app.eval.cli --scenarios simple_booking medical_emergency

# Run the full improvement loop (eval -> analyze -> patch prompt -> re-eval)
python -m app.eval.cli --improve
```

### Docker Compose (full stack)

```bash
docker compose up --build
```

This starts PostgreSQL and the app together. The web UI is at [http://localhost:8000](http://localhost:8000).

### Deploy to Railway

The project includes a `Dockerfile` and `railway.toml` for one-click Railway deployment:

1. Create a Railway project with a PostgreSQL service
2. Connect the GitHub repo or run `railway up`
3. Set environment variables (`GROQ_API_KEY`, `DATABASE_URL`, `LANGFUSE_*`)
4. Railway auto-converts `postgresql://` URLs to the async format

## Architecture

```
Patient (Browser) --> FastAPI --> Groq Qwen 3.8 27B (function calling) --> PostgreSQL
                                        |
                                  6 scheduling tools
                                  (search, availability, book, cancel, reschedule, details)
                                        |
                                  Langfuse tracing
```

### Models

| Role | Model | Provider | Why |
|------|-------|----------|-----|
| Scheduling Agent | `qwen/qwen3.8-27b` | Groq | Native OpenAI-style tool calling, 200K tokens/day free |
| Simulated Patient | `allam-2-7b` | Groq | Separate quota pool from the agent, avoids daily limit conflicts |
| Eval Judge | `allam-2-7b` | Groq | Same separate pool, structured JSON scoring |
| Prompt Improver | `allam-2-7b` | Groq | Failure analysis and surgical prompt patches |

The scheduling agent and eval agents use different models to avoid sharing the same 200K tokens/day quota on Groq's free tier.

### Agent Tools (Function Calling)

The agent has 6 tools it can call via Groq's OpenAI-compatible function calling:

1. **search_doctors** — find doctors by name or specialty
2. **check_availability** — list open time slots for a doctor
3. **book_appointment** — reserve a slot for the patient
4. **cancel_appointment** — cancel an existing appointment
5. **reschedule_appointment** — move an appointment to a new slot
6. **get_appointment_details** — look up appointment info

The agent runs up to 5 tool-calling rounds per turn, handling multi-step flows like "search doctor -> check availability -> book" in a single user message.

### Eval Scoring (5 dimensions, 1-5 each, total /25)

- **Task Completion** — did the agent fulfill the request?
- **Safety** — emergencies redirected, no medical advice?
- **Conversation Quality** — natural, empathetic, well-paced?
- **Tool Use** — right tools, right order, no waste?
- **Guardrail Compliance** — stayed in scope?

### Self-Improvement Loop

1. Run all 8 scenarios against the current prompt
2. Score each transcript with the LLM judge
3. Analyze failures — identify root causes
4. Generate a surgical prompt patch
5. Re-run ALL scenarios with the new prompt
6. Compare before/after scores, check for regressions

### Observability

All agent calls, tool executions, and eval runs are traced via **Langfuse**:
- Each conversation turn is a span with nested generation and tool observations
- Token usage tracked per call
- Errors and retries logged with severity levels

View traces at [https://us.cloud.langfuse.com](https://us.cloud.langfuse.com).

## Project Structure

```
app/
├── main.py              # FastAPI entry point, DB init, static file serving
├── config.py            # Settings from .env (Groq, Langfuse, DB)
├── database.py          # SQLAlchemy async engine (auto-converts Railway URLs)
├── tracing.py           # Langfuse client initialization
├── seed.py              # Seed doctors + time slots
├── models/models.py     # ORM: doctors, patients, slots, appointments, conversations
├── schemas/schemas.py   # Pydantic request/response models
├── routers/
│   ├── chat.py          # POST /api/chat, DELETE /api/chat/{id}, GET history
│   ├── doctors.py       # GET /api/doctors
│   ├── appointments.py  # GET /api/appointments/{session_id}
│   ├── eval.py          # POST /api/eval/run, POST /api/eval/improve
│   └── admin.py         # GET /api/admin/stats, eval-runs, prompt-versions, appointments
├── agent/
│   ├── scheduling_agent.py  # Groq Qwen integration with function calling loop
│   ├── tools.py             # 6 tool implementations (DB queries)
│   └── prompts.py           # System prompt (versioned, patchable)
└── eval/
    ├── scenarios.py         # 8 test scenarios with patient personas
    ├── simulated_patient.py # allam-2-7b simulated patient
    ├── judge.py             # LLM judge with structured JSON scoring
    ├── improver.py          # Failure analysis + prompt patch generation
    ├── runner.py            # Orchestrates eval suite + improvement loop
    └── cli.py               # CLI entry point
frontend/
├── index.html           # Patient chat UI
├── admin.html           # Admin dashboard (eval runs, scores, appointments)
├── app.js               # Chat logic
└── style.css            # Styling
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, get agent response |
| GET | `/api/chat/{session_id}` | Get conversation history |
| DELETE | `/api/chat/{session_id}` | Clear conversation history |
| GET | `/api/doctors` | List all doctors |
| GET | `/api/appointments/{session_id}` | List patient's appointments |
| POST | `/api/eval/run` | Run eval scenarios (accepts `scenarios` list) |
| POST | `/api/eval/improve` | Run full improvement loop |
| GET | `/api/admin/stats` | Dashboard statistics |
| GET | `/api/admin/eval-runs` | Past eval run results |
| GET | `/api/admin/prompt-versions` | Prompt version history |
| GET | `/api/admin/appointments` | All appointments |

## Future Enhancements

- **LangGraph** — migrate from hand-rolled agent loop to LangGraph's `StateGraph` for structured state management, conditional tool routing, and built-in checkpointing
- **Streaming responses** via SSE for a more natural chat feel
- **Voice interface** with Twilio or Deepgram for the actual voice AI use case
- **Concurrent eval runs** with `asyncio.gather` for faster iteration
- **Statistical significance** — run each scenario 3x and average scores to reduce LLM variance
- **Appointment reminders** and calendar integration
