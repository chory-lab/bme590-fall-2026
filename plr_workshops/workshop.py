"""Runtime helpers for working in the workshops, in a notebook or a script.

Two things the raw PyLabRobot API makes easy to get wrong in a notebook, where
cells are re-run out of order:

    from plr_workshops.workshop import visualizer, wait_for_recording

    lh, vis = await visualizer(deck)     # re-runnable: closes any previous one
    await wait_for_recording()           # handshake, not a fixed sleep

Neither is required to complete a workshop; both remove a confusing failure.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Tuple

# The live visualizer for this kernel. Module-level on purpose: a notebook cell
# re-run creates new local names but imports the same module object, which is
# what lets the second call find and close the first server.
_ACTIVE: Optional[object] = None

VISUALIZER_URL = "http://127.0.0.1:1337"


def _release_websocket(vis) -> None:
    """Make the websocket server actually shut down.

    Works around a bug in PyLabRobot 0.2.2: `Visualizer.stop()` resolves the
    future that ends the websocket serve loop *only inside* `if
    self.has_connection():`. With no browser attached -- the tab was closed, or
    was never opened -- the loop keeps running and the port stays bound, while
    `stop()` goes on to clear `_loop`/`_t`, so nothing can ever release it. The
    next visualizer then lands on 2122, and the browser page (served from the
    still-bound 1337) keeps talking to 2121.

    Resolving the future before calling `stop()` covers the disconnected case;
    `stop()` handles the connected one itself. Guarded with getattr so that a
    PyLabRobot which has fixed this simply makes it a no-op.
    """
    loop = getattr(vis, "_loop", None)
    future = getattr(vis, "_stop_", None)
    if loop is None or future is None or future.done():
        return
    try:
        loop.call_soon_threadsafe(future.set_result, "done")
    except (RuntimeError, asyncio.InvalidStateError):  # loop already closed, or someone beat us to it
        pass


async def stop_visualizer() -> None:
    """Close the visualizer this kernel has open, if any. Safe to call always."""
    global _ACTIVE
    if _ACTIVE is None:
        return
    visualizer_ = _ACTIVE
    _ACTIVE = None
    try:
        if not visualizer_.has_connection():
            _release_websocket(visualizer_)
        await visualizer_.stop()
    except Exception as exc:  # noqa: BLE001 - a half-dead server must not block a restart
        print(f"(note: closing the previous visualizer raised {type(exc).__name__}: {exc})")


async def visualizer(deck, backend=None, open_browser: bool = True) -> Tuple[object, object]:
    """Set up a LiquidHandler plus Visualizer for `deck`, and return both.

    Re-running this is safe, which is the whole point. PyLabRobot's visualizer
    binds a file server on port 1337 and a websocket on 2121; starting a second
    one does *not* fail -- it takes the next websocket port (2122) while the page
    your browser already has open stays attached to 2121. The result is a
    visualizer that says "Connected" and never updates again, which looks like a
    bug in your protocol and is not. Closing the previous one first avoids it.
    """
    from pylabrobot.liquid_handling import LiquidHandler
    from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
    from pylabrobot.visualizer.visualizer import Visualizer

    global _ACTIVE
    await stop_visualizer()

    lh = LiquidHandler(backend=backend or LiquidHandlerChatterboxBackend(), deck=deck)
    vis = Visualizer(resource=lh, open_browser=open_browser)
    await lh.setup()
    await vis.setup()
    _ACTIVE = vis
    print(f"Visualizer ready at {VISUALIZER_URL} (top right should read: Connected)")
    return lh, vis


async def wait_for_recording(prompt: str = "Click Start Recording in the visualizer, then press Enter here") -> None:
    """Pause until the student says the recorder is armed.

    The workshops otherwise use `await asyncio.sleep(5 * SLEEP)` to leave a window
    for switching tabs and clicking Start Recording. That is a race: five seconds
    is not always enough, and it disappears entirely once SLEEP is set to 0 to run
    at full speed. Waiting for a keypress turns the race into a handshake.

    Falls back to a five second sleep where there is no one to ask (a headless
    run, or CI), so a notebook driven by nbclient still completes.
    """
    import sys

    if not sys.stdin or not sys.stdin.isatty():
        try:  # a notebook kernel has no tty, but can still prompt
            from IPython import get_ipython

            if get_ipython() is not None:
                input(f"{prompt}: ")
                return
        except Exception:  # noqa: BLE001 - fall through to the sleep
            pass
        await asyncio.sleep(5)
        return
    input(f"{prompt}: ")
