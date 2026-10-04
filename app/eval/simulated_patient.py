"""Simulated patient using Groq Llama 3.3 70B."""
from groq import Groq

from app.config import settings

groq_client = Groq(api_key=settings.groq_api_key)
PATIENT_MODEL = "llama-3.3-70b-versatile"


def generate_patient_message(
    persona: str,
    conversation_history: list[dict],
    agent_message: str,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                f"You are a simulated patient in a scheduling conversation. Stay in character.\n\n"
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

    response = groq_client.chat.completions.create(
        model=PATIENT_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=200,
    )

    return response.choices[0].message.content.strip()
