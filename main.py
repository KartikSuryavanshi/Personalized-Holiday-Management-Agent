import argparse
import asyncio
import json

from app.config import get_settings
from app.orchestration import HolidayTeam
from app.schemas import TripRequest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CLI for the Personalized Holiday Management Agent",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Trip request prompt. If omitted, input will be requested interactively.",
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--budget", choices=["low", "medium", "high"], default="medium")
    parser.add_argument(
        "--pace",
        choices=["relaxed", "balanced", "intense"],
        default="balanced",
    )
    parser.add_argument("--start-city", default=None)
    parser.add_argument("--notes", default=None)
    return parser.parse_args()


async def run_cli(args: argparse.Namespace) -> None:
    prompt = args.prompt.strip() if args.prompt else input("Trip prompt: ").strip()
    if len(prompt) < 10:
        raise SystemExit("Prompt must be at least 10 characters.")

    request = TripRequest(
        prompt=prompt,
        days=args.days,
        budget_level=args.budget,
        pace=args.pace,
        start_city=args.start_city,
        notes=args.notes,
    )

    team = HolidayTeam(get_settings())
    result = await team.plan(request)

    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=True))


def main() -> None:
    args = parse_args()
    asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()
