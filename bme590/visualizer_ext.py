"""Code-driven GIF recording for the PyLabRobot visualizer.

The stock visualizer (pylabrobot 0.2.2) records GIFs entirely in the browser:
students must click "Start Recording" before running a protocol, switch back,
run it, switch again, click "Stop Recording", type a filename, and click
"Download GIF". This module removes that choreography.

:class:`RecordingVisualizer` subclasses the stock :class:`Visualizer` and
injects a small script into the page it serves. The script intercepts two new
websocket commands, ``class_start_gif`` and ``class_stop_gif``, and maps them
onto the page's own recording globals (``startRecording``, ``stopRecording``,
``frameInterval``, ``renderedGifBlob``). The stock visualizer is otherwise
untouched: no site-packages files are modified.

Recording is driven from Python with :func:`gif_recorder`::

    rec = gif_recorder(lh.vis, name="exercise_1.gif")
    await rec.start()
    ...  # any number of operations, across as many notebook cells as you like
    await rec.stop()   # renders the frames and downloads exercise_1.gif

Because ``start()``/``stop()`` are plain calls, a recording may span multiple
notebook cells -- something an ``async with`` block cannot do. As a safety
net, a recording left running is **auto-stopped after ``max_duration``
seconds** (default 60): the GIF is finalized and downloaded anyway rather
than being lost to a forgotten ``stop()``.

For single-cell protocols, :func:`gif_recording` wraps the same machinery in
an ``async with`` block that cannot be forgotten::

    async with gif_recording(lh.vis, name="exercise_1.gif"):
        ...
"""

import asyncio
import os
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.resources import Deck
from pylabrobot.visualizer.visualizer import Visualizer
from pylabrobot.visualizer import visualizer as _plr_visualizer_module

__all__ = [
    "RecordingVisualizer",
    "GifRecorder",
    "gif_recorder",
    "gif_recording",
    "step",
    "set_step_delay",
    "visualize_deck",
    "close_visualizer",
]

# ---------------------------------------------------------------------------
# Injected browser script
# ---------------------------------------------------------------------------

# Runs after lib.js/vis.js have defined their globals. Wraps the page's event
# dispatcher so two extra commands are handled locally instead of raising
# "Unknown event". Because vis.js acknowledges every command it processes, the
# Python side gets a real success response for both commands.
_RECORDER_JS = """
<script>
(function () {
  function install() {
    if (typeof window.processCentralEvent !== "function" ||
        typeof window.startRecording !== "function" ||
        typeof window.stopRecording !== "function") {
      return setTimeout(install, 200);
    }
    var origProcessCentralEvent = window.processCentralEvent;
    window.processCentralEvent = async function (event, data) {
      if (event === "class_start_gif") {
        var interval = data && data.frame_interval;
        if (typeof interval === "number") {
          interval = Math.max(1, Math.min(96, Math.round(interval)));
          // lib.js declares `let frameInterval` at the top level of a classic
          // script, so that binding lives in the global *declarative* record
          // and is NOT a property of window. Assigning window.frameInterval
          // creates a lookalike the capture loop never reads -- the slider
          // would show the new value while recording ran at the old one. An
          // unqualified assignment resolves up the scope chain to the real
          // binding; if upstream ever drops it, this degrades to creating the
          // property, which is what the next line does anyway.
          try { frameInterval = interval; } catch (e) {}
          window.frameInterval = interval;
          var cv = document.getElementById("current-value");
          var slider = document.getElementById("gif-frame-rate");
          if (cv) cv.textContent = "Frame Interval: " + interval;
          if (slider) slider.value = interval;
        }
        window.renderedGifBlob = null;
        window.startRecording();
        return;
      }
      if (event === "class_stop_gif") {
        window._classGifName = (data && data.filename) || "plr-protocol";
        // Drop any stale blob from an earlier recording before polling.
        window.renderedGifBlob = null;
        window.stopRecording();
        waitForRenderedBlob(0);
        return;
      }
      return origProcessCentralEvent.call(this, event, data);
    };
    window.__classRecorderInstalled = true;
  }

  function waitForRenderedBlob(attempt) {
    if (window.renderedGifBlob) {
      downloadRenderedGif();
      return;
    }
    if (attempt > 1200) return; // give up after ~2 minutes
    setTimeout(function () { waitForRenderedBlob(attempt + 1); }, 100);
  }

  function downloadRenderedGif() {
    var fileName = window._classGifName || "plr-protocol";
    if (!fileName.endsWith(".gif")) fileName += ".gif";
    var url = URL.createObjectURL(window.renderedGifBlob);
    var a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // Release the object URL once the download has certainly started. Revoking
    // straight after click() can cancel the save in some browsers, so this
    // waits; without it every recording leaks its blob for the page's lifetime.
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    window.renderedGifBlob = null; // allow a fresh recording afterwards
  }

  install();
})();
</script>
"""

