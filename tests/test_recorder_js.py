"""The browser half of visualizer_ext, run in a real Chromium.

``_RECORDER_JS`` ships as a string that is spliced into the visualizer page; it
is unreachable from Python, so nothing in the other two test files touches a
single line of it. These tests run the shipped string itself -- imported from
the module, never copied -- against a harness page that stubs only what it
wraps.

The stock ``index.html`` is deliberately not used for the recorder tests: it
pulls konva from unpkg and jszip/html2canvas from cdnjs, and ``vis.js`` blocks
on a live websocket. The declutter tests at the bottom do load the genuine page,
because the elements they check are static markup, with the CDNs aborted.
"""

import pytest

from bme590.visualizer_ext import _DECLUTTER_CSS
from conftest import CDN_HOSTS

pytestmark = pytest.mark.browser


async def calls(page, fn=None):
    """The stub calls recorded so far, optionally filtered by function name."""
    recorded = await page.evaluate("window.__calls")
    return [c for c in recorded if fn is None or c["fn"] == fn]


async def lexical(page, name):
    """Read a global `let` binding.

    ``page.evaluate`` compiles its argument into a function, and a function
    body cannot see the global declarative record -- a top-level ``let`` reads
    back as "is not defined" there however plainly it exists. A real injected
    <script> shares that record, so it can.
    """
    await page.add_script_tag(content=f"window.__lex = String({name});")
    return await page.evaluate("window.__lex")


async def dispatch(page, event, data=None):
    """Fire an event at the wrapped dispatcher, as the websocket would."""
    return await page.evaluate(
        "([event, data]) => window.processCentralEvent(event, data)", [event, data]
    )


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


async def test_the_script_installs_over_the_page_dispatcher(harness):
    page = await harness()
    assert await page.evaluate("window.__classRecorderInstalled") is True


async def test_install_retries_until_the_page_globals_exist(harness):
    """vis.js may not have run yet; the script polls rather than giving up."""
    page = await harness(stub_globals=False)
    assert await page.evaluate("window.__classRecorderInstalled") is None

    await page.evaluate(
        """() => {
            window.__calls = [];
            window.renderedGifBlob = null;
            window.processCentralEvent = function (event, data) {
              window.__calls.push({ fn: "processCentralEvent", event: event, data: data });
            };
            window.startRecording = function () { window.__calls.push({ fn: "startRecording" }); };
            window.stopRecording = function () { window.__calls.push({ fn: "stopRecording" }); };
        }"""
    )
    # The retry is a 200ms setTimeout, so this resolves on its next tick.
    await page.wait_for_function("window.__classRecorderInstalled === true")


# ---------------------------------------------------------------------------
# class_start_gif
# ---------------------------------------------------------------------------


async def test_start_calls_the_page_recorder(harness):
    page = await harness()
    await dispatch(page, "class_start_gif", {"frame_interval": 24})
    assert [c["fn"] for c in await calls(page)] == ["startRecording"]


async def test_start_does_not_fall_through_to_the_stock_dispatcher(harness):
    """vis.js would answer 'Unknown event' -- the wrapper must absorb it."""
    page = await harness()
    await dispatch(page, "class_start_gif", {"frame_interval": 24})
    assert await calls(page, "processCentralEvent") == []


async def test_start_clears_a_stale_blob_before_recording(harness):
    """Otherwise the previous recording is what downloads at the next stop."""
    page = await harness()
    await page.evaluate("window.renderedGifBlob = 'stale'")
    await dispatch(page, "class_start_gif", {"frame_interval": 24})
    assert (await calls(page, "startRecording"))[0]["blobAtCall"] is None


@pytest.mark.parametrize(
    "sent, expected",
    [
        (24, 24),
        (1, 1),
        (96, 96),
        (0, 1),  # clamped up to the minimum
        (-5, 1),
        (97, 96),  # clamped down to the maximum
        (1000, 96),
        (24.6, 25),  # rounded, not truncated
        (24.4, 24),
        (0.2, 1),  # rounds to 0, then clamps
    ],
)
async def test_frame_interval_is_clamped_and_rounded(harness, sent, expected):
    page = await harness()
    await dispatch(page, "class_start_gif", {"frame_interval": sent})
    assert await lexical(page, "frameInterval") == str(expected)


async def test_the_interval_reaches_the_binding_the_capture_loop_reads(harness):
    """Regression: setting only ``window.frameInterval`` is invisible to lib.js.

    lib.js reads its own top-level ``let frameInterval`` when it paces capture.
    A window property of the same name is a different variable, so a recorder
    that set only that would leave the slider reading 40 while frames were
    still captured at the stock 8 -- with every other test here green.
    """
    page = await harness()
    assert await lexical(page, "frameInterval") == "8"

    await dispatch(page, "class_start_gif", {"frame_interval": 40})

    assert await lexical(page, "frameInterval") == "40"
    assert await page.evaluate("window.frameInterval") == 40


