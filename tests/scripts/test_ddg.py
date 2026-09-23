import asyncio
import json

from ddgs import DDGS


async def main() -> None:
    """Run a manual DDG smoke test without executing during pytest collection."""
    try:
        results = await asyncio.to_thread(lambda: list(DDGS().text("Apple", max_results=3)))
        print("RESULTS", json.dumps(results, indent=2))
    except Exception as exc:
        print("ERROR", exc)


if __name__ == "__main__":
    asyncio.run(main())
