"""One call that puts a simulated STAR on screen with motion playback and collision gates.

`open_viewer` is the only thing the notebook needs from this package, and it hides nothing a
reader of the demo would want to see: it starts a `Viewer3D`, makes the iSWAP transport, and
attaches the two hooks the PRs add (`attach_viewer_motion`, `attach_viewer_collisions`). What it
adds over calling those directly is that the same notebook cell works everywhere it runs:

* On a desktop kernel it serves the page and opens a browser tab, then waits until that tab has
  drawn the models, so the first move is seen.
* Under JupyterLite (Pyodide) there is no socket to serve from; the page is a sibling of the
  notebook on the hosted site and the bridge viewer carries the same messages over postMessage.
* With `VIZ3D_HEADLESS=1` (CI) nothing is opened or waited for. The commands still run, and the
  collision gates still refuse what they would refuse with a page attached.

Re-running the cell stops the previous viewer first, so its ports are free and the old tree stops
publishing to it.
"""

import dataclasses
import os
import sys
from pathlib import Path
from typing import Any

from pylabrobot.hamilton.star.device import STARDevice
from pylabrobot.hamilton.star.driver.features.iswap_transport import iSWAPTransport
from pylabrobot.hamilton.star.motion import attach_viewer_collisions, attach_viewer_motion
from pylabrobot.resources.resource import Resource

IN_BROWSER = sys.platform == "emscripten"


def headless() -> bool:
  """Whether no page is going to watch: CI, or anyone who sets `VIZ3D_HEADLESS=1`."""
  return os.environ.get("VIZ3D_HEADLESS", "") not in ("", "0")


@dataclasses.dataclass
class Session:
  viewer: Any
  transport: iSWAPTransport
  star: STARDevice


_current: Session | None = None


async def open_viewer(
  facility: Resource, star: STARDevice, *, name: str = "viz3d demo", timeout: float = 120.0
) -> Session:
  """Show `facility` in the 3D viewer, with `star`'s commands played and gated there.

  Args:
    facility: the root resource the viewer draws.
    star: the simulated STAR in it, already set up.
    name: what the page's header calls the run.
    timeout: how long to wait for a page to draw the models, in seconds.
  """
  global _current
  if _current is not None:
    await _current.viewer.stop()
    _current = None

  if star.iswap is None:
    raise RuntimeError("the demo needs a STAR with an iSWAP")

  if IN_BROWSER:
    from .bridge import BridgeViewer

    viewer: Any = BridgeViewer(facility, name=name, raise_on_collision=True)
  else:
    from pylabrobot.visualizer3D.server import Viewer3D

    # A test harness drives its own browser to the page and says so with VIZ3D_OPEN_BROWSER=0.
    open_browser = not headless() and os.environ.get("VIZ3D_OPEN_BROWSER", "1") != "0"
    viewer = Viewer3D(facility, name=name, open_browser=open_browser, raise_on_collision=True)
  await viewer.start()

  url_file = os.environ.get("VIZ3D_URL_FILE")
  if url_file and not IN_BROWSER:
    # How a test harness running the notebook learns where the page is.
    Path(url_file).write_text(viewer.url, encoding="utf-8")

  transport = iSWAPTransport(star.iswap)
  attach_viewer_motion(star.driver, viewer)
  attach_viewer_collisions(star.driver, viewer, transport)

  if not headless():
    print("waiting for the page to draw the deck...")
    await viewer.wait_for_browser(timeout=timeout)
    await viewer.wait_for_models(timeout=timeout)
    print("ready")

  _current = Session(viewer=viewer, transport=transport, star=star)
  return _current


async def close_viewer() -> None:
  """Stop the viewer `open_viewer` started, if any."""
  global _current
  if _current is not None:
    await _current.viewer.stop()
    _current = None
