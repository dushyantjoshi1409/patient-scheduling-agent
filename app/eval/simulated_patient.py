"""Simulated patient agent for eval conversations.

Uses a separate LLM model (allam-2-7b) from the scheduling agent to avoid
sharing the same daily token quota on Groq's free tier. Each model gets its
own 200K tokens/day allowance, so eval work doesn't starve the product agent.

The simulated patient stays in character according to the scenario persona
and produces natural multi-turn conversation that exercises the scheduling
agent's capabilities.
"""
from groq import Groq

from app.config import settings
from app.tracing import langfuse

groq_client = Groq(api_key=settings.groq_api_key)
PATIENT_MODEL = "allam-2-7b"


def generate_patient_message(
    persona: str,
    conversation_history: list[dict],
    agent_message: str,
) -> str:
    """Generate the next patient message in a simulated conversation.

    Args:
        persona: Character description from the eval scenario (symptoms,
            preferences, personality traits the patient should exhibit).
        conversation_history: Full conversation so far in OpenAI message
            format. Roles are flipped so the patient sees agent messages
            as 'user' and its own past messages as 'assistant'.
        agent_message: The scheduling agent's latest reply to respond to.
            Empty string on the first turn (patient opens the conversation).

    Returns:
        The patient's next message, or a string containing '[END]' when
        the conversation has reached a natural conclusion.
    """
    messages = [
        {
            "role": "system",
            "content": (
                f"You are a simulated patient in a scheduling conversation. "
                f"Stay in character. Respond in English only.\n\n"
                f"Your persona:\n{persona}\n\n"
                f"Rules:\n"
                f"- Respond naturally as this patient would\n"
                f"- Keep responses concise (1-3 sentences)\n"
                f"- Do NOT break character or mention you are simulated\n"
                f"- If the agent asks for information your persona has, provide it\n"
                f"- If the conversation has reached a natural end (appointment booked, "
                f"emergency redirect accepted, etc.), respond with just: [END]"
            ),
        }
    ]

    for msg in conversation_history:
        if msg["role"] in ("user", "assistant"):
            role = "assistant" if msg["role"] == "user" else "user"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})

    if agent_message:
        messages.append({"role": "user", "content": agent_message})
    else:
        messages.append({
            "role": "user",
            "content": "Start the conversation. You are calling the clinic now. Say your opening line.",
        })

    gen = langfuse.start_observation(
        name="simulated-patient",
        as_type="generation",
        model=PATIENT_MODEL,
        input={"agent_message": agent_message[:200] if agent_message else ""},
        metadata={"agent": "simulated-patient"},
    )

    response = groq_client.chat.completions.create(
        model=PATIENT_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=200,
    )

    result = response.choices[0].message.content.strip()
    if "</think>" in result:
        result = result.split("</think>", 1)[1].strip()

    gen.update(
        output=result,
        usage_details={
            "input": response.usage.prompt_tokens if response.usage else 0,
            "output": response.usage.completion_tokens if response.usage else 0,
        },
    )
    gen.end()

    return result
