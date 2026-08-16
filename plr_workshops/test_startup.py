"""Verify the Phase 3 startup hook: stock ``Visualizer(...)`` becomes the inline
docked widget, without touching the notebook source.

Run: python -m plr_workshops.test_startup
"""

import asyncio
import os
import tempfile

from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
from pylabrobot.resources.hamilton import STARLetDeck

from .cli import _prepare_workspace
from .startup import install
from .transport import RecordingTransport


def _patched_transport(name, **kwargs):
  return RecordingTransport()


def test_patch_turns_visualizer_inline():
  """After install(), the notebook's exact code path produces a recording
  transport with the same event stream the widget would receive."""
  install(transport_factory=_patched_transport)

  # This is the import line every workshop notebook runs. It must now resolve
  # to the patched class even though it is imported after install().
  from pylabrobot.visualizer.visualizer import Visualizer

  assert Visualizer.__name__ == "NotebookVisualizer", Visualizer.__name__

  lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(), deck=STARLetDeck())
  vis = Visualizer(resource=lh)

  transport = vis._transport
  assert isinstance(transport, RecordingTransport), type(transport)


async def _run():
  transport_factory = lambda name, **kwargs: transport


async def main():
  transport = RecordingTransport()
  install(transport_factory=lambda name, **kwargs: transport)

  from pylabrobot.visualizer.visualizer import Visualizer

  lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(num_channels=8), deck=STARLetDeck())
  await lh.setup()

  vis = Visualizer(resource=lh)
  assert isinstance(vis._transport, RecordingTransport)

  await vis.setup()
  assert transport.events[0] == "set_root_resource", transport.events
  assert "set_state" in transport.events, transport.events
  print(f"patched setup   -> {transport.events}")

  await vis.stop()
  assert transport.stopped
  print("teardown        -> transport stopped")

  print("\nPatch check passed.")


def test_cli_workspace_layout():
  """_prepare_workspace mirrors the repo layout so ../figs and ../data resolve,
  and drops the startup hook where a kernel launched with IPYTHONDIR reads it."""
  from pathlib import Path

  repo = Path(__file__).resolve().parent.parent

  with tempfile.TemporaryDirectory() as tmp:
    ws, ipython_dir = _prepare_workspace(repo, Path(tmp) / "ws", force=True)

    for name in ("workshops", "data", "figs"):
      assert (ws / name).is_dir(), f"missing {name}"

    notebooks = list((ws / "workshops").glob("*.ipynb"))
    assert len(notebooks) == 6, f"expected 6 notebooks, got {len(notebooks)}"

    data_files = list((ws / "data").glob("*.csv"))
    assert len(data_files) == 2, f"expected 2 csvs, got {len(data_files)}"

    figs = list((ws / "figs").iterdir())
    assert figs, "no figs copied"

    hook = ipython_dir / "profile_default" / "startup" / "zz_plr_inline.py"
    assert hook.is_file(), "startup hook not written"
    assert "plr_workshops" in hook.read_text(encoding="utf-8")

    # Relative refs in the notebooks must resolve inside the workspace.
    assert (ws / "figs").is_dir() and (ws / "data").is_dir()
    print(f"workspace       -> {notebooks[0].name} (+{len(notebooks) - 1} more), "
          f"{len(data_files)} csvs, {len(figs)} figs, hook installed")

  print("\nCLI layout check passed.")


if __name__ == "__main__":
  test_patch_turns_visualizer_inline()
  asyncio.run(main())
  test_cli_workspace_layout()
