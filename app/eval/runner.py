"""Eval runner — orchestrates scenarios, scoring, and the self-improvement loop.

Three main entry points:
- run_single_scenario(): Run one eval scenario end-to-end
- run_eval_suite(): Run all (or selected) scenarios and store results
- run_improvement_loop(): Full cycle — baseline eval → analyze failures →
  patch prompt → re-eval → compare before/after scores

Each scenario simulates a multi-turn patient conversation (up to 12 turns),
scores it with the LLM judge, and stores results in the eval_runs table.
"""
import uuid
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import EvalRun, PromptVersion, Conversation, Slot
from app.eval.scenarios import SCENARIOS
from app.eval.simulated_patient import generate_patient_message
from app.eval.judge import score_transcript
from app.eval.improver import analyze_failures, generate_prompt_patch
from app.agent.scheduling_agent import run_agent_turn
from app.seed import seed_database


PASS_THRESHOLD = 18
MAX_TURNS = 12


async def _reset_slots(db: AsyncSession):
    """Re-open all slots so each scenario starts fresh."""
    result = await db.execute(select(Slot))
    for slot in result.scalars().all():
        slot.is_available = True
    await db.commit()


async def run_single_scenario(
    db: AsyncSession,
    scenario_key: str,
    prompt_version: str,
    system_prompt: str,
) -> EvalRun:
    """Run one eval scenario: simulate a patient conversation, then score it.

    Creates a simulated multi-turn conversation between the patient agent
    and scheduling agent (up to MAX_TURNS), then passes the transcript to
    the LLM judge for scoring on 5 dimensions.

    Args:
        db: Async DB session (slots are reset before each scenario).
        scenario_key: Key into SCENARIOS dict (e.g., 'simple_booking').
        prompt_version: Version label for tracking (e.g., 'v1').
        system_prompt: The system prompt text to use for the scheduling agent.

    Returns:
        The persisted EvalRun record with scores and transcript.
    """
    scenario = SCENARIOS[scenario_key]
    session_id = f"eval-{scenario_key}-{uuid.uuid4().hex[:8]}"
    history = []
    transcript = []

    await _reset_slots(db)

    opening = generate_patient_message(scenario["persona"], [], "")
    history_for_agent = []

    agent_response, history_for_agent = await run_agent_turn(
        db=db,
        session_id=session_id,
        user_message=opening,
        history=history_for_agent,
        system_prompt_text=system_prompt,
    )

    transcript = list(history_for_agent)

    for turn in range(MAX_TURNS):
        patient_msg = generate_patient_message(
            scenario["persona"], transcript, agent_response
        )

        if "[END]" in patient_msg:
            break

        await asyncio.sleep(0.5)

        agent_response, history_for_agent = await run_agent_turn(
            db=db,
            session_id=session_id,
            user_message=patient_msg,
            history=history_for_agent,
            system_prompt_text=system_prompt,
        )

        transcript = list(history_for_agent)

    scores = score_transcript(
        scenario_name=scenario["name"],
        expected_behaviors=scenario["expected_behavior"],
        transcript=transcript,
    )

    dimension_scores = {
        k: scores.get(k, 1)
        for k in ["task_completion", "safety", "conversation_quality", "tool_use", "guardrail_compliance"]
    }
    total = sum(dimension_scores.values())
    passed = total >= scenario.get("min_score", PASS_THRESHOLD)

    eval_run = EvalRun(
        id=uuid.uuid4(),
        prompt_version=prompt_version,
        scenario_name=scenario_key,
        transcript=transcript,
        scores=scores,
        total_score=total,
        passed=passed,
        failure_analysis=scores.get("reasoning", ""),
    )
    db.add(eval_run)
    await db.commit()

    return eval_run


async def run_eval_suite(
    db: AsyncSession,
    scenario_names: list[str] | None = None,
    prompt_version: str | None = None,
) -> list[EvalRun]:
    """Run the full eval suite (all or selected scenarios).

    Args:
        db: Async DB session.
        scenario_names: Optional list of scenario keys to run. Defaults
            to all scenarios in SCENARIOS.
        prompt_version: Optional version to test. Defaults to the latest
            prompt version in the database.

    Returns:
        List of EvalRun records, one per scenario.
    """
    if not prompt_version:
        result = await db.execute(
            select(PromptVersion).order_by(PromptVersion.id.desc()).limit(1)
        )
        pv = result.scalar_one_or_none()
        if not pv:
            raise ValueError("No prompt versions found. Run seed first.")
        prompt_version = pv.version
        system_prompt = pv.system_prompt
    else:
        result = await db.execute(
            select(PromptVersion).where(PromptVersion.version == prompt_version)
        )
        pv = result.scalar_one_or_none()
        if not pv:
            raise ValueError(f"Prompt version {prompt_version} not found.")
        system_prompt = pv.system_prompt

    keys = scenario_names or list(SCENARIOS.keys())
    results = []
    for key in keys:
        if key not in SCENARIOS:
            continue
        run = await run_single_scenario(db, key, prompt_version, system_prompt)
        results.append(run)
        await asyncio.sleep(1)

    return results


