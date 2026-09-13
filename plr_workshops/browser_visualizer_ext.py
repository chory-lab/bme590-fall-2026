"""Browser (Pyodide) build of :mod:`bme590.visualizer_ext`.

The desktop module (:file:`bme590/visualizer_ext.py`) records GIFs by starting a
websocket file server and scripting the browser page it serves. In the hosted
JupyterLite site there is no desktop process to serve from: the deck iframe is
already on the parent page, and the bridge transport
(:mod:`plr_workshops.jupyterlite_bridge`) delivers events to it directly.
GIF recording also cannot work in-browser, so the recorder is a no-op that
keeps the workshops' ``rec = gif_recorder(lh.vis, ...)`` / ``await rec.start()``
/ ``await rec.stop()`` choreography intact.

The wheel build stages this file as ``bme590/visualizer_ext.py`` (next to a
minimal ``bme590/__init__.py``), so the workshops run unmodified in the browser
without ever importing the desktop module.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

__all__ = [
    "close_visualizer",
    "gif_recorder",
    "gif_recording",
    "step",
    "set_step_delay",
    "visualize_deck",
]


class _NoopRecorder:
    """Placeholder for :class:`bme590.visualizer_ext.GifRecorder`.

    ``start()``/``stop()`` exist so the workshop cells that drive a recording
    run unchanged; nothing is captured or downloaded in the browser.
    """

    def __init__(self, vis=None, name="plr-protocol.gif", frame_interval=8, max_duration=60.0):
        self.vis = vis
        self.name = name

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


def gif_recorder(
    vis=None,
    name: str = "plr-protocol.gif",
    frame_interval: int = 8,
    max_duration: "float | None" = 60.0,
) -> _NoopRecorder:
    """Browser no-op: GIF recording needs the desktop capture loop."""
    return _NoopRecorder(vis, name=name, frame_interval=frame_interval, max_duration=max_duration)


@asynccontextmanager
async def gif_recording(
    vis=None,
    name: str = "plr-protocol.gif",
    frame_interval: int = 8,
    max_duration: "float | None" = 60.0,
):
    """Single-cell form of :func:`gif_recorder`; browser no-op."""
    yield gif_recorder(vis, name=name, frame_interval=frame_interval, max_duration=max_duration)


def set_step_delay(seconds: float) -> None:
    """Browser no-op: there is no desktop event loop to pace."""


async def step(multiplier: float = 1.0) -> None:
    """Browser no-op: there is no desktop event loop to pace."""


# The session this kernel last created, mirroring the desktop module's
# singleton. There are no ports to collide in Pyodide, but the lifecycle the
# workshops teach -- one live session, closed before the next opens -- has to
# hold here too, or the hosted site quietly exercises a lifecycle the students
# are told they are not taking. Without it workshop 01 built ten LiquidHandlers
# and stopped none.
_active = None


async def close_visualizer() -> None:
    """Close the current session, if there is one.

    The browser counterpart of :func:`bme590.visualizer_ext.close_visualizer`.
    Every workshop imports this name and calls it to finish, so it must exist
    here even though there is no websocket or file server to release: an
    ImportError in the first setup cell would take down the whole notebook.
    """
    global _active
    lh, _active = _active, None
    if lh is None:
        return
    vis = getattr(lh, "vis", None)
    closers = [getattr(vis, "stop", None)]
    # Matches the desktop module: `LiquidHandler.stop()` raises RuntimeError on
    # an already-stopped handler, so it is only called when setup finished.
    if getattr(lh, "setup_finished", False):
        closers.append(lh.stop)
    for closer in closers:
        if closer is None:
            continue
        try:
            await closer()
        except Exception:  # noqa: BLE001, S110 - teardown must not mask the new setup
            pass


async def visualize_deck(
    deck,
    backend,
    open_browser: bool = True,
    declutter: bool = False,
    **vis_kwargs,
):
    """Build a LiquidHandler whose deck renders through the site's bridge.

    Mirrors ``bme590.visualizer_ext.visualize_deck``'s signature, but attaches
    the bridge-backed ``BrowserVisualizer`` (no websocket, no browser tab) as
    ``lh.vis``, so exercise code can pass it straight into :func:`gif_recorder`.
    """
    from pylabrobot.liquid_handling import LiquidHandler

    from plr_workshops.jupyterlite_bridge import BrowserVisualizer

    global _active
    if _active is not None:
        await close_visualizer()

    lh = LiquidHandler(backend=backend, deck=deck)
    await lh.setup()
    vis = BrowserVisualizer(resource=lh)
    await vis.setup()
    lh.vis = vis  # type: ignore[attr-defined]
    _active = lh
    return lh
