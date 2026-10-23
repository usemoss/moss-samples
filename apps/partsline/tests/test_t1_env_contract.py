from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_VOICE_ENV_KEYS = [
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "DEEPGRAM_API_KEY",
    "CARTESIA_API_KEY",
]


def parse_env_template(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator, f"{path.name} line must be KEY=VALUE: {raw_line!r}"
        entries[key] = value
    return entries


def git_ignores(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", path],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


class T1EnvContractTest(unittest.TestCase):
    def test_env_example_has_blank_voice_provider_keys(self) -> None:
        env_example = ROOT / ".env.example"

        self.assertTrue(env_example.exists())
        entries = parse_env_template(env_example)

        for key in REQUIRED_VOICE_ENV_KEYS:
            self.assertIn(key, entries)
            self.assertEqual(entries[key], "")

    def test_gitignore_excludes_secrets_dependencies_and_build_artifacts(self) -> None:
        ignored_paths = [
            ".env",
            ".env.local",
            "__pycache__/module.cpython-313.pyc",
            "node_modules/livekit-client/index.js",
            ".next/build-manifest.json",
            "build/app.js",
            "dist/app.js",
            "out/index.html",
        ]

        for path in ignored_paths:
            self.assertTrue(git_ignores(path), f"{path} should be ignored")

        self.assertFalse(git_ignores(".env.example"))