# Hides everything that is not the deck: the left toolbar (aside), the right
# side panel and its resize handle, and the reset-view button. Applied when
# RecordingVisualizer is built with declutter=True, or per-page-load with
# ?minimal=1 in the URL.
_DECLUTTER_CSS = """
<style id="class-declutter-style">
  body.class-minimal aside,
  body.class-minimal #sidepanel,
  body.class-minimal #sidepanel-resize-handle,
  body.class-minimal #home-button {
    display: none !important;
  }
  body.class-minimal main {
    position: fixed !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
  }
</style>
<script>
(function () {
  var params = new URLSearchParams(window.location.search);
  var byUrl = params.has("minimal") || params.has("clean") || params.has("deck-only");
  // window.__CLASS_DECLUTTER_KWARG is set by the server-injected flag script
  // when RecordingVisualizer was built with declutter=True.
  if (byUrl || window.__CLASS_DECLUTTER_KWARG) {
    document.body.classList.add("class-minimal");
    window.addEventListener("load", function () { window.dispatchEvent(new Event("resize")); });
  }
})();
</script>
"""


class RecordingVisualizer(Visualizer):
    """A :class:`Visualizer` whose served page accepts ``class_start_gif`` /
    ``class_stop_gif`` websocket commands, enabling code-driven recording via
    :func:`gif_recorder`.

    With ``declutter=True`` the page shows only the deck: toolbar, side panel,
    and reset button are hidden and machine-tool popups stay closed. Any page
    of a RecordingVisualizer can also be toggled per-load with ``?minimal=1``
    (or ``?clean=1``, ``?deck-only=1``) in its URL.
    """

    def __init__(self, resource, declutter: bool = False, **kwargs):
        if declutter:
            # Machine-tool popups are part of the clutter; keep them closed
            # unless explicitly requested.
            kwargs.setdefault("show_machine_tools_at_start", False)
        self._declutter = declutter
        super().__init__(resource, **kwargs)

    def _run_file_server(self):
        """Copy of ``Visualizer._run_file_server`` that additionally injects
        the recorder script into index.html. Anchored on ``</body>``, which is
        stable across PLR releases; re-check this override when upgrading."""
        path = os.path.join(os.path.dirname(_plr_visualizer_module.__file__), ".")
        server = self  # the Visualizer instance, for the handler closure below

        def start_server(lock):
            ws_port, fs_port, source_filename = self.ws_port, self.fs_port, self._source_filename
            favicon_path = self._favicon_path
            liquid_color = self._liquid_color

            class QuietSimpleHTTPRequestHandler(SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=path, **kwargs)

                def log_message(self, format, *args):
                    pass

                def end_headers(self):
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                    super().end_headers()

                def do_GET(self) -> None:
                    parts = urlsplit(self.path)
                    if parts.path == "/":
                        with open(os.path.join(path, "index.html"), "r", encoding="utf-8") as f:
                            content = f.read()

                        content = content.replace("{{ ws_port }}", str(ws_port))
                        content = content.replace("{{ fs_port }}", str(fs_port))
                        content = content.replace("{{ source_filename }}", source_filename)
                        content = content.replace("{{ liquid_color }}", liquid_color)

                        # Inject the code-driven recorder (the one change vs stock).
                        extras = [_RECORDER_JS]
                        # Declutter: kwarg applies always; ?minimal=1 (or
                        # ?clean=1, ?deck-only=1) toggles it per page load.
                        minimal_kwarg = getattr(server, "_declutter", False)
                        # keep_blank_values: people type "?minimal", not
                        # "?minimal=1", and the injected script's
                        # URLSearchParams.has() accepts the bare flag. Without
                        # this the two halves disagree and the body class is
                        # added with no CSS to act on it.
                        query = parse_qs(parts.query, keep_blank_values=True)
                        minimal_query = any(
                            q in query for q in ("minimal", "clean", "deck-only")
                        )
                        if minimal_kwarg:
                            # The flag must precede _DECLUTTER_CSS: its script
                            # reads window.__CLASS_DECLUTTER_KWARG at parse time.
                            extras.append(
                                "<script>window.__CLASS_DECLUTTER_KWARG = true;</script>"
                            )
                        if minimal_kwarg or minimal_query:
                            extras.append(_DECLUTTER_CSS)
                        content = content.replace(
                            "</body>", "".join(extras) + "\n  </body>"
                        )

                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(content.encode("utf-8"))
                    elif self.path == "/favicon.png":
                        with open(favicon_path, "rb") as f:
                            data = f.read()
                        self.send_response(200)
                        self.send_header("Content-type", "image/png")
                        self.end_headers()
                        self.wfile.write(data)
                    else:
                        return super().do_GET()

            while True:
                try:
                    self._httpd = HTTPServer((self.host, self.fs_port), QuietSimpleHTTPRequestHandler)
                    print(
                        f"File server started at http://{self.host}:{self.fs_port} . "
                        "Open this URL in your browser."
                    )
                    lock.release()
                    break
                except OSError:
                    self.fs_port += 1

            self.httpd.serve_forever()

        lock = threading.Lock()
        lock.acquire()
        self._fst = threading.Thread(
            name="visualizer_fs",
            target=start_server,
            args=(lock,),
            daemon=True,
        )
        self.fst.start()

        while lock.locked():
            time.sleep(0.001)

        if self.open_browser:
            webbrowser.open(f"http://{self.host}:{self.fs_port}")


