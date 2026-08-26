"""A VisualizerTransport for the JupyterLite-hosted demo.

The deck iframe lives on the **parent page**, beside the JupyterLite iframe; the
widget is only a wire.

Event flow::

    kernel (Pyodide worker) --comm--> anywidget JS (inside JupyterLite iframe)
        --window.parent.postMessage--> outer page --postMessage--> deck iframe

The deck iframe is the same self-contained ``frontend.build_page()`` document as
everywhere else. Its socket shim posts ``__plrReady`` to *its* parent -- which is the
outer page, not the widget -- so the outer page relays readiness back into the
JupyterLite iframe, and this widget forwards it to Python as the ready handshake.

Also hosts :func:`patch_visualizer`, which lets the workshop notebooks run
*unmodified* in the browser by swapping the stock ``Visualizer`` name for a
bridge-backed :class:`~plr_workshops.inline.InlineVisualizer`.
"""

from typing import List, Optional

import anywidget
import traitlets

from pylabrobot.resources import Resource

from .inline import InlineVisualizer
from .transport import VisualizerTransport

_ESM = """
function render({ model, el }) {
  // No visible UI: the deck is a sibling iframe owned by the parent page. This
  // widget is only the transport between the kernel and that iframe.
  el.style.display = "none";

  // Tell the parent page this widget's frontend is mounted (BRIDGE_READY). The
  // parent queues visualizer events until BOTH the deck and this widget are
  // ready, then it flushes and tells us -- see the parent's relay script.
  window.parent.postMessage({ __plrBridgeUp: true }, "*");

  // Parent -> widget: both sides ready. Signal Python so the transport stops
  // buffering and replays what it held.
  window.addEventListener("message", (e) => {
    if (e.data && e.data.__plrReady) model.send({ ready: true });
  });

  // Python -> parent: every event, immediately. The parent holds the queue, so
  // there is no widget-side buffering to get out of sync with the deck.
  model.on("msg:custom", (msg) => {
    window.parent.postMessage(msg, "*");
  });
}
export default { render };
"""


class JupyterLiteBridgeWidget(anywidget.AnyWidget):
  """Invisible passthrough widget; the transport for the hosted demo."""

  _esm = _ESM
  ready = traitlets.Bool(False).tag(sync=True)


class JupyterLiteBridgeTransport(VisualizerTransport):
  """Deliver visualizer events to a deck iframe on the parent page.

  Args:
    name: Only used for parity with other transports; nothing is shown.
    title: Notebook-side title, unused but kept for symmetry.
  """

  def __init__(self, name: str = "PyLabRobot", title: str = "Deck"):
    self.widget = JupyterLiteBridgeWidget()
    self._title = title
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

    display(self.widget)

  async def emit(self, message: str) -> None:
    if not self._ready:
      self._log.append(message)
    self.widget.send({"__plrEvent": message})

  async def stop(self) -> None:
    self._log.clear()
    self._ready = False


class BrowserVisualizer(InlineVisualizer):
  """The workshop ``Visualizer`` under JupyterLite: bridge-backed, no edits.

  The workshops construct ``vis = Visualizer(resource=lh)`` and the name is
  imported from ``pylabrobot.visualizer.visualizer``. :func:`patch_visualizer`
  swaps that name to this class so the *same notebook* runs unmodified in a real
  kernel (stock ``Visualizer``) or in the browser (this, eventing to the deck
  iframe via :class:`JupyterLiteBridgeTransport`).
  """

  def __init__(self, resource: Resource, **kwargs):
    kwargs.pop("transport", None)  # the bridge is always the transport here
    super().__init__(resource=resource, transport=JupyterLiteBridgeTransport(name="Deck"), **kwargs)


def patch_visualizer() -> None:
  """Make ``pylabrobot.visualizer.visualizer.Visualizer`` resolve to
  :class:`BrowserVisualizer` in this interpreter.

  Call this in the notebook's bootstrap cell *before* any workshop cell that
  imports ``Visualizer``. ``InlineVisualizer`` subclasses ``Visualizer``, so
  isinstance checks and pylabrobot's internals keep working.
  """
  import pylabrobot.visualizer.visualizer as _visualizer_module

  _visualizer_module.Visualizer = BrowserVisualizer
  print("visualizer patched for the browser bridge")

