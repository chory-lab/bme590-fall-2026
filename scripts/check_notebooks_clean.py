"""Assert the committed workshops carry no execution state.

    uv run python scripts/check_notebooks_clean.py [--fix]

Run in CI. The property it protects: `git pull` must always be a clean
fast-forward for every student. Notebooks are JSON, so a conflict inside one
usually produces a file that will not open at all -- and outputs plus execution
counts are exactly the fields that change on every run, which is what turns a
one-line fix into a conflict for anyone who has the file open.

Students' own work is unaffected either way: they work on copies in
`assignments/`, which is gitignored.

`--fix` strips the state instead of complaining, which is the right move right
before committing a workshop you ran while editing it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSHOPS = ROOT / "workshops"

# What every workshop must claim, so VS Code binds the class kernel on open
# without asking. The name is the match key; the version is what stops a
# notebook executed under some other interpreter from advertising it.
KERNEL_NAME = "bme590"
DISPLAY_NAME = "BME 590 (lab automation)"
CLASS_PYTHON = (ROOT / ".python-version").read_text(encoding="utf-8").strip()


def metadata_offenders(notebook: dict) -> list[str]:
    """Kernel metadata that would stop a notebook binding to the class kernel."""
    found = []
    metadata = notebook.get("metadata", {})
    kernelspec = metadata.get("kernelspec", {})
    if kernelspec.get("name") != KERNEL_NAME:
        found.append(f"kernelspec.name={kernelspec.get('name')!r}, expected {KERNEL_NAME!r}")
    if kernelspec.get("display_name") != DISPLAY_NAME:
        found.append(f"kernelspec.display_name={kernelspec.get('display_name')!r}")
    version = metadata.get("language_info", {}).get("version")
    # Compare the minor series only: the patch level tracks whoever ran it last,
    # and nothing matches on it.
    if version and ".".join(str(version).split(".")[:2]) != CLASS_PYTHON:
        found.append(f"language_info.version={version!r}, expected {CLASS_PYTHON}.x")
    return found


def normalize_metadata(notebook: dict) -> None:
    metadata = notebook.setdefault("metadata", {})
    metadata["kernelspec"] = {
        "display_name": DISPLAY_NAME,
        "language": "python",
        "name": KERNEL_NAME,
    }
    language_info = metadata.setdefault("language_info", {})
    language_info["name"] = "python"
    language_info["version"] = CLASS_PYTHON


def offenders(notebook: dict) -> list[str]:
    found = metadata_offenders(notebook)
    for index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        if cell.get("outputs"):
            found.append(f"cell {index}: {len(cell['outputs'])} output(s)")
        if cell.get("execution_count") is not None:
            found.append(f"cell {index}: execution_count={cell['execution_count']}")
    return found


def strip(notebook: dict) -> None:
    normalize_metadata(notebook)
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="strip outputs and execution counts in place")
    args = parser.parse_args(argv)

    failures = 0
    for path in sorted(WORKSHOPS.glob("*.ipynb")):
        notebook = json.loads(path.read_text(encoding="utf-8"))
        problems = offenders(notebook)
        if not problems:
            continue
        if args.fix:
            strip(notebook)
            # indent=1 and a trailing newline: what Jupyter itself writes, so
            # --fix does not reformat the whole file into a large diff.
            with path.open("w", encoding="utf-8", newline="\n") as fh:
                json.dump(notebook, fh, indent=1, ensure_ascii=False)
                fh.write("\n")
            print(f"fixed {path.relative_to(ROOT)} ({len(problems)} field(s))")
        else:
            failures += 1
            print(f"NOT CLEAN: {path.relative_to(ROOT)}")
            for problem in problems[:5]:
                print(f"    {problem}")
            if len(problems) > 5:
                print(f"    ... and {len(problems) - 5} more")

    if failures:
        print(
            f"\n{failures} workshop(s) carry execution state or the wrong kernel metadata. Run:\n"
            "    uv run python scripts/check_notebooks_clean.py --fix\n"
            "and commit the result, so that every student's `git pull` stays a clean fast-forward."
        )
        return 1
    print(
        f"all {len(list(WORKSHOPS.glob('*.ipynb')))} workshops are free of outputs and execution "
        f"counts, and name the {KERNEL_NAME} kernel on python {CLASS_PYTHON}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
