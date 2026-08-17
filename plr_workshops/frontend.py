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


# --------------------------------------------------------------------------
# Deck-first chrome
# --------------------------------------------------------------------------
#
# The stock page is a standalone app: a 60 px navbar, a 48 px tool rail either
# side and a 310 px Workcell Tree. Embedded in a notebook pane that leaves the
# Konva canvas a sliver. Everything below hides that chrome *by addition* --
# one stylesheet and one script appended before </body> -- so lib.js, vis.js and
# main.css stay byte-for-byte upstream.
#
# Nothing is removed from the DOM and no stock handler is replaced, so the
# panels keep working; they simply start closed.

# id -> what it is. Keys are asserted against the stock page at build time: an
# upstream rename fails loudly here instead of silently un-hiding a panel.
_CHROME_HIDE = {
  "toolbar-left": "left tool rail (select / locate / GIF)",
  "toolbar": "right tool rail (tree + search buttons)",
  "sidepanel": "Workcell Tree and resource search",
  "coords-panel": "coordinate readout",
  "gif-panel": "GIF export",
  "navbar-lh-machine-tools": "floating pipette-head panel, which overlaps the deck",
}

# Hidden by class, not id: these panels are built per resource at runtime
# (``single-channel-dropdown-<deck>`` and friends), so there is no fixed id to
# target. They anchor to buttons in #navbar-lh-machine-tools, which is hidden
# above, and they open by default -- leaving three opaque cards floating over
# the middle of the deck with nothing to dismiss them.
_CHROME_HIDE_CLASSES = {
  "machine-tool-dropdown": "pipette-head / arm panels floating over the deck",
}

# The deck and the overlays that explain it. These must survive every level.
_CHROME_KEEP = ("kanvas", "zoom-controls", "home-button", "scale-bar", "axis-legend")

# Both live in the navbar, outside every element they reveal -- which is what
# makes "hidden by default" recoverable rather than a one-way door.
_CHROME_TOGGLES = ("toolbar-left-toggle", "toolbar-right-toggle")

CHROME_LEVELS = ("full", "deck", "bare")

_CHROME_STYLE = """
<style id="plr-chrome">
__HIDDEN__ { display: none !important; }
  /* The navbar is the only way back, so make it cheap rather than absent. */
  body.plr-deck-first .navbar { height: 40px; }
  body.plr-deck-first .content { height: calc(100vh - 40px); }
  body.plr-deck-first .navbar-brand img { height: 26px; }
  body.plr-bare .navbar { display: none !important; }
  body.plr-bare .content { height: 100vh; }
</style>
"""

_CHROME_SCRIPT = """
<script id="plr-chrome-script">
(function () {
  var LEVEL = "__LEVEL__";
  var root = document.body;
  root.classList.add("plr-deck-first");
  if (LEVEL === "bare") root.classList.add("plr-bare");

  // First click on either navbar toggle hands the whole toolset back, then gets
  // out of the way: from that point the stock handlers own the panels. Capture
  // phase + stopPropagation, because the stock listener on the same button would
  // otherwise interpret this click as "collapse the thing I just revealed".
  ["__TOGGLES__"].forEach(function (id) {
    var btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener("click", function reveal(e) {
      e.stopPropagation();
      e.preventDefault();
      root.classList.remove("plr-deck-first", "plr-bare");
      btn.removeEventListener("click", reveal, true);
    }, true);
  });
})();
</script>
"""

