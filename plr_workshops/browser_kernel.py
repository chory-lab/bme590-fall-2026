"""A minimal notebook kernel for the Pyodide demo page.

The page used to hand cell sources straight to ``pyodide.runPythonAsync``. That
runs the code, but it is not what a notebook does: the value of the last
expression is thrown away, exceptions surface as a JavaScript ``Error.message``
rather than a Python traceback, and there is no way to clear the namespace
without tearing down the whole runtime.

This module supplies those three things and nothing else. It is deliberately
JSON-in/JSON-out so the JavaScript side never has to touch a ``PyProxy``.

Only :func:`run_cell` needs Pyodide (for ``eval_code_async``, which is what
makes top-level ``await`` work); the rest imports and tests fine under CPython.
"""

import json
import traceback

#: The shared namespace every cell executes in — the notebook's globals.
USER_NS: dict = {"__name__": "__main__", "__doc__": None}

#: Keys present in a fresh namespace, so :func:`reset` knows what to keep.
_BASE_KEYS = frozenset(USER_NS)

MAX_REPR = 10_000


def reset() -> None:
  """Clear the user namespace, as "restart kernel" does.

  Already-imported modules stay in ``sys.modules`` (re-downloading pylabrobot
  would take another ten seconds), so this is a namespace reset rather than a
  true runtime restart. Every name the notebook bound is gone.
  """
  for key in [k for k in USER_NS if k not in _BASE_KEYS]:
    del USER_NS[key]


def format_result(value) -> str:
  """The ``text/plain`` rendering of a cell's value, as a notebook shows it."""
  try:
    text = repr(value)
  except Exception as exc:  # a broken __repr__ must not kill the cell
    text = f"<unrepresentable {type(value).__name__}: {exc}>"
  if len(text) > MAX_REPR:
    text = text[:MAX_REPR] + f"\n... [{len(text) - MAX_REPR} more characters]"
  return text


def _is_internal(frame_text: str) -> bool:
  """True for frames belonging to the machinery that runs a cell.

  Jupyter hides its own plumbing from tracebacks; leaving it in would put four
  lines of Pyodide internals above every one of a student's typos.
  """
  return ("browser_kernel.py" in frame_text) or ("_pyodide/_base.py" in frame_text)


def clean_traceback(text: str, cell_label: str = "Cell") -> str:
  """Drop the kernel's own frames and label the user's as a notebook cell."""
  lines = text.rstrip("\n").split("\n")
  out, skipping = [], False
  for line in lines:
    if line.startswith("  File "):
      skipping = _is_internal(line)
      if not skipping:
        # `File "<exec>", line 3, in <module>` is the cell itself.
        out.append(line.replace('File "<exec>", line', f"{cell_label}, line")
                       .replace(", in <module>", ""))
      continue
    if skipping and (line.startswith("    ") or line.startswith("     ")):
      continue  # the source line and caret that belong to a hidden frame
    skipping = False
    out.append(line)
  return "\n".join(out)


def format_exception(exc: BaseException, cell_label: str = "Cell") -> dict:
  """A Jupyter-shaped error payload for an exception."""
  raw = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
  return {
    "ok": False,
    "ename": type(exc).__name__,
    "evalue": str(exc),
    "traceback": clean_traceback(raw, cell_label),
  }


async def run_cell(source: str, cell_label: str = "Cell") -> str:
  """Execute one cell in the shared namespace; return a JSON result string.

  Returns ``{"ok": true, "repr": <str|null>}`` on success -- ``repr`` is null
  when the cell ends in a statement rather than an expression, which is exactly
  when Jupyter shows no ``Out[n]`` -- or ``{"ok": false, "ename", "evalue",
  "traceback"}`` when it raises.
  """
  from pyodide.code import eval_code_async

  try:
    value = await eval_code_async(source, globals=USER_NS)
  except BaseException as exc:  # noqa: BLE001 - a cell may raise anything
    return json.dumps(format_exception(exc, cell_label))
  return json.dumps({"ok": True, "repr": None if value is None else format_result(value)})
