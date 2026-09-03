"""Only one visualizer session may be live at a time.

A notebook calls ``visualize_deck()`` more than once -- workshop 00 does it
twice by design, and a student does it again after every mistake. PLR's file
server does not move off port 1337 when that port is already taken, so a second
session used to leave the browser reading the *first* session's page: the page
kept advertising ws 2121 while the notebook recorded ws 2122, and
``rec.start()`` then waited out its full 60s timeout for a connection that
could not arrive. These tests pin the teardown that prevents it.
"""

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


def served_ws_port(lh) -> str:
    """The websocket port the page a student opens tells the browser to use."""
    url = f"http://{lh.vis.host}:{lh.vis.fs_port}/"
    html = urllib.request.urlopen(url).read().decode("utf-8", "replace")
    marker = 'id="ws_port" value="'
    start = html.index(marker) + len(marker)
    return html[start:html.index('"', start)]


async def test_the_served_page_points_at_the_current_session():
    """The regression: page and recorder must name the same websocket."""
    await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(), open_browser=False)
    second = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(), open_browser=False)
    assert served_ws_port(second) == str(second.vis.ws_port)


async def test_a_new_session_replaces_the_old_one():
    first = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(), open_browser=False)
    second = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(), open_browser=False)
    assert first is not second
    assert visualizer_ext._active is second


async def test_close_visualizer_is_idempotent():
    """Students run cells twice; a second close must not raise."""
    await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(), open_browser=False)
    await close_visualizer()
    await close_visualizer()
    assert visualizer_ext._active is None


async def test_close_survives_a_session_that_cannot_be_stopped():
    """A half-dead session must not block the next setup."""
    lh = await visualize_deck(STARLetDeck(), LiquidHandlerChatterboxBackend(), open_browser=False)

    async def boom():
        raise RuntimeError("socket already gone")

    lh.vis.stop = boom
    await close_visualizer()
    assert visualizer_ext._active is None
