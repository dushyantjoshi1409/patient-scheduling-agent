"""Core scheduling agent powered by Groq (Qwen 3.8 27B) with function calling.

This is the main conversational agent that patients interact with. It uses
Groq's OpenAI-compatible API with native tool/function calling to search
doctors, check availability, book/cancel/reschedule appointments.

Architecture:
- Receives user messages via the /api/chat endpoint
- Maintains conversation history in OpenAI message format
- Calls tools (DB queries) via Groq's function calling, up to 5 rounds
- All calls are traced via Langfuse for observability

Model choice: qwen/qwen3.8-27b on Groq free tier (200K tokens/day).
Eval agents use allam-2-7b separately to avoid sharing this quota.
"""
import asyncio
import json
import re
import time
from datetime import date

from groq import Groq

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT_V1
from app.agent.tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS
from app.tracing import langfuse


def _parse_retry_seconds(error_msg: str) -> float:
    """Extract the retry wait time from a Groq rate-limit error message.

    Parses patterns like 'try again in 4m12.287s' or 'try again in 30.5s'.
    Returns seconds to wait, defaulting to 10 if parsing fails.
    """
    match = re.search(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s", error_msg)
    if match:
        minutes = int(match.group(1) or 0)
        seconds = float(match.group(2))
        return minutes * 60 + seconds
    return 10.0


groq_client = Groq(api_key=settings.groq_api_key)
MODEL = "qwen/qwen3.8-27b"


def _build_tools() -> list[dict]:
    """Convert tool declarations into OpenAI-style function tool format.

    Wraps each tool declaration dict from tools.py in the
    {"type": "function", "function": {...}} envelope that Groq expects.
    """
    return [
        {"type": "function", "function": decl}
        for decl in TOOL_DECLARATIONS
    ]


def _build_system_prompt(system_prompt_text: str | None = None) -> str:
    """Build the system prompt with today's date injected.

    Args:
        system_prompt_text: Custom prompt text (used during eval with
            improved prompt versions). Falls back to SYSTEM_PROMPT_V1.

    Returns:
        The system prompt with {today} replaced by the current date.
    """
    text = system_prompt_text or SYSTEM_PROMPT_V1
    return text.format(today=date.today().isoformat())


def _history_to_messages(history: list[dict]) -> list[dict]:
    """Convert stored conversation history to OpenAI-style messages.

    The history is stored in a normalized format with role, content,
    and optional tool_calls/tool_call_id fields. This function converts
    it to the exact format Groq's API expects.

    Args:
        history: List of message dicts with 'role' (user/assistant/tool),
            'content', and optionally 'tool_calls' or 'tool_call_id'.

    Returns:
        List of OpenAI-format message dicts ready for the API.
    """
    messages = []
    for msg in history:
        role = msg["role"]
        if role == "user":
            messages.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            m = {"role": "assistant", "content": msg.get("content") or ""}
            if msg.get("tool_calls"):
                m["tool_calls"] = msg["tool_calls"]
            messages.append(m)
        elif role == "tool":
            messages.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", ""),
                "content": msg["content"],
            })
    return messages


async def run_agent_turn(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    history: list[dict],
    system_prompt_text: str | None = None,
    trace_name: str = "scheduling-agent",
) -> tuple[str, list[dict]]:
    """Run one conversational turn of the scheduling agent.

    Sends the user's message (with full conversation history) to Groq,
    handles any tool calls the model makes (up to 5 rounds of tool
    calling), and returns the final text response.

    Args:
        db: Async SQLAlchemy session for tool DB queries.
        session_id: UUID identifying the chat session (used for
            patient identity in bookings).
        user_message: The patient's latest message.
        history: Conversation history so far (mutated — a copy is made).
        system_prompt_text: Optional custom system prompt for eval runs.
        trace_name: Langfuse trace name for observability grouping.

    Returns:
        Tuple of (assistant_response_text, updated_history).
        The updated history includes the new user message, any tool
        calls/results, and the final assistant response.
    """
    trace = langfuse.start_observation(
        name=trace_name,
        as_type="span",
        input={"user_message": user_message, "history_length": len(history)},
        metadata={"session_id": session_id},
    )

    system_prompt = _build_system_prompt(system_prompt_text)
    tools = _build_tools()

    updated_history = list(history)
    updated_history.append({"role": "user", "content": user_message})

    api_messages = [{"role": "system", "content": system_prompt}]
    api_messages.extend(_history_to_messages(updated_history))

    max_tool_rounds = 5
    for round_num in range(max_tool_rounds):
        gen = langfuse.start_observation(
            name="groq-call",
            as_type="generation",
            model=MODEL,
            input={"user_message": user_message, "round": round_num},
            metadata={"agent": "scheduling-agent"},
        )

        try:
            response = groq_client.chat.completions.create(
                model=MODEL,
                messages=api_messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=900,
            )
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate_limit" in error_msg:
                wait = _parse_retry_seconds(error_msg)
                gen.update(
                    output={"error": "rate_limited", "wait_seconds": wait},
                    level="WARNING",
                )
                gen.end()
                print(f"[rate-limit] waiting {wait:.0f}s before retry...")
                await asyncio.sleep(wait)
                try:
                    response = groq_client.chat.completions.create(
                        model=MODEL,
                        messages=api_messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.3,
                        max_tokens=900,
                    )
                except Exception as retry_e:
                    trace.update(output={"error": str(retry_e)}, level="ERROR")
                    trace.end()
                    raise
            else:
                gen.update(output={"error": error_msg}, level="ERROR")
                gen.end()
                trace.update(output={"error": error_msg}, level="ERROR")
                trace.end()
                raise

        gen.update(
            output={"finish_reason": response.choices[0].finish_reason},
            usage_details={
                "input": response.usage.prompt_tokens if response.usage else 0,
                "output": response.usage.completion_tokens if response.usage else 0,
            },
        )
        gen.end()

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            assistant_msg = {
                "role": "assistant",
                "content": choice.message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ],
            }
            updated_history.append(assistant_msg)
            api_messages.append(assistant_msg)

            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                tool_span = langfuse.start_observation(
                    name=f"tool:{fn_name}",
                    as_type="span",
                    input={"function": fn_name, "args": fn_args, "round": round_num},
                )

                tool_fn = TOOL_FUNCTIONS.get(fn_name)
                if tool_fn:
                    call_args = dict(fn_args)
                    if fn_name == "book_appointment":
                        call_args["session_id"] = session_id
                    result = await tool_fn(db, **call_args)
                else:
                    result = f"Unknown tool: {fn_name}"

                tool_span.update(output={"result": result[:500]})
                tool_span.end()

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
                updated_history.append(tool_msg)
                api_messages.append(tool_msg)

            continue

        assistant_text = (choice.message.content or "").strip()
        updated_history.append({"role": "assistant", "content": assistant_text})
        trace.update(output={"response": assistant_text[:500], "tool_rounds": round_num, "model": MODEL})
        trace.end()
        return assistant_text, updated_history

    fallback = "I apologize, but I'm having trouble processing your request. Could you please try again?"
    trace.update(output={"response": fallback, "error": "max_tool_rounds_exceeded"}, level="WARNING")
    trace.end()
    return fallback, updated_history
