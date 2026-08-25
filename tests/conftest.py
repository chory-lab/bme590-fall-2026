"""Shared fixtures for the visualizer_ext test suite.

Two kinds of test live here:

  * Python-side tests build a real ``RecordingVisualizer`` but never call
    ``setup()``, so no websocket server starts. ``Visualizer.__init__`` only
    registers resource callbacks and stores ports, which makes the object
    cheap and safe to construct in-process.
  * Browser tests drive the injected JavaScript in Chromium. That code is
    unreachable from Python, so a real browser is the only place it can be
    exercised.
"""

import socket

import pytest

from pylabrobot.resources.hamilton import STARLetDeck
from pylabrobot.visualizer.visualizer import Visualizer

from bme590.visualizer_ext import RecordingVisualizer, _RECORDER_JS


def _free_port() -> int:
    """Ask the OS for an unused port.

    The visualizer's own port-collision loop increments until it finds a free
    one, which would leave the test unable to predict the URL it must fetch.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def deck():
    """A concrete deck, matching what the workshops build.

    The abstract ``Deck`` requires explicit size arguments in pylabrobot 0.2.2;
    every workshop instantiates a named deck subclass instead, so the tests use
    the one they reach for most.
    """
    return STARLetDeck()


@pytest.fixture
def make_visualizer(deck):
    """Build RecordingVisualizers that are torn down at end of test.

    ``open_browser=False`` matters: the default pops a real browser window on
    the machine running the suite.
    """
    built = []

    def _make(**kwargs):
        kwargs.setdefault("open_browser", False)
        kwargs.setdefault("fs_port", _free_port())
        kwargs.setdefault("ws_port", _free_port())
        # Pin the header name so a test never depends on how the source-file
        # autodetection reacts to being run under pytest.
        kwargs.setdefault("name", "test.ipynb")
        vis = RecordingVisualizer(resource=deck, **kwargs)
        built.append(vis)
        return vis

    yield _make

    for vis in built:
        httpd = getattr(vis, "_httpd", None)
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


@pytest.fixture
def serve(make_visualizer):
    """Start a RecordingVisualizer's file server and return its base URL.

    Only ``_run_file_server`` is called, not ``setup()``: the injection under
    test happens entirely in the HTTP handler, and skipping the websocket
    server keeps the test from needing a browser to connect.
    """

    def _serve(**kwargs):
        vis = make_visualizer(**kwargs)
        vis._run_file_server()
        return vis, f"http://{vis.host}:{vis.fs_port}"

    return _serve


class FakeConnection:
    """Stands in for a connected browser.

    ``GifRecorder`` type-checks its argument against ``Visualizer``, so the
    fake has to be a real visualizer with its transport replaced rather than a
    free-standing mock. Records every command for assertion.
    """

    def __init__(self, vis: Visualizer, connected: bool = True):
        self.vis = vis
        self.sent = []
        self.connected = connected
        vis.has_connection = lambda: self.connected  # type: ignore[method-assign]

        async def send_command(event, data=None, wait_for_response=True):
            self.sent.append((event, data or {}))
            return {"success": True}

        vis.send_command = send_command  # type: ignore[method-assign]

    @property
    def events(self):
        return [event for event, _ in self.sent]

    def data_for(self, event):
        return next(data for name, data in self.sent if name == event)


@pytest.fixture
def connected(make_visualizer):
    """A visualizer that reports a live browser and records what it is sent."""
    return FakeConnection(make_visualizer())


@pytest.fixture
def disconnected(make_visualizer):
    """A visualizer with no browser attached, for the wait/timeout paths."""
    return FakeConnection(make_visualizer(), connected=False)


# ---------------------------------------------------------------------------
# Browser fixtures
# ---------------------------------------------------------------------------

# The harness is served from a URL that is never resolved: every request for it
# is fulfilled by a Playwright route, so the browser layer needs no network and
# no local HTTP server.
HARNESS_URL = "http://recorder-harness.test/"

# The CDNs the stock index.html pulls from. Aborted in the tests that load the
# genuine page so they run offline.
CDN_HOSTS = ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com")

# Everything the injected recorder touches on the page, and nothing else: the
# four globals it wraps or calls, the lexical `frameInterval` it assigns, and
# the two elements it writes the frame interval into. Each stub records its call so a test can assert what the real
# script did, including what ``renderedGifBlob`` held at the moment of the call
# -- that is how "clears the stale blob first" is observed.
_HARNESS_STUBS = """
<script>
  // Mirrors lib.js:783 exactly. `let` at the top level of a classic script
  // puts the binding in the global declarative record, NOT on window -- the
  // whole reason the recorder cannot set the interval with a plain
  // `window.frameInterval = ...`. Declaring it the way the stock page does is
  // what lets these tests catch that offline; window.frameInterval is
  // deliberately left unset here so the two are distinguishable.
  let frameInterval = 8;
  window.__calls = [];
  window.renderedGifBlob = null;
  window.__origReturn = "original-result";
  window.processCentralEvent = function (event, data) {
    window.__calls.push({ fn: "processCentralEvent", event: event, data: data });
    return window.__origReturn;
  };
  window.startRecording = function () {
    window.__calls.push({ fn: "startRecording", blobAtCall: window.renderedGifBlob });
  };
  window.stopRecording = function () {
    window.__calls.push({ fn: "stopRecording", blobAtCall: window.renderedGifBlob });
  };
</script>
"""

_HARNESS_ELEMENTS = """
<span id="current-value">Frame Interval: 24</span>
<input type="range" id="gif-frame-rate" min="1" max="96" value="24" />
"""


def _harness_html(stub_globals: bool = True) -> str:
    """The harness page: stubbed page globals plus the real recorder script.

    ``stub_globals=False`` omits the globals so the script's install-retry loop
    can be exercised; the test defines them afterwards and waits for the retry
    to land.
    """
    return (
        "<!DOCTYPE html><html><head><title>recorder harness</title></head><body>"
        + _HARNESS_ELEMENTS
        + (_HARNESS_STUBS if stub_globals else "")
        + _RECORDER_JS
        + "</body></html>"
    )


@pytest.fixture(scope="session")
async def browser():
    """One Chromium for the whole session.

    Launching per test is correct but slow enough to matter: on Windows the
    launches dominate the run and vary by minutes between runs. Isolation comes
    from the per-test browser context in ``page`` instead, which is a much
    cheaper boundary and just as clean.
    """
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        try:
            instance = await pw.chromium.launch()
        except PlaywrightError as exc:  # pragma: no cover - environment guard
            pytest.skip(
                "Chromium is not installed for Playwright. Run "
                "`uv run playwright install chromium`, or deselect these tests "
                f"with -m 'not browser'. ({exc})"
            )
        try:
            yield instance
        finally:
            await instance.close()


@pytest.fixture
async def page(browser):
    """A blank page with downloads accepted, closed at end of test."""
    context = await browser.new_context(accept_downloads=True)
    try:
        yield await context.new_page()
    finally:
        await context.close()


@pytest.fixture
def harness(page):
    """Open the stub page carrying the real ``_RECORDER_JS``.

    The shipped script string is what runs -- only the page around it is
    substituted, so these tests cannot drift from the code that is served.
    """

    async def _open(stub_globals: bool = True):
        html = _harness_html(stub_globals=stub_globals)

        async def _fulfill(route):
            await route.fulfill(status=200, content_type="text/html", body=html)

        await page.route(HARNESS_URL, _fulfill)
        await page.goto(HARNESS_URL)
        return page

    return _open
