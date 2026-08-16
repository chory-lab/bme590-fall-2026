"""Verify the Phase 4 demo site assembles into a coherent static bundle.

The page is only as good as its references: it fetches Python modules into
Pyodide's filesystem at runtime and imports its notebook engine as an ES module,
and neither failure mode shows up until a browser hits a 404. So every reference
the page makes is checked against the files the build actually emits.

Run: python -m plr_workshops.test_demo
"""

import re
import tempfile
from pathlib import Path

from .build_demo import _JS_MODULE, _NEEDED, build


def main():
  with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "demo"
    build(out)

    index = out / "index.html"
    assert index.is_file(), "index.html missing"
    html = index.read_text(encoding="utf-8")
    js = (out / _JS_MODULE[1]).read_text(encoding="utf-8")

    # -- the page: a notebook UI over a Pyodide kernel --
    for expected in (
      "loadPyodide",
      "micropip.install",
      "pylabrobot==0.2.2",
      "plr-deck",
      "indexedDB",
      "a.download",
      "codemirror",              # syntax highlighting
      "browser_kernel",          # tracebacks + Out[n] values
      "kernel.run_cell",
      "runAll",
      "restartKernel",
      "fromIpynb",               # open a notebook
      "toIpynb",                 # download one
      "Keymap",                  # Jupyter key bindings
      "jp-Prompt",               # In[n]: / Out[n]: gutter
      "jp-OutputArea",
      "dblclick",                # markdown cells edit like Jupyter's
    ):
      assert expected in html, f"index.html missing {expected!r}"

    # -- the engine: model, nbformat, keymap and the starter protocol --
    for expected in (
      "export class NotebookModel",
      "export class Keymap",
      "export function toIpynb",
      "export function fromIpynb",
      "export function renderMarkdown",
      "export const STARTER_CELLS",
      "PyodideTransport",        # the starter notebook mounts the deck
      "InlineVisualizer",
    ):
      assert expected in js, f"{_JS_MODULE[1]} missing {expected!r}"

    # Blocking sleeps freeze the single-threaded browser runtime. (Prose may
    # mention `time.sleep()` in backticks; test_notebook_js.mjs checks the cell
    # sources properly.)
    assert not re.findall(r"(?<!`)time\.sleep", js), "starter cells must not block the loop"
    assert "asyncio.sleep" in js, "the protocol must yield so the deck can draw"

    # -- every Python module the page fetches must be next to it --
    py_dir = out / "py" / "plr_workshops"
    fetched = {m for m in re.findall(r"py/plr_workshops/([A-Za-z0-9_]+\.py)", html)}
    for name in fetched:
      assert (py_dir / name).is_file(), f"page fetches missing {name}"
    for name in _NEEDED:
      assert (py_dir / name).is_file(), f"build omitted {name}"

    # The page builds those paths from a JS list, so check the list itself.
    listed = re.search(r"const PY_MODULES = \[(.*?)\];", html, re.S)
    assert listed, "PY_MODULES list not found in index.html"
    names = re.findall(r'"([A-Za-z0-9_.]+\.py)"', listed.group(1))
    assert set(names) == set(_NEEDED), (
      f"page loads {sorted(names)} but build ships {sorted(_NEEDED)}"
    )

    # -- ES module imports must resolve too --
    imports = re.findall(r'from\s+"(\./[^"]+)"', html)
    assert imports, "index.html imports no notebook engine"
    for ref in imports:
      assert (out / ref[2:]).is_file(), f"page imports missing {ref}"
    assert (out / _JS_MODULE[1]).is_file(), "notebook engine not shipped"

    # -- no local <script>/<link> that the build does not emit --
    for ref in re.findall(r'(?:src|href)="([^"]+)"', html):
      if ref.startswith(("http://", "https://", "data:", "#")):
        continue
      assert (out / ref).is_file(), f"unresolved static ref {ref}"

    print(f"demo bundle     -> {out.name}/: index.html, {_JS_MODULE[1]}, "
          f"py/plr_workshops/ ({len(_NEEDED)} modules)")
    print(f"                   refs OK: {len(names)} kernel modules listed, "
          f"{len(imports)} ES import(s)")

  print("\nDemo build check passed.")


if __name__ == "__main__":
  main()
