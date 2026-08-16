"""Kernel startup hook: make the stock ``Visualizer`` render inline, docked.

The workshop notebooks construct ``pylabrobot``'s ``Visualizer`` and ``await
vis.setup()``. Locally that opens a browser window pointed at a websocket
server; in a browser runtime that is impossible. ``InlineVisualizer`` renders
the same deck through a transport instead.

This hook swaps the imported name so the notebooks run **unmodified**::

    from pylabrobot.visualizer.visualizer import Visualizer
    vis = Visualizer(resource=lh)

now yields a subclass that delivers events to a docked widget instead of a
server. Install it once per kernel by placing this module on an IPython
startup path (see :func:`install`), or from the command line via
``plr-workshops``.
"""


def install(transport_factory=None):
  """Patch ``pylabrobot.visualizer.visualizer.Visualizer`` in place.

  After this call, importing ``Visualizer`` in the same process produces an
  :class:`~plr_workshops.inline.InlineVisualizer` bound to a docked
  :class:`~plr_workshops.widget.AnyWidgetTransport`.

  Args:
    transport_factory: A callable ``(name, **kwargs) -> VisualizerTransport``.
      Defaults to a ``split-right`` anywidget sidecar. Tests inject a
      :class:`~plr_workshops.transport.RecordingTransport` through this.
  """
  import pylabrobot.visualizer.visualizer as _visualizer_module

  from .inline import InlineVisualizer
  from .widget import AnyWidgetTransport

  def _default_transport(name, **kwargs):
    return AnyWidgetTransport(name=name, **kwargs)

  factory = transport_factory or _default_transport

  class NotebookVisualizer(InlineVisualizer):
    def __init__(self, resource, transport=None, name=None, **kwargs):
      if transport is None:
        transport = factory(
          name or "PyLabRobot",
          liquid_color=kwargs.get("liquid_color", "F39C12"),
        )
      super().__init__(resource=resource, transport=transport, name=name, **kwargs)

  _visualizer_module.Visualizer = NotebookVisualizer
  return NotebookVisualizer


HOOK_SNIPPET = """\
# Installed by plr-workshops. Renders pylabrobot's Visualizer inline in a
# docked sidecar instead of opening a browser window.
try:
    from plr_workshops.startup import install
    install()
except Exception as exc:  # never break the kernel over a visualizer
    print(f"[plr-workshops] visualizer patch skipped: {exc}")
"""
