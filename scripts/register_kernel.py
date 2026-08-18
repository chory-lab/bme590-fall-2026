"""Register the 'BME 590 (lab automation)' Jupyter kernel against this .venv.

    uv run python scripts/register_kernel.py

The one implementation used by both the installer (scripts/install.py) and
`uv run bme590 start` (bme590/cli.py), so a fix here reaches both paths.

It exists beyond a plain `ipykernel install` because of macOS: .venv/bin/python
is a symlink to the interpreter uv manages, and sys.executable -- which
ipykernel writes into the kernelspec -- resolves to that base interpreter rather
than the venv path. A kernel launched from the resolved path never activates the
class environment, so every notebook would fail as if pylabrobot were missing.
This re-points the kernelspec at the venv's own interpreter, which is what
ipykernel writes anyway everywhere else, so the patch is a no-op off macOS.
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


def main() -> int:
    python = venv_python()
    if not python.exists():
        print(f"no interpreter at {python} - run the installer first")
        return 1

    if subprocess.run(
        [str(python), "-m", "ipykernel", "install", "--user",
         "--name", KERNEL_NAME, "--display-name", DISPLAY_NAME],
        cwd=ROOT, stdout=subprocess.DEVNULL,
    ).returncode != 0:
        print("registering the Jupyter kernel failed")
        return 1

    # Re-point argv[0] at the venv's own interpreter (see module docstring).
    try:
        from jupyter_client.kernelspec import KernelSpecManager

        spec_dir = KernelSpecManager().find_kernel_specs().get(KERNEL_NAME)
        if spec_dir is None:
            raise FileNotFoundError(f"no kernelspec directory for {KERNEL_NAME}")
        spec_file = Path(spec_dir) / "kernel.json"
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        spec["argv"][0] = str(python)
        spec_file.write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - a wrong argv is exactly the bug this
        print(f"could not re-point the kernel at {python}: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
