"""The `bme590` command: one entry point for a working session.

    uv run bme590              # what to do next, and whether the env is healthy
    uv run bme590 start 01     # copy workshop 01, open it in VS Code, ready to run
    uv run bme590 lab          # same, in JupyterLab instead of VS Code
    uv run bme590 update       # pull the latest materials and match the environment
    uv run bme590 check        # the install doctor

Why this exists: the per-session recipe used to be six manual steps (pull, sync,
copy the notebook to the right folder, open the folder, pick the interpreter, pick
the kernel), each with its own way to go wrong. They are all deterministic, so
they belong in a command rather than in a student's memory.

Deliberately thin: every subcommand shells out to the same scripts the installer
and CI use, so there is one implementation of each step, not two.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Line-buffered for the same reason as install.py: every subcommand shells out,
# and block-buffered output would print our headings after the output they
# introduce.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

WINDOWS = os.name == "nt"
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")

# The visualizer's defaults, restated here only so the CLI can tell the student
# where to look. PyLabRobot 0.2.2: Visualizer(host="127.0.0.1", ws_port=2121,
# fs_port=1337).
VISUALIZER_URL = "http://127.0.0.1:1337"


def python() -> str:
    """The class interpreter, falling back to whatever is running this."""
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def run(cmd: list[str], **kwargs) -> int:
    """Run a command in the class folder, reporting a missing tool rather than raising.

    A stale PATH entry (a tool that was uninstalled or moved) is otherwise a
    traceback, which reads as "the class software is broken" when it means "this
    program is not where PATH says it is".
    """
    try:
        return subprocess.run([str(part) for part in cmd], cwd=ROOT, **kwargs).returncode
    except FileNotFoundError:
        print(f"could not run {cmd[0]} - it is not where PATH says it is")
        return 127
    except subprocess.TimeoutExpired:
        print(f"{cmd[0]} took too long and was stopped")
        return 124


def uv() -> str | None:
    return os.environ.get("UV_BIN") or shutil.which("uv")


def find_code() -> str | None:
    """The VS Code CLI, looked for where it lives as well as on PATH.

    On macOS `code` reaches PATH only after the user runs "Shell Command: Install
    'code' command in PATH", which nobody has done on a fresh machine -- so
    `bme590 start` would print "open it yourself" to a student who has VS Code
    installed exactly as the README asks. Kept in step with the copy in
    scripts/install.py, which cannot import this module (it runs before the
    environment exists).
    """
    on_path = shutil.which("code")
    if on_path:
        return on_path
    if sys.platform == "darwin":
        candidates = [
            Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"),
            Path.home() / "Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
        ]
    elif WINDOWS:
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


def sync_if_needed() -> None:
    """Bring the environment in line with uv.lock.

    Cheap when nothing changed (uv audits in milliseconds), and it is the fix for
    the one failure a `git pull` can cause: new material that needs a package the
    student does not have yet.
    """
    tool = uv()
    if not tool:
        print("note: uv is not on PATH, so the environment cannot be checked - skipping")
        return
    run([tool, "sync", "--frozen", "--quiet"])


def kernel_is_ours() -> bool:
    """True if the registered `bme590` kernel points at *this* checkout's .venv.

    The kernelspec is a single user-level file holding an absolute path, so a
    second checkout (or a moved folder) leaves it aimed somewhere else. A
    notebook run against the wrong environment fails in ways that look like
    broken packages, so this is worth checking rather than assuming.
    """
    try:
        from jupyter_client.kernelspec import KernelSpecManager

        spec = KernelSpecManager().get_kernel_spec("bme590")
    except Exception:  # noqa: BLE001 - not installed, or no such kernel
        return False
    argv = spec.argv or []
    if not argv:
        return False
    # Compare paths unresolved. On macOS the venv's bin/python is a symlink to
    # the interpreter uv manages, so resolving both sides would also match a
    # kernel registered by a *different* checkout built on the same interpreter.
    # Registration always writes this checkout's venv path (register_kernel.py),
    # so the stored argv[0] must equal it, exactly.
    expected = ROOT / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
    return Path(argv[0]) == expected


def repair_kernel() -> None:
    """Re-point the kernel at this checkout. Idempotent, about a second."""
    if kernel_is_ours():
        return
    print("registering this folder's Jupyter kernel...")
    run([python(), "scripts/register_kernel.py"], stdout=subprocess.DEVNULL)


def busy_ports() -> list[int]:
    """The visualizer ports something is already listening on.

    Realistic cause: a kernel that is still alive. VS Code keeps kernels running
    per window, so opening a second workshop while the first one's kernel is
    live means the second visualizer binds 2122 while the browser page (served
    from the still-bound 1337) talks to 2121 -- a visualizer that reads
    "Connected" and never updates. A *dead* process is not a problem: the OS
    releases its sockets, which is verified behaviour, so this only ever fires
    when something is genuinely still running.
    """
    import socket

    busy = []
    for port in (1337, 2121):
        probe = socket.socket()
        probe.settimeout(0.3)
        try:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                busy.append(port)
        finally:
            probe.close()
    return busy


def cmd_start(args: argparse.Namespace) -> int:
    if not args.workshop:
        return run([python(), "scripts/start_workshop.py"])

    # No sync_if_needed() here: `uv run bme590` has already synced the
    # environment before this command ran. Syncing again just re-audits the same
    # lock (cmd_update pulls first, so it is the command that actually needs it).
    repair_kernel()
    if run([python(), "scripts/start_workshop.py", args.workshop]) not in (0, 1):
        return 1

    # Exit code 1 from start_workshop means "you already have a copy", which is
    # the normal case when resuming work -- not a reason to stop.
    matches = sorted((ROOT / "assignments").glob(f"*{args.workshop.zfill(2)}*.ipynb"))
    if not matches:
        matches = sorted((ROOT / "assignments").glob(f"*{args.workshop}*.ipynb"))
    if not matches:
        print("could not find your copy in assignments/ - run `bme590 start` to see the list")
        return 1
    notebook = matches[0]

    code = find_code()
    if code:
        # Open the folder *and* the notebook: the folder is what carries
        # .vscode/settings.json, so opening the file alone would lose the
        # interpreter selection.
        run([code, str(ROOT), str(notebook)])
        print(f"\nOpened {notebook.relative_to(ROOT)} in VS Code.")
    else:
        print(f"\nYour copy is at {notebook.relative_to(ROOT)}")
        print("VS Code was not found - open that file from VS Code yourself.")

    busy = busy_ports()
    if busy:
        print(
            f"""