# fitToViewport() runs once, from vis.js's setRootResource. lib.js's own
# ResizeObserver then resizes the Konva stage on every layout change but never
# re-fits and never repositions it, so the deck keeps the scale and absolute
# position it happened to get at first paint -- and drifts out of view as soon as
# the pane changes width (split drag, sidecar open, window resize, or the chrome
# above collapsing). Re-fit on resize, but stop the moment the student pans or
# zooms, so auto-fit never fights a deliberate view. The home button, which
# already means "reset the view", takes auto-fit back.
_AUTOFIT_SCRIPT = """
<script id="plr-autofit">
(function () {
  var auto = true;
  var timer = null;

  // fitToViewport() subtracts 40px of padding per side with no floor, so a pane
  // narrower than 80px yields a negative scale and the deck renders mirrored.
  // Upstream never hit that because it fit exactly once, at setup; re-fitting on
  // every resize means a collapsed split pane, a minimised window or a hidden
  // tab all reach it. Below that, keep the last good view.
  var MIN_PX = 120;

  function refit() {
    if (!auto || typeof fitToViewport !== "function" || !stage) return;
    if (stage.width() < MIN_PX || stage.height() < MIN_PX) return;
    fitToViewport();
  }

  // Debounced: a split drag fires the observer continuously, and lib.js's own
  // observer has to update stage.width()/height() before a fit means anything.
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(refit, 80);
  }

  function whenReady(cb) {
    if (typeof stage !== "undefined" && stage) return cb();
    setTimeout(function () { whenReady(cb); }, 50);
  }

  window.addEventListener("load", function () {
    var canvas = document.getElementById("kanvas");
    if (!canvas || typeof ResizeObserver === "undefined") return;

    whenReady(function () {
      stage.on("wheel", function () { auto = false; });
      stage.on("dragstart", function () { auto = false; });
      ["zoom-in-btn", "zoom-out-btn"].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.addEventListener("click", function () { auto = false; });
      });
      var home = document.getElementById("home-button");
      if (home) home.addEventListener("click", function () { auto = true; });

      new ResizeObserver(schedule).observe(canvas);
      schedule();  // the first fit ran against a pane that may not have settled
    });
  });

  // For tests and for anyone driving the page from the host frame.
  window.__plrAutoFit = {
    refit: function () { auto = true; refit(); },
    get enabled() { return auto; },
    get minPx() { return MIN_PX; },
  };
})();
</script>
"""


# --------------------------------------------------------------------------
# Third-party assets
# --------------------------------------------------------------------------
#
# The stock page pulls five files from three CDNs. Only one of them earns its
# place. See vendor.DROPPED for the evidence behind each removal; test_vendor.py
# re-derives it from upstream on every run, so if PLR starts using bootstrap
# icons (say) the build fails rather than shipping a page missing its glyphs.

# Bootstrap supplies eight classes to the stock page, of which only the navbar
# group survives in deck-first mode. 164 KB of framework for that is a bad
# trade in a bundle meant to work offline, so these are the rules it provided,
# written out. main.css already restyles .navbar on top of these.
_BOOTSTRAP_SHIM = """
<style id="plr-bootstrap-shim">
  /* Bootstrap's only unconditional contribution to this page was the body font.
     Dropping bootstrap.min.css (164 KB for 8 classes) therefore handed the
     navbar back to the browser default -- Times -- so "PyLabRobot Visualizer"
     and the deck name rendered in serif. Restore the stack bootstrap sets,
     minus the CSS custom properties nothing else here uses. */
  body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
            Arial, "Noto Sans", sans-serif; font-size: 1rem; font-weight: 400;
            line-height: 1.5; color: #212529; }
  .navbar { position: relative; display: flex; flex-wrap: wrap;
            align-items: center; justify-content: space-between; }
  .navbar > .container-fluid { display: flex; flex-wrap: inherit;
            align-items: center; justify-content: space-between; }
  .container-fluid { width: 100%; padding-right: .75rem; padding-left: .75rem;
            margin-right: auto; margin-left: auto; }
  .bg-light { background-color: #f8f9fa; }
  .navbar-brand { padding-top: .3125rem; padding-bottom: .3125rem;
            margin-right: 1rem; font-size: 1rem; font-weight: 600;
            letter-spacing: -.01em; text-decoration: none;
            white-space: nowrap; color: #212529; }
  /* The deck's name, rendered beside the brand ({{ source_filename }}). */
  #source-filename { font-size: .8125rem; font-weight: 500; letter-spacing: .04em;
            text-transform: uppercase; color: #5b6472; }
  .btn { display: inline-block; font-weight: 400; line-height: 1.5;
            color: #212529; text-align: center; vertical-align: middle;
            cursor: pointer; user-select: none; background-color: transparent;
            border: 1px solid transparent; padding: .375rem .75rem;
            font-size: 1rem; border-radius: .25rem;
            transition: color .15s ease-in-out, background-color .15s ease-in-out,
                        border-color .15s ease-in-out, box-shadow .15s ease-in-out; }
  .btn-primary { color: #fff; background-color: #0d6efd; border-color: #0d6efd; }
  .btn-danger  { color: #fff; background-color: #dc3545; border-color: #dc3545; }
  .btn-success { color: #fff; background-color: #198754; border-color: #198754; }
</style>
"""


