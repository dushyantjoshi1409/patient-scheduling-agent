"""Scheduling agent powered by Gemini Flash with function calling.

Uses Gemini Chat sessions which handle thought signatures automatically.
Tries multiple models with retry on transient errors.
"""
import time
from datetime import date

from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT_V1
from app.agent.tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS


client = genai.Client(api_key=settings.google_api_key)
MODELS = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.8-flash"]


def _build_tools() -> list[types.Tool]:
    function_declarations = []
    for tool in TOOL_DECLARATIONS:
        fd = types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters=tool["parameters"],
        )
        function_declarations.append(fd)
    return [types.Tool(function_declarations=function_declarations)]


def _build_system_prompt(system_prompt_text: str | None = None) -> str:
    text = system_prompt_text or SYSTEM_PROMPT_V1
    return text.format(today=date.today().isoformat())


def _history_to_contents(history: list[dict]) -> list[types.Content]:
    contents = []
    for msg in history:
        role = msg["role"]
        if role == "user":
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=msg["content"])]
            ))
        elif role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append(types.Part.from_text(text=msg["content"]))
            if msg.get("function_calls"):
                for fc in msg["function_calls"]:
                    parts.append(types.Part.from_function_call(
                        name=fc["name"], args=fc["args"]
                    ))
            if parts:
                contents.append(types.Content(role="model", parts=parts))
        elif role == "tool":
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_function_response(
                    name=msg["name"],
                    response={"result": msg["content"]}
                )]
            ))
    return contents


def _send_with_retry(chat, message, max_retries=5):
    for attempt in range(max_retries):
        try:
            return chat.send_message(message)
        except ServerError:
            if attempt == max_retries - 1:
                raise
            wait = min(2 ** attempt * 3, 30)
            time.sleep(wait)


async def run_agent_turn(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    history: list[dict],
    system_prompt_text: str | None = None,
) -> tuple[str, list[dict]]:
    system_prompt = _build_system_prompt(system_prompt_text)
    tools = _build_tools()
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
        temperature=0.3,
    )

    previous_contents = _history_to_contents(history)

    last_error = None
    chat = None
    for model in MODELS:
        try:
            chat = client.chats.create(model=model, config=config, history=previous_contents)
            response = _send_with_retry(chat, user_message)
            break
        except (ClientError, ServerError) as e:
            last_error = e
            time.sleep(1)
            continue

    if chat is None or last_error and response is None:
        raise last_error or RuntimeError("All models unavailable")

    updated_history = list(history)
    updated_history.append({"role": "user", "content": user_message})

    max_tool_rounds = 5
    for _ in range(max_tool_rounds):
        candidate = response.candidates[0]
        has_function_call = False
        function_responses = []
        text_parts = []

        for part in candidate.content.parts:
            if part.function_call:
                has_function_call = True
                fc = part.function_call
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}

                tool_fn = TOOL_FUNCTIONS.get(fn_name)
                if tool_fn:
                    call_args = dict(fn_args)
                    if fn_name == "book_appointment":
                        call_args["session_id"] = session_id
                    result = await tool_fn(db, **call_args)
                else:
                    result = f"Unknown tool: {fn_name}"

                function_responses.append(types.Part.from_function_response(
                    name=fn_name,
                    response={"result": result},
                ))

                updated_history.append({
                    "role": "assistant", "content": "",
                    "function_calls": [{"name": fn_name, "args": fn_args}]
                })
                updated_history.append({
                    "role": "tool", "name": fn_name, "content": result
                })
            elif part.text:
                text_parts.append(part.text)

        if not has_function_call:
            assistant_text = " ".join(text_parts).strip()
            updated_history.append({"role": "assistant", "content": assistant_text})
            return assistant_text, updated_history

        response = _send_with_retry(chat, function_responses)

    return "I apologize, but I'm having trouble processing your request. Could you please try again?", updated_history
