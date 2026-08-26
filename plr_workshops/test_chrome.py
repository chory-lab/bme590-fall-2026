"""Verify the deck-first chrome and the auto-fit patch.

Both features work by *appending* to the stock page: a stylesheet that hides
panels by id, and a script that calls lib.js's own ``fitToViewport()`` on
resize. Neither edits ``lib.js``, ``vis.js`` or ``main.css``, which is what keeps
upstream upgrades a drop-in -- but it also means both depend on element ids and
one function name staying put.

So the real job here is to fail loudly when an upgrade moves any of them. A
silent miss looks like "the Workcell Tree came back" weeks after the upgrade
that caused it.

Run: python -m plr_workshops.test_chrome
"""

import re

from .frontend import (
  _CHROME_HIDE,
  _CHROME_HIDE_CLASSES,
  _CHROME_KEEP,
  _CHROME_TOGGLES,
  CHROME_LEVELS,
  _read,
  build_page,
)


def main():
  stock = _read("index.html")
  lib = _read("lib.js")
  css = _read("main.css")

  # -- the anchors, checked against upstream directly --
  for element, what in _CHROME_HIDE.items():
    assert f'id="{element}"' in stock, f"stock page has no #{element} ({what})"
  for element in _CHROME_KEEP + _CHROME_TOGGLES:
    assert f'id="{element}"' in stock, f"stock page has no #{element}"

  # Class anchors: these panels have no fixed id, so the class is the contract.
  for klass, what in _CHROME_HIDE_CLASSES.items():
    assert f".{klass}" in css, f"main.css no longer styles .{klass} ({what})"
    assert klass in lib, f"lib.js no longer builds .{klass} ({what})"

  # Both toggles must sit outside everything they reveal, or hiding by default
  # is a one-way door.
  for aside in ("toolbar-left", "sidepanel", "toolbar"):
    start = stock.find(f'<aside id="{aside}"')
    assert start >= 0, f"#{aside} is no longer an <aside>"
    end = stock.find("</aside>", start)
    for toggle in _CHROME_TOGGLES:
      assert f'id="{toggle}"' not in stock[start:end], (
        f"#{toggle} moved inside #{aside}; hiding #{aside} would strip the way back"
      )

  # Auto-fit calls upstream's own reset-view function and reads its stage.
  assert re.search(r"\bfunction fitToViewport\(\)", lib), "lib.js lost fitToViewport()"
  assert re.search(r"^var stage;", lib, re.M), "lib.js no longer declares a global stage"

  # The drift auto-fit corrects: upstream resizes the stage but never re-fits.
  observer = lib[lib.find("new ResizeObserver") : lib.find("resizeObserver.observe")]
  assert "stage.width(" in observer, "lib.js's ResizeObserver changed shape"
  assert "fitToViewport" not in observer, (
    "upstream now re-fits on resize -- the auto-fit patch is redundant, drop it"
  )
  print(f"anchors         -> {len(_CHROME_HIDE)} hidden, {len(_CHROME_KEEP)} kept, "
        f"{len(_CHROME_TOGGLES)} toggles, fitToViewport() + global stage")

  # -- levels --
  pages = {level: build_page(chrome=level) for level in CHROME_LEVELS}

  for level, html in pages.items():
    assert 'id="plr-autofit"' in html, f"chrome={level!r} dropped auto-fit"
    assert "fitToViewport()" in html, f"chrome={level!r} never calls the fit"

  assert 'id="plr-chrome"' not in pages["full"], "chrome='full' must not hide anything"
  for level in ("deck", "bare"):
    html = pages[level]
    assert 'id="plr-chrome"' in html, f"chrome={level!r} has no chrome stylesheet"
    for element in _CHROME_HIDE:
      assert f"body.plr-deck-first #{element} " in html or (
        f"body.plr-deck-first #{element}," in html
      ), f"chrome={level!r} does not hide #{element}"
    for klass in _CHROME_HIDE_CLASSES:
      assert f"body.plr-deck-first .{klass}" in html, f"chrome={level!r} does not hide .{klass}"
    for element in _CHROME_KEEP:
      assert f"plr-deck-first #{element} " not in html, f"chrome={level!r} hides #{element}"

  assert "plr-bare" in pages["bare"] and ".navbar { display: none" in pages["bare"]
  assert 'classList.add("plr-bare")' in pages["bare"]
  assert 'root.classList.add("plr-bare")' not in pages["deck"].split('LEVEL === "bare"')[0]

  # The reveal path has to survive: hidden-by-default is only acceptable because
  # one click brings everything back.
  for toggle in _CHROME_TOGGLES:
    assert f'"{toggle}"' in pages["deck"], f"chrome='deck' does not wire up #{toggle}"
  assert 'removeEventListener("click", reveal, true)' in pages["deck"], (
    "the reveal handler must detach, or the stock toggles never take over"
  )

  # Upstream's collapsed rules are what make the panels reopen cleanly; if they
  # go, the stock toggle buttons stop working and hiding is no longer reversible.
  for rule in ("#sidepanel.collapsed", "#toolbar-left.collapsed"):
    assert rule in css, f"main.css lost {rule}; the stock toggles no longer reopen"

  # How much horizontal room "deck" actually buys back, read off upstream's CSS
  # rather than asserted, so the number stays honest across upgrades.
  widths = {}
  for element in ("toolbar-left", "sidepanel", "toolbar"):
    block = css[css.find(f"#{element} {{") :]
    block = block[: block.find("}")]
    found = re.search(r"^\s*width: (\d+)px", block, re.M)
    if found:
      widths[element] = found.group(1)
  reclaimed = sum(int(w) for w in widths.values())
  assert reclaimed > 300, f"only {reclaimed}px reclaimed; the chrome widths moved"
  print(f"chrome levels   -> {', '.join(CHROME_LEVELS)}; "
        f"deck/bare reclaim {reclaimed}px of width ({widths})")

  # -- still self-contained --
  from .frontend import unresolved_local_refs

  for level, html in pages.items():
    assert not unresolved_local_refs(html), f"chrome={level!r} broke self-containment"

  try:
    build_page(chrome="nope")
  except ValueError as exc:
    assert "chrome must be one of" in str(exc)
  else:
    raise AssertionError("an unknown chrome level must be rejected")

  print("\nChrome + auto-fit check passed.")


if __name__ == "__main__":
  main()
