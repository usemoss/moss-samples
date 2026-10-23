from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_MAIN = ROOT / "agent" / "main.py"


def module_constants() -> dict[str, object]:
    tree = ast.parse(AGENT_MAIN.read_text(encoding="utf-8"))
    constants: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue

        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value

    return constants


def literal_value(node: ast.AST, constants: dict[str, object]) -> object:
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]

    return ast.literal_eval(node)


def literal_dict(node: ast.AST) -> dict[str, object]:
    if not isinstance(node, ast.Dict):
        raise AssertionError("expected a literal dict")

    constants = module_constants()
    values: dict[str, object] = {}
    for key, value in zip(node.keys, node.values, strict=True):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            raise AssertionError("dict keys must be string literals")
        values[key.value] = literal_value(value, constants)
    return values


def turn_handling_keyword(name: str) -> ast.AST:
    tree = ast.parse(AGENT_MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "TurnHandlingOptions"
        ):
            for keyword in node.keywords:
                if keyword.arg == name:
                    return keyword.value

    raise AssertionError(f"TurnHandlingOptions missing {name!r}")


class T6EndpointingConfigTest(unittest.TestCase):
    def test_turn_handling_config_sets_fixed_endpointing_delay_for_manual_number_test(
        self,
    ) -> None:
        # Static config check only. Real validation is the manual voice test:
        # say "A dash one hundred ... B" and "two point five ... liter".
        endpointing = literal_dict(turn_handling_keyword("endpointing"))
        min_delay = endpointing["min_delay"]
        max_delay = endpointing["max_delay"]

        self.assertEqual(endpointing["mode"], "fixed")
        assert isinstance(min_delay, float)
        assert isinstance(max_delay, float)
        self.assertGreaterEqual(min_delay, 1.0)
        self.assertGreaterEqual(max_delay, 3.0)
        self.assertLessEqual(max_delay, 4.0)
        self.assertLess(min_delay, max_delay)

    def test_turn_handling_config_keeps_adaptive_barge_in_enabled(self) -> None:
        interruption = literal_dict(turn_handling_keyword("interruption"))

        self.assertIs(interruption["enabled"], True)
        self.assertEqual(interruption["mode"], "adaptive")
