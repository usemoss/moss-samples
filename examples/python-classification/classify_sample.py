"""
Moss Classification — Question Normalization
==============================================
Normalizes noisy ASR questions into clean standalone questions
using conversation context.

Prerequisites:
    pip install -r requirements.txt

Usage:
    python classify_sample.py
"""

import asyncio
import os
import time

from dotenv import load_dotenv
from moss_classify_rest import MossClassifyClient

load_dotenv()


async def main():
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("Error: MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set.")
        print("Create a .env file in this directory and set MOSS_PROJECT_ID and MOSS_PROJECT_KEY.")
        return

    async with MossClassifyClient(project_id=project_id, project_key=project_key) as client:
        context = [
            "Agent: Thanks for joining the call today.",
            "Customer: Yeah thanks, so we've been looking at a few vendors.",
            "Agent: Happy to walk you through what we offer.",
        ]

        utterances = [
            "so like how does the the pricing work exactly",
            "you use aws right?",
            "and what about like the the onboarding process",
            "I'll send that over after the call.",
        ]

        print("Question Normalization")
        print("-" * 50)

        for text in utterances:
            t0 = time.monotonic()
            result = await client.classify(text, context=context)
            elapsed = (time.monotonic() - t0) * 1000

            print(f"  Input:      {text}")
            if result.is_question and result.normalized_question:
                print(f"  Normalized: {result.normalized_question}")
            print(f"  Label:      {result.label} ({result.confidence:.0%})  {elapsed:.0f}ms")
            print()


if __name__ == "__main__":
    asyncio.run(main())
