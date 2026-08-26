"""Fetch the demo's third-party dependencies so it runs with no network.

The demo reached for the network in three places, every single boot: the Pyodide
runtime (~13 MB from jsdelivr), the ``pylabrobot`` wheel from PyPI, and nine
CDN files for CodeMirror and the visualizer page. A classroom with flaky wifi,
or a CDN that moves a path, breaks the whole thing.

Everything is fetched at *build* time into a cache, then copied into the bundle.
Build-time fetching beats committing binaries: ``demo/`` is gitignored output,
so nothing large lands in git, and a cached rebuild is itself offline.

Two destinations, because the assets are consumed differently:

- ``plr_workshops/_vendored/`` -- read by :mod:`plr_workshops.frontend` and inlined
  into the visualizer page. That page is built *inside Pyodide* at runtime, where
  there is no urllib, so these bytes must already be on disk. ``build_demo``
  ships them into the Pyodide filesystem alongside the Python modules.
- ``demo/`` -- plain static files the page loads by URL.

Not everything the stock pages reference is worth carrying. See
:data:`DROPPED` for the four libraries that are provably unused (or that only
serve an already-inert feature) and are dropped rather than vendored.
"""

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

#: Where fetched bytes are kept between builds, so a rebuild needs no network.
CACHE_DIR = Path(os.environ.get("PLR_VENDOR_CACHE", REPO_ROOT / ".vendor-cache"))

#: Inlined into the visualizer page by frontend.py, so it must be on disk before
#: that page is built (which happens inside Pyodide, where urllib does not work).
#: Deliberately not named ``vendor/``: a package directory of that name would
#: shadow this very module on import, which is the same trap that once had a
#: stray ``plr_workshops.py`` shadowing the whole package.
INLINE_DIR = HERE / "_vendored"

PYODIDE_VERSION = "0.26.4"
PYODIDE_CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
PYLABROBOT_VERSION = "0.2.2"

CODEMIRROR = "5.65.16"
_CM = f"https://cdnjs.cloudflare.com/ajax/libs/codemirror/{CODEMIRROR}/"

#: name -> url, inlined straight into the visualizer page.
INLINE_ASSETS = {
  "konva.min.js": "https://unpkg.com/konva@8/konva.min.js",
}

#: relative path under demo/ -> url. Plain static files the notebook page loads.
STATIC_ASSETS = {
  "vendor/codemirror.min.css": _CM + "codemirror.min.css",
  "vendor/codemirror.min.js": _CM + "codemirror.min.js",
  "vendor/python.min.js": _CM + "mode/python/python.min.js",
  "vendor/markdown.min.js": _CM + "mode/markdown/markdown.min.js",
}

#: Referenced by the stock visualizer page but deliberately not vendored.
#: test_vendor.py re-derives each claim from the upstream source, so the day one
#: of them stops being true the build fails instead of quietly shipping a
#: broken page.
DROPPED = {
  "bootstrap-icons": "no bi-* class appears anywhere in the stock page, lib.js or main.css",
  "jszip": "the JSZip global is never referenced by lib.js, vis.js or gif.js",
  "html2canvas": "only called from _captureLoop(), and GIF export is already inert",
  "bootstrap": "eight classes are used; _BOOTSTRAP_SHIM in frontend.py covers them",
}


def _cache_path(url: str) -> Path:
  digest = hashlib.sha256(url.encode()).hexdigest()[:16]
  return CACHE_DIR / f"{digest}-{url.rsplit('/', 1)[-1]}"


def fetch(url: str, *, refresh: bool = False) -> bytes:
  """Return the bytes at ``url``, caching them under :data:`CACHE_DIR`."""
  cached = _cache_path(url)
  if cached.is_file() and not refresh:
    return cached.read_bytes()

  request = urllib.request.Request(url, headers={"User-Agent": "plr-workshops-build"})
  with urllib.request.urlopen(request, timeout=180) as response:
    data = response.read()

  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  cached.write_bytes(data)
  return data


#: PyLabRobot's logo is 500x500 and lands in a 42px navbar slot. The page
#: inlines it twice -- favicon and navbar brand -- so at full size it was 432 KB
#: of an 796 KB page: more than half, for one small image shown once.
LOGO_MAX_PX = 96
LOGO_NAME = "logo.png"


def ensure_inline_assets(*, refresh: bool = False) -> None:
  """Put the inlined assets on disk next to the package."""
  INLINE_DIR.mkdir(parents=True, exist_ok=True)
  for name, url in INLINE_ASSETS.items():
    (INLINE_DIR / name).write_bytes(fetch(url, refresh=refresh))
  _shrink_logo()


def _shrink_logo() -> None:
  """Write a navbar-sized copy of the logo for frontend.py to inline.

  Done here, at build time, rather than in ``build_page``: that function also
  runs *inside Pyodide*, where Pillow does not exist, so a runtime resize would
  silently skip exactly where the bytes matter most.
  """
  from pylabrobot.visualizer import visualizer as _visualizer_module

  source = Path(_visualizer_module.__file__).parent / "img" / LOGO_NAME
  target = INLINE_DIR / LOGO_NAME
  if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
    return
  try:
    import io

    from PIL import Image
  except ImportError:
    return  # frontend.py falls back to the full-size original

  image = Image.open(source).convert("RGBA")
  image.thumbnail((LOGO_MAX_PX, LOGO_MAX_PX), Image.LANCZOS)
  buffer = io.BytesIO()
  image.save(buffer, "PNG", optimize=True)
  target.write_bytes(buffer.getvalue())


