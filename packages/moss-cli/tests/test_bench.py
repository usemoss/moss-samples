"""Tests for moss bench command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moss_cli.commands.bench import _percentile
from moss_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


# ---------------------------------------------------------------------------
# _percentile unit tests
# ---------------------------------------------------------------------------


def test_percentile_single_element() -> None:
    assert _percentile([5.0], 50) == 5.0
    assert _percentile([5.0], 99) == 5.0


def test_percentile_two_elements() -> None:
    data = [1.0, 3.0]
    assert _percentile(data, 0) == 1.0
    assert _percentile(data, 100) == 3.0
    assert _percentile(data, 50) == pytest.approx(2.0)


def test_percentile_p50_odd_length() -> None:
    data = sorted([1.0, 2.0, 3.0, 4.0, 5.0])
    assert _percentile(data, 50) == pytest.approx(3.0)


def test_percentile_p95_known_values() -> None:
    # 20 evenly-spaced values 1..20
    data = [float(i) for i in range(1, 21)]
    # p95 index = 0.95 * 19 = 18.05 → interpolate between 19 and 20
    expected = 19.0 + 0.05 * (20.0 - 19.0)
    assert _percentile(data, 95) == pytest.approx(expected)


def test_percentile_p99_known_values() -> None:
    data = [float(i) for i in range(1, 101)]  # 1..100
    # p99 index = 0.99 * 99 = 98.01 → between index 98 (99.0) and 99 (100.0)
    expected = 99.0 + 0.01 * (100.0 - 99.0)
    assert _percentile(data, 99) == pytest.approx(expected)


def test_percentile_empty_returns_zero() -> None:
    assert _percentile([], 50) == 0.0


# ---------------------------------------------------------------------------
# CLI validation tests (no credentials / no network needed)
# ---------------------------------------------------------------------------


def _make_mock_client() -> Any:
    mock_result = MagicMock()
    mock_result.docs = []
    mock_result.query = "q"
    mock_result.index_name = "test-index"
    mock_result.time_taken_ms = 1.0

    mock_client = MagicMock()
    mock_client.load_index = AsyncMock(return_value=None)
    mock_client.query = AsyncMock(return_value=mock_result)
    return mock_client


def test_bench_no_queries_error() -> None:
    with patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")):
        result = runner.invoke(app, ["bench", "my-index"])
    assert result.exit_code != 0
    assert "No queries provided" in result.output


def test_bench_zero_runs_error() -> None:
    with patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")):
        result = runner.invoke(app, ["bench", "my-index", "--query", "hello", "--runs", "0"])
    assert result.exit_code != 0
    assert "--runs must be >= 1" in result.output


def test_bench_negative_warmup_error() -> None:
    with patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")):
        result = runner.invoke(
            app, ["bench", "my-index", "--query", "hello", "--warmup", "-1"]
        )
    assert result.exit_code != 0
    assert "--warmup must be >= 0" in result.output


def test_bench_missing_queries_file_error(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.txt"
    with patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")):
        result = runner.invoke(
            app, ["bench", "my-index", "--queries-file", str(missing)]
        )
    assert result.exit_code != 0
    assert "Cannot read queries file" in result.output


# ---------------------------------------------------------------------------
# Happy-path tests (mocked MossClient)
# ---------------------------------------------------------------------------


def test_bench_single_query_human_output() -> None:
    mock_client = _make_mock_client()
    with (
        patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")),
        patch("moss_cli.commands.bench.MossClient", return_value=mock_client),
    ):
        result = runner.invoke(
            app,
            ["bench", "my-index", "--query", "what is semantic search?", "--runs", "5", "--warmup", "1"],
        )
    assert result.exit_code == 0
    assert "Overall" in result.output
    assert "p50" in result.output
    assert "p95" in result.output
    assert "p99" in result.output


def test_bench_json_output() -> None:
    mock_client = _make_mock_client()
    with (
        patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")),
        patch("moss_cli.commands.bench.MossClient", return_value=mock_client),
    ):
        result = runner.invoke(
            app,
            ["--json", "bench", "my-index", "--query", "hello", "--runs", "3", "--warmup", "0"],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["index"] == "my-index"
    assert len(data["queries"]) == 1
    assert data["queries"][0]["runs"] == 3
    assert "p50_ms" in data["queries"][0]
    assert "p95_ms" in data["queries"][0]
    assert "p99_ms" in data["queries"][0]
    assert "overall" in data


def test_bench_queries_file(tmp_path: Path) -> None:
    qfile = tmp_path / "queries.txt"
    qfile.write_text("what is AI?\nhow does embedding work?\n")
    mock_client = _make_mock_client()
    with (
        patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")),
        patch("moss_cli.commands.bench.MossClient", return_value=mock_client),
    ):
        result = runner.invoke(
            app,
            ["bench", "my-index", "--queries-file", str(qfile), "--runs", "3", "--warmup", "0"],
        )
    assert result.exit_code == 0
    assert "Overall" in result.output
    # Two queries → table should be rendered
    assert "Benchmark" in result.output


def test_bench_cloud_skips_load_index() -> None:
    mock_client = _make_mock_client()
    with (
        patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")),
        patch("moss_cli.commands.bench.MossClient", return_value=mock_client),
    ):
        result = runner.invoke(
            app,
            ["bench", "my-index", "--query", "hello", "--cloud", "--runs", "2", "--warmup", "0"],
        )
    assert result.exit_code == 0
    mock_client.load_index.assert_not_called()


def test_bench_warmup_calls_are_discarded() -> None:
    mock_client = _make_mock_client()
    with (
        patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")),
        patch("moss_cli.commands.bench.MossClient", return_value=mock_client),
    ):
        runner.invoke(
            app,
            ["bench", "my-index", "--query", "hello", "--runs", "4", "--warmup", "2", "--cloud"],
        )
    # 2 warmup + 4 timed = 6 total calls
    assert mock_client.query.call_count == 6


def test_bench_cloud_omits_alpha() -> None:
    """In cloud mode QueryOptions must not receive alpha."""
    mock_client = _make_mock_client()
    captured: list[Any] = []

    async def capture_query(index: str, q: str, opts: Any) -> Any:
        captured.append(opts)
        return mock_client.query.return_value

    mock_client.query = capture_query  # type: ignore[method-assign]

    with (
        patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")),
        patch("moss_cli.commands.bench.MossClient", return_value=mock_client),
        patch("moss_cli.commands.bench.QueryOptions") as mock_qo,
    ):
        mock_qo.return_value = MagicMock()
        runner.invoke(
            app,
            ["bench", "my-index", "--query", "hello", "--cloud", "--runs", "1", "--warmup", "0"],
        )
        mock_qo.assert_called_once_with(top_k=10)


def test_bench_duplicate_queries_preserved_as_separate_entries(tmp_path: Path) -> None:
    """Repeated queries must be tracked as separate workload entries (weighted traffic)."""
    qfile = tmp_path / "queries.txt"
    qfile.write_text("hello\nhello\nworld\n")
    mock_client = _make_mock_client()
    with (
        patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")),
        patch("moss_cli.commands.bench.MossClient", return_value=mock_client),
    ):
        result = runner.invoke(
            app,
            ["--json", "bench", "my-index", "--queries-file", str(qfile), "--runs", "2", "--warmup", "0"],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    # 3 input lines → 3 separate entries, not 2
    assert len(data["queries"]) == 3
    assert data["overall"]["total_runs"] == 6  # 3 entries × 2 runs


def test_bench_json_flag_after_subcommand() -> None:
    """--json placed after the subcommand (moss bench ... --json) must work."""
    mock_client = _make_mock_client()
    with (
        patch("moss_cli.commands.bench.resolve_credentials", return_value=("pid", "pkey")),
        patch("moss_cli.commands.bench.MossClient", return_value=mock_client),
    ):
        result = runner.invoke(
            app,
            ["bench", "my-index", "--query", "hello", "--runs", "3", "--warmup", "0", "--json"],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["index"] == "my-index"
    assert "overall" in data