async def run_improvement_loop(db: AsyncSession) -> dict:
    """Run the full self-improvement loop: eval → analyze → patch → re-eval.

    Steps:
    1. Run baseline eval with current prompt version
    2. Analyze failures with the LLM improver agent
    3. Generate an improved prompt and save it as a new version
    4. Re-run ALL scenarios with the new prompt
    5. Compare scores, flag regressions and improvements

    Returns:
        Dict with old_version, new_version, old_scores, new_scores,
        regressions list, and improvements list.
    """
    result = await db.execute(
        select(PromptVersion).order_by(PromptVersion.id.desc()).limit(1)
    )
    current_pv = result.scalar_one_or_none()
    if not current_pv:
        raise ValueError("No prompt versions found.")

    old_version = current_pv.version

    print(f"\n{'='*60}")
    print(f"IMPROVEMENT LOOP — Starting with prompt {old_version}")
    print(f"{'='*60}")

    print("\n[Step 1] Running baseline eval...")
    baseline_results = await run_eval_suite(db, prompt_version=old_version)

    baseline_scores = {}
    failed_scenarios = []
    for r in baseline_results:
        baseline_scores[r.scenario_name] = r.total_score
        if not r.passed:
            failed_scenarios.append(r)

    print(f"\nBaseline scores:")
    for name, score in baseline_scores.items():
        status = "PASS" if score >= SCENARIOS[name].get("min_score", PASS_THRESHOLD) else "FAIL"
        print(f"  {name}: {score}/25 [{status}]")

    if not failed_scenarios:
        print("\nAll scenarios passed! No improvement needed.")
        return {
            "old_version": old_version,
            "new_version": old_version,
            "old_scores": baseline_scores,
            "new_scores": baseline_scores,
            "regressions": [],
            "improvements": [],
            "message": "All scenarios already passing.",
        }

    print(f"\n[Step 2] Analyzing {len(failed_scenarios)} failures...")
    analysis = analyze_failures(failed_scenarios)
    print(f"  Analysis: {analysis[:200]}...")

    print("\n[Step 3] Generating prompt patch...")
    new_prompt = generate_prompt_patch(current_pv.system_prompt, analysis)

    version_num = int(old_version.lstrip("v")) + 1
    new_version = f"v{version_num}"

    new_pv = PromptVersion(
        version=new_version,
        system_prompt=new_prompt,
        change_description=f"Auto-improvement from {old_version}: {analysis[:500]}",
    )
    db.add(new_pv)
    await db.commit()

    print(f"\n[Step 4] Re-running ALL scenarios with {new_version}...")
    new_results = await run_eval_suite(db, prompt_version=new_version)

    new_scores = {}
    for r in new_results:
        new_scores[r.scenario_name] = r.total_score

    regressions = []
    improvements = []
    for name in baseline_scores:
        old = baseline_scores.get(name, 0)
        new = new_scores.get(name, 0)
        if new < old:
            regressions.append(f"{name}: {old} -> {new}")
        elif new > old:
            improvements.append(f"{name}: {old} -> {new}")

    print(f"\n{'='*60}")
    print("IMPROVEMENT RESULTS")
    print(f"{'='*60}")
    print(f"{'Scenario':<25} {'Before':>8} {'After':>8} {'Delta':>8}")
    print("-" * 51)
    for name in baseline_scores:
        old = baseline_scores.get(name, 0)
        new = new_scores.get(name, 0)
        delta = new - old
        marker = "+" if delta > 0 else (" " if delta == 0 else "")
        print(f"{name:<25} {old:>8.0f} {new:>8.0f} {marker}{delta:>7.0f}")

    if regressions:
        print(f"\nREGRESSIONS: {regressions}")
    if improvements:
        print(f"\nIMPROVEMENTS: {improvements}")

    return {
        "old_version": old_version,
        "new_version": new_version,
        "old_scores": baseline_scores,
        "new_scores": new_scores,
        "regressions": regressions,
        "improvements": improvements,
    }
