import json

cells = []


def md(s):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": s.splitlines(keepends=True)})


def code(s):
    cells.append({
        "cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
        "source": s.splitlines(keepends=True),
    })


md(
    "# PyLabRobot deck through the bridge\n"
    "\n"
    "Five gates plus a real protocol. The **deck is a sibling iframe on the outer page**;\n"
    "this notebook's cells only emit events. Run all cells in order."
)

code(
    "# pylabrobot and anywidget: resolve their REAL deps (typing_extensions,\n"
    "# websockets / ipywidgets, traitlets, ...) from the bundled index -- every one\n"
    "# is there, so the resolver stays hermetic. bme590-workshops: deps=False -- the\n"
    "# general-purpose wheel's metadata (jupyterlab, sidecar, numpy, ...) is for a\n"
    "# desktop install, not the browser; piplite.install(..., deps=False) is the\n"
    "# supported API for exactly this.\n"
    "import piplite\n"
    "await piplite.install(\"pylabrobot==0.2.2\")\n"
    "await piplite.install(\"anywidget==0.11.0\")\n"
    "await piplite.install(\"bme590-workshops==0.1.0\", deps=False)\n"
    "import pylabrobot\n"
    'print("PLR", pylabrobot.__version__)'
)

md("## Tracking must be on, or the deck never updates")
code(
    "from pylabrobot.resources import set_volume_tracking, set_tip_tracking\n"
    "set_volume_tracking(True)\n"
    "set_tip_tracking(True)"
)

md("## 1. Build the deck")
code(
    "from pylabrobot.liquid_handling import LiquidHandler\n"
    "from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend\n"
    "from pylabrobot.resources import (\n"
    "  STARLetDeck, TIP_CAR_480_A00, PLT_CAR_L5AC_A00,\n"
    "  cor_96_wellplate_360uL_Fb, hamilton_96_tiprack_1000uL_filter,\n"
    ")\n"
    "\n"
    'deck = STARLetDeck()\n'
    'tip_carrier = TIP_CAR_480_A00(name="tips")\n'
    'plate_carrier = PLT_CAR_L5AC_A00(name="plates")\n'
    "deck.assign_child_resource(plate_carrier, rails=5)\n"
    "deck.assign_child_resource(tip_carrier, rails=11)\n"
    'tip_carrier[0] = hamilton_96_tiprack_1000uL_filter(name="tips_0")\n'
    'plate_carrier[0] = cor_96_wellplate_360uL_Fb(name="plate_0")\n'
    "\n"
    "lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(), deck=deck)\n"
    "await lh.setup()\n"
    "lh"
)

md(
    "## 2. Mount the visualizer via the bridge\n"
    "\n"
    "The transport renders nothing of its own: the deck iframe lives on the outer page,\n"
    "beside JupyterLite. Events hop kernel -> widget -> outer page -> deck."
)
code(
    "from plr_workshops import InlineVisualizer\n"
    "from plr_workshops.jupyterlite_bridge import JupyterLiteBridgeTransport\n"
    "\n"
    'vis = InlineVisualizer(resource=lh, transport=JupyterLiteBridgeTransport(name="Deck"))\n'
    "await vis.setup()\n"
    'print("VIS_MOUNTED")'
)

md("## 3. Animate: fill, pick up, aspirate, dispense, return")
code(
    "import asyncio\n"
    "\n"
    'plate = deck.get_resource("plate_0")\n'
    'tips = deck.get_resource("tips_0")\n'
    "\n"
    "plate.set_well_volumes([200.0] * 96)\n"
    "await asyncio.sleep(0.4)\n"
    "\n"
    'await lh.pick_up_tips(tips["A1"])\n'
    "await asyncio.sleep(0.4)\n"
    "\n"
    'await lh.aspirate(plate["A1"], vols=[50])\n'
    "await asyncio.sleep(0.4)\n"
    "\n"
    'await lh.dispense(plate["B1"], vols=[50])\n'
    "await asyncio.sleep(0.4)\n"
    "\n"
    "await lh.return_tips()\n"
    'print("PROTOCOL_DONE")'
)

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python (Pyodide)", "language": "python", "name": "python"},
        "language_info": {"name": "python", "version": "3.13"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = r"C:\Users\stefa\plr-class\bme590-fall-2025\jupyterlite\content\deck.ipynb"
with open(out, "w", encoding="utf-8") as fh:
    fh.write(json.dumps(nb, indent=1))
print("wrote deck.ipynb", len(cells), "cells")
