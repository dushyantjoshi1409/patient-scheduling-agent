"""Failure analyzer and prompt improver using Groq Llama 3.3 70B."""
import json

from groq import Groq

from app.config import settings
from app.models.models import EvalRun

groq_client = Groq(api_key=settings.groq_api_key)
IMPROVER_MODEL = "llama-3.3-70b-versatile"


def analyze_failures(failed_runs: list[EvalRun]) -> str:
    failure_summaries = []
    for run in failed_runs:
        transcript_text = ""
        for msg in (run.transcript or []):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                transcript_text += f"{role.upper()}: {content}\n"

        failure_summaries.append(
            f"Scenario: {run.scenario_name}\n"
            f"Scores: {json.dumps(run.scores)}\n"
            f"Total: {run.total_score}/25\n"
            f"Transcript excerpt:\n{transcript_text[:1000]}\n"
        )

    prompt = f"""Analyze these failed evaluation scenarios for a patient scheduling AI agent.
Identify the ROOT CAUSES of each failure — what the agent did wrong or failed to do.

## Failed Scenarios
{"---".join(failure_summaries)}

## Instructions
Respond with a concise analysis (under 300 words) that:
1. Lists each failure's root cause
2. Identifies patterns across failures
3. Suggests specific prompt changes to fix them

Focus on actionable, specific fixes. Not vague advice."""

    response = groq_client.chat.completions.create(
        model=IMPROVER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=600,
    )

    return response.choices[0].message.content.strip()


def generate_prompt_patch(current_prompt: str, analysis: str) -> str:
    prompt = f"""You are a prompt engineer. Given the current system prompt and failure analysis,
produce an IMPROVED version of the system prompt.

## Current System Prompt
{current_prompt}

## Failure Analysis
{analysis}

## Rules
- Keep the overall structure and tone
- Add specific instructions to address each identified failure
- Do NOT remove existing safety guardrails
- Do NOT make the prompt excessively long — be surgical
- The prompt must still include the {{today}} placeholder for the date
- Return ONLY the improved prompt text, no explanation or markdown fences"""

    response = groq_client.chat.completions.create(
        model=IMPROVER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2000,
    )

    new_prompt = response.choices[0].message.content.strip()
    if "{today}" not in new_prompt:
        new_prompt += "\n\nToday's date is {today}."

    return new_prompt
