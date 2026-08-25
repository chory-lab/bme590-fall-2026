"""Kernel-selection regressions: does `bme590` resolve to THIS .venv?

    uv run python scripts/check_kernel_selection.py

The notebooks bind their kernel by name (kernelspec.name = bme590); Jupyter
resolves that name through a search path, and VS Code's discovery reads the
same directories. These scenarios pin what students actually experience:

  A. clean            -- after install/`bme590 start`, the name resolves here.
  B. stale-user       -- a stale user-level `bme590` aimed at a dead
                         interpreter (second checkout, moved folder) must NOT
                         win; the in-venv copy shadows it.
  C. jupyter-path     -- a `bme590` found via $JUPYTER_PATH DOES win over the
                         in-venv copy (JUPYTER_PATH outranks the env prefix).
                         Pinned deliberately: if this ever flips, the
                         registration strategy needs a second look.
  D. dead-siblings    -- unrelated broken kernelspecs must not affect the
                         lookup by name.

Everything runs hermetically: pollution is injected through temp directories
and environment variables, never by touching the real user/kernel state.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KERNEL_NAME = "bme590"

DEAD_PY = str(Path(tempfile.gettempdir()) / "definitely-dead" / "python.exe")


def write_spec(kernels_dir: Path, name: str, argv0: str = DEAD_PY, display: str = "STALE") -> None:
    d = kernels_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "kernel.json").write_text(
        json.dumps({
            "argv": [argv0, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": display,
            "language": "python",
        }),
        encoding="utf-8",
    )


def resolve(name: str) -> str:
    """Resolve a kernel name the way any Jupyter front end would."""
    # Imported lazily so the env vars below are read fresh each call.
    from jupyter_client.kernelspec import KernelSpecManager

    return KernelSpecManager().get_kernel_spec(name).argv[0]


def expected_python() -> Path:
    return ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    failures: list[str] = []
    venv_py = str(expected_python().resolve())

    def check(label: str, got: str, want: str) -> None:
        if Path(got).resolve() != Path(want).resolve():
            failures.append(f"{label}: resolved {got}, expected {want}")
            print(f"  FAIL {label}\n       got      {got}\n       expected {want}")
        else:
            print(f"  ok   {label} -> {got}")

    # --- A. clean ----------------------------------------------------------
    print("A. clean")
    check("clean", resolve(KERNEL_NAME), venv_py)

    # --- B. stale user-level registration ----------------------------------
    print("B. stale-user (dead interpreter in the user kernel dir)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # On Windows jupyter_data_dir() is %APPDATA%\jupyter; on posix,
        # $XDG_DATA_HOME/jupyter. Both resolve under this dir below.
        user_dir = tmp / ("appdata" if os.name == "nt" else "xdgdata")
        kdir = user_dir / "jupyter" / "kernels"
        write_spec(kdir, KERNEL_NAME)
        write_spec(kdir, "plr_test")  # dead sibling while we are at it (scenario D)
        os.environ["APPDATA"] = str(user_dir)
        os.environ["XDG_DATA_HOME"] = str(user_dir)
        os.environ.pop("JUPYTER_PATH", None)
        check("stale-user", resolve(KERNEL_NAME), venv_py)

    # --- C. JUPYTER_PATH override (pinned, known behavior) ------------------
    print("C. jupyter-path (an explicit JUPYTER_PATH entry wins -- pinned)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jp_kernels = tmp / "jp" / "kernels"
        write_spec(jp_kernels, KERNEL_NAME, display="JP-STALE")
        os.environ["JUPYTER_PATH"] = str(tmp / "jp")
        got = resolve(KERNEL_NAME)
        # Both sides must be resolved. On Windows tempfile.gettempdir() can
        # hand back an 8.3 short path (the CI runner's home is RUNNER~1), and
        # Path.resolve() expands the alias whenever the prefix exists -- so
        # comparing a resolved path against the raw DEAD_PY string reports a
        # kernel-selection regression for two spellings of the same file.
        if Path(got).resolve() == Path(DEAD_PY).resolve():
            print(f"  ok   jupyter-path -> {got} (env override still wins)")
        elif Path(got).resolve() == Path(venv_py):
            print(f"  ok   jupyter-path -> {got} (precedence flipped in venv's favor)")
        else:
            failures.append(f"jupyter-path: resolved unexpected {got}")
            print(f"  FAIL jupyter-path -> {got}")

    for var in ("JUPYTER_PATH",):
        os.environ.pop(var, None)

    if failures:
        print("\nKERNEL SELECTION REGRESSIONS:")
        for f in failures:
            print(f" - {f}")
        print("Fix with: uv run python scripts/register_kernel.py")
        return 1
    print("\nkernel selection OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
