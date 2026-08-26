"""Verify PyodideTransport mounts the visualizer and streams events into it.

Runs in CPython with a fake ``js``/``pyodide.ffi`` module injected, since the
transport's browser calls only happen inside its methods. This proves the
message path (postMessage to the iframe, ready handshake, queue-and-replay)
that the demo page relies on.
"""

import asyncio
import json
import sys
import types

# --- fake browser ---
class _FakeEventTarget:
  def __init__(self):
    self.listeners = {}
    self.posted = []

  def addEventListener(self, name, fn, *_):
    self.listeners.setdefault(name, []).append(fn)

  def removeEventListener(self, name, fn, *_):
    self.listeners.setdefault(name, []).remove(fn)

  def dispatch(self, name, data):
    evt = data if isinstance(data, _FakeMessageEvent) else _FakeMessageEvent(data)
    for fn in self.listeners.get(name, []):
      fn(evt)

  def postMessage(self, payload, _target):
    self.posted.append(payload)


class _FakeMessageEvent:
  def __init__(self, data):
    # mimic a JS object whose keys are reachable as attributes (Pyodide's js
    # proxy does exactly this), plus a JS-free dict for postMessage payloads.
    self.data = _JsLike(data) if isinstance(data, dict) else data


class _JsLike:
  """Attr access over a dict, like a Pyodide JsProxy for a plain object."""

  def __init__(self, mapping):
    self._m = mapping

  def __getattr__(self, name):
    if name in self._m:
      return self._m[name]
    raise AttributeError(name)


class _FakeElement(_FakeEventTarget):
  def __init__(self, tag):
    super().__init__()
    self.tag = tag
    self.id = None
    self.parentNode = None
    self.children = []
    self.contentWindow = _FakeEventTarget()

  def setAttribute(self, name, value):
    setattr(self, "_attr_" + name, value)

  def getAttribute(self, name):
    return getattr(self, "_attr_" + name, None)

  def appendChild(self, child):
    child.parentNode = self
    self.children.append(child)
    if child.id:
      _js.document._elements[child.id] = child

  def removeChild(self, child):
    child.parentNode = None
    if child in self.children:
      self.children.remove(child)
    if child.id in _js.document._elements:
      del _js.document._elements[child.id]


class _FakeDocument(_FakeEventTarget):
  def __init__(self):
    super().__init__()
    self._elements = {}

  def getElementById(self, ident):
    return self._elements.get(ident)

  def setElement(self, ident, el):
    self._elements[ident] = el

  def createElement(self, tag):
    return _FakeElement(tag)


_js = types.ModuleType("js")
_js.window = _FakeEventTarget()
_js.document = _FakeDocument()
sys.modules["js"] = _js

class _FakeProxy:
  """Stands in for pyodide.ffi.create_proxy's owned JsProxy.

  Real Pyodide destroys a *borrowed* proxy the moment the JS call that received
  it returns, which silently kills any listener registered that way. Modelling
  the ownership here keeps that bug from coming back: a proxy that is called
  after destroy() raises, exactly as the real one does.
  """

  def __init__(self, fn):
    self._fn = fn
    self.destroyed = False

  def __call__(self, *args, **kwargs):
    if self.destroyed:
      raise RuntimeError("This borrowed proxy was automatically destroyed")
    return self._fn(*args, **kwargs)

  def destroy(self):
    self.destroyed = True


_js.Object = types.SimpleNamespace(fromEntries=dict)

_ffi = types.ModuleType("pyodide.ffi")
def _to_js(obj, dict_converter=None):
  """Stand-in for pyodide.ffi.to_js.

  The real one turns a dict into a JS ``Map`` unless a ``dict_converter`` is
  given. postMessage cannot structured-clone a Map (DataCloneError), and the
  iframe shim reads ``msg.__plrEvent`` as a property, which a Map does not
  have — so a converted dict is the only thing that works in a browser. Refuse
  the default here rather than let a test pass on a payload the browser drops.
  """
  if isinstance(obj, dict) and dict_converter is None:
    raise TypeError("to_js(dict) without dict_converter yields a JS Map, "
                    "which postMessage cannot clone")
  return dict_converter(obj.items()) if isinstance(obj, dict) else obj
_ffi.to_js = _to_js
_ffi.create_proxy = _FakeProxy
_ffi.__package__ = "pyodide"
_ffi.__path__ = []

_pyodide = types.ModuleType("pyodide")
_pyodide.__path__ = []
_pyodide.__package__ = "pyodide"
_pyodide.ffi = _ffi
sys.modules["pyodide"] = _pyodide
sys.modules["pyodide.ffi"] = _ffi

from .pyodide_transport import PyodideTransport


async def main():
  container = _FakeElement("div")
  container.id = "plr-deck"
  _js.document.setElement("plr-deck", container)

  t = PyodideTransport(container_id="plr-deck", name="demo")
  await t.start()

  # the listener must be an owned proxy, or it is dead on arrival in Pyodide
  listener = _js.window.listeners["message"][0]
  assert isinstance(listener, _FakeProxy), "listener was not wrapped in create_proxy"
  assert not listener.destroyed

  # transport must have mounted an iframe into the container
  frame = _js.document._elements["plr-deck-frame"]
  assert frame is not None, "iframe not created"
  assert frame.parentNode is container, "iframe not appended to container"
  assert "srcdoc" in frame.__dict__ or "_attr_srcdoc" in frame.__dict__
  page = frame.getAttribute("srcdoc")
  assert page and "processCentralEvent" in page, "srcdoc not the visualizer page"

  # emit before ready -> queued, not delivered
  await t.emit('{"id":1,"version":"0.1.0","event":"set_root_resource","data":{}}')
  assert frame.contentWindow.posted == [], "pre-ready message leaked"

  # simulate the iframe signaling ready
  _js.window.dispatch("message", _FakeMessageEvent({"__plrReady": True}))
  assert frame.contentWindow.posted, "queued messages not replayed on ready"
  first = frame.contentWindow.posted[0]
  assert first["__plrEvent"] == '{"id":1,"version":"0.1.0","event":"set_root_resource","data":{}}'

  # after ready, messages deliver immediately
  await t.emit('{"id":2,"version":"0.1.0","event":"set_state","data":{"a":1}}')
  assert frame.contentWindow.posted[1]["__plrEvent"].startswith('{"id":2')

  # a render-error ack is surfaced, not swallowed
  _js.window.dispatch("message", _FakeMessageEvent({"__plrAck": '{"success":false,"error":"boom"}'}))

  # the deck fills its pane rather than assuming a fixed height
  assert "height: 100%" in frame.getAttribute("style"), "iframe does not fill the container"

  await t.stop()
  assert frame.parentNode is None, "iframe not torn down"
  assert not _js.window.listeners.get("message"), "listener not removed"
  assert listener.destroyed, "proxy leaked; every start() would add another listener"

  print("mount+stream OK: srcdoc page, owned proxy, ready handshake, queue/replay, teardown")


if __name__ == "__main__":
  asyncio.run(main())
  print("PyodideTransport check passed.")
