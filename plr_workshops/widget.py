"""Render the deck visualizer beside notebook cells, in a real Jupyter kernel.

The frontend goes into a srcdoc iframe, which keeps ``main.css`` (20 KB of global
rules written for a standalone page) from leaking into JupyterLab's own styles.
Events reach it by ``postMessage``; inside, the shim from :mod:`plr_workshops.frontend`
hands them to ``vis.js`` as if a websocket had delivered them.

Docking it beside the notebook is ``sidecar``'s job::

    from plr_workshops.widget import AnyWidgetTransport
    from plr_workshops import InlineVisualizer

    transport = AnyWidgetTransport(name="workshop 2", dock="split-right")
    vis = InlineVisualizer(resource=lh, transport=transport)
    await vis.setup()
"""

from typing import List, Optional

import anywidget
import traitlets

from .frontend import build_page
from .transport import VisualizerTransport

_ESM = """
function render({ model, el }) {
  const frame = document.createElement("iframe");
  frame.style.width = "100%";
  frame.style.height = model.get("height") + "px";
  frame.style.border = "1px solid var(--jp-border-color2, #ccc)";
  frame.setAttribute("srcdoc", model.get("page"));
  el.appendChild(frame);

  // The iframe needs a moment to parse ~1 MB of inlined renderer. Anything sent
  // before it signals ready would land on a page with no processCentralEvent yet.
  let ready = false;
  const pending = [];

  window.addEventListener("message", (e) => {
    if (!e.data) return;
    if (e.data.__plrReady && e.source === frame.contentWindow) {
      ready = true;
      model.send({ ready: true });      // ask Python to replay anything it already sent
      pending.splice(0).forEach((m) => frame.contentWindow.postMessage(m, "*"));
    }
    if (e.data.__plrAck) {
      const ack = JSON.parse(e.data.__plrAck);
      if (ack.success === false) console.error("[plr] render error:", ack.error);
    }
  });

  model.on("msg:custom", (msg) => {
    if (ready) frame.contentWindow.postMessage(msg, "*");
    else pending.push(msg);
  });
}
export default { render };
"""


class VisualizerWidget(anywidget.AnyWidget):
  """Hosts the visualizer frontend in an iframe."""

  _esm = _ESM
  page = traitlets.Unicode("").tag(sync=True)
  height = traitlets.Int(600).tag(sync=True)


class AnyWidgetTransport(VisualizerTransport):
  """Delivers visualizer events to a notebook widget.

  Args:
    name: Shown in the visualizer header.
    liquid_color: Hex fill for wells, without ``#``.
    height: Widget height in pixels.
    dock: Where to place the view. ``None`` renders inline in the cell output;
      any ``sidecar`` anchor (``"split-right"``, ``"right"``, ``"split-bottom"``,
      ...) opens a dockable panel beside the notebook.
    title: Panel title when docked.
    chrome: How much of the visualizer's own furniture to show. See
      :func:`~plr_workshops.frontend.build_page`. A docked panel is narrow, so
      the default hides everything but the deck.
  """

  def __init__(
    self,
    name: str = "PyLabRobot",
    liquid_color: str = "F39C12",
    height: int = 600,
    dock: Optional[str] = "split-right",
    title: str = "Deck",
    chrome: str = "deck",
  ):
    self.widget = VisualizerWidget(
      page=build_page(name=name, liquid_color=liquid_color, chrome=chrome), height=height
    )
    self._dock = dock
    self._title = title
    self._sidecar = None
    # Events emitted before the frontend finishes loading -- setup() sends the
    # whole deck before the iframe has parsed -- are replayed on its ready
    # signal. Only those: once the iframe is live every event goes straight
    # through, so the backlog is dropped instead of growing for the whole
    # session. A long protocol emits one message per liquid-handling step, and
    # retaining all of them was the one place this leaked.
    self._log: List[str] = []
    self._ready = False
    self.widget.on_msg(self._on_frontend_message)

  def _on_frontend_message(self, _widget, content, _buffers):
    if isinstance(content, dict) and content.get("ready"):
      for message in self._log:
        self.widget.send({"__plrEvent": message})
      self._log.clear()
      self._ready = True

  async def start(self) -> None:
    from IPython.display import display

    if self._dock:
      from sidecar import Sidecar

      self._sidecar = Sidecar(title=self._title, anchor=self._dock)
      with self._sidecar:
        display(self.widget)
    else:
      display(self.widget)

  async def emit(self, message: str) -> None:
    if not self._ready:
      self._log.append(message)
    self.widget.send({"__plrEvent": message})

  async def stop(self) -> None:
    if self._sidecar is not None:
      self._sidecar.close()
      self._sidecar = None
    self._log.clear()
    self._ready = False