# ---------------------------------------------------------------------------
# Pacing helper
# ---------------------------------------------------------------------------

_step_delay = 1.0


def set_step_delay(seconds: float) -> None:
    """Set the delay used by :func:`step` between protocol operations."""
    global _step_delay
    _step_delay = max(0.0, float(seconds))


async def step(multiplier: float = 1.0) -> None:
    """Pause so the current deck state lands on its own GIF frame.

    Every workshop notebook defines a ``SLEEP`` constant for exactly this
    purpose; ``await step()`` replaces ``await asyncio.sleep(N * SLEEP)`` and
    is shared by all course code.
    """
    await asyncio.sleep(_step_delay * multiplier)


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


class GifRecorder:
    """Records everything the visualized deck does between ``start()`` and
    ``stop()`` and downloads the result under ``name``.

    A recording left running is finalized automatically after ``max_duration``
    seconds (default 60) so a forgotten ``stop()`` costs a short GIF, not the
    whole recording. Pass ``max_duration=None`` to disable the watchdog.
    """

    def __init__(
        self,
        vis: Visualizer,
        name: str = "plr-protocol.gif",
        frame_interval: int = 8,
        max_duration: "float | None" = 60.0,
        wait_for_browser: bool = True,
        browser_timeout: float = 60.0,
    ):
        if not isinstance(vis, Visualizer):
            raise TypeError(f"expected a Visualizer instance, got {type(vis).__name__}")
        self.vis = vis
        self.name = name
        self.frame_interval = frame_interval
        self.max_duration = max_duration
        self.wait_for_browser = wait_for_browser
        self.browser_timeout = browser_timeout
        self._watchdog: "asyncio.Task | None" = None
        self._stopped = False

    async def _wait_for_browser(self) -> None:
        if self.wait_for_browser and not self.vis.has_connection():
            deadline = time.monotonic() + self.browser_timeout
            while not self.vis.has_connection():
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        "Browser tab never connected to the visualizer websocket "
                        f"within {self.browser_timeout:.0f}s. Open the printed URL first."
                    )
                await asyncio.sleep(0.2)

    async def start(self) -> None:
        """Start recording. Waits for the browser page to connect first."""
        await self._wait_for_browser()
        await self.vis.send_command(
            "class_start_gif", {"frame_interval": self.frame_interval}
        )
        if self.max_duration is not None:
            self._watchdog = asyncio.create_task(self._auto_stop())

    async def stop(self) -> None:
        """Stop recording, render, and download the GIF."""
        if self._stopped:
            return
        self._stopped = True
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None
        # Let the last state push flush before capturing stops. The page
        # captures on a timer (max(200, frame_interval * 50) ms), so a flush
        # shorter than a couple of those ticks can end the recording before the
        # final deck state is ever photographed -- measured in Chromium: a
        # 9-change protocol landed 5 frames with the old 0.5s flush and 9 once
        # the finished deck was held. Since the last state is the one students
        # submit, wait out two frame intervals at minimum.
        frame_seconds = max(0.2, self.frame_interval * 0.05)
        await asyncio.sleep(max(0.3, _step_delay * 0.5, frame_seconds * 2))
        await self.vis.send_command("class_stop_gif", {"filename": self.name})

    async def _auto_stop(self) -> None:
        await asyncio.sleep(self.max_duration)
        print(
            f"[bme590] Recording {self.name!r} hit its {self.max_duration:.0f}s "
            "timeout and was stopped automatically. Call rec.stop() when the "
            "protocol finishes to capture the full run."
        )
        # Detach ourselves first: stop() cancels the watchdog, and we ARE the
        # watchdog -- self-cancellation would kill this call before it could
        # send the stop command.
        self._watchdog = None
        await self.stop()

    def __del__(self):
        if getattr(self, "_watchdog", None) is not None and not self._watchdog.done():
            self._watchdog.cancel()


