"""Verify the vendoring decisions still hold against the installed PyLabRobot.

Four of the five libraries the stock visualizer page loads are dropped rather
than vendored, each on a specific claim about how upstream uses them. Those
claims are the whole justification, and none of them is self-evident from
reading our code -- so every one is re-derived here from the upstream source on
each run. If PLR starts using bootstrap icons, or wires JSZip into a working
export, this fails and names the library instead of shipping a page with
missing glyphs or a dead button.

Run: python -m plr_workshops.test_vendor
"""

import re

from .frontend import _read, build_page, remote_refs, unresolved_local_refs
from . import vendor


def main():
  stock = _read("index.html")
  lib = _read("lib.js")
  vis = _read("vis.js")
  css = _read("main.css")
  gif = _read("gif.js")
  everything = stock + lib + vis + css + gif

  # -- every claim in vendor.DROPPED, checked against upstream --
  icons = sorted(set(re.findall(r"\bbi-[a-z0-9-]+", everything)))
  assert not icons, (
    f"bootstrap-icons is dropped but upstream now uses {icons[:5]}; vendor it again"
  )

  assert "JSZip" not in everything, (
    "jszip is dropped but upstream now references the JSZip global; vendor it again"
  )

  # html2canvas may only be reached from the GIF path, which is inert because
  # gif.js is never inlined (it needs a worker a srcdoc iframe cannot provide).
  for match in re.finditer(r"^.*\bhtml2canvas\s*\(", lib, re.M):
    line = lib[: match.start()].count("\n") + 1
    enclosing = _enclosing_function(lib, match.start())
    assert enclosing in ("_captureLoop", "startRecording"), (
      f"html2canvas is dropped as GIF-only, but lib.js:{line} calls it from "
      f"{enclosing}(); vendor it again or narrow the claim"
    )

  used = {c for c in re.findall(r'class="([^"]+)"', stock) for c in c.split()}
  bootstrap_used = used & {
    "navbar", "container-fluid", "bg-light", "navbar-brand",
    "btn", "btn-primary", "btn-danger", "btn-success",
  }
  page = build_page()
  for klass in bootstrap_used:
    assert f".{klass}" in page, f"bootstrap class {klass} is used but the shim does not define it"
  # A class we never anticipated would silently lose its styling.
  unknown = {c for c in used if c.startswith(("btn-", "navbar-", "bg-", "col-", "row", "d-flex"))}
  unexpected = unknown - bootstrap_used - {
    c for c in unknown if f".{c}" in css  # main.css styles it itself
  }
  assert not unexpected, (
    f"the stock page uses bootstrap classes the shim does not cover: {sorted(unexpected)}"
  )
  print(f"dropped         -> {', '.join(sorted(vendor.DROPPED))} "
        f"({len(bootstrap_used)} bootstrap classes shimmed)")

  # -- konva is the one that must be carried, and must actually be present --
  assert "konva.min.js" in vendor.INLINE_ASSETS
  konva = vendor.read_inline("konva.min.js")
  assert "Konva" in konva and len(konva) > 100_000, "the vendored konva looks wrong"
  assert 'src="https://unpkg.com/konva' not in page, "konva is still loaded from a CDN"
  assert "Konva" in page, "konva was dropped from the page entirely"

  # -- the page must reach neither a CDN nor a file server --
  for level in ("deck", "full", "bare"):
    built = build_page(chrome=level)
    assert not remote_refs(built), f"chrome={level!r} still fetches {remote_refs(built)}"
    assert not unresolved_local_refs(built), f"chrome={level!r} is not self-contained"

  deck, full = build_page(chrome="deck"), build_page(chrome="full")
  assert len(deck) < len(full), "deck mode should be smaller: it drops the pipette artwork"
  print(f"page bytes      -> deck {len(deck):,}, full {len(full):,} "
        f"(no CDN, no file server)")

  print("\nVendor check passed.")


def _enclosing_function(source, index):
  """Name of the last function declared before ``index``."""
  names = re.findall(r"^(?:async )?function (\w+)", source[:index], re.M)
  return names[-1] if names else "<top level>"


if __name__ == "__main__":
  main()