async def test_install_waits_for_the_stop_recorder_too(harness):
    """All three wrapped globals must exist, not just two.

    lib.js defines startRecording before stopRecording. Installing on the
    first alone leaves a window where class_stop_gif calls undefined.
    """
    page = await harness(stub_globals=False)
    await page.evaluate(
        """() => {
            window.__calls = [];
            window.processCentralEvent = function () {};
            window.startRecording = function () {};
        }"""
    )
    await page.wait_for_timeout(400)  # two retry ticks
    assert await page.evaluate("window.__classRecorderInstalled") is None

    await page.evaluate("window.stopRecording = function () {}")
    await page.wait_for_function("window.__classRecorderInstalled === true")


@pytest.mark.parametrize("sent, expected", [(24, 24), (200, 96), (0, 1), (7.5, 8)])
async def test_the_slider_and_its_label_follow_the_frame_interval(harness, sent, expected):
    """The page's own controls have to agree with what was set for them."""
    page = await harness()
    await dispatch(page, "class_start_gif", {"frame_interval": sent})
    assert await page.input_value("#gif-frame-rate") == str(expected)
    assert await page.text_content("#current-value") == f"Frame Interval: {expected}"


@pytest.mark.parametrize("data", [None, {}, {"frame_interval": None}, {"frame_interval": "24"}])
async def test_a_missing_or_non_numeric_interval_leaves_the_controls_alone(harness, data):
    page = await harness()
    await dispatch(page, "class_start_gif", data)
    assert await page.input_value("#gif-frame-rate") == "24"
    assert await page.text_content("#current-value") == "Frame Interval: 24"
    assert [c["fn"] for c in await calls(page)] == ["startRecording"]


# ---------------------------------------------------------------------------
# class_stop_gif
# ---------------------------------------------------------------------------


async def test_stop_calls_the_page_recorder_and_records_the_name(harness):
    page = await harness()
    await dispatch(page, "class_stop_gif", {"filename": "my-run"})
    assert [c["fn"] for c in await calls(page)] == ["stopRecording"]
    assert await page.evaluate("window._classGifName") == "my-run"


async def test_stop_clears_a_stale_blob_before_polling(harness):
    """A blob left over from a previous recording would download immediately."""
    page = await harness()
    await page.evaluate("window.renderedGifBlob = 'stale'")
    await dispatch(page, "class_stop_gif", {"filename": "my-run"})
    assert (await calls(page, "stopRecording"))[0]["blobAtCall"] is None


@pytest.mark.parametrize("data", [None, {}, {"filename": None}, {"filename": ""}])
async def test_stop_falls_back_to_the_default_name(harness, data):
    page = await harness()
    await dispatch(page, "class_stop_gif", data)
    assert await page.evaluate("window._classGifName") == "plr-protocol"


# ---------------------------------------------------------------------------
# The download
# ---------------------------------------------------------------------------


async def download_after_stop(page, data, blob_delay_ms=0):
    """Stop a recording, then hand the page a blob and catch the download."""
    async with page.expect_download() as caught:
        await dispatch(page, "class_stop_gif", data)
        await page.evaluate(
            """(delay) => setTimeout(function () {
                 window.renderedGifBlob = new Blob(["GIF89a"], { type: "image/gif" });
               }, delay)""",
            blob_delay_ms,
        )
    return await caught.value


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("my-run", "my-run.gif"),  # suffix appended
        ("my-run.gif", "my-run.gif"),  # not doubled
        ("plate transfer", "plate transfer.gif"),
        (None, "plr-protocol.gif"),  # default name, still suffixed
    ],
)
async def test_the_download_filename_gets_exactly_one_gif_suffix(harness, filename, expected):
    page = await harness()
    download = await download_after_stop(page, {"filename": filename})
    assert download.suggested_filename == expected


async def test_the_poller_waits_for_a_blob_that_arrives_late(harness):
    """Rendering takes time; the download fires when it finishes, not before."""
    page = await harness()
    download = await download_after_stop(page, {"filename": "late"}, blob_delay_ms=600)
    assert download.suggested_filename == "late.gif"


async def test_the_blob_is_released_after_downloading(harness):
    """A leftover blob would make the next stop download the wrong recording."""
    page = await harness()
    await download_after_stop(page, {"filename": "first"})
    await page.wait_for_function("window.renderedGifBlob === null")


