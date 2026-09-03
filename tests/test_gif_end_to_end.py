"""Workshop 00's recording section, run for real.

Every other test in this suite stubs one side of the boundary: the Python tests
capture the transport, and the JS tests run the injected script against a
harness page. Neither can answer the question a student actually asks -- does
running these cells produce a GIF file? -- so this one runs the whole path: a
real visualizer, the stock page in a real Chromium, the notebook's own
build_deck(), and the download that comes out the other end.

Marked ``browser``: it needs Chromium and the CDNs the visualizer page loads
(konva, jszip, html2canvas), so it is deselected by ``-m 'not browser'`` along
with the rest of the browser layer.
"""

import asyncio
import json
import pathlib

import pytest

from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
from pylabrobot.resources.hamilton import STARLetDeck

from bme590.visualizer_ext import (
    close_visualizer,
    gif_recorder,
    set_step_delay,
    step,
    visualize_deck,
)

pytestmark = pytest.mark.browser

NOTEBOOK = pathlib.Path(__file__).resolve().parent.parent / "workshops/00_plr_introduction.ipynb"


def notebook_build_deck():
    """Compile the notebook's own build_deck cell, imports and all.

    Reading it out of the .ipynb rather than restating it here is the point: a
    copy would keep passing after the notebook broke.
    """
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    sources = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    imports = next(s for s in sources if s.startswith("from pylabrobot.resources import"))
    builder = next(s for s in sources if "async def build_deck" in s)
    namespace = {}
    exec(compile(imports + "\n" + builder, str(NOTEBOOK), "exec"), namespace)
    return namespace["build_deck"]


@pytest.fixture
async def _clean_session():
    await close_visualizer()
    yield
    await close_visualizer()


async def test_workshop_00_produces_a_downloadable_gif(page, _clean_session, tmp_path):
    deck = STARLetDeck()
    lh = await visualize_deck(deck, LiquidHandlerChatterboxBackend(), open_browser=False)

    # The tab a student opens, at the URL the notebook prints.
    await page.goto(f"http://{lh.vis.host}:{lh.vis.fs_port}/")
    for _ in range(300):  # 30s, the same question rec.start() asks
        if lh.vis.has_connection():
            break
        await asyncio.sleep(0.1)
    assert lh.vis.has_connection(), "the page did not register with the visualizer"

    rec = gif_recorder(lh.vis, name="lab_0_deck_setup.gif")
    set_step_delay(1.0)  # exactly what the notebook runs at
    await rec.start()
    await notebook_build_deck()(deck)
    await step(2)  # the notebook's hold on the finished deck

    async with page.expect_download(timeout=120_000) as caught:
        await rec.stop()
    download = await caught.value

    assert download.suggested_filename == "lab_0_deck_setup.gif"
    saved = tmp_path / download.suggested_filename
    await download.save_as(saved)
    data = saved.read_bytes()

    assert data[:6] in (b"GIF89a", b"GIF87a"), "not a GIF"
    # One Graphic Control Extension per frame: a still image would mean the
    # step() pauses never separated the deck changes.
    frames = data.count(b"\x21\xf9\x04")
    # Frames are photographed on a timer inside the page, and headless render
    # timing moves the count around (5-9 observed for this protocol across
    # runs), so this asserts an animation that shows the build rather than an
    # exact frame-per-change count the browser never promised.
    assert frames >= 6, f"expected the build to animate, got {frames} frame(s)"
    print(f"\n[e2e] {len(data):,} bytes, {frames} frames -> {download.suggested_filename}")
