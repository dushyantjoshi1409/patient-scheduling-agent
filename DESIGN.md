# Design Note

## Why This Architecture

**Groq for everything, two models for quota isolation.** The scheduling agent uses Groq's `qwen/qwen3.8-27b` because it supports native OpenAI-style function calling (`tools`, `tool_choice`, `tool_calls` in responses) — the model decides which scheduling tool to call and with what arguments, and we feed results back until it has a final text response. The eval agents (simulated patient, judge, improver) use `allam-2-7b` on the same Groq platform but a separate daily quota pool, so running evals never starves the production agent's 200K tokens/day free-tier limit.

**No framework, hand-rolled agent loop.** The agent is a simple `for` loop: send messages to Groq, check `finish_reason`, execute tool calls if any, append results, repeat up to 5 rounds. This is intentional — it keeps the agent transparent and debuggable without the abstraction overhead of LangChain or LangGraph. For a production system, LangGraph's `StateGraph` would add structured state management, conditional routing, and checkpointing (noted in Future Enhancements).

**Synchronous function calling loop.** The agent runs up to 5 tool calls per turn. This handles multi-step flows like "search doctor -> check availability -> confirm details -> book" in a single user message. The loop breaks when the model returns text instead of a function call.

**Session-based identity.** Each browser gets a UUID stored in `localStorage`. No auth — this is a scheduling demo, not a production system. The session ID links conversations, patients, and appointments.

**Rate limit handling.** Groq's free tier enforces 1000 output tokens per minute. The agent requests `max_tokens=900` to stay under, and retries once with a 2-second backoff on 429 errors. This trades occasional latency for reliability on the free tier.

## Observability with Langfuse

Every Groq API call and tool execution is traced through Langfuse v4:

- **Spans** wrap each conversation turn with input/output and session metadata
- **Generations** capture individual Groq calls with model name, token usage, and finish reason
- **Tool spans** capture each function call with arguments and results
- **Error levels** distinguish rate-limit retries (WARNING) from hard failures (ERROR)

This gives full visibility into agent behavior, token spend, and failure patterns without coupling to any specific LLM provider.

## Eval Design

The eval harness tests what matters for a voice/scheduling agent:

1. **Safety is non-negotiable.** The emergency and out-of-scope scenarios have the highest minimum scores. A scheduling agent that gives medical advice or doesn't redirect a chest-pain call is dangerous.

2. **Simulated patients, not canned scripts.** Each of the 8 scenarios has a persona with motivations and behaviors. The `allam-2-7b` model plays the patient, producing natural variation across runs. The patient signals `[END]` when the conversation reaches a natural conclusion.

3. **The judge scores behavior, not keywords.** Five dimensions capture different failure modes. Task completion catches broken flows. Safety catches medical advice. Conversation quality catches robotic or rude responses. Tool use catches unnecessary API calls. Guardrails catch scope drift.

4. **Separate models avoid bias.** The judge (`allam-2-7b`) is a different model from the agent (`qwen/qwen3.8-27b`), so it won't self-validate patterns it naturally produces.

### The 8 Test Scenarios

| Scenario | Tests |
|----------|-------|
| `simple_booking` | Happy-path: search, check slots, book |
| `reschedule` | Modify an existing appointment |
| `cancellation` | Cancel with a reason |
| `multi_step` | Complex: search by specialty, compare doctors, then book |
| `medical_emergency` | Must redirect to 911, not schedule |
| `out_of_scope` | Prescription/diagnosis requests — must refuse politely |
| `ambiguous_request` | Vague input — agent should ask clarifying questions |
| `edge_case_no_slots` | All slots full — handle gracefully |

## Self-Improvement Loop

The loop is designed to be safe:

- **Run ALL scenarios** before and after the prompt patch — a fix that helps one scenario but breaks another is caught.
- **Surgical patches** — the improver is told to add specific instructions, not rewrite the whole prompt. This reduces the risk of breaking working behavior.
- **Version tracking** — every prompt version is stored in the database with its change description. You can always roll back by inspecting the admin dashboard.
- **Three-agent pipeline** — the improver analyzes failures separately from generating patches, keeping diagnosis and action cleanly separated.

## Deployment

The app deploys to Railway with:
- **Dockerfile** — Python 3.11-slim, installs deps, runs Uvicorn on Railway's dynamic `$PORT`
- **PostgreSQL service** — Railway provides a managed Postgres instance
- **Auto URL conversion** — `database.py` converts Railway's `postgresql://` to `postgresql+asyncpg://` automatically
- **Health check** — Railway polls `/docs` (FastAPI's Swagger UI) for liveness

All secrets (`GROQ_API_KEY`, `DATABASE_URL`, `LANGFUSE_*`) are Railway environment variables, never committed.

## What I'd Add With More Time

- **LangGraph migration** — replace the hand-rolled loop with `StateGraph` for structured state, conditional edges (e.g., emergency -> redirect node vs. booking -> tool node), and built-in conversation checkpointing
- **Streaming responses** via SSE for a more natural chat feel
- **Voice interface** with Twilio or Deepgram for the actual voice AI use case
- **Concurrent eval runs** with `asyncio.gather` for faster iteration
- **Statistical significance** — run each scenario 3x and average scores to reduce noise from LLM variance
- **Multi-turn eval memory** — test that the agent remembers context across turns within a session
- **Appointment reminders** and calendar integration
- **Webhook notifications** for appointment confirmations
