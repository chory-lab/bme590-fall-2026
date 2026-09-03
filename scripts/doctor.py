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


def vscode_cli() -> str | None:
    """The VS Code CLI, wherever it lives.

    A third copy of the same lookup (scripts/install.py, bme590/cli.py). Each
    file is standalone on purpose -- this one runs before the package is
    importable -- so the duplication is the price of that.
    """
    import shutil

    on_path = shutil.which("code")
    if on_path:
        return on_path
    if sys.platform == "darwin":
        candidates = [
            Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"),
            Path.home() / "Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
        ]
    elif os.name == "nt":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/bin/code.cmd",
            Path(os.environ.get("ProgramFiles", "")) / "Microsoft VS Code/bin/code.cmd",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft VS Code/bin/code.cmd",
        ]
    else:
        candidates = [Path("/usr/share/code/bin/code"), Path("/snap/bin/code"), Path("/usr/bin/code")]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def check_vscode_extensions(warnings: list[str]) -> None:
    """Report whether the two extensions the workshops need are installed.

    A warning, never a problem: the environment runs notebooks perfectly well
    without VS Code, and `bme590 lab` does not involve it at all. It is here
    because "failed to install the Python extension" is otherwise something a
    student can only report from memory -- this turns it into a line they can
    paste, and says which of the two extensions is actually missing.
    """
    import subprocess

    code = vscode_cli()
    if code is None:
        print("vscode       not found (fine if you use JupyterLab: uv run bme590 lab)")
        return
    try:
        result = subprocess.run([code, "--list-extensions"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"vscode       found, but could not list extensions ({exc})")
        return
    if result.returncode != 0:
        print(f"vscode       found, but `code --list-extensions` failed (exit {result.returncode})")
        return

    installed = {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    needed = {"ms-python.python": "Python", "ms-toolsai.jupyter": "Jupyter"}
    missing = [name for ext, name in needed.items() if ext not in installed]
    if missing:
        print(f"vscode       MISSING extension(s): {', '.join(missing)}")
        warnings.append(
            f"VS Code is missing the {' and '.join(missing)} extension(s). Notebooks will not run "
            "in VS Code without them. Install from the Extensions panel; if that fails, the two "
            "usual causes are a VS Code too old for the current extension (Help > Check for "
            "Updates) and a network that blocks the marketplace (campus wifi, VPN, proxy)."
        )
    else:
        print("vscode       Python and Jupyter extensions installed")


def report_environment() -> tuple[list[str], list[str]]:
    """Print what a support request needs, and sort what is wrong into two lists.

    Returns (problems, warnings). A problem means the environment cannot run the
    workshops; a warning means something is worth fixing but the environment
    still works. The line matters because scripts/install.py runs this as its
    last step and fails the install on a non-zero exit -- so anything in the
    first list tells a student their install failed, and it had better be true.
    """
    problems: list[str] = []
    warnings: list[str] = []
    venv = ROOT / ".venv"
    # Which environment is this? Not sys.executable: on macOS a uv venv's
    # bin/python is a symlink to the interpreter uv manages, and sys.executable
    # reports that resolved target even though the venv is active. sys.prefix is
    # set from pyvenv.cfg and points at the venv whenever the process started
    # from a venv interpreter, which is exactly the claim being checked.
    running = Path(sys.prefix).resolve()

    print(f"python       {platform.python_version()}  ({sys.executable})")
    print(f"platform     {platform.platform()}")
    print(f"project      {ROOT}")

    # Where the packages actually come from -- the question sys.prefix is only a
    # proxy for, and the one that decides whether a notebook works.
    #
    # A real student install failed here on a healthy environment: running
    # .venv/bin/python on macOS with conda active, sys.executable was the venv's
    # python but sys.prefix was the base interpreter uv manages, because CPython
    # computed the prefix from the resolved symlink and never saw pyvenv.cfg. The
    # install was fine; the check was not. So when the prefix looks wrong, ask
    # where an actual class package loads from before calling it a failure.
    def loads_from_venv(name: str) -> bool | None:
        """True/False if `name` resolves in/outside .venv; None if not installed."""
        try:
            spec = importlib.util.find_spec(name)
        except Exception:  # noqa: BLE001 - a broken parent package, i.e. not ours
            return None
        if spec is None or not spec.origin:
            return None
        try:
            Path(spec.origin).resolve().relative_to(venv.resolve())
            return True
        except (ValueError, OSError):
            return False

    try:
        running.relative_to(venv.resolve())
    except (ValueError, OSError):
        if loads_from_venv("pylabrobot"):
            # Odd, but harmless and out of our hands: the packages being imported
            # are this folder's, which is what has to be true.
            warnings.append(
                f"sys.prefix reports {sys.prefix},\n"
                f"    not {venv} -- but the class packages are loading from .venv,\n"
                f"    so this IS the class environment and the checks below are the real test."
            )
        else:
            # The single most common cause of "ModuleNotFoundError: pylabrobot"
            # in a notebook that looked installed.
            problems.append(
                f"this is not the project environment.\n"
                f"    expected an interpreter inside {venv}\n"
                f"    got                            {sys.prefix} (python {sys.executable})\n"
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

        manager = KernelSpecManager()
        spec_dir = manager.find_kernel_specs().get("bme590", "(unknown location)")
        argv = manager.get_kernel_spec("bme590").argv
        # Compare paths unresolved: on macOS the venv's bin/python is a symlink
        # to the interpreter uv manages, and resolving both sides would also
        # match a kernel registered by a *different* checkout built on the same
        # interpreter. Registration always writes this checkout's venv path, so
        # the stored argv[0] must equal it exactly.
        expected = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        target = Path(argv[0]) if argv else None
        if target is None or target != expected:
            # State what was found, not why. The old wording asserted "another
            # copy of the course folder probably registered it", which was simply
            # wrong in the one real report we have -- it was the macOS
            # venv-symlink path, from this folder. A guessed cause sends whoever
            # reads the transcript looking for a folder that does not exist.
            warnings.append(
                f"the 'BME 590' Jupyter kernel runs the wrong interpreter.\n"
                f"    kernel at {spec_dir}\n"
                f"    runs      {target}\n"
                f"    expected  {expected}\n"
                f"    Fix with: uv run bme590 start"
            )
    except Exception:  # noqa: BLE001 - no such kernel, or jupyter_client absent
        # A warning, not a problem: the kernelspec is a convenience file, `uv run
        # bme590 start` re-registers it, and VS Code can run notebooks against
        # .venv by interpreter alone. The packages below are what actually decide
        # whether this environment works.
        warnings.append(
            "the 'BME 590' Jupyter kernel is not registered. Fix with: uv run bme590 start"
        )

    # The environment is otherwise sealed -- .venv is built with
    # include-system-site-packages = false and user site-packages disabled, so no
    # package installed elsewhere on the machine can reach it. PYTHONPATH and
    # PYTHONHOME are the exceptions: they are prepended ahead of site-packages, so
    # a stale entry silently shadows a real package (verified: a numpy.py on
    # PYTHONPATH wins over the installed numpy). Rare, but it produces
    # bewildering errors, so name it here rather than let someone hunt for it.
    #
    # A warning rather than a problem: plenty of people set PYTHONPATH for
    # unrelated work and never collide with anything here, and the import check
    # below is what proves whether it actually broke this environment. Failing
    # the install on the mere presence of the variable told students with a
    # perfectly good setup that it had failed.
    for variable in ("PYTHONPATH", "PYTHONHOME"):
        value = os.environ.get(variable)
        if value:
            warnings.append(
                f"{variable} is set to {value!r}. It takes priority over this environment's "
                f"packages -- if a package ever fails to import, unset it and try again."
            )

    # Not a problem, just the single most common source of confusion: a conda base
    # environment stays on PATH, so a plain `python` in the terminal may not be
    # this one. `uv run` and VS Code's interpreter selection both ignore it.
    if os.environ.get("CONDA_DEFAULT_ENV"):
        print(f"note         conda environment '{os.environ['CONDA_DEFAULT_ENV']}' is active in this shell;")
        print("             use `uv run python ...` so you get the class environment")

    check_vscode_extensions(warnings)

    return problems, warnings


def main() -> int:
    print("=== BME 590 install check ===")
    problems, warnings = report_environment()

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

    if warnings:
        print("\n=== WORTH FIXING (the environment still works) ===")
        for w in warnings:
            print(f"  - {w}")

    if problems:
        print("\n=== PROBLEMS FOUND ===")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nCopy this whole report into #ed-discuss on Slack.\n"
            "Most problems are fixed by re-running the installer."
        )
        return 1

    if warnings:
        print("\nEverything needed to run the workshops is in place (see above for the rest).")
    else:
        print("\nAll checks passed. The environment is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