async def test_the_poller_gives_up_after_1200_attempts(harness):
    """Bounded so a failed render leaves no timer running forever.

    setTimeout is replaced with an immediate call so the ~2 minutes of real
    polling collapse into one synchronous unwind.
    """
    page = await harness()
    await page.evaluate(
        """() => {
            window.__ticks = 0;
            window.setTimeout = function (fn) { window.__ticks++; fn(); };
        }"""
    )
    await dispatch(page, "class_stop_gif", {"filename": "never-renders"})
    # Attempts 0 through 1200 each schedule one more; 1201 is the one that quits.
    assert await page.evaluate("window.__ticks") == 1201


# ---------------------------------------------------------------------------
# Fall-through
# ---------------------------------------------------------------------------


async def test_unknown_events_reach_the_original_dispatcher(harness):
    """The wrapper must not swallow the stock protocol."""
    page = await harness()
    result = await dispatch(page, "resource_assigned", {"resource": "plate"})
    assert result == "original-result"
    assert await calls(page, "processCentralEvent") == [
        {"fn": "processCentralEvent", "event": "resource_assigned", "data": {"resource": "plate"}}
    ]
    assert await calls(page, "startRecording") == []
    assert await calls(page, "stopRecording") == []


async def test_the_stock_protocol_still_works_between_recordings(harness):
    page = await harness()
    await dispatch(page, "class_start_gif", {"frame_interval": 10})
    await dispatch(page, "resource_assigned", {"resource": "plate"})
    await dispatch(page, "class_stop_gif", {"filename": "run"})
    assert [c["fn"] for c in await calls(page)] == [
        "startRecording",
        "processCentralEvent",
        "stopRecording",
    ]


# ---------------------------------------------------------------------------
# Declutter, against the genuine served page
# ---------------------------------------------------------------------------
#
# test_page_injection.py proves the CSS text is in the response. These prove a
# browser actually applies it: that the kwarg and each query alias add the body
# class, and that the elements really compute to display:none.

# The CSS hides bare `aside`, and the stock page has three of them --
# #toolbar-left, #sidepanel and the right-hand #toolbar. Naming each one keeps
# a future upstream aside from being silently left visible.
DECLUTTERED = (
    "aside#toolbar-left",
    "aside#toolbar",
    "#sidepanel",
    "#sidepanel-resize-handle",
    "#home-button",
)


async def load_visualizer(page, url):
    """Open the real visualizer page offline.

    The three CDNs are aborted; the declutter script and CSS are inline and the
    elements they hide are static markup, so none of it is needed here.
    """
    for host in CDN_HOSTS:
        await page.route(f"**://{host}/**", lambda route: route.abort())
    await page.goto(url, wait_until="domcontentloaded")


async def displays(page):
    return {
        selector: await page.eval_on_selector(selector, "el => getComputedStyle(el).display")
        for selector in DECLUTTERED
    }


async def main_box(page):
    """The <main> rule is the half that actually fills the frame."""
    return await page.eval_on_selector(
        "main",
        """el => {
             const s = getComputedStyle(el);
             return { position: s.position, w: el.clientWidth, h: el.clientHeight };
           }""",
    )


async def test_the_declutter_kwarg_hides_the_chrome_in_a_browser(serve, page):
    _, url = serve(declutter=True)
    await load_visualizer(page, url)

    assert await page.evaluate("document.body.classList.contains('class-minimal')") is True
    assert await displays(page) == dict.fromkeys(DECLUTTERED, "none")


async def test_declutter_makes_the_deck_fill_the_viewport(serve, page):
    """Hiding the chrome is only half of it: <main> is pinned to the viewport
    so the recording frames the deck and nothing else."""
    _, url = serve(declutter=True)
    await load_visualizer(page, url)

    box = await main_box(page)
    viewport = await page.evaluate("({w: innerWidth, h: innerHeight})")
    assert box["position"] == "fixed"
    assert (box["w"], box["h"]) == (viewport["w"], viewport["h"])


async def test_main_is_not_pinned_without_declutter(serve, page):
    _, url = serve()
    await load_visualizer(page, url)
    assert (await main_box(page))["position"] != "fixed"


@pytest.mark.parametrize("query", ["?minimal=1", "?clean=1", "?deck-only=1", "?minimal"])
async def test_the_query_aliases_hide_the_chrome_in_a_browser(serve, page, query):
    _, url = serve()
    await load_visualizer(page, f"{url}/{query}")

    assert await page.evaluate("document.body.classList.contains('class-minimal')") is True
    assert await displays(page) == dict.fromkeys(DECLUTTERED, "none")


async def test_the_page_is_untouched_by_default_in_a_browser(serve, page):
    _, url = serve()
    await load_visualizer(page, url)

    assert await page.evaluate("document.body.classList.contains('class-minimal')") is False
    assert _DECLUTTER_CSS not in await page.content()
    assert "none" not in (await displays(page)).values()
