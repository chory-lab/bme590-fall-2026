"""Verify a student install, and print a paste-able report when it is broken.

Run by the installers as the last step, and by students any time afterwards:

    uv run python scripts/doctor.py

It checks the three things that actually break: the interpreter is the project's
own .venv, every `pylabrobot` import the workshops use resolves, and a chatterbox
protocol runs end to end. It deliberately does *not* execute the notebooks --
that is CI's job (.github/scripts/check_workshops.py), and it takes minutes.

The import list and the smoke protocol are reused from that CI checker rather
than restated here, so a workshop that starts importing something new is covered
in both places at once.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import platform
import sys
from pathlib import Path

# Windows consoles still default to a legacy codepage when stdout is a pipe (the
# installers capture it), which turns PyLabRobot's "µL" into a decode error.
for stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / ".github" / "scripts" / "check_workshops.py"


def load_checker():
    """Import .github/scripts/check_workshops.py by path (it is not a package)."""
    spec = importlib.util.spec_from_file_location("check_workshops", CHECKER)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {CHECKER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report_environment() -> list[str]:
    """Print what a support request needs, and return any hard problems."""
    problems: list[str] = []
    venv = ROOT / ".venv"
    running = Path(sys.executable).resolve()

    print(f"python       {platform.python_version()}  ({sys.executable})")
    print(f"platform     {platform.platform()}")
    print(f"project      {ROOT}")

    try:
        running.relative_to(venv.resolve())
    except (ValueError, OSError):
        # Not fatal in CI (which runs the checker against its own interpreter),
        # but on a student machine it is the single most common cause of
        # "ModuleNotFoundError: pylabrobot" in a notebook that looked installed.
        problems.append(
            f"this is not the project environment.\n"
            f"    expected an interpreter inside {venv}\n"
            f"    got                            {running}\n"
            f"    Run the command as: uv run python scripts/doctor.py"
        )

    if sys.version_info < (3, 11):
        problems.append(f"Python 3.11 or newer is required; this is {platform.python_version()}")

    for name in ("pylabrobot", "ipykernel", "ipywidgets", "nbformat", "pandas", "numpy", "PIL"):
        if importlib.util.find_spec(name) is None:
            problems.append(f"package missing: {name} (re-run the installer)")

    # The Jupyter kernel is a single user-level file holding an absolute path to
    # an interpreter, so a second checkout of this repo -- or a folder that was
    # moved or renamed -- leaves it aimed at the wrong environment. Notebooks then
    # run somewhere unexpected and fail as if packages were missing.
    try:
        from jupyter_client.kernelspec import KernelSpecManager

        argv = KernelSpecManager().get_kernel_spec("bme590").argv
        target = Path(argv[0]).resolve() if argv else None
        if target is None or not target.is_relative_to(venv.resolve()):
            problems.append(
                f"the 'BME 590' Jupyter kernel points at {target}, not this folder's .venv.\n"
                f"    Another copy of the course folder probably registered it. Fix with:\n"
                f"    uv run bme590 start"
            )
    except Exception:  # noqa: BLE001 - no such kernel, or jupyter_client absent
        problems.append(
            "the 'BME 590' Jupyter kernel is not registered. Fix with: uv run bme590 start"
        )

    # The environment is otherwise sealed -- .venv is built with
    # include-system-site-packages = false and user site-packages disabled, so no
    # package installed elsewhere on the machine can reach it. PYTHONPATH and
    # PYTHONHOME are the exceptions: they are prepended ahead of site-packages, so
    # a stale entry silently shadows a real package (verified: a numpy.py on
    # PYTHONPATH wins over the installed numpy). Rare, but it produces
    # bewildering errors, so name it here rather than let someone hunt for it.
    for variable in ("PYTHONPATH", "PYTHONHOME"):
        value = os.environ.get(variable)
        if value:
            problems.append(
                f"{variable} is set to {value!r}. It overrides this environment's packages -- "
                f"unset it and try again."
            )

    # Not a problem, just the single most common source of confusion: a conda base
    # environment stays on PATH, so a plain `python` in the terminal may not be
    # this one. `uv run` and VS Code's interpreter selection both ignore it.
    if os.environ.get("CONDA_DEFAULT_ENV"):
        print(f"note         conda environment '{os.environ['CONDA_DEFAULT_ENV']}' is active in this shell;")
        print("             use `uv run python ...` so you get the class environment")

    return problems


def main() -> int:
    print("=== BME 590 install check ===")
    problems = report_environment()

    if not problems:
        try:
            checker = load_checker()
            failures = checker.check_imports()
            if failures:
                problems.append(f"{failures} workshop import(s) failed -- see IMPORT FAIL lines above")
            # The chatterbox backend narrates every pipetting step; 40 lines of
            # it is noise in a pass and context in a failure, so hold it and
            # print it only if the protocol raises.
            chatter = io.StringIO()
            try:
                with contextlib.redirect_stdout(chatter):
                    checker.run_smoke()
            except Exception:
                print(chatter.getvalue())
                raise
            print("smoke protocol OK (a chatterbox pipetting run completed)")
        except Exception as exc:  # noqa: BLE001 - any failure here is a real install problem
            import traceback

            traceback.print_exc()
            problems.append(f"{type(exc).__name__}: {exc}")

    if problems:
        print("\n=== PROBLEMS FOUND ===")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nCopy this whole report into the #pylabrobot Slack channel.\n"
            "Most problems are fixed by re-running the installer."
        )
        return 1

    print("\nAll checks passed. The environment is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
