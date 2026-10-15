"""Run the demo notebook the way a person would, and hand back what each cell printed."""

import os
from pathlib import Path

import nbclient
import nbformat
import pytest

NOTEBOOK = Path(__file__).resolve().parent.parent / "demo.ipynb"


def cell_texts(nb: nbformat.NotebookNode) -> list[str]:
  """Everything each code cell printed, one string per code cell."""
  texts = []
  for cell in nb.cells:
    if cell.cell_type != "code":
      continue
    parts = []
    for output in cell.get("outputs", []):
      if output.get("output_type") == "error":
        parts.append(f"{output['ename']}: {output['evalue']}")
      parts.append(output.get("text", "") or output.get("data", {}).get("text/plain", ""))
    texts.append("".join(parts))
  return texts


def run_notebook(env: dict[str, str], timeout: int = 600) -> list[str]:
  """Execute every cell of the demo in a fresh kernel with `env` added to its environment."""
  nb = nbformat.read(NOTEBOOK, as_version=4)
  saved = dict(os.environ)
  # The kernel is a child process: it takes the environment this process has when it starts.
  os.environ.update(env)
  try:
    nbclient.NotebookClient(nb, timeout=timeout, kernel_name="python3").execute()
  finally:
    os.environ.clear()
    os.environ.update(saved)
  return cell_texts(nb)


@pytest.fixture(scope="session")
def notebook_path() -> Path:
  return NOTEBOOK
