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
]

_PAGE_TEMPLATE = HERE / "demo_index.html"
# The notebook engine (cell model, nbformat round-trip, keymap) ships as its own
# ES module so it can be unit-tested under Node; the page imports it.
_JS_MODULE = (HERE / "demo_notebook.js", "notebook.js")
_OUT_DIR = REPO_ROOT / "demo"


def build(out: Path = _OUT_DIR, force: bool = False) -> None:
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

  shutil.copy2(_PAGE_TEMPLATE, out / "index.html")

  js_src, js_name = _JS_MODULE
  if not js_src.is_file():
    raise FileNotFoundError(f"plr_workshops/{js_src.name} missing; is the package intact?")
  shutil.copy2(js_src, out / js_name)

  size = sum(p.stat().st_size for p in py_dir.iterdir())
  print(f"demo assembled -> {out}")
  print(f"  index.html + {js_name} + py/plr_workshops ({len(_NEEDED)} modules, {size:,} bytes)")


def main(argv=None):
  parser = argparse.ArgumentParser(description="Assemble the Pyodide demo site.")
  parser.add_argument("--out", default=str(_OUT_DIR), help="Output directory")
  parser.add_argument("--force", action="store_true", help="Overwrite an existing demo/")
  args = parser.parse_args(argv)
  build(Path(args.out), force=args.force)


if __name__ == "__main__":
  main()