def gif_recorder(
    vis: Visualizer,
    name: str = "plr-protocol.gif",
    frame_interval: int = 8,
    max_duration: "float | None" = 60.0,
) -> GifRecorder:
    """Create a recorder for ``vis``.

    Args:
        vis: The visualizer to record (e.g. ``lh.vis`` from :func:`visualize_deck`).
        name: Download filename for the GIF. Use the exact submission filename.
            A filename, not a path: the browser performs the download, so the file
            lands in its download directory and path separators are flattened
            (``runs/out.gif`` saves as ``runs_out.gif``). Pinned in
            tests/test_recorder_js.py.
        frame_interval: Slider ticks between frames (1-96); each frame is
            ``max(200, tick * 50)`` ms apart. Larger = smaller GIFs.
        max_duration: Safety timeout in seconds; a recording still running is
            stopped automatically after this long. ``None`` disables it.
    """
    return GifRecorder(
        vis,
        name=name,
        frame_interval=frame_interval,
        max_duration=max_duration,
    )


@asynccontextmanager
async def gif_recording(
    vis: Visualizer,
    name: str = "plr-protocol.gif",
    frame_interval: int = 8,
    max_duration: "float | None" = 60.0,
):
    """Single-cell form of :func:`gif_recorder`::

        async with gif_recording(lh.vis, name="exercise_1.gif"):
            ...

    Guarantees ``stop()`` runs even if the protocol raises. Cannot span
    multiple notebook cells -- use :func:`gif_recorder` for that.
    """
    rec = gif_recorder(vis, name=name, frame_interval=frame_interval, max_duration=max_duration)
    await rec.start()
    try:
        yield rec
    finally:
        await rec.stop()


# ---------------------------------------------------------------------------
# Course-standard deck setup
# ---------------------------------------------------------------------------

_HEADLESS = os.environ.get("BME590_HEADLESS", "").lower() in {"1", "true", "yes"}


# The visualizer session this process last created, if it is still up.
# Notebooks call visualize_deck() more than once -- workshop 00 does it twice by
# design, and every student does it again after a mistake -- and the second call
# used to leave the first one running. That is not merely untidy: PLR's file
# server does not move off port 1337 when it is taken, so the page a student
# opens keeps advertising the FIRST visualizer's websocket port. The browser
# then talks to the old session while the notebook records the new one, and
# `rec.start()` waits 60s for a connection that cannot arrive. Verified against
# pylabrobot 0.2.2: a second setup lands on ws 2122 while the served page still
# says 2121.
_active: "LiquidHandler | None" = None


async def close_visualizer() -> None:
    """Shut down the visualizer session this process last opened, if any.

    Safe to call when there is nothing open. :func:`visualize_deck` calls it
    for you; it is public so a notebook can free the ports explicitly when it
    is done with a deck.
    """
    global _active
    lh, _active = _active, None
    if lh is None:
        return
    vis = getattr(lh, "vis", None)
    for closer in (getattr(vis, "stop", None), getattr(lh, "stop", None)):
        if closer is None:
            continue
        try:
            await closer()
        except Exception:  # noqa: BLE001, S110 - teardown must not mask the new setup
            # Routinely raises when the tab is already gone: closing a socket
            # whose peer has left reports "1001 (going away)". That is the
            # normal path after a student closes the visualizer tab, so it is
            # not worth a line of output that reads like something went wrong.
            pass


async def visualize_deck(
    deck: Deck,
    backend,
    open_browser: bool = True,
    declutter: bool = False,
    **vis_kwargs,
) -> LiquidHandler:
    """Build a LiquidHandler + RecordingVisualizer pair.

    Returns the handler with the visualizer attached as ``lh.vis`` so exercise
    code can pass it straight into :func:`gif_recorder`. Replaces the
    ``visualize_deck()`` helper previously copy-pasted into every workbook,
    which swallowed exceptions (returning ``None`` on failure) and discarded
    the visualizer reference.

    ``declutter=True`` serves a deck-only page: toolbar, side panel, reset
    button, and machine-tool popups are hidden. Also available per-load via
    ``?minimal=1`` in the page URL.

    Set the environment variable ``BME590_HEADLESS=1`` to skip the visualizer
    entirely (used by headless CI).
    """
    global _active
    if _active is not None:
        print("[bme590] closing the previous visualizer so this one gets the same ports")
        await close_visualizer()

    lh = LiquidHandler(backend=backend, deck=deck)
    if _HEADLESS:
        await lh.setup()
        lh.vis = None  # type: ignore[attr-defined]
        return lh
    vis = RecordingVisualizer(
        resource=lh, open_browser=open_browser, declutter=declutter, **vis_kwargs
    )
    await lh.setup()
    await vis.setup()
    lh.vis = vis  # type: ignore[attr-defined]
    _active = lh
    return lh
