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
