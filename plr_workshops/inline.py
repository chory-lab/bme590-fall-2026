"""A Visualizer that renders in-process instead of over a websocket server.

The stock :class:`~pylabrobot.visualizer.visualizer.Visualizer` starts an HTTP file
server and a websocket server on background threads and opens a browser window.
None of that is possible in a browser runtime (Pyodide), and none of it is wanted
in a notebook where the frontend is already on the page.

:class:`InlineVisualizer` keeps every bit of PyLabRobot's event generation --
resource callbacks, serialization, state batching -- and swaps only the delivery
mechanism for a :class:`~plr_workshops.transport.VisualizerTransport`.
"""

from typing import Any, Dict, Optional

from pylabrobot.resources import Resource
from pylabrobot.visualizer.visualizer import Visualizer

from .transport import VisualizerTransport


class InlineVisualizer(Visualizer):
  """A Visualizer that delivers events through a transport rather than a websocket.

  Args:
    resource: The root resource to visualize, usually the ``LiquidHandler``.
    transport: Where to deliver events. See :mod:`plr_workshops.transport`.
    name: Header name for the frontend. Defaults to stack detection, which is
      unreliable outside a normal script; pass it explicitly when that matters.

  Note:
    ``send_command(..., wait_for_response=True)`` returns ``None`` here. The
    websocket path round-trips to the browser for an acknowledgement; an inline
    transport has no such channel. Nothing inside ``Visualizer`` awaits a
    response -- every internal call is already ``wait_for_response=False``.
  """

  def __init__(
    self,
    resource: Resource,
    transport: VisualizerTransport,
    name: Optional[str] = None,
    **kwargs,
  ):
    # open_browser is meaningless without a file server to open, and the port
    # arguments are inert once the servers are gone.
    kwargs.pop("open_browser", None)
    super().__init__(resource=resource, open_browser=False, name=name, **kwargs)
    self._transport = transport

  async def setup(self):
    """Mount the frontend and push the initial deck state.

    Deliberately does not call ``super().setup()``, which would start the
    websocket and file servers.
    """
    if self.setup_finished:
      raise RuntimeError("The visualizer has already been started.")

    # Resource callbacks schedule their sends onto self.loop via
    # run_coroutine_threadsafe / call_soon_threadsafe. Pointing it at the
    # notebook's own running loop keeps that machinery -- including the
    # set_state batching that collapses a 96-channel pickup into one message --
    # working unchanged.
    self._loop = self._get_running_loop()

    await self._transport.start()
    await self._send_resources_and_state()
    self.setup_finished = True

  async def send_command(
    self,
    event: str,
    data: Optional[Dict[str, Any]] = None,
    wait_for_response: bool = True,
  ) -> None:
    """Deliver an event to the frontend through the transport.

    Uses the parent's ``_assemble_command`` so the wire format -- id, version
    and float sanitization -- is identical to the websocket path.
    """
    serialized, _id = self._assemble_command(event=event, data=data or {})
    await self._transport.emit(serialized)
    return None

  def has_connection(self) -> bool:
    """True once a transport is attached. There is no socket to inspect."""
    return self._transport is not None

  async def stop(self):
    """Tear down the transport. No servers, threads or futures to unwind."""
    if not self.setup_finished:
      raise RuntimeError("The visualizer has not been started.")

    await self._transport.stop()

    self.received.clear()
    self._pending_response_ids.clear()
    self._pending_state_updates.clear()
    self._flush_scheduled = False
    self._loop = None
    self.setup_finished = False

  @staticmethod
  def _get_running_loop():
    import asyncio

    try:
      return asyncio.get_running_loop()
    except RuntimeError as e:
      raise RuntimeError(
        "InlineVisualizer.setup() must be awaited from a running event loop "
        "(a notebook cell, or asyncio.run). Resource callbacks are scheduled "
        "onto that loop."
      ) from e