def _read(name, binary=False):
  path = os.path.join(VISUALIZER_DIR, name)
  with open(path, "rb" if binary else "r", encoding=None if binary else "utf-8") as fh:
    return fh.read()


def _data_uri(rel_path, prefer_vendored=None):
  """Inline a PNG as a data URI.

  ``prefer_vendored`` names a build-time-shrunk copy under
  ``plr_workshops/_vendored/`` to use instead of the stock image. The logo is
  500x500 and lands in a 42px navbar slot, and the page inlines it twice, so at
  full size it was 432 KB of an 796 KB page. Resizing has to happen at build
  time -- this function also runs inside Pyodide, where Pillow does not exist.
  """
  raw = None
  if prefer_vendored is not None:
    from . import vendor

    candidate = vendor.INLINE_DIR / prefer_vendored
    if candidate.is_file():
      raw = candidate.read_bytes()
  if raw is None:
    raw = _read(rel_path, binary=True)
  return "data:image/png;base64," + base64.b64encode(raw).decode()


def _splice(html, tag_pattern, replacement):
  """Swap a tag for literal text.

  The replacement goes through a lambda because re.sub parses backslash escapes
  in a string replacement, and lib.js is full of \\u sequences.
  """
  return re.sub(tag_pattern, lambda _m: replacement, html)


def _chrome_block(html, chrome):
  """Return the stylesheet + scripts that make the page deck-first.

  Raises:
    ValueError: if ``chrome`` is not one of :data:`CHROME_LEVELS`, or if the
      stock page no longer contains an element this depends on. The second case
      is the point: a silent miss would look like "the panel came back" long
      after the upgrade that caused it.
  """
  if chrome not in CHROME_LEVELS:
    raise ValueError(f"chrome must be one of {CHROME_LEVELS}, got {chrome!r}")

  missing = [
    f'{i} ({what})'
    for i, what in list(_CHROME_HIDE.items())
    + [(k, "deck view") for k in _CHROME_KEEP]
    + [(t, "chrome toggle") for t in _CHROME_TOGGLES]
    if f'id="{i}"' not in html
  ]
  # main.css is inlined by now, so the class anchors are checkable here too.
  missing += [
    f"class {c} ({what})"
    for c, what in _CHROME_HIDE_CLASSES.items()
    if f".{c}" not in html
  ]
  if missing:
    raise ValueError(
      "the visualizer page no longer has: " + ", ".join(missing) + ". "
      "Upstream renamed or dropped these; update _CHROME_HIDE/_CHROME_KEEP."
    )

  # Auto-fit is worth having at every level, including "full": the drift it
  # corrects is upstream behaviour, not something the chrome change introduced.
  block = _AUTOFIT_SCRIPT
  if chrome == "full":
    return block

  selectors = ",\n".join(
    [f"  body.plr-deck-first #{i}" for i in _CHROME_HIDE]
    + [f"  body.plr-deck-first .{c}" for c in _CHROME_HIDE_CLASSES]
  )
  style = _CHROME_STYLE.replace("__HIDDEN__", selectors)
  script = _CHROME_SCRIPT.replace("__LEVEL__", chrome).replace(
    '"__TOGGLES__"', ", ".join(f'"{t}"' for t in _CHROME_TOGGLES)
  )
  return style + script + block


