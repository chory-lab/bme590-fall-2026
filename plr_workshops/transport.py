"""Transports for delivering visualizer events to a frontend.

PyLabRobot's :class:`~pylabrobot.visualizer.visualizer.Visualizer` renders entirely
in the browser: ``lib.js`` holds all the drawing code and consumes a stream of
``{id, version, event, data}`` messages through a single entry point,
``processCentralEvent(event, data)``. The websocket server is only the pipe.

A transport is that pipe, abstracted. Each one receives the exact JSON string the
websocket path would have sent, so the frontend contract is unchanged and no
JavaScript needs modifying.
"""

import abc
import json
from typing import Any, Dict, List


class VisualizerTransport(abc.ABC):
  """Delivers visualizer messages to a frontend.

  Implementations must be usable from within a running asyncio event loop and
  must preserve message ordering: the frontend applies events incrementally, so
  a reordered ``set_state`` paints stale data.
  """

  @abc.abstractmethod
  async def start(self) -> None:
    """Mount the frontend and make it ready to receive messages."""

  @abc.abstractmethod
  async def emit(self, message: str) -> None:
    """Deliver one serialized message.

    Args:
      message: A JSON string of the form ``{"id", "version", "event", "data"}``,
        byte-identical to what the websocket server would have sent.
    """

  @abc.abstractmethod
  async def stop(self) -> None:
    """Tear down the frontend. Must be safe to call more than once."""


class RecordingTransport(VisualizerTransport):
  """Captures the event stream in memory instead of rendering it.

  This is the transport used to test the visualizer shim without a browser: the
  event stream is the contract every other transport delivers, so asserting on it
  here validates all of them.
  """

  def __init__(self):
    self.messages: List[Dict[str, Any]] = []
    self.started = False
    self.stopped = False

  async def start(self) -> None:
    self.started = True

  async def emit(self, message: str) -> None:
    self.messages.append(json.loads(message))

  async def stop(self) -> None:
    self.stopped = True

  # -- inspection helpers, for tests and debugging --

  @property
  def events(self) -> List[str]:
    """The event names in order, e.g. ``["set_root_resource", "set_state", ...]``."""
    return [m["event"] for m in self.messages]

  def of_type(self, event: str) -> List[Dict[str, Any]]:
    """Every message with the given event name."""
    return [m for m in self.messages if m["event"] == event]

  def clear(self) -> None:
    self.messages.clear()
