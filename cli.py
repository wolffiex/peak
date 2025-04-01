#!/usr/bin/env python3
import asyncio
import argparse
from app.traffic import analyze_traffic
from app.events import gen_events


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="CLI tool for testing Peak modules")
    parser.add_argument(
        "module",
        choices=["events", "traffic"],
        help="Module to test (events or traffic)",
    )
    args = parser.parse_args()

    if args.module == "events":
        gen = gen_events()
    elif args.module == "traffic":
        gen = analyze_traffic()

    if not gen:
        raise ValueError(f"Unrecognized module: {args.module}")

    async for text_chunk in gen:
        print(text_chunk, end="", flush=True)
    print()


if __name__ == "__main__":
    # Create event loop and run the main function
    asyncio.run(main())
