"""Only one visualizer session may be live at a time.

A notebook calls ``visualize_deck()`` more than once -- workshop 00 does it
twice by design, workshop 01 ten times, and a student does it again after every
mistake. Each call used to orphan the previous session's websocket server:
``Visualizer.stop()`` ends the serve loop only ``if self.has_connection()``, so
a session whose tab the student had closed stayed bound and stayed live. The
student's first tab went on rendering the first deck while the notebook drove
the second, and a recording started against that tab waited out its full 60s.

This is a single-notebook failure -- it needs no second kernel -- and these
tests pin the teardown that prevents it.
"""

import socket
import urllib.request

import pytest

from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
from pylabrobot.resources.hamilton import STARLetDeck

from bme590 import visualizer_ext
from bme590.visualizer_ext import close_visualizer, visualize_deck


@pytest.fixture(autouse=True)
async def _no_session_leaks():
    """Every test here starts and ends with nothing bound."""
    await close_visualizer()
    yield
    await close_visualizer()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def port_is_bound(port: int) -> bool:
    """True while something still holds the port.

    A released websocket server is the whole point of the teardown, and the
    only way to observe it from outside the visualizer is to try to take the
    port back.
    """
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def served_ws_port(lh) -> str:
    """The websocket port the page a student opens tells the browser to use."""
    url = f"http://{lh.vis.host}:{lh.vis.fs_port}/"
    html = urllib.request.urlopen(url).read().decode("utf-8", "replace")
    marker = 'id="ws_port" value="'
    start = html.index(marker) + len(marker)
    return html[start:html.index('"', start)]


async def test_the_served_page_points_at_the_current_session():
    """The regression: page and recorder must name the same websocket.

    Both sessions are pinned to the same pair of ports, which is what the
    default 1337/2121 amount to in a notebook -- but chosen free here, so the
    test reproduces the collision on ports it owns. Reading the real defaults
    would make this fail whenever anything else on the machine holds them, and
    a live kernel from another notebook does exactly that.
    """
    ports = {"fs_port": free_port(), "ws_port": free_port()}
    await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(),
                         open_browser=False, **ports)
    second = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(),
                                  open_browser=False, **ports)
    assert served_ws_port(second) == str(second.vis.ws_port)


async def test_a_new_session_replaces_the_old_one():
    ports = {"fs_port": free_port(), "ws_port": free_port()}
    first = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(),
                                 open_browser=False, **ports)
    second = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(),
                                  open_browser=False, **ports)
    assert first is not second
    assert visualizer_ext._active is second


async def test_close_visualizer_is_idempotent():
    """Students run cells twice; a second close must not raise."""
    await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(), open_browser=False,
                         fs_port=free_port(), ws_port=free_port())
    await close_visualizer()
    await close_visualizer()
    assert visualizer_ext._active is None


async def test_close_survives_a_session_that_cannot_be_stopped():
    """A half-dead session must not block the next setup."""
    lh = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(), open_browser=False,
                              fs_port=free_port(), ws_port=free_port())

    async def boom():
        raise RuntimeError("socket already gone")

    lh.vis.stop = boom
    await close_visualizer()
    assert visualizer_ext._active is None


async def test_repeated_sessions_do_not_leak_websocket_servers():
    """The classroom regression, in the shape a workshop actually runs.

    No tab is ever attached here, which is the case `Visualizer.stop()` gets
    wrong and the normal one for a student who closed the dead tab. Before
    `_release_websocket`, four calls climbed ws 2121->2124 and left all four
    bound; the live 2121 is what kept the student's first tab showing a deck
    the notebook had stopped driving.
    """
    ports = {"fs_port": free_port(), "ws_port": free_port()}
    used = []
    for _ in range(4):
        lh = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(),
                                  open_browser=False, **ports)
        assert not lh.vis.has_connection(), "test must exercise the no-tab path"
        used.append(lh.vis.ws_port)

    # Every call reuses the one port, because each close actually released it.
    assert used == [ports["ws_port"]] * 4, f"websocket port drifted: {used}"

    await close_visualizer()
    for port in set(used):
        assert not port_is_bound(port), f"ws {port} still bound after close"


async def test_close_releases_the_websocket_with_no_tab_attached():
    """`stop()` alone leaves the serve loop running; teardown must not."""
    ws = free_port()
    lh = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(),
                              open_browser=False, fs_port=free_port(), ws_port=ws)
    assert port_is_bound(ws)
    await close_visualizer()
    assert not port_is_bound(ws)


async def test_close_stops_a_handler_only_once():
    """`LiquidHandler.stop()` raises on an already-stopped handler.

    Teardown used to call it unconditionally and swallow the RuntimeError,
    which is the habit this module exists to stop teaching. Asserting no
    exception escapes is not enough -- the old code passed that too -- so this
    checks the handler is actually stopped and not stopped twice.
    """
    lh = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(),
                              open_browser=False, fs_port=free_port(), ws_port=free_port())
    calls = []
    real_stop = lh.stop

    async def counting_stop():
        calls.append(1)
        await real_stop()

    lh.stop = counting_stop
    await close_visualizer()
    await close_visualizer()
    assert calls == [1], f"handler stopped {len(calls)} times"
    assert not lh.setup_finished
