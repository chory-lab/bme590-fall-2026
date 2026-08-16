"""Browser-runnable tooling for the BME 590 PyLabRobot workshops.

The visualizer's renderer is already client-side; only its transport assumed a
server. :class:`~plr_workshops.inline.InlineVisualizer` makes that transport
pluggable so the same deck view works in a notebook widget, in Pyodide, or in a
test harness with no browser at all.
"""

from .frontend import build_page, build_replay_page
from .inline import InlineVisualizer
from .pyodide_transport import PyodideTransport
from .transport import RecordingTransport, VisualizerTransport

__all__ = [
  "InlineVisualizer",
  "PyodideTransport",
  "RecordingTransport",
  "VisualizerTransport",
  "build_page",
  "build_replay_page",
]

# AnyWidgetTransport is imported lazily: anywidget and sidecar are only needed in
# a notebook, and the package must stay importable in a bare CI environment.

