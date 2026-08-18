"""Regression test for the macOS venv-symlink kernel bug.

On macOS, uv's .venv/bin/python is a symlink to the interpreter uv manages, and
sys.executable resolves to that base interpreter. That used to make doctor.py
report a healthy install as "not the project environment", and ipykernel used to
write the resolved base path into the kernelspec, so notebooks launched a kernel
without the class packages.

The positive side -- doctor passes when run with the class venv python, and the
kernelspec argv[0] points at the venv -- is already enforced in CI, because the
student installer runs doctor.py as its last verify step. What was untested is
the negative side: doctor.py must still REJECT an interpreter outside the venv,
or the check could be "fixed" by making it pass always. sys._base_executable is
the interpreter this venv is based on -- on macOS exactly the resolved path the
buggy kernelspec used to point at.

Run with the class venv python, e.g. .venv/bin/python .github/scripts/check_doctor_negative.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR = ROOT / "scripts" / "doctor.py"


def main() -> int:
    base_exe = getattr(sys, "_base_executable", None)
    if not base_exe:
        print("SKIP: not running inside a virtualenv; nothing to compare against")
        return 0
    result = subprocess.run(
        [base_exe, str(DOCTOR)], capture_output=True, text=True, cwd=ROOT
    )
    output = result.stdout + result.stderr
    if result.returncode == 0:
        print(f"FAIL: doctor passed when run with the base interpreter ({base_exe})")
        print(output)
        return 1
    if "not the project environment" not in output:
        print(f"FAIL: doctor failed, but not for the reason this test guards ({base_exe}):")
        print(output)
        return 1
    print(f"OK: doctor rejects an interpreter outside the class venv ({base_exe})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
