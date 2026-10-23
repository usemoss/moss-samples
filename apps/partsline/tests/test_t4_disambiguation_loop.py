from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_PROMPTS = ROOT / "agent" / "prompts.py"


class T4DisambiguationLoopTest(unittest.TestCase):
    def test_prompt_requires_lookup_before_engine_or_trim_disambiguation(self) -> None:
        prompt_source = AGENT_PROMPTS.read_text(encoding="utf-8")

        self.assertIn(
            "Do not ask for engine or trim before the first lookup", prompt_source
        )
        self.assertIn(
            "Once part, year, make, and model are known, call lookup_part even if engine or trim is missing",
            prompt_source,
        )

    def test_prompt_requires_ambiguous_answer_recall_loop(self) -> None:
        prompt_source = AGENT_PROMPTS.read_text(encoding="utf-8")

        for required_text in [
            "store the pending lookup",
            "wait for the caller's answer",
            "call lookup_part again with the same part, year, make, and model",
            "add only the returned attribute",
            "quote only after the second lookup returns single_match",
            "never choose a candidate yourself",
        ]:
            self.assertIn(required_text, prompt_source)
