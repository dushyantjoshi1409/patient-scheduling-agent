"""Failure analyzer and prompt improver for the self-improvement loop.

Uses allam-2-7b on Groq (separate daily quota from the scheduling agent's
qwen model) to analyze why eval scenarios failed and generate an improved
system prompt that addresses those specific failures.

The two-step process:
1. analyze_failures() — identifies root causes across failed scenarios
2. generate_prompt_patch() — produces a surgically improved system prompt
"""
import json

from groq import Groq

from app.config import settings
from app.models.models import EvalRun
from app.tracing import langfuse

groq_client = Groq(api_key=settings.groq_api_key)
IMPROVER_MODEL = "allam-2-7b"


def analyze_failures(failed_runs: list[EvalRun]) -> str:
    """Analyze failed eval runs to identify root causes and patterns.

    Examines transcripts and scores from failed scenarios to produce a
    concise analysis of what went wrong and what prompt changes would fix it.

    Args:
        failed_runs: List of EvalRun records that scored below the pass
            threshold. Each contains the scenario name, transcript, and
            per-dimension scores.

    Returns:
        A concise analysis string (under 300 words) listing root causes,
        patterns, and specific prompt changes to fix the failures.
    """
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
Respond in English only.

## Failed Scenarios
{"---".join(failure_summaries)}

## Instructions
Respond with a concise analysis (under 300 words) that:
1. Lists each failure's root cause
2. Identifies patterns across failures
3. Suggests specific prompt changes to fix them

Focus on actionable, specific fixes. Not vague advice."""

    gen = langfuse.start_observation(
        name="failure-analysis",
        as_type="generation",
        model=IMPROVER_MODEL,
        input={"failed_scenarios": [r.scenario_name for r in failed_runs]},
        metadata={"agent": "prompt-improver"},
    )

    response = groq_client.chat.completions.create(
        model=IMPROVER_MODEL,
        messages=[
            {"role": "system", "content": "You are a prompt engineering expert. Always respond in English."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=600,
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


def generate_prompt_patch(current_prompt: str, analysis: str) -> str:
    """Generate an improved system prompt based on failure analysis.

    Takes the current system prompt and the failure analysis, then produces
    a surgically improved version that addresses the identified issues
    without removing existing safety guardrails.

    Args:
        current_prompt: The current system prompt text (with {today}
            placeholder intact).
        analysis: Output from analyze_failures() describing root causes
            and suggested fixes.

    Returns:
        The improved system prompt text, guaranteed to contain the
        {today} placeholder for date injection.
    """
    prompt = f"""You are a prompt engineer. Given the current system prompt and failure analysis,
produce an IMPROVED version of the system prompt. Respond in English only.

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

    gen = langfuse.start_observation(
        name="prompt-patch",
        as_type="generation",
        model=IMPROVER_MODEL,
        input={"current_prompt_length": len(current_prompt)},
        metadata={"agent": "prompt-improver"},
    )

    response = groq_client.chat.completions.create(
        model=IMPROVER_MODEL,
        messages=[
            {"role": "system", "content": "You are a prompt engineering expert. Always respond in English."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    new_prompt = response.choices[0].message.content.strip()
    if "</think>" in new_prompt:
        new_prompt = new_prompt.split("</think>", 1)[1].strip()
    if "{today}" not in new_prompt:
        new_prompt += "\n\nToday's date is {today}."

    gen.update(
        output={"new_prompt_length": len(new_prompt)},
        usage_details={
            "input": response.usage.prompt_tokens if response.usage else 0,
            "output": response.usage.completion_tokens if response.usage else 0,
        },
    )
    gen.end()

    return new_prompt
