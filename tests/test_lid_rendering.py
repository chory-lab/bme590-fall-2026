"""Lids added to a plate already on the deck show up immediately.

The stock page caches each plate's Konva group as a bitmap once it goes idle.
A lid assigned later is drawn into that group, but the page only re-caches a
group that is not cached yet -- so the stale bitmap without the lid keeps being
painted until the plate itself is redrawn (moved). Workshop 03's exercise 2.D
adds lids and then moves the plates, so students saw the lids "appear" only on
the move. These tests run the stock page in Chromium against a real visualizer
and compare rendered pixels, which is the only place the bug is visible: the
resource tree and the Konva node tree were correct all along.

Marked ``browser`` like the rest of the Chromium layer; the CDN for konva must
be reachable.
"""

import asyncio

import pytest

from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
from pylabrobot.resources import (
    PLT_CAR_L5AC_A00,
    STARDeck,
    cor_96_wellplate_360uL_Fb,
    cor_96_wellplate_360uL_Fb_lid,
)

from bme590.visualizer_ext import close_visualizer, visualize_deck

pytestmark = pytest.mark.browser


def exercise_2_deck():
    """Workshop 03's make_deck(): one carrier of five plates, one empty."""
    deck = STARDeck()
    carrier_0 = PLT_CAR_L5AC_A00("plate_carrier_0")
    carrier_1 = PLT_CAR_L5AC_A00("plate_carrier_1")
    for i in range(5):
        carrier_0[i] = cor_96_wellplate_360uL_Fb(name=f"plate_{i}")
    deck.assign_child_resource(carrier_0, rails=7)
    deck.assign_child_resource(carrier_1, rails=14)
    return deck


@pytest.fixture
async def _clean_session():
    await close_visualizer()
    yield
    await close_visualizer()


async def _open(page, deck):
    lh = await visualize_deck(deck, LiquidHandlerChatterboxBackend(), open_browser=False)
    await page.goto(f"http://{lh.vis.host}:{lh.vis.fs_port}/")
    for _ in range(300):
        if lh.vis.has_connection():
            break
        await asyncio.sleep(0.1)
    assert lh.vis.has_connection(), "the page did not register with the visualizer"
    # Wait until plate_0 exists on the page and has gone idle (cached).
    await page.wait_for_function(
        "() => typeof resources !== 'undefined' && resources['plate_0']"
        " && resources['plate_0'].group && resources['plate_0'].group.isCached()",
        timeout=30_000,
    )
    return lh


async def _pixels(page) -> str:
    # Let any pending message, redraw and the 250ms idle re-cache all land.
    await asyncio.sleep(1.0)
    return await page.evaluate("() => resourceLayer.toDataURL({ pixelRatio: 1 })")


async def test_lid_on_a_cached_plate_renders_without_moving_it(page, _clean_session):
    deck = exercise_2_deck()
    await _open(page, deck)
    before = await _pixels(page)

    plate = deck.get_resource("plate_0")
    plate.assign_child_resource(cor_96_wellplate_360uL_Fb_lid(name="plate_0_lid"))

    after = await _pixels(page)
    assert after != before, "the lid was assigned but the plate's stale bitmap is still drawn"


async def test_removing_a_lid_from_a_cached_plate_renders(page, _clean_session):
    deck = exercise_2_deck()
    plate = deck.get_resource("plate_0")
    lid = cor_96_wellplate_360uL_Fb_lid(name="plate_0_lid")
    plate.assign_child_resource(lid)
    await _open(page, deck)
    with_lid = await _pixels(page)

    plate.unassign_child_resource(lid)

    without_lid = await _pixels(page)
    assert without_lid != with_lid, "the lid was removed but the plate's stale bitmap is still drawn"