def build_page(name="PyLabRobot", liquid_color="F39C12", include_gif_export=False,
               chrome="deck"):
  """Return the visualizer frontend as one self-contained HTML string.

  Args:
    name: Shown in the page header. Fills the ``{{ source_filename }}``
      placeholder that the stock file server substitutes on the fly.
    liquid_color: Hex fill (no ``#``) for wells, troughs and tubes. Leaving this
      unsubstituted renders liquid with an invalid color, so it must be set.
    include_gif_export: Inline ``gif.js``. Off by default -- GIF export also needs
      ``gif.worker.js`` loaded from a blob URL, which a srcdoc iframe cannot
      provide. Left out, the export button is simply inert.
    chrome: How much of the standalone app's furniture to show.

      - ``"deck"`` (default): the deck and its overlays. Both tool rails, the
        Workcell Tree, the coordinate and GIF panels and the pipette-head panel
        start hidden; a slim navbar remains, and clicking either of its toggle
        buttons brings the full toolset back.
      - ``"bare"``: as above, plus no navbar -- nothing but the deck, and no way
        to reveal the rest. For a thumbnail or a replay, not for students.
      - ``"full"``: stock. Still gets the auto-fit fix.

  The page is entirely self-contained: no CDN, no file server, no network. Konva
  is inlined from ``plr_workshops/vendor/`` (populated by
  :mod:`plr_workshops.vendor`); the other four CDN references the stock page
  makes are dropped as unused -- see :data:`plr_workshops.vendor.DROPPED`.
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

  # -- third-party: inline what is used, drop what is not --
  from . import vendor

  html = _splice(
    html,
    r'<script src="https://unpkg\.com/konva@8[^"]*"></script>',
    "<script>\n" + vendor.read_inline("konva.min.js") + "\n</script>",
  )
  # bootstrap's stylesheet is replaced by the shim; the other three go entirely.
  html = _splice(
    html,
    r'<link[^>]*href="https://cdn\.jsdelivr\.net/npm/bootstrap@[^"]*"[^>]*/?>',
    _BOOTSTRAP_SHIM,
  )
  for pattern in (
    r'<link[^>]*href="https://cdn\.jsdelivr\.net/npm/bootstrap-icons@[^"]*"[^>]*/?>',
    r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/jszip/[^"]*"></script>',
    r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/html2canvas/[^"]*"></script>',
  ):
    html = _splice(html, pattern, "")

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
  html = html.replace(
    "/favicon.png", _data_uri(os.path.join("img", "logo.png"), prefer_vendored="logo.png")
  )

  # The arm and pipette artwork is only ever drawn inside the machine-tool
  # panels, which deck-first mode hides. Inlining 99 KB of base64 for panels
  # nobody will see is pure weight, so it goes in unless the chrome is stock.
  for img in ("integrated_arm.png", "multi_channel_pipette.png", "single_channel_pipette.png"):
    replacement = _data_uri(os.path.join("img", img)) if chrome == "full" else ""
    html = html.replace(f"img/{img}", replacement)

  # Appended last, so it overrides main.css without editing it. _chrome_block
  # checks the stock page still has the ids it targets before we get here.
  html = html.replace("</body>", _chrome_block(html, chrome) + "</body>")

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


def remote_refs(html):
  """Return every absolute URL the page would fetch at load.

  The companion to :func:`unresolved_local_refs`, which only ever looked at
  *relative* paths -- which is exactly why five CDN dependencies sat in this
  page unnoticed until someone tried to run it without a network. Anything
  returned here is a boot-time network dependency.
  """
  return sorted(set(re.findall(r'(?:src|href)="((?:https?:)?//[^"]+)"', html)))
