"""Assemble the static Pyodide demo into a self-contained ``demo/`` directory.

The demo is a single static page that loads Pyodide from a CDN, installs
``pylabrobot==0.2.2`` from PyPI via micropip, and drops a copy of the
``plr_workshops`` package into Pyodide's virtual filesystem. The visitor edits
a protocol on the left, the deck renders on the right, and the notebook is
autosaved to IndexedDB and downloadable as a real ``.ipynb``.

Nothing here runs a server: the output is plain files that any static host
(GitHub Pages, ``python -m http.server``) can serve.
"""

import argparse
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

# Modules the browser needs. widget.py (anywidget/sidecar) and the CLI are
# notebook/local concerns; they pull in dependencies that don't exist under
# Pyodide and are excluded.
_NEEDED = [
  "__init__.py",
  "transport.py",
  "inline.py",
  "frontend.py",
  "pyodide_transport.py",
  "browser_kernel.py",
  "vendor.py",
]

_PAGE_TEMPLATE = HERE / "demo_index.html"
# The notebook engine (cell model, nbformat round-trip, keymap) ships as its own
# ES module so it can be unit-tested under Node; the page imports it.
_JS_MODULE = (HERE / "demo_notebook.js", "notebook.js")
_OUT_DIR = REPO_ROOT / "demo"


def _localize(page: str, out: Path) -> str:
  """Point the page at the vendored copies instead of the CDNs.

  The template keeps its CDN URLs so it stays readable and so ``--no-vendor``
  still produces a working page; the swap happens here, on the built copy.
  """
  import re

  from . import vendor

  for rel, url in vendor.STATIC_ASSETS.items():
    if url not in page:
      raise ValueError(f"the page no longer references {url}; vendor.STATIC_ASSETS is stale")
    page = page.replace(url, rel)

  # Generated in the bundle, so the page cannot hardcode the list without
  # drifting from it -- which is exactly how vendor.py went missing from
  # PY_MODULES and broke the deck with an unrelated-looking ImportError.
  names = ", ".join(f'"{n}"' for n in vendor.inline_asset_names())
  page, count = re.subn(r"const PY_VENDOR = \[[^\]]*\];", f"const PY_VENDOR = [{names}];", page)
  if count != 1:
    raise ValueError(f"expected exactly one PY_VENDOR list, found {count}")

  pyodide_js = f"{vendor.PYODIDE_CDN}pyodide.js"
  if pyodide_js not in page:
    raise ValueError(f"the page no longer loads {pyodide_js}; vendor.PYODIDE_VERSION is stale")
  page = page.replace(pyodide_js, "pyodide/pyodide.js")

  # Without indexURL, pyodide.js resolves pyodide.asm.wasm and python_stdlib.zip
  # against its own CDN origin -- the local pyodide.js would still pull ~13 MB
  # over the network, which is the whole thing we are trying to avoid.
  page, count = re.subn(r"loadPyodide\(\)", 'loadPyodide({ indexURL: "pyodide/" })', page)
  if count != 1:
    raise ValueError(f"expected exactly one loadPyodide() call, found {count}")

  # micropip resolves dependencies over the network unless every wheel is given
  # up front, so pylabrobot's typing_extensions and websockets ship too.
  wheels = sorted(p.name for p in (out / "wheels").glob("*.whl"))
  if not wheels:
    raise ValueError("no wheels were vendored; cannot install pylabrobot offline")
  # The call sits inside a JS single-quoted string, so double quotes pass through.
  install = ", ".join(f'"wheels/{w}"' for w in wheels)
  page, count = re.subn(
    r'await micropip\.install\("pylabrobot==[^"]+"\)',
    f"await micropip.install([{install}], deps=False)",
    page,
  )
  if count != 1:
    raise ValueError(f"expected exactly one micropip.install call, found {count}")

  return page


def build(out: Path = _OUT_DIR, force: bool = False, offline: bool = True) -> None:
  if out.exists() and force:
    shutil.rmtree(out)
  out.mkdir(parents=True, exist_ok=True)

  py_dir = out / "py" / "plr_workshops"
  py_dir.mkdir(parents=True, exist_ok=True)

  for name in _NEEDED:
    src = HERE / name
    if not src.is_file():
      raise FileNotFoundError(f"plr_workshops/{name} missing; is the package intact?")
    shutil.copy2(src, py_dir / name)

  sizes = {}
  page = _PAGE_TEMPLATE.read_text(encoding="utf-8")
  if offline:
    from . import vendor

    # Must run before _localize: it names the wheels the install line lists.
    sizes = vendor.populate_demo(out)
    page = _localize(page, out)
  (out / "index.html").write_text(page, encoding="utf-8")

  js_src, js_name = _JS_MODULE
  if not js_src.is_file():
    raise FileNotFoundError(f"plr_workshops/{js_src.name} missing; is the package intact?")
  shutil.copy2(js_src, out / js_name)

  size = sum(p.stat().st_size for p in py_dir.iterdir() if p.is_file())
  print(f"demo assembled -> {out}")
  print(f"  index.html + {js_name} + py/plr_workshops ({len(_NEEDED)} modules, {size:,} bytes)")

  if offline:
    from . import vendor

    for label in ("pyodide", "wheels", "vendor", "inline"):
      if label in sizes:
        print(f"  {sizes[label]:>12,}  {label}/")
    print(f"  {sum(sizes.values()):>12,}  vendored total (cache: {vendor.CACHE_DIR})")
  else:
    # --no-vendor keeps the ~16 MB fetch out of a quick iteration loop. The page
    # falls back to its CDNs, so the result needs a network to boot.
    print("  (--no-vendor: page will load Pyodide and CodeMirror from CDNs)")


def main(argv=None):
  parser = argparse.ArgumentParser(description="Assemble the Pyodide demo site.")
  parser.add_argument("--out", default=str(_OUT_DIR), help="Output directory")
  parser.add_argument("--force", action="store_true", help="Overwrite an existing demo/")
  parser.add_argument("--no-vendor", action="store_true",
                      help="Skip the ~16 MB asset fetch; the demo will need a network")
  args = parser.parse_args(argv)
  build(Path(args.out), force=args.force, offline=not args.no_vendor)


if __name__ == "__main__":
  main()
