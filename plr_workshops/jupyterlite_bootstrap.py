"""Everything a Pyodide kernel needs before a workshop cell runs.

This used to be a code cell prepended to every workshop notebook. It is site
infrastructure, not coursework, so it lives here and the
``plr-workshops:bootstrap`` labextension calls :func:`initialize` once per
kernel -- including after a restart, which is when a notebook-cell bootstrap
would silently stop applying.

Keeping it in the package rather than in generated notebook source buys three
things: the notebooks are portable (nothing in them mentions piplite), the
paths resolve from package data instead of the notebook's working directory,
and a failure raises where a caller can see it rather than into a hidden cell.
"""

import os
import shutil
from importlib.resources import files
from typing import List

from .jupyterlite_bridge import patch_visualizer

#: Opentrons labware the workshops build.
#:
#: PyLabRobot's ``resources/opentrons/load.py`` downloads these from
#: raw.githubusercontent.com the first time one is constructed. Pyodide cannot
#: open a TLS socket, so that raises ``RuntimeError: TLS not supported in this
#: environment`` and any notebook touching an Opentrons resource stops there.
#:
#: The loader caches to ``/tmp/<name>.json`` and checks that path first, so
#: shipping the definitions and putting them where it already looks means it
#: never reaches for the network. Keep this list in step with the pinned
#: pylabrobot when upgrading.
OT_DEFINITIONS = (
  "opentrons_96_tiprack_1000ul",
  "opentrons_96_tiprack_300ul",
)


def seed_opentrons_cache() -> List[str]:
  """Copy the packaged Opentrons definitions into PyLabRobot's cache path.

  Returns the names actually written (an already-seeded kernel writes none).
  Missing package data is an error: silently skipping would just move the
  failure to the first notebook that builds an OT deck, far from the cause.
  """
  written = []
  source = files("plr_workshops").joinpath("otdefs")

  for name in OT_DEFINITIONS:
    destination = f"/tmp/{name}.json"
    if os.path.exists(destination):
      continue
    definition = source.joinpath(f"{name}.json")
    if not definition.is_file():
      raise FileNotFoundError(
        f"packaged Opentrons definition missing: {name}.json. "
        "The browser wheel was built without its otdefs/ package data."
      )
    os.makedirs("/tmp", exist_ok=True)
    shutil.copyfile(str(definition), destination)
    written.append(name)

  return written


async def initialize() -> dict:
  """Prepare this kernel for the workshops.

  Called by the site's bootstrap labextension once per kernel id. Safe to call
  again -- patching is idempotent and seeding skips what is already present --
  so a re-run after a restart costs nothing.

  Returns a small summary the extension can log; raises on failure, which the
  extension turns into a visible PLR_BOOTSTRAP_FAILED rather than letting the
  student meet the consequences several cells later.
  """
  patch_visualizer()
  seeded = seed_opentrons_cache()
  return {"patched": True, "seeded": seeded}
