"""Stepping through a workshop cell by cell must never leave two servers up.

`test_notebook_lifecycle.py` reads the notebooks as text: it can see that a
`close_visualizer()` cell exists, not that running the notebook actually frees
the ports. `test_session_lifecycle.py` runs the real teardown, but it calls
`visualize_deck()` directly -- it never touches a notebook. The gap between them
is the failure students actually hit: a workshop opens eight sessions in
sequence, and if any one of them fails to release its websocket, PyLabRobot's
collision loop moves the next session up a port while the page the student is
looking at keeps rendering the old deck.

CI could not close that gap, because `check_workshops.py` replaces the
`from bme590.visualizer_ext import ...` line with a shim whose `visualize_deck`
sets `lh.vis = None` and starts no server at all. It proves the notebooks *run*;
it cannot prove anything about sessions.

So this walks each workshop's code cells in order, in one namespace, against the
real module, and after every cell asserts that at most one session is live and
that it is sitting on the ports it was given.

That last part is the whole signal. PyLabRobot increments its ports on a
collision, so a session whose predecessor never released the websocket records a
*different* port number on itself -- which is direct, attributable evidence of
the leak. An earlier version of this test instead scanned for anything holding a
port in a range above the pinned pair; nothing owns those numbers, the OS hands
them out as ephemeral ports to any process (this suite's own free_port() probes
included), and the check produced false positives on a different notebook each
run.

What is pinned, and why it does not weaken the test:

  * **Ports.** Both are fixed to one free pair, which is what the defaults
    1337/2121 amount to in a notebook -- but chosen free, so the test cannot
    fail because something else on the machine holds the defaults. Reading the
    real defaults would break whenever a developer has a live kernel. Pinning is
    also what makes drift *observable*: a session that failed to release its
    port forces the next one upwards, and the scan below sees it.
  * **`open_browser=False`.** The default pops a real window on the machine
    running the suite.

Nothing else is substituted: `_active`, `close_visualizer()` and
`_release_websocket()` are the real ones, and they are the subject.
"""

import ast
import json
import os
import pathlib
import socket
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / ".github" / "scripts"))

from check_workshops import SKIP_MARKERS, is_stub  # noqa: E402

from bme590 import visualizer_ext  # noqa: E402

# Recorder cells are skipped. A recording with no tab attached has no frames to
# render and waits out its 60s watchdog, which would make this test slow without
# telling it anything: the recorder has its own tests, including a Playwright
# layer, and what is under test here is the session underneath it.
# Calls, not the word: the course-standard setup cell mentions `gif_recording`
# in a comment and defines `make_liquid_handling_deck`, so matching the bare
# name skipped the cell every later cell depends on.
RECORDER_MARKERS = ("gif_recorder(", "gif_recording(", "rec.start()", "rec.stop()")



def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def port_is_bound(port: int) -> bool:
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def workshops():
    return sorted((REPO / "workshops").glob("*.ipynb"))


