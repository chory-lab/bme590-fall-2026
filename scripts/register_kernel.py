"""Register the 'BME 590 (lab automation)' Jupyter kernel against this .venv.

    uv run python scripts/register_kernel.py

The one implementation used by both the installer (scripts/install.py) and
`uv run bme590 start` (bme590/cli.py), so a fix here reaches both paths.

It exists beyond a plain `ipykernel install` for two reasons.

macOS: .venv/bin/python is a symlink to the interpreter uv manages, and
sys.executable -- which ipykernel writes into the kernelspec -- resolves to that
base interpreter rather than the venv path. A kernel launched from the resolved
path never activates the class environment, so every notebook would fail as if
pylabrobot were missing. This re-points the kernelspec at the venv's own
interpreter, which is what ipykernel writes anyway everywhere else, so the patch
is a no-op off macOS.

Both scopes: the workshops bind their kernel by *name* (every notebook carries
kernelspec.name = bme590), and a name is resolved through Jupyter's search path.
Registering only --user makes that name global and singular, so a second checkout
-- or this folder renamed -- leaves one `bme590` pointing at somebody else's
.venv. The name still matches, the notebook still binds, and the student gets
ModuleNotFoundError in a notebook that looks correctly configured. The venv's own
share/jupyter/kernels comes FIRST in that search path, so a --sys-prefix copy
shadows a stale global one for anything running from this environment (verified:
with the user-level spec deliberately pointed at a bogus interpreter, this
environment still resolved its own). --user is kept as well, because it is what
lets a notebook opened from anywhere -- JupyterLab, or a copy outside this folder
-- still find this environment.

It is also why a failed registration is not fatal to the install: if the user
directory cannot be written on a managed machine, the in-venv kernel still works.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KERNEL_NAME = "bme590"
DISPLAY_NAME = "BME 590 (lab automation)"


def venv_python() -> Path:
    return ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install(python: Path, *scope: str) -> bool:
    """Install the kernelspec at one scope. Returns whether it worked."""
    return subprocess.run(
        [str(python), "-m", "ipykernel", "install", *scope,
         "--name", KERNEL_NAME, "--display-name", DISPLAY_NAME],
        cwd=ROOT, stdout=subprocess.DEVNULL,
    ).returncode == 0


def repoint(spec_dir: Path, python: Path) -> None:
    """Make this kernelspec launch the venv's own interpreter (see module docstring)."""
    spec_file = spec_dir / "kernel.json"
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    if spec["argv"][0] == str(python):
        return
    spec["argv"][0] = str(python)
    spec_file.write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    python = venv_python()
    if not python.exists():
        print(f"no interpreter at {python} - run the installer first")
        return 1

    # The in-venv copy first: it is the one that has to be right, because it wins.
    #
    # --prefix, not --sys-prefix: the latter installs wherever sys.prefix points,
    # and sys.prefix can disagree with the venv even while running the venv's own
    # python (observed on macOS, where CPython computed the prefix from the
    # resolved symlink). That would file the kernel under the uv-managed base
    # interpreter -- shared with every other project on the machine -- and it
    # would not shadow anything. Name the directory outright.
    venv = ROOT / ".venv"
    installed: list[Path] = []
    if install(python, "--prefix", str(venv)):
        installed.append(venv / "share" / "jupyter" / "kernels" / KERNEL_NAME)
    if install(python, "--user"):
        try:
            from jupyter_core.paths import jupyter_data_dir

            installed.append(Path(jupyter_data_dir()) / "kernels" / KERNEL_NAME)
        except Exception as exc:  # noqa: BLE001 - the sys-prefix copy still stands
            print(f"note: could not locate the user kernel directory: {exc}")

    installed = [d for d in installed if (d / "kernel.json").exists()]
    if not installed:
        print("registering the Jupyter kernel failed")
        return 1

    for spec_dir in installed:
        try:
            repoint(spec_dir, python)
        except Exception as exc:  # noqa: BLE001 - a wrong argv is exactly the bug this
            print(f"could not point {spec_dir} at {python}: {exc}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
