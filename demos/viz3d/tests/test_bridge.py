"""The hosted site's transport, without the site: the notebook's own cells through `BridgeViewer`.

The browser half of the bridge (the WebSocket shim over a BroadcastChannel) is exercised by the
site's own headless run; this is the Python half, which CI can run anywhere. A fake page stands
where the shim would: it opens a socket when a viewer announces itself, says hello, reports its
models drawn, and answers every motion as played - so every command of the demo waits on the same
handshake it does on the hosted page, and a message the bridge drops is a test that hangs, then
fails.
"""

import ast
import asyncio
import json
from collections.abc import Callable
from typing import Any

import nbformat
import pytest

from viz3d_demo import session
from viz3d_demo.bridge import BridgeViewer

from .conftest import NOTEBOOK


class FakePage:
  """The viewer page, as the kernel hears it on the channel: the shim's half of the protocol."""

  SOCKET = 7

  def __init__(self) -> None:
    self.received: list[dict[str, Any]] = []
    self.viewer_announced = 0
    self._to_kernel: Callable[[str], None] = lambda raw: None

  def channel(self, on_message: Callable[[str], None]) -> "FakePage":
    """Stands in for `_BrowserChannel`: the kernel posts here, and hears what `_say` posts."""
    self._to_kernel = on_message
    return self

  def post(self, raw: str) -> None:
    content = json.loads(raw)
    if "viewer" in content:
      # A viewer started: open a socket, as the shim's page does.
      self.viewer_announced += 1
      asyncio.get_running_loop().call_soon(self._send, {"open": self.SOCKET})
      return
    assert content["to"] == self.SOCKET
    if content.get("opened"):
      asyncio.get_running_loop().call_soon(
        self._say, "hello", {"backend": "WebGL2", "renderer": "fake", "userAgent": "test"}
      )
      return
    message = json.loads(content["message"])
    self.received.append(message)
    loop = asyncio.get_running_loop()
    if message["event"] == "scene":
      loop.call_soon(self._say, "models_drawn", {})
    elif message["event"] == "motion":
      # Played on a later turn of the loop, as a page answers.
      loop.call_later(0.001, self._say, "motion_done", {"id": message["data"]["id"]})

  def close(self) -> None:
    pass

  def _send(self, content: dict[str, Any]) -> None:
    self._to_kernel(json.dumps(content))

  def _say(self, event: str, data: Any) -> None:
    message = json.dumps({"event": event, "data": data})
    self._send({"id": self.SOCKET, "message": message})


@pytest.fixture
def bridged(monkeypatch):
  pages: list[FakePage] = []
  original_init = BridgeViewer.__init__

  def init(self: BridgeViewer, root: Any, **kwargs: Any) -> None:
    page = FakePage()
    pages.append(page)
    original_init(self, root, channel=page.channel, **kwargs)

  monkeypatch.setattr(BridgeViewer, "__init__", init)
  monkeypatch.setattr(session, "IN_BROWSER", True)
  monkeypatch.delenv("VIZ3D_HEADLESS", raising=False)
  return pages


async def test_the_whole_demo_runs_over_the_bridge(bridged, capsys):
  namespace: dict[str, Any] = {}
  nb = nbformat.read(NOTEBOOK, as_version=4)
  for cell in nb.cells:
    if cell.cell_type != "code":
      continue
    code = compile(cell.source, "<cell>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    result = eval(code, namespace)
    if asyncio.iscoroutine(result):
      await asyncio.wait_for(result, timeout=120)
  await session.close_viewer()
  printed = capsys.readouterr().out

  (page,) = bridged
  assert page.viewer_announced == 1
  events = [m["event"] for m in page.received]
  assert events[:2] == ["scene", "state"], events[:5]
  assert events.count("motion") >= 10
  collisions = [m["data"]["collisions"] for m in page.received if m["event"] == "collisions"]
  assert len(collisions) == 9
  assert {c["resource"] for c in collisions[-1]} == {"tip_carrier"}
  assert "source now sits on destination_carrier-3" in printed


async def test_meshes_point_at_the_sites_model_files(bridged):
  namespace: dict[str, Any] = {}
  nb = nbformat.read(NOTEBOOK, as_version=4)
  setup_cells = [c for c in nb.cells if c.cell_type == "code"][:2]
  for cell in setup_cells:
    code = compile(cell.source, "<cell>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    result = eval(code, namespace)
    if asyncio.iscoroutine(result):
      await result
  await session.close_viewer()

  (page,) = bridged
  scene = next(m["data"] for m in page.received if m["event"] == "scene")
  urls = {m["mesh"]["url"] for m in scene.get("models", []) if isinstance(m.get("mesh"), dict)}
  assert urls, "the scene has no models with meshes"
  assert all(u.startswith("models/") and u.endswith(".glb") for u in urls), sorted(urls)[:5]
