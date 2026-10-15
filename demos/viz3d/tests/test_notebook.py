"""The demo, top to bottom, with no page attached: what it says it does, it does.

The collision gates do not need a page - they judge against the resource model - so this is the
whole of the collision story. What a page adds (motion playback, red boxes) is test_browser.py's.
"""

import pytest

from .conftest import run_notebook


@pytest.fixture(scope="module")
def outputs():
  return run_notebook({"VIZ3D_HEADLESS": "1"})


def test_no_cell_raised(outputs):
  for i, text in enumerate(outputs):
    assert "Error:" not in text or "refused" in text, f"code cell {i} failed:\n{text}"


def test_pipetting_moves_liquid(outputs):
  assert "destination A1 holds 50" in "".join(outputs)


def test_the_channel_crash_is_refused_naming_the_command(outputs):
  joined = "".join(outputs)
  assert "refused: channel 0's Z move (P1 ZA)" in joined
  assert "'destination'" in joined


def test_the_iswap_moves_the_plate(outputs):
  assert "destination now sits on source_carrier-3" in "".join(outputs)


def test_the_packed_deck_is_refused_and_nothing_moves(outputs):
  joined = "".join(outputs)
  assert "the fingers would hit: ['tip_carrier']" in joined
  assert "source is still on source_carrier-1" in joined


def test_fixing_the_deck_lets_the_same_move_run(outputs):
  assert "source now sits on destination_carrier-3" in "".join(outputs)


def test_the_notebook_is_committed_without_outputs(notebook_path):
  import nbformat

  nb = nbformat.read(notebook_path, as_version=4)
  for cell in nb.cells:
    if cell.cell_type == "code":
      assert not cell.outputs and cell.execution_count is None, "strip outputs before committing"
