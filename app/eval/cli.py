"""CLI entry point for running evals outside the web server."""
import asyncio
import argparse

from app.database import init_db, async_session
from app.seed import seed_database
from app.eval.runner import run_eval_suite, run_improvement_loop


async def main():
    parser = argparse.ArgumentParser(description="Run scheduling agent evaluations")
    parser.add_argument("--improve", action="store_true", help="Run the full improvement loop")
    parser.add_argument("--scenarios", nargs="*", help="Specific scenarios to run (default: all)")
    parser.add_argument("--version", type=str, help="Prompt version to use (default: latest)")
    args = parser.parse_args()

    await init_db()
    async with async_session() as db:
        await seed_database(db)

        if args.improve:
            result = await run_improvement_loop(db)
            print(f"\nDone. Old: {result['old_version']}, New: {result['new_version']}")
            if result["regressions"]:
                print(f"Regressions: {result['regressions']}")
            if result["improvements"]:
                print(f"Improvements: {result['improvements']}")
        else:
            results = await run_eval_suite(db, scenario_names=args.scenarios, prompt_version=args.version)
            print(f"\n{'='*50}")
            print(f"{'Scenario':<25} {'Score':>8} {'Status':>8}")
            print("-" * 43)
            for r in results:
                status = "PASS" if r.passed else "FAIL"
                print(f"{r.scenario_name:<25} {r.total_score:>8.0f} {status:>8}")
            total_passed = sum(1 for r in results if r.passed)
            print(f"\n{total_passed}/{len(results)} scenarios passed")


if __name__ == "__main__":
    asyncio.run(main())
