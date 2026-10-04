"""Eval router — run evaluations and improvement loop via API."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.schemas import EvalScenarioRequest
from app.eval.runner import run_eval_suite, run_improvement_loop

router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.post("/run")
async def run_eval(req: EvalScenarioRequest, db: AsyncSession = Depends(get_db)):
    results = await run_eval_suite(db, scenario_names=req.scenarios, prompt_version=req.prompt_version)
    return {
        "results": [
            {
                "scenario": r.scenario_name,
                "scores": r.scores,
                "total_score": r.total_score,
                "passed": r.passed,
                "failure_analysis": r.failure_analysis,
            }
            for r in results
        ]
    }


@router.post("/improve")
async def run_improvement(db: AsyncSession = Depends(get_db)):
    result = await run_improvement_loop(db)
    return result
