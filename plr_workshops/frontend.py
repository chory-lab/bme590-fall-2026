"""Assemble PyLabRobot's visualizer frontend into a single standalone HTML page.

The stock frontend is a directory of files served over HTTP: ``index.html`` pulls in
``main.css``, ``lib.js`` (the renderer), ``vis.js`` (the websocket client) and a few
images. Without a file server those relative URLs resolve to nothing, so every
serverless target -- an iframe in a notebook widget, a static Pyodide page -- needs
the whole thing folded into one self-contained document.

The one substantive change is the transport. Rather than editing ``vis.js`` (which
also defines ``processCentralEvent`` and the rest of the event handling), a stub
``WebSocket`` class is installed ahead of it. ``vis.js`` then "connects" as usual and
messages are delivered by dispatching events at the stub, so the page behaves exactly
as it would against a real server and ``vis.js`` stays byte-for-byte unmodified.
"""

import base64
import os
import re

from pylabrobot.visualizer import visualizer as _visualizer_module

VISUALIZER_DIR = os.path.dirname(os.path.abspath(_visualizer_module.__file__))

# Installed before vis.js. Stands in for the browser's WebSocket so vis.js runs
# unmodified: openSocket() constructs one of these, gets an "open", and messages
# arrive through the normal addEventListener("message") path.
_SOCKET_SHIM = """
(function () {
  class InlineSocket extends EventTarget {
    constructor() {
      super();
      this.readyState = 1;
      window.__plrSocket = this;
      setTimeout(() => { if (this.onopen) this.onopen({ target: { url: "inline://plr" } }); }, 0);
    }
    send(data) {
      // Acknowledgements from handleEvent. Nothing inline awaits them, but
      // forward to the host so a widget can surface render errors.
      try { parent.postMessage({ __plrAck: data }, "*"); } catch (e) {}
    }
    close() {}
  }
  InlineSocket.OPEN = 1;
  window.WebSocket = InlineSocket;

  // Host -> page. The host posts the same JSON string the websocket would have
  // carried, so vis.js parses it exactly as before.
  window.addEventListener("message", function (e) {
    const msg = e.data;
    if (!msg || typeof msg.__plrEvent !== "string") return;
    const sock = window.__plrSocket;
    if (!sock) return;
    sock.dispatchEvent(new MessageEvent("message", { data: msg.__plrEvent }));
  });

  window.addEventListener("load", function () {
    try { parent.postMessage({ __plrReady: true }, "*"); } catch (e) {}
  });
})();
"""


def _read(name, binary=False):
  path = os.path.join(VISUALIZER_DIR, name)
  with open(path, "rb" if binary else "r", encoding=None if binary else "utf-8") as fh:
    return fh.read()


def _data_uri(rel_path):
  return "data:image/png;base64," + base64.b64encode(_read(rel_path, binary=True)).decode()


def _splice(html, tag_pattern, replacement):
  """Swap a tag for literal text.

  The replacement goes through a lambda because re.sub parses backslash escapes
  in a string replacement, and lib.js is full of \\u sequences.
  """
  return re.sub(tag_pattern, lambda _m: replacement, html)


def build_page(name="PyLabRobot", liquid_color="F39C12", include_gif_export=False):
  """Return the visualizer frontend as one self-contained HTML string.

  Args:
    name: Shown in the page header. Fills the ``{{ source_filename }}``
      placeholder that the stock file server substitutes on the fly.
    liquid_color: Hex fill (no ``#``) for wells, troughs and tubes. Leaving this
      unsubstituted renders liquid with an invalid color, so it must be set.
    include_gif_export: Inline ``gif.js``. Off by default -- GIF export also needs
      ``gif.worker.js`` loaded from a blob URL, which a srcdoc iframe cannot
      provide. Left out, the export button is simply inert.

  Note:
    Bootstrap, Konva and friends are still loaded from their CDNs, exactly as the
    stock page does. That is fine for a networked machine; vendoring them is a
    prerequisite for offline classroom use.
  """
  html = _read("index.html")

  # index.html is a template the stock file server fills in per request. Without
  # a file server we substitute here, or the header shows raw {{ }} markers and
  # wells are filled with the literal string "{{ liquid_color }}".
  # The port values are inert -- nothing dials them -- but vis.js reads the
  # ws_port input during startup, so it has to hold something numeric.
  for placeholder, value in (
    ("{{ source_filename }}", name),
    ("{{ liquid_color }}", liquid_color.strip().lstrip("#")),
    ("{{ ws_port }}", "0"),
    ("{{ fs_port }}", "0"),
  ):
    html = html.replace(placeholder, value)

  # main.css -> inline <style>
  html = _splice(
    html,
    r'<link href="\./main\.css[^"]*" rel="stylesheet" />',
    "<style>\n" + _read("main.css") + "\n</style>",
  )

  # The renderer. Everything the deck view actually draws with lives here.
  html = _splice(
    html,
    r'<script src="\./lib\.js[^"]*"></script>',
    "<script>\n" + _read("lib.js") + "\n</script>",
  )

  # Transport shim ahead of vis.js, then vis.js verbatim.
  html = _splice(
    html,
    r'<script src="\./vis\.js[^"]*"></script>',
    "<script>\n" + _SOCKET_SHIM + "\n</script>\n<script>\n" + _read("vis.js") + "\n</script>",
  )

  # gif.js drives the export button; gif.worker.js is worker code and must never
  # run in window scope, so it is always dropped.
  html = _splice(html, r'<script src="\./gif\.worker\.js"></script>', "")
  html = _splice(
    html,
    r'<script src="\./gif\.js"></script>',
    ("<script>\n" + _read("gif.js") + "\n</script>") if include_gif_export else "",
  )

  # Images: no file server, so fold them in as data URIs.
  html = html.replace("/favicon.png", _data_uri(os.path.join("img", "logo.png")))
  for img in ("integrated_arm.png", "multi_channel_pipette.png", "single_channel_pipette.png"):
    html = html.replace(f"img/{img}", _data_uri(os.path.join("img", img)))

  return html


def build_replay_page(messages, step_ms=0, **page_kwargs):
  """Return a page that replays a captured event stream with no Python behind it.

  Feed it the messages from a
  :class:`~plr_workshops.transport.RecordingTransport`. Useful for eyeballing the
  renderer without a kernel, and the basis of a fully static deck demo.

  Args:
    messages: Message dicts as recorded, in order.
    step_ms: Delay between messages. 0 applies the whole stream at once; a
      positive value plays it back as an animation.
  """
  import json

  page = build_page(**page_kwargs)
  payload = json.dumps([json.dumps(m) for m in messages])
  replay = f"""
<script>
(function () {{
  const stream = {payload};
  window.addEventListener("load", function () {{
    let i = 0;
    (function next() {{
      if (i >= stream.length) {{ window.__plrReplayDone = true; return; }}
      window.postMessage({{ __plrEvent: stream[i++] }}, "*");
      setTimeout(next, {step_ms});
    }})();
  }});
}})();
</script>
"""
  return page.replace("</body>", replay + "</body>")


def unresolved_local_refs(html):
  """Return any local asset URLs the page still depends on.

  A non-empty result means the page is not self-contained and will 404 wherever
  there is no file server -- the exact failure that broke the published site.
  """
  refs = re.findall(r'(?:src|href)="([^"]+)"', html)
  return sorted(
    {
      r
      for r in refs
      if not r.startswith(("http://", "https://", "data:", "#", "//"))
      and r not in ("", "/")
    }
  )
