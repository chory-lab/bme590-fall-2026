"""Build reference solution notebooks from the workshop stubs.

    uv run python scripts/make_solutions.py            # all
    uv run python scripts/make_solutions.py 01         # one

A solution notebook is the workshop notebook with each `... # YOUR CODE HERE`
cell replaced by a worked answer. The answers live in `solutions/sources/NN_*.py`
as `CELLS = {marker: source}`; the notebooks under `solutions/` are generated
from them and committed, so `scripts/grade.py solutions/` runs without a build
step.

Why generate rather than hand-maintain the notebooks: a solution has to stay the
*same notebook* the student gets -- same prose, same scaffolding cells, same
cell order -- or it stops proving that the rubric passes real submissions. The
generator copies the stub and touches only the answer cells, so a change to the
workshop text propagates on the next run and cannot silently diverge.

A marker is matched against the start of a cell's source, after stripping, so it
is normally the cell's first line (`# Exercise 1`) or the first line of the
function being implemented. Every marker must match exactly one cell; a marker
that matches none (or several) is an error, because that means the workshop moved
under the solution and the answer would have been silently dropped.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSHOPS = ROOT / "workshops"
SOLUTIONS = ROOT / "solutions"
SOURCES = SOLUTIONS / "sources"


def load_cells(source_file: Path) -> dict[str, str]:
    spec = importlib.util.spec_from_file_location(source_file.stem, source_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CELLS


def build(notebook: Path, source_file: Path, out: Path) -> int:
    cells = load_cells(source_file)
    nb = json.loads(notebook.read_text(encoding="utf-8"))

    for marker, replacement in cells.items():
        hits = [
            cell
            for cell in nb["cells"]
            if cell["cell_type"] == "code" and "".join(cell["source"]).strip().startswith(marker)
        ]
        if len(hits) != 1:
            raise SystemExit(
                f"{notebook.name}: marker {marker!r} matched {len(hits)} cells, expected 1 "
                "-- the workshop changed under the solution"
            )
        hits[0]["source"] = replacement.strip("\n").splitlines(keepends=True)
        hits[0]["outputs"] = []
        hits[0]["execution_count"] = None

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out.relative_to(ROOT)}  ({len(cells)} cells answered)")
    return len(cells)


def main(argv: list[str]) -> int:
    wanted = argv[0] if argv else None
    sources = sorted(SOURCES.glob("*.py"))
    if wanted:
        sources = [s for s in sources if s.stem.startswith(wanted)]
    if not sources:
        print(f"no solution sources in {SOURCES}" + (f" matching {wanted!r}" if wanted else ""))
        return 2
    for source_file in sources:
        notebook = WORKSHOPS / f"{source_file.stem}.ipynb"
        if not notebook.exists():
            raise SystemExit(f"no workshop notebook for {source_file.name}")
        build(notebook, source_file, SOLUTIONS / notebook.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
