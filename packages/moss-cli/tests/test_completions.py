import sys
import types

from typer.testing import CliRunner

from moss_cli import completion
from moss_cli.commands import completions
from moss_cli.main import app

runner = CliRunner()


def test_completions_bash_outputs_script():
    result = runner.invoke(app, ["completions", "bash"])

    assert result.exit_code == 0
    # Click/Typer bash completion script markers.
    assert "_moss_completion" in result.stdout
    assert "_MOSS_COMPLETE=complete_bash" in result.stdout
    assert "complete -o default -F _moss_completion moss" in result.stdout


def test_completions_zsh_outputs_script():
    result = runner.invoke(app, ["completions", "zsh"])

    assert result.exit_code == 0
    assert "#compdef moss" in result.stdout
    assert "_MOSS_COMPLETE=complete_zsh" in result.stdout
    assert "compdef _moss_completion moss" in result.stdout


def test_completions_rejects_unsupported_shell():
    result = runner.invoke(app, ["completions", "fish"])

    # Typer validates the Shell enum and exits with a usage error.
    assert result.exit_code != 0


def _fake_module(name, has_script):
    module = types.ModuleType(name)
    if has_script:
        module.get_completion_script = lambda **kwargs: f"script from {name}"
    return module


def _install_typer_modules(monkeypatch, availability):
    # None in sys.modules makes importlib raise ImportError, i.e. "module missing".
    for name, has_script in availability.items():
        module = None if has_script is None else _fake_module(name, has_script)
        monkeypatch.setitem(sys.modules, name, module)


def test_resolve_get_completion_script_prefers_typer_main(monkeypatch):
    _install_typer_modules(
        monkeypatch,
        {
            "typer.main": True,
            "typer.completion": True,
            "typer._completion_shared": True,
        },
    )

    func = completions._resolve_get_completion_script()

    assert func is not None
    assert func() == "script from typer.main"


def test_resolve_get_completion_script_falls_back_in_order(monkeypatch):
    # typer.main exists but lacks the symbol, typer.completion is missing entirely.
    _install_typer_modules(
        monkeypatch,
        {
            "typer.main": False,
            "typer.completion": None,
            "typer._completion_shared": True,
        },
    )

    func = completions._resolve_get_completion_script()

    assert func is not None
    assert func() == "script from typer._completion_shared"


def test_resolve_get_completion_script_returns_none_when_unavailable(monkeypatch):
    _install_typer_modules(
        monkeypatch,
        {
            "typer.main": False,
            "typer.completion": False,
            "typer._completion_shared": None,
        },
    )

    assert completions._resolve_get_completion_script() is None


def test_completions_reports_error_when_typer_has_no_completion_api(monkeypatch):
    monkeypatch.setattr(completions, "_resolve_get_completion_script", lambda: None)

    result = runner.invoke(app, ["completions", "bash"])

    assert result.exit_code == 1
    assert "Shell completion is unavailable" in result.output


def test_complete_index_name_lists_indexes(monkeypatch):
    class FakeIndex:
        def __init__(self, name):
            self.name = name

    class FakeClient:
        def __init__(self, project_id, project_key):
            pass

        async def list_indexes(self):
            return [FakeIndex("alpha"), FakeIndex("beta"), FakeIndex("gamma")]

    monkeypatch.setenv("MOSS_PROJECT_ID", "pid")
    monkeypatch.setenv("MOSS_PROJECT_KEY", "pkey")
    # complete_index_name imports MossClient from the moss module lazily.
    import moss

    monkeypatch.setattr(moss, "MossClient", FakeClient)

    names = completion.complete_index_name(None, [], "")
    assert names == ["alpha", "beta", "gamma"]


def test_complete_index_name_returns_empty_on_error(monkeypatch):
    class BrokenClient:
        def __init__(self, project_id, project_key):
            raise RuntimeError("boom")

    monkeypatch.setenv("MOSS_PROJECT_ID", "pid")
    monkeypatch.setenv("MOSS_PROJECT_KEY", "pkey")
    import moss

    monkeypatch.setattr(moss, "MossClient", BrokenClient)

    # Any failure must yield no completions rather than raising.
    assert completion.complete_index_name(None, [], "") == []


def test_complete_index_name_handles_missing_credentials(monkeypatch):
    # No credentials available anywhere -> resolve_credentials raises -> [].
    monkeypatch.delenv("MOSS_PROJECT_ID", raising=False)
    monkeypatch.delenv("MOSS_PROJECT_KEY", raising=False)
    monkeypatch.delenv("MOSS_PROFILE", raising=False)
    monkeypatch.setattr(completion, "resolve_credentials", _raise_bad_params)

    assert completion.complete_index_name(None, [], "") == []


def _raise_bad_params(*args, **kwargs):
    import typer

    raise typer.BadParameter("missing creds")
