# Design Note

## Why This Architecture

**Gemini for the agent, Groq for eval.** The scheduling agent uses Gemini Flash (with automatic fallback across model versions) because its native function calling maps cleanly to scheduling tools — the model decides which tool to call and with what arguments, and we feed results back in a loop until it has a final response. Groq (Llama 3.3 70B) handles the eval judge and simulated patient because it's fast and free, and these roles don't need function calling.

**Synchronous function calling loop.** The agent runs up to 5 tool calls per turn. This handles multi-step flows like "search doctor → check availability → book" in a single user message. The loop breaks when the model returns text instead of a function call.

**Session-based identity.** Each browser gets a UUID stored in localStorage. No auth — this is a scheduling demo, not a production system. The session ID links conversations, patients, and appointments.

## Eval Design

The eval harness tests what matters for a voice/scheduling agent:

1. **Safety is non-negotiable.** The emergency and out-of-scope scenarios have the highest minimum scores. A scheduling agent that gives medical advice or doesn't redirect a chest-pain call is dangerous.

2. **Simulated patients, not canned scripts.** Each scenario has a persona with motivations and behaviors. The Llama 3.3 model plays the patient, producing natural variation across runs. The patient signals `[END]` when the conversation reaches a natural conclusion.

3. **The judge scores behavior, not keywords.** Five dimensions capture different failure modes. Task completion catches broken flows. Safety catches medical advice. Conversation quality catches robotic or rude responses. Tool use catches unnecessary API calls. Guardrails catch scope drift.

## Improvement Loop

The loop is designed to be safe:

- **Run ALL scenarios** before and after the prompt patch — a fix that helps one scenario but breaks another is caught.
- **Surgical patches** — the improver is told to add specific instructions, not rewrite the whole prompt.
- **Version tracking** — every prompt version is stored with its change description. You can always roll back.

## What I'd Add With More Time

- **Streaming responses** via SSE for a more natural chat feel
- **Appointment reminders** and calendar integration
- **Voice interface** with Twilio or Deepgram for the actual voice AI use case
- **Concurrent eval runs** with asyncio.gather for faster iteration
- **Statistical significance** — run each scenario 3x and average scores to reduce noise from LLM variance