def code_cells(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [
        "".join(cell.get("source", []))
        for cell in doc.get("cells", [])
        if cell.get("cell_type") == "code"
    ]


def runnable(src):
    """Cells CI already declines to run, plus the recorder cells."""
    if any(m in src for m in SKIP_MARKERS) or is_stub(src):
        return False
    body = "\n".join(line.split("#", 1)[0] for line in src.split("\n"))
    return not any(m in body for m in RECORDER_MARKERS)


async def run_cell(src, namespace):
    """Execute one notebook cell, top-level `await` included.

    `PyCF_ALLOW_TOP_LEVEL_AWAIT` makes the compiled module return a coroutine
    when it needs awaiting -- the same mechanism IPython uses, which is why the
    notebooks can write `await lh.setup()` at the top level.
    """
    code = compile(src, "<cell>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    outcome = eval(code, namespace)  # noqa: S307 - the notebook *is* the input
    if outcome is not None:
        await outcome


ALL = workshops()


def ids(paths):
    return [p.name for p in paths]


def test_there_are_workshops_to_walk():
    """A glob that matched nothing would make the walk below vacuously pass."""
    assert ALL, f"no notebooks found under {REPO / 'workshops'}"


@pytest.mark.parametrize("path", ALL, ids=ids(ALL))
async def test_walking_a_workshop_leaves_one_session_at_a_time(path):
    cells = [c for c in code_cells(path) if runnable(c)]
    if not any("visualize_deck(" in c for c in cells):
        # Workshop 05 lands here: it opens three sessions, but all three are
        # inside exercise stubs, so there is no runnable session to walk. Its
        # teardown ordering is still checked by the test below.
        pytest.skip("no runnable visualizer cell in this notebook")

    fs_port, ws_port = free_port(), free_port()
    real_visualize_deck = visualizer_ext.visualize_deck

    async def pinned_visualize_deck(deck, backend, **kwargs):
        kwargs.setdefault("open_browser", False)
        kwargs.setdefault("fs_port", fs_port)
        kwargs.setdefault("ws_port", ws_port)
        return await real_visualize_deck(deck, backend, **kwargs)

    def drifted(live):
        """Where this session actually landed, when that is not where we put it.

        Read off the session itself rather than probed from outside, so the
        answer cannot be perturbed by an unrelated process taking a port.
        """
        vis = getattr(live, "vis", None)
        if vis is None:
            return ""
        got = (getattr(vis, "fs_port", None), getattr(vis, "ws_port", None))
        if got == (fs_port, ws_port):
            return ""
        return f"fs/ws {got[0]}/{got[1]} instead of the pinned {fs_port}/{ws_port}"

    # A notebook resolves its own imports; the walk only replaces the two names
    # that would otherwise open a browser or fight for the default ports, and
    # zeroes the demo pauses.
    namespace = {
        "__name__": "__main__",
        "visualize_deck": pinned_visualize_deck,
        "SLEEP": 0,
    }

    await visualizer_ext.close_visualizer()
    cwd = os.getcwd()
    os.chdir(path.parent)
    try:
        for index, src in enumerate(cells):
            # Left to pytest's capture: several cells print `deck.summary()`,
            # whose box-drawing characters a cp1252 Windows console cannot
            # encode.
            await run_cell(src, namespace)
            # The notebooks import these themselves, so re-pin after every cell:
            # the import cell would otherwise hand the rest of the walk the real
            # `visualize_deck` and its default ports.
            namespace["visualize_deck"] = pinned_visualize_deck
            namespace["SLEEP"] = 0

            live = visualizer_ext._active
            assert live is None or hasattr(live, "deck"), (
                f"{path.name} cell {index}: _active is not a handler ({live!r})"
            )
            moved = drifted(live)
            assert not moved, (
                f"{path.name} cell {index}: this session was pushed off the pinned "
                f"ports, so the one before it never released them -- {moved}"
            )
    finally:
        os.chdir(cwd)
        await visualizer_ext.close_visualizer()

    assert not port_is_bound(ws_port), (
        f"{path.name}: ws {ws_port} still bound after the walk"
    )
    assert not port_is_bound(fs_port), (
        f"{path.name}: fs {fs_port} still bound after the walk"
    )


@pytest.mark.parametrize("path", ALL, ids=ids(ALL))
def test_the_teardown_cell_is_the_last_thing_in_the_notebook(path):
    """`close_visualizer()` has to come after the last session it must close.

    The text check in `test_notebook_lifecycle.py` accepts a teardown cell
    anywhere; a workshop that closed its visualizer and then opened another
    would pass it while leaving a live server behind at the end.
    """
    cells = code_cells(path)
    if not any("visualize_deck(" in c for c in cells):
        pytest.skip("no visualizer in this notebook")
    last_open = max(i for i, c in enumerate(cells) if "visualize_deck(" in c)
    closes = [i for i, c in enumerate(cells) if "close_visualizer()" in c]
    assert closes, f"{path.name} never closes its last session"
    assert max(closes) > last_open, (
        f"{path.name} opens a session in cell {last_open} after its last "
        f"close_visualizer() in cell {max(closes)}"
    )
