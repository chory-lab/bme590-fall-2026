"""Grade a submitted workshop notebook against the rubric.

    uv run python scripts/grade.py assignments/01_deck_setup.ipynb
    uv run python scripts/grade.py submissions/            # a whole directory

Runs the notebook, then probes what it defined. See
plr_workshops/grading/rubric.py for what each exercise is checked against.

Why it works this way:

  * **Probe the namespace, not cell outputs.** Nearly every graded cell defines a
    function and prints nothing, so there is no output to compare -- the check
    has to call what the student defined. It also makes grading immune to cells
    being inserted, deleted or reordered, which grading by cell index is not.
  * **Run the whole notebook, not "the cells we want".** Workshop 03 builds a
    chain of subclasses across sixteen cells; cell N is meaningless without
    1..N-1 having run.
  * **allow_errors=True.** A submission that raises in cell 12 should still be
    graded on cells 1-11; otherwise the first mistake scores zero.
  * Stubs are left in place. `...` is a valid expression, so an unimplemented
    function runs and returns None, and the checks report "not attempted".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from plr_workshops.grading.rubric import RUBRIC, points_for, probe_for, score_for  # noqa: E402

MARKER = "###GRADE###"

# Cells that exist only to be copied into a `.txt` submission. Workshop 03 ends
# each exercise with one, and it re-declares every graded class -- with `...`
# bodies in an untouched copy -- and re-runs the exercise 2E protocol against a
# deck that protocol has already finished with. Executing them therefore either
# replaces the student's working classes with stubs or raises, in both cases
# grading something the student never meant to run.
TEMPLATE_MARKERS = ("Save as exercise_",)


def run_notebook(path: Path, probe: str):
    """Execute a submission with the probe appended, and return its results."""
    import nbformat
    from nbclient import NotebookClient
    from check_workshops import neutralize  # the visualiser/sleep neutraliser CI already uses

    nb = nbformat.read(str(path), as_version=4)
    for cell in nb.cells:
        if cell.cell_type == "code":
            if any(m in cell.source for m in TEMPLATE_MARKERS):
                cell.source = "pass  # .txt submission template, not run"
            else:
                cell.source = neutralize(cell.source)
    nb.cells.append(nbformat.v4.new_code_cell(probe))

    NotebookClient(
        nb,
        timeout=300,        # a runaway student loop must not hang a batch
        allow_errors=True,  # grade everything that did run
        kernel_name="python3",
        resources={"metadata": {"path": str(path.parent)}},
    ).execute()

    for output in nb.cells[-1].get("outputs", []):
        text = output.get("text", "")
        if MARKER in text:
            return json.loads(text.split(MARKER, 1)[1].strip())
    return None


def grade_one(path: Path, quiet: bool = False) -> tuple[int, int, float, int]:
    """Grade one notebook. Returns (checks passed, checks total, points, points available)."""
    probe = probe_for(path.name)
    if probe is None:
        print(f"{path.name}: no rubric (graded: {', '.join(sorted(RUBRIC))})")
        return (0, 0, 0.0, 0)

    results = run_notebook(path, probe)
    if results is None:
        print(f"{path.name}: the probe never ran -- the notebook failed before reaching it")
        return (0, 1, 0.0, points_for(path.name))

    passed = sum(1 for _, ok, _ in results if ok)
    points, available = score_for(path.name, results)
    print(f"\n{path.name}   ({points_for(path.name)} points at stake)")
    for label, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"  {mark}  {label}" + (f"\n          {detail}" if detail and not quiet else ""))
    print(f"  ----  {passed}/{len(results)} checks passed, {points}/{available} points")
    return (passed, len(results), points, available)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.splitlines()[2].strip())
        return 2
    target = Path(argv[0]).resolve()
    notebooks = sorted(target.glob("*.ipynb")) if target.is_dir() else [target]
    if not notebooks:
        print(f"no notebooks in {target}")
        return 2

    total_passed = total_checks = total_available = 0
    total_points = 0.0
    for notebook in notebooks:
        passed, checks, points, available = grade_one(notebook)
        total_passed += passed
        total_checks += checks
        total_points += points
        total_available += available
    if len(notebooks) > 1:
        print(f"\n=== {total_passed}/{total_checks} checks passed, "
              f"{round(total_points, 1)}/{total_available} points "
              f"across {len(notebooks)} notebooks ===")
    return 0 if total_passed == total_checks else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
