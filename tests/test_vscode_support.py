"""The VS Code half of the install: extensions, and what we say when they fail.

"Failed to install the Python extension" arrives at office hours with nothing
attached to it. The installer maps the CLI's own explanation onto the two causes
that actually produce it, and the doctor reports which extension is missing, so
neither depends on a student remembering the wording. Both are exercised here
against a stub `code` on PATH -- the real CLI would need a real marketplace, and
the failure modes worth testing cannot be provoked on demand anyway.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def load(name: str):
    """Import one of the standalone scripts/ modules by path."""
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_code(tmp_path, monkeypatch):
    """Put a stub `code` CLI on PATH and return a way to script its behaviour."""

    def _install(stdout: str = "", exit_code: int = 0):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        if os.name == "nt":
            shim = bin_dir / "code.cmd"
            lines = ["@echo off"]
            lines += [f"echo {line}" for line in stdout.splitlines()]
            lines.append(f"exit /b {exit_code}")
            shim.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        else:
            shim = bin_dir / "code"
            body = "".join(f"echo {line!r}\n" for line in stdout.splitlines())
            shim.write_text(f"#!/bin/sh\n{body}exit {exit_code}\n", encoding="utf-8")
            shim.chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
        return shim

    return _install


# --------------------------------------------------------------------- doctor


def test_doctor_reports_both_extensions_present(fake_code, capsys):
    fake_code("ms-python.python\nms-toolsai.jupyter\nsome.other-extension")
    doctor = load("doctor")
    warnings: list[str] = []
    doctor.check_vscode_extensions(warnings)
    assert "Python and Jupyter extensions installed" in capsys.readouterr().out
    assert warnings == []


def test_doctor_names_the_missing_extension(fake_code, capsys):
    fake_code("ms-toolsai.jupyter")  # Jupyter installed, Python is not
    doctor = load("doctor")
    warnings: list[str] = []
    doctor.check_vscode_extensions(warnings)
    out = capsys.readouterr().out
    assert "MISSING extension(s): Python" in out
    assert len(warnings) == 1
    assert "Check for Updates" in warnings[0]  # the advice, not just the fact


def test_doctor_treats_a_missing_editor_as_fine(monkeypatch, capsys):
    doctor = load("doctor")
    monkeypatch.setattr(doctor, "vscode_cli", lambda: None)
    warnings: list[str] = []
    doctor.check_vscode_extensions(warnings)
    assert "not found" in capsys.readouterr().out
    assert warnings == []  # JupyterLab is a complete answer; this cannot fail an install


# ------------------------------------------------------------------ installer


@pytest.mark.parametrize(
    "cli_output, expected",
    [
        ("Unable to install extension because it is not compatible with VS Code 1.74.0",
         "Update VS Code"),
        ("getaddrinfo ENOTFOUND marketplace.visualstudio.com", "another network"),
        ("something nobody has seen before", "Extensions panel"),
    ],
    ids=["outdated-editor", "blocked-network", "unrecognized"],
)
def test_installer_explains_why_an_extension_failed(fake_code, tmp_path, capsys, cli_output, expected):
    fake_code(cli_output, exit_code=1)
    install = load("install")
    install.configure_vscode(tmp_path)
    out = capsys.readouterr().out
    assert "could not install ms-python.python" in out
    assert expected in out
    # The CLI's own words survive: without them a report says only "it failed".
    assert cli_output.split()[0] in out


# ------------------------------------------------- PyLabRobot's source in search
#
# PyLabRobot used to sit at the top level of the class folder, where students
# searched it for labware. It now installs into .venv, which .gitignore hides and
# which VS Code's search therefore skips -- and no `search.exclude` entry can undo
# a .gitignore. The installer's answer is a workspace file with the installed
# package as a second folder root, which search treats on its own terms.


def _fake_venv(tmp_path):
    """A tmp course folder whose .venv python prints a pylabrobot directory."""
    package = tmp_path / ".venv" / "Lib" / "site-packages" / "pylabrobot"
    package.mkdir(parents=True)
    return package


def test_workspace_lists_the_installed_pylabrobot_as_a_second_root(tmp_path, monkeypatch):
    import json as _json

    install = load("install")
    package = _fake_venv(tmp_path)
    monkeypatch.setattr(install, "pylabrobot_dir", lambda root: package)

    install.write_workspace(tmp_path)

    workspace = _json.loads((tmp_path / "bme590.code-workspace").read_text(encoding="utf-8"))
    paths = [folder["path"] for folder in workspace["folders"]]
    assert paths[0] == "."
    # Relative to the workspace file, so the file survives the folder being moved
    # or renamed -- which students do.
    assert paths[1] == ".venv/Lib/site-packages/pylabrobot"
    assert not Path(paths[1]).is_absolute()


def test_workspace_keeps_the_interpreter_the_installer_chose(tmp_path, monkeypatch):
    import json as _json

    install = load("install")
    package = _fake_venv(tmp_path)
    monkeypatch.setattr(install, "pylabrobot_dir", lambda root: package)

    install.write_workspace(tmp_path)

    settings = _json.loads((tmp_path / "bme590.code-workspace").read_text(encoding="utf-8"))["settings"]
    # Absolute: ${workspaceFolder} is ambiguous with more than one folder root,
    # and a workspace that silently loses the interpreter is worse than no
    # workspace at all.
    assert Path(settings["python.defaultInterpreterPath"]).is_absolute()
    assert settings["jupyter.askForKernelSelection"] is False


def test_a_missing_pylabrobot_skips_the_workspace_rather_than_failing(tmp_path, monkeypatch, capsys):
    install = load("install")
    monkeypatch.setattr(install, "pylabrobot_dir", lambda root: None)

    install.write_workspace(tmp_path)

    assert not (tmp_path / "bme590.code-workspace").exists()
    assert "skipping the workspace file" in capsys.readouterr().out


def test_settings_index_pylabrobot_deeply_enough_to_find_labware(tmp_path, monkeypatch, fake_code):
    """Ctrl+T and completions are only as good as what Pylance indexed.

    An unlisted package is indexed one level deep -- for PyLabRobot that is the
    top-level module and nothing else, so none of the labware names that
    `pylabrobot.resources` re-exports are known to the editor.
    """
    import json as _json

    fake_code()
    install = load("install")
    install.configure_vscode(tmp_path)

    settings = _json.loads((tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    depths = {entry["name"]: entry for entry in settings["python.analysis.packageIndexDepths"]}
    assert depths["pylabrobot"]["depth"] >= 2  # `pylabrobot.resources` is where the names live
    # `pylabrobot.resources` declares no __all__, so without this Pylance has
    # nothing to index.
    assert depths["pylabrobot"]["includeAllSymbols"] is True
    # Pylance replaces this array rather than merging, so its defaults must survive.
    assert {"sklearn", "matplotlib", "scipy"} <= set(depths)
    assert settings["python.analysis.autoImportCompletions"] is True


def test_the_workspace_and_the_folder_settings_do_not_drift(tmp_path, monkeypatch, fake_code):
    """Whichever file VS Code ends up reading, a student gets the same editor."""
    import json as _json

    fake_code()
    install = load("install")
    package = _fake_venv(tmp_path)
    monkeypatch.setattr(install, "pylabrobot_dir", lambda root: package)

    install.configure_vscode(tmp_path)

    folder = _json.loads((tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    workspace = _json.loads((tmp_path / "bme590.code-workspace").read_text(encoding="utf-8"))["settings"]
    # The interpreter path is deliberately different (see write_workspace); the
    # rest must match key for key.
    assert set(folder) == set(workspace)
    for key in folder:
        if key != "python.defaultInterpreterPath":
            assert folder[key] == workspace[key], key