WARNING: something is already using the visualizer port(s) {', '.join(map(str, busy))}.
That is almost always a kernel from another notebook that is still running --
VS Code keeps kernels alive per window. If you start a visualizer now it will
quietly bind a different port, and your browser will keep showing the *other*
notebook's deck.

Fix it first: in the other notebook, run "Jupyter: Restart Kernel" or close that
VS Code window."""
        )

    print(
        f"""
While you work:
  - Run the cells in order. The kernel is already chosen: the notebook's top
    right should read "BME 590 (lab automation)". If it reads "Select Kernel",
    click it and choose "Jupyter Kernel..." then "BME 590 (lab automation)" --
    the kernels are one level down, under that heading, not in the first list.
  - When a cell starts the Visualizer, your browser opens {VISUALIZER_URL}
    and the top right should read "Connected". If it does not, reload that page.
  - Re-running a Visualizer cell leaves the old one running, and your browser
    stays attached to it -- so the deck appears to freeze. Restart the kernel
    to close the old visualizer.
  - To record a GIF, click Start Recording BEFORE the protocol cell runs.
  - `SLEEP` at the top of the notebook scales every pause; set it to 0 to run
    at full speed once you have watched it.

Stuck? Run:  uv run bme590 check
"""
    )
    return 0


def cmd_lab(args: argparse.Namespace) -> int:
    tool = uv()
    if not tool:
        print("uv is not on PATH - reinstall with the command in the README")
        return 1
    # JupyterLab is not in the default install (it is the largest download in the
    # tree and VS Code is the documented editor), so pull it in on demand.
    print("making sure JupyterLab is installed...")
    if run([tool, "sync", "--frozen", "--group", "notebook"]) != 0:
        return 1
    (ROOT / "assignments").mkdir(exist_ok=True)
    return run([tool, "run", "--frozen", "--group", "notebook", "jupyter", "lab",
                "--notebook-dir", str(ROOT)])


def cmd_update(args: argparse.Namespace) -> int:
    if shutil.which("git") and (ROOT / ".git").exists():
        print("pulling the latest course materials...")
        # Never let git stop to ask a question: a credential or host-key prompt
        # with nothing to answer it reads as a hang. Same reasoning, and the same
        # variables, as scripts/install.py:git_env().
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
        env.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
        if run(["git", "pull", "--ff-only"], env=env, timeout=300) != 0:
            print(
                "\ngit pull did not fast-forward. That usually means you edited files in\n"
                "workshops/ directly. Your work in assignments/ is safe; ask on Slack\n"
                "before doing anything else."
            )
            return 1
    else:
        print("this copy was downloaded as a zip, so re-run the installer to update the materials")
    sync_if_needed()
    return run([python(), "scripts/doctor.py"])


def cmd_check(args: argparse.Namespace) -> int:
    return run([python(), "scripts/doctor.py"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bme590", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start", help="copy a workshop and open it, ready to run")
    start.add_argument("workshop", nargs="?", help="workshop number, e.g. 01 (omit to list them)")
    start.set_defaults(func=cmd_start)

    sub.add_parser("lab", help="work in JupyterLab instead of VS Code").set_defaults(func=cmd_lab)
    sub.add_parser("update", help="pull the latest materials and match the environment").set_defaults(func=cmd_update)
    sub.add_parser("check", help="verify the install (the doctor)").set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Bare `bme590`: orient the student rather than printing usage at them.
        print(f"BME 590 class environment  ({ROOT})\n")
        run([python(), "scripts/start_workshop.py"])
        print("\n  bme590 start 01   open workshop 01 and start working")
        print("  bme590 check      verify the install")
        print("  bme590 update     get the latest materials")
        print("  bme590 lab        work in JupyterLab instead of VS Code")
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