def read_inline(name: str) -> str:
  """Return an inlined asset, with an actionable error when it is missing.

  Under Pyodide there is no way to recover from a missing file -- no urllib, no
  filesystem the user can reach -- so the message has to name the build step
  that populates it.
  """
  path = INLINE_DIR / name
  if not path.is_file():
    raise FileNotFoundError(
      f"vendored asset {name!r} is missing from {INLINE_DIR}. "
      "Run `python -m plr_workshops.vendor` to fetch it (needs network once), "
      "or `python -m plr_workshops.build_demo` which does it for you."
    )
  return path.read_text(encoding="utf-8")


def _pyodide_runtime(dest: Path, *, refresh: bool = False) -> int:
  """Fetch the Pyodide runtime and the packages micropip needs into ``dest``."""
  dest.mkdir(parents=True, exist_ok=True)
  total = 0

  core = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
          "python_stdlib.zip", "pyodide-lock.json"]
  for name in core:
    data = fetch(PYODIDE_CDN + name, refresh=refresh)
    (dest / name).write_bytes(data)
    total += len(data)

  # loadPackage(["micropip", "ssl"]) resolves names through pyodide-lock.json,
  # so the wheels those two pull in have to sit beside it or the call 404s.
  lock = json.loads((dest / "pyodide-lock.json").read_text(encoding="utf-8"))
  packages = lock["packages"]

  def resolve(names, seen=None):
    seen = seen if seen is not None else set()
    for name in names:
      key = name.lower()
      if key in seen or key not in packages:
        continue
      seen.add(key)
      resolve(packages[key].get("depends", []), seen)
    return seen

  for key in sorted(resolve(["micropip", "ssl"])):
    file_name = packages[key]["file_name"]
    data = fetch(PYODIDE_CDN + file_name, refresh=refresh)
    (dest / file_name).write_bytes(data)
    total += len(data)

  return total


def _wheels(dest: Path, *, refresh: bool = False) -> int:
  """Fetch pylabrobot and its runtime dependencies as wheels.

  micropip resolves dependencies over the network by default. Pointing it at a
  local wheel only helps if that wheel's own requirements -- ``typing_extensions``
  and ``websockets`` -- are local too.
  """
  dest.mkdir(parents=True, exist_ok=True)
  total = 0
  for project, version in (
    ("pylabrobot", PYLABROBOT_VERSION),
    ("typing_extensions", None),
    ("websockets", None),
  ):
    url = _pypi_wheel_url(project, version)
    data = fetch(url, refresh=refresh)
    (dest / url.rsplit("/", 1)[-1]).write_bytes(data)
    total += len(data)
  return total


def _pypi_wheel_url(project: str, version=None) -> str:
  """Return the URL of a pure-Python wheel for ``project``.

  Pyodide can only install ``py3-none-any`` wheels; anything platform-specific
  would fail at runtime, in the browser, where the error is hardest to read.
  """
  api = f"https://pypi.org/pypi/{project}/{version}/json" if version else \
        f"https://pypi.org/pypi/{project}/json"
  with urllib.request.urlopen(api, timeout=120) as response:
    data = json.load(response)

  for entry in data["urls"]:
    if entry["packagetype"] == "bdist_wheel" and entry["filename"].endswith("py3-none-any.whl"):
      return entry["url"]
  raise RuntimeError(
    f"no pure-Python wheel for {project}; Pyodide cannot install a platform wheel"
  )


def populate_demo(out: Path, *, refresh: bool = False) -> dict:
  """Fill ``out`` with everything the page would otherwise fetch at runtime."""
  sizes = {}

  for rel, url in STATIC_ASSETS.items():
    target = out / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(url, refresh=refresh)
    target.write_bytes(data)
    sizes["vendor"] = sizes.get("vendor", 0) + len(data)

  sizes["pyodide"] = _pyodide_runtime(out / "pyodide", refresh=refresh)
  sizes["wheels"] = _wheels(out / "wheels", refresh=refresh)

  # The inlined assets ride along into the Pyodide filesystem, because the
  # visualizer page is assembled there at runtime.
  ensure_inline_assets(refresh=refresh)
  target = out / "py" / "plr_workshops" / "_vendored"
  target.mkdir(parents=True, exist_ok=True)
  # Everything in the directory, not just INLINE_ASSETS: the shrunk logo is
  # generated rather than fetched, and was silently left behind when this
  # iterated the fetch manifest.
  for source in sorted(INLINE_DIR.iterdir()):
    if source.is_file():
      shutil.copy2(source, target / source.name)
      sizes["inline"] = sizes.get("inline", 0) + source.stat().st_size

  return sizes


def inline_asset_names():
  """Names the demo page must copy into Pyodide's filesystem."""
  return sorted(p.name for p in INLINE_DIR.iterdir() if p.is_file())


def main(argv=None):
  import argparse

  parser = argparse.ArgumentParser(description="Fetch the demo's third-party assets.")
  parser.add_argument("--refresh", action="store_true", help="Ignore the cache")
  parser.add_argument("--inline-only", action="store_true",
                      help="Only the assets inlined into the visualizer page")
  args = parser.parse_args(argv)

  ensure_inline_assets(refresh=args.refresh)
  for name in INLINE_ASSETS:
    print(f"  {(INLINE_DIR / name).stat().st_size:>12,}  plr_workshops/vendor/{name}")
  if args.inline_only:
    return
  print(f"cache: {CACHE_DIR}")


if __name__ == "__main__":
  main()
