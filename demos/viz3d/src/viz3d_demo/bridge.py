"""The 3D viewer under JupyterLite, where the kernel is a Pyodide worker and cannot serve anything.

`Viewer3D` talks to its page over a websocket it serves, and serves the page and its model files
over HTTP. A browser kernel can do neither, so on the hosted site:

* The page is a static copy of the viewer's own `static/` directory, beside the notebook on the
  site's `viz3d.html`, with the model files under `models/` at their paths in the package.
* The page's `WebSocket` is a shim (`viz3d_shim.js`) over a `BroadcastChannel`, and this kernel
  listens on the same channel. The kernel's worker and the page share an origin, so the channel
  joins them directly.

Why a channel and not the notebook's comm: JupyterLite hands a kernel its messages one at a time,
so a comm message from the page waits until the running cell finishes - and a motion is a cell
waiting for the page to say it has played it. A channel message is an event on the kernel's own
worker, which is free whenever the cell is awaiting, so it arrives mid-cell like a socket's would.

Everything above the wire is `Viewer3D`'s own code: scenes, state deltas, motions held until the
page has played them, collision boxes. This class only replaces the transport: each socket the page
opens is a `_PageSocket` here, sitting in the same `_clients` set the websocket handler fills.

Messages, each a JSON string on the channel `CHANNEL`:

  kernel -> pages  {"viewer": <nonce>}           a viewer has started: pages reconnect to it
                   {"to": id, "opened": true}     a socket is accepted
                   {"to": id, "message": <msg>}   what the websocket would have carried
  page -> kernel   {"open": id} | {"close": id}
                   {"id": id, "message": <msg>}
"""

import asyncio
import json
import os
import secrets
from collections.abc import Callable
from typing import Any

from pylabrobot.visualizer3D.scene import legacy_size, pack_state
from pylabrobot.visualizer3D.server import PACKAGE_ROOT, Viewer3D, _encode

CHANNEL = "plr-viz3d"


class _BrowserChannel:
  """A `BroadcastChannel` in the kernel's worker, carrying strings."""

  def __init__(self, on_message: Callable[[str], None]):
    import js
    from pyodide.ffi import create_proxy

    self._channel = js.BroadcastChannel.new(CHANNEL)
    self._proxy = create_proxy(lambda event: on_message(str(event.data)))
    self._channel.onmessage = self._proxy

  def post(self, message: str) -> None:
    self._channel.postMessage(message)

  def close(self) -> None:
    self._channel.onmessage = None
    self._channel.close()
    self._proxy.destroy()


class _PageSocket:
  """One of the page's sockets, as `Viewer3D` expects a client to be: something it can send to."""

  def __init__(self, viewer: "BridgeViewer", socket_id: int):
    self.viewer = viewer
    self.socket_id = socket_id

  async def send(self, message: str) -> None:
    self.viewer._post({"to": self.socket_id, "message": message})


class BridgeViewer(Viewer3D):
  """`Viewer3D` with its page on the hosted site and its websocket replaced by a channel.

  Takes `Viewer3D`'s arguments; the ones about serving (host, ports, browser) are ignored.

  Args:
    channel: makes the channel from a message handler; a `BroadcastChannel` by default. Tests pass
      their own.
  """

  # Where the hosted page finds a model file: the same path it has under the package.
  MODELS_URL = "models/"

  def __init__(
    self,
    root: Any,
    channel: Callable[[Callable[[str], None]], Any] | None = None,
    **kwargs: Any,
  ):
    for serving in ("host", "fs_port", "ws_port", "open_browser", "allowed_hosts"):
      kwargs.pop(serving, None)
    super().__init__(root, open_browser=False, **kwargs)
    self._make_channel = channel or _BrowserChannel
    self._channel: Any = None
    self._sockets: dict[int, _PageSocket] = {}

  @property
  def url(self) -> str:
    return "the viewer beside this notebook"

  def _register_meshes(self, models: list[dict[str, Any]]) -> None:
    super()._register_meshes(models)
    # `Viewer3D` serves each file under a random id; here the files are on the site already.
    for model in models:
      mesh = model.get("mesh")
      if not isinstance(mesh, dict) or not str(mesh.get("url", "")).startswith("mesh/"):
        continue
      path = self._mesh_files.get(mesh["url"][len("mesh/") :])
      if path is None:
        continue
      relative = os.path.relpath(path, PACKAGE_ROOT).replace(os.sep, "/")
      mesh["url"] = self.MODELS_URL + relative

  def _post(self, message: dict[str, Any]) -> None:
    if self._channel is not None:
      self._channel.post(json.dumps(message))

  async def start(self) -> None:
    self._loop = asyncio.get_running_loop()
    self._browser_drawing = asyncio.Event()
    self._models_drawn = asyncio.Event()
    # No threads in Pyodide: measured here, on the loop. It is a walk of the tree, once.
    self._legacy_bytes = legacy_size(self.root)
    self._channel = self._make_channel(self._on_channel_message)
    # A page already open is connected to whatever viewer came before, or to none: either way it
    # reconnects, and this viewer greets it as it would any page.
    self._post({"viewer": secrets.token_hex(8)})

  def _on_channel_message(self, raw: str) -> None:
    try:
      content = json.loads(raw)
    except ValueError:
      return
    if not isinstance(content, dict) or self._loop is None:
      return
    if "open" in content:
      socket = _PageSocket(self, int(content["open"]))
      self._sockets[socket.socket_id] = socket
      self._clients.add(socket)  # type: ignore[arg-type]
      self._post({"to": socket.socket_id, "opened": True})
      asyncio.ensure_future(self._greet(socket))
    elif "close" in content:
      socket = self._sockets.pop(int(content["close"]), None)
      if socket is not None:
        self._clients.discard(socket)  # type: ignore[arg-type]
        self._release_motions(socket)
    elif "id" in content and "message" in content:
      socket = self._sockets.get(int(content["id"]))
      if socket is None:
        return
      message = content["message"]
      # As `Viewer3D._handler` reads a page's messages.
      if self._on_motion_played(socket, message) or self._on_models_drawn(message):
        return
      self._on_client_message(message)

  async def _greet(self, socket: _PageSocket) -> None:
    """What a page is told as it connects, as `Viewer3D._handler` tells it."""
    await socket.send(_encode("scene", self._scene_message()))
    await socket.send(_encode("state", pack_state(self._snapshot(), self._epoch)))

  async def stop(self) -> None:
    self._release_motions()
    self._unsubscribe(self.root)
    self.root.deregister_did_assign_resource_callback(self._on_assign)
    self.root.deregister_did_unassign_resource_callback(self._on_unassign)
    self._loop = None
    if self._scene_timer is not None:
      self._scene_timer.cancel()
      self._scene_timer = None
    self._clients.clear()
    self._sockets.clear()
    if self._channel is not None:
      self._channel.close()
      self._channel = None
