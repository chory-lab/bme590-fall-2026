"""A VisualizerTransport for a plain Pyodide page, with no anywidget or sidecar.

The notebook path delivers events through an anywidget -> srcdoc iframe. On a
static Pyodide page there is no notebook and no comm channel; the iframe is
still the right mount point (it keeps the visualizer's 20 KB of global CSS from
leaking into the demo page), but the events cross directly from Python to the
iframe via ``window.postMessage``.

``js`` is imported lazily inside the methods, so this module imports cleanly in
CPython (for tests) and only touches the browser when actually running under
Pyodide.
"""

import json

from .frontend import build_page
from .transport import VisualizerTransport


class PyodideTransport(VisualizerTransport):
  """Mount the visualizer frontend in an iframe and stream events into it.

  Args:
    container_id: ``id`` of the element the iframe is appended to.
    name: Header name for the visualizer page.
    liquid_color: Hex fill (no ``#``) for wells.
    height: Iframe height in pixels. The default, ``None``, fills the container,
      which is what a docked deck panel wants; pass an integer when the
      container has no height of its own.
  """

  def __init__(
    self,
    container_id: str = "plr-deck",
    name: str = "PyLabRobot",
    liquid_color: str = "F39C12",
    height=None,
  ):
    self._container_id = container_id
    self._name = name
    self._liquid_color = liquid_color
    self._height = height
    self._iframe = None
    self._on_message = None
    self._ready = False
    self._queue = []

  # -- transport protocol --

  async def start(self) -> None:
    from js import document, window
    from pyodide.ffi import create_proxy

    page = build_page(name=self._name, liquid_color=self._liquid_color)

    container = document.getElementById(self._container_id)
    if container is None:
      raise RuntimeError(f"no element with id={self._container_id!r} to mount the visualizer")

    # Re-running a protocol starts a fresh transport; replace any previous
    # iframe so the deck does not accumulate.
    old = document.getElementById("plr-deck-frame")
    if old is not None and old.parentNode is not None:
      old.parentNode.removeChild(old)

    height = "100%" if self._height is None else f"{self._height}px"
    frame = document.createElement("iframe")
    frame.setAttribute("srcdoc", page)
    frame.setAttribute("style", f"width: 100%; height: {height}; border: 0; display: block;")
    frame.id = "plr-deck-frame"
    container.appendChild(frame)
    self._iframe = frame

    def on_message(event):
      data = event.data
      if data is None:
        return
      # The iframe's socket shim posts __plrReady once lib.js has parsed, and
      # __plrAck when handleEvent reports a render error.
      ready = getattr(data, "__plrReady", None)
      if ready:
        self._ready = True
        pending, self._queue = self._queue, []
        try:
          for message in pending:
            self._emit(message)
        except Exception as exc:  # noqa: BLE001
          # Nothing awaits this listener, so an exception here would vanish
          # into the console and leave a silently blank deck.
          print(f"[plr] could not deliver {len(pending)} queued events: {exc}")
          raise
        return
      ack = getattr(data, "__plrAck", None)
      if ack:
        try:
          parsed = json.loads(str(ack))
          if parsed.get("success") is False:
            print("[plr] render error:", parsed.get("error"))
        except (TypeError, json.JSONDecodeError):
          pass

    # A Python callable handed straight to addEventListener is only *borrowed*
    # for the duration of that call: Pyodide destroys the proxy as soon as
    # addEventListener returns, and the listener is dead before the iframe ever
    # posts __plrReady. It has to be an owned proxy, kept alive here and
    # destroyed in stop().
    self._on_message = create_proxy(on_message)
    window.addEventListener("message", self._on_message, False)

  async def emit(self, message: str) -> None:
    if self._ready:
      self._emit(message)
    else:
      self._queue.append(message)

  async def stop(self) -> None:
    from js import document, window

    if self._on_message is not None:
      window.removeEventListener("message", self._on_message, False)
      self._on_message.destroy()
      self._on_message = None
    if self._iframe is not None:
      frame = self._iframe
      if frame.parentNode is not None:
        frame.parentNode.removeChild(frame)
      self._iframe = None
    self._ready = False
    self._queue.clear()

  # -- helpers --

  def _emit(self, message: str) -> None:
    from js import Object
    from pyodide.ffi import to_js

    # to_js turns a dict into a JS Map by default. postMessage cannot structured
    # -clone one, and the iframe's shim reads `msg.__plrEvent` as a property, so
    # the payload has to be a plain object.
    payload = to_js({"__plrEvent": message}, dict_converter=Object.fromEntries)
    self._iframe.contentWindow.postMessage(payload, "*")
