"""Check the parts of the browser kernel that do not need a browser.

``run_cell`` needs Pyodide (test_demo_pyodide.mjs covers it against a real
runtime); everything it formats and stores is plain Python and is checked here.

Run: python -m plr_workshops.test_browser_kernel
"""

from . import browser_kernel as bk


def test_namespace_reset():
  bk.USER_NS["lh"] = object()
  bk.USER_NS["plate"] = 1
  bk.reset()
  assert "lh" not in bk.USER_NS and "plate" not in bk.USER_NS, "reset left user names behind"
  assert bk.USER_NS["__name__"] == "__main__", "reset destroyed the base namespace"
  bk.reset()  # idempotent
  print("reset           -> user names cleared, base namespace intact")


def test_result_formatting():
  assert bk.format_result(42) == "42"
  assert bk.format_result("hi") == "'hi'"

  huge = bk.format_result("x" * (bk.MAX_REPR * 2))
  assert len(huge) < bk.MAX_REPR + 200, "an unbounded repr would lock up the page"
  assert "more characters" in huge

  class Broken:
    def __repr__(self):
      raise RuntimeError("nope")

  assert "unrepresentable Broken" in bk.format_result(Broken())
  print(f"format_result   -> repr, truncation at {bk.MAX_REPR:,}, broken __repr__ survived")


def test_exception_payload():
  try:
    raise ValueError("bad thing")
  except ValueError as exc:
    payload = bk.format_exception(exc)
  assert payload["ok"] is False
  assert payload["ename"] == "ValueError"
  assert payload["evalue"] == "bad thing"
  assert payload["traceback"].startswith("Traceback (most recent call last):")
  assert payload["traceback"].rstrip().endswith("ValueError: bad thing")
  print("format_exception-> ename/evalue/traceback")


def test_traceback_is_trimmed_to_the_user_s_code():
  raw = (
    'Traceback (most recent call last):\n'
    '  File "/home/pyodide/plr_workshops/browser_kernel.py", line 72, in run_cell\n'
    '    value = await eval_code_async(source, globals=USER_NS)\n'
    '            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
    '  File "/lib/python312.zip/_pyodide/_base.py", line 597, in eval_code_async\n'
    '    await CodeRunner(\n'
    '  File "<exec>", line 2, in <module>\n'
    '  File "/home/pyodide/mine.py", line 9, in helper\n'
    '    raise ValueError("boom")\n'
    'ValueError: boom\n'
  )
  cleaned = bk.clean_traceback(raw, "Cell In[3]")
  assert "browser_kernel.py" not in cleaned, "kernel frames leaked into the traceback"
  assert "_pyodide/_base.py" not in cleaned, "pyodide internals leaked into the traceback"
  assert "eval_code_async" not in cleaned, "a hidden frame's source line was left behind"
  assert "Cell In[3], line 2" in cleaned, "the cell frame was not labelled"
  assert "mine.py" in cleaned, "the user's own frames must survive"
  assert cleaned.splitlines()[0] == "Traceback (most recent call last):"
  assert cleaned.rstrip().endswith("ValueError: boom")
  print("clean_traceback -> kernel frames hidden, cell frame labelled, user frames kept")


def main():
  test_namespace_reset()
  test_result_formatting()
  test_exception_payload()
  test_traceback_is_trimmed_to_the_user_s_code()
  print("\nBrowser kernel check passed.")


if __name__ == "__main__":
  main()
