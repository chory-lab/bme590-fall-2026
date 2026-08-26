"""Verify the inline visualizer produces the same event stream as the websocket path.

The event stream is the contract shared by every transport and by the untouched
JavaScript renderer, so asserting on it here covers the widget and Pyodide
adapters too -- without a browser.

Run: python -m plr_workshops.test_inline
"""

import asyncio

from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
from pylabrobot.resources import (
  PLT_CAR_L5AC_A00,
  TIP_CAR_480_A00,
  cor_96_wellplate_360uL_Fb,
  hamilton_96_tiprack_1000uL_filter,
)
from pylabrobot.resources.hamilton import STARLetDeck

from .inline import InlineVisualizer
from .transport import RecordingTransport


async def drain():
  """Let queued visualizer callbacks run to completion.

  Resource callbacks schedule their sends with run_coroutine_threadsafe, which
  needs one loop iteration to create the task and another to finish it -- a
  single sleep(0) is not enough. Notebook cells await between operations, so
  this only matters when driving the loop directly.
  """
  await asyncio.sleep(0.05)


def build_deck(lh):
  """Populate a STARlet deck the way workshop 01 does."""
  tip_car = TIP_CAR_480_A00(name="tip_carrier")
  tip_car[0] = hamilton_96_tiprack_1000uL_filter(name="tiprack")
  lh.deck.assign_child_resource(tip_car, rails=3)

  plt_car = PLT_CAR_L5AC_A00(name="plate_carrier")
  plt_car[0] = cor_96_wellplate_360uL_Fb(name="plate")
  lh.deck.assign_child_resource(plt_car, rails=9)
  return tip_car, plt_car


async def main():
  transport = RecordingTransport()

  lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(num_channels=8), deck=STARLetDeck())
  await lh.setup()

  vis = InlineVisualizer(resource=lh, transport=transport, name="test")
  await vis.setup()

  assert transport.started, "transport was never started"
  assert transport.events[0] == "set_root_resource", transport.events
  assert "set_state" in transport.events, transport.events
  print(f"setup           -> {transport.events}")

  # -- the root resource carries a full 3D scene graph --
  root = transport.of_type("set_root_resource")[0]["data"]["resource"]
  for key in ("size_x", "size_y", "size_z", "location", "rotation", "children"):
    assert key in root, f"missing {key} in serialized root"
  print(f"scene graph     -> size_z={root['size_z']}, rotation={root['rotation']}, "
        f"{len(root['children'])} children")

  # -- assignment fires resource_assigned --
  transport.clear()
  build_deck(lh)
  await drain()
  assigned = transport.of_type("resource_assigned")
  assert len(assigned) == 2, f"expected 2 assignments, got {transport.events}"
  print(f"deck setup      -> {len(assigned)} resource_assigned "
        f"({', '.join(a['data']['resource']['name'] for a in assigned)})")

  # -- a tip pickup batches into a single set_state --
  transport.clear()
  tiprack = lh.deck.get_resource("tiprack")
  await lh.pick_up_tips(tiprack["A1:D1"])
  await drain()
  # PLR reports a pickup as one deck-level state update carrying head_state, not
  # one message per tip spot -- so four channels collapse into a single event.
  states = transport.of_type("set_state")
  assert len(states) == 1, f"expected 1 batched set_state, got {len(states)}"
  head = states[0]["data"]["lh_deck"]["head_state"]
  tips = {ch: s["tip"]["name"] for ch, s in head.items() if s.get("tip")}
  assert len(tips) == 4, f"expected 4 channels holding tips, got {tips}"
  print(f"pick_up_tips    -> 1 batched set_state, {len(tips)} channels tipped "
        f"({', '.join(sorted(tips))})")

  # -- unassignment fires resource_unassigned --
  transport.clear()
  lh.deck.get_resource("plate_carrier").unassign()
  await drain()
  assert transport.of_type("resource_unassigned"), transport.events
  print(f"unassign        -> {transport.events}")

  # -- wire format matches the websocket path --
  msg = transport.messages[0] if transport.messages else states[0]
  assert set(msg) == {"id", "version", "event", "data"}, msg.keys()
  print(f"wire format     -> {sorted(msg)} (id={msg['id']}, version={msg['version']})")

  await vis.stop()
  assert transport.stopped and not vis.setup_finished
  print("teardown        -> transport stopped, visualizer reset")

  print("\nAll checks passed.")


if __name__ == "__main__":
  asyncio.run(main())
