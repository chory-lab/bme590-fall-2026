"""Every shipped notebook must close the visualizer it opens.

The helper closes the *previous* session on each `visualize_deck()` call, so a
notebook can spawn freely mid-run. What it cannot do is close the last one:
nothing follows it. That session stays bound and stays live until the kernel
dies, and its still-serving websocket is what leaves a student's tab rendering
a deck the notebook has stopped driving.

`assignments/` is deliberately not checked: it is gitignored scratch, copied
out of `workshops/` by `scripts/start_workshop.py`, so it inherits whatever
this guard enforces on the source.
"""

import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SHIPPED = ("workshops", "solutions")


def notebooks():
    for folder in SHIPPED:
        yield from sorted((REPO / folder).glob("*.ipynb"))


def code_cells(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [
        "".join(cell.get("source", []))
        for cell in doc.get("cells", [])
        if cell.get("cell_type") == "code"
    ]


def ids(paths):
    return [f"{p.parent.name}/{p.name}" for p in paths]


ALL = list(notebooks())


def test_there_are_notebooks_to_check():
    """A glob that silently matches nothing would make every test below pass."""
    assert ALL, f"no notebooks found under {SHIPPED}"


@pytest.mark.parametrize("path", ALL, ids=ids(ALL))
def test_a_notebook_that_opens_a_visualizer_closes_it(path):
    cells = code_cells(path)
    opens = [c for c in cells if "visualize_deck(" in c]
    if not opens:
        pytest.skip("no visualizer in this notebook")
    assert any("close_visualizer()" in c for c in cells), (
        f"{path.name} calls visualize_deck() {len(opens)}x but never closes the last "
        "session; add `await close_visualizer()` as the final cell"
    )


@pytest.mark.parametrize("path", ALL, ids=ids(ALL))
def test_the_close_is_imported_where_it_is_used(path):
    """A teardown cell that NameErrors is worse than none: it fails at the end."""
    cells = code_cells(path)
    if not any("close_visualizer()" in c for c in cells):
        pytest.skip("no teardown in this notebook")
    assert any(
        "close_visualizer" in c and "import" in c for c in cells
    ), f"{path.name} calls close_visualizer() without importing it"


@pytest.mark.parametrize("path", ALL, ids=ids(ALL))
def test_notebooks_do_not_build_visualizers_by_hand(path):
    """`visualize_deck()` is the only spawn that registers with the singleton.

    A bare `Visualizer(...)` is invisible to `close_visualizer()`, so it leaks
    however carefully the rest of the notebook is written.
    """
    for cell in code_cells(path):
        body = "\n".join(line.split("#", 1)[0] for line in cell.split("\n"))
        if "Visualizer(" in body and "visualize_deck" not in body:
            pytest.fail(
                f"{path.name} constructs a Visualizer directly; use visualize_deck() "
                "so the session is tracked and closed"
            )
