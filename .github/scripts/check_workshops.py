"""Cross-platform check for the workshop notebooks.

Verifies, against the installed pylabrobot:
  1. Every `from pylabrobot... import` used anywhere in the workshops resolves.
  2. A smoke protocol exercises the core API surface (deck, carriers, tips,
     aspirate/dispense, tip reuse) end to end.
  3. Each notebook executes headless, skipping cells that cannot run without a
     browser or human interaction (the visualizer server, demo sleeps, and
     exercise stubs).

Runs from the repo root in CI on ubuntu / macos / windows.
"""
import ast
import glob
import json
import os
import subprocess
import sys


def iter_notebooks():
    import nbformat

    for path in sorted(glob.glob(os.path.join("workshops", "*.ipynb"))):
        with open(path, encoding="utf-8") as fh:
            yield path, nbformat.read(fh, as_version=4)


def cell_source(cell):
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def pylabrobot_imports():
    seen = set()
    for _path, nb in iter_notebooks():
        for cell in nb["cells"]:
            if cell.get("cell_type") != "code":
                continue
            try:
                tree = ast.parse(cell_source(cell))
            except SyntaxError:
                continue  # exercise stubs are intentionally incomplete
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pylabrobot"):
                    seen.add(f"from {node.module} import " + ", ".join(a.name for a in node.names))
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.startswith("pylabrobot"):
                            seen.add("import " + a.name)
    return sorted(seen)


def check_imports():
    imports = pylabrobot_imports()
    failed = 0
    for stmt in imports:
        try:
            exec(stmt, {})
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"IMPORT FAIL: {stmt}\n  -> {type(exc).__name__}: {exc}")
    print(f"pylabrobot imports checked: {len(imports)}, failures: {failed}")
    return failed


def run_smoke():
    import asyncio

    import pylabrobot
    from pylabrobot.liquid_handling import LiquidHandler
    from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
    from pylabrobot.resources import (
        PLT_CAR_L5AC_A00,
        STARLetDeck,
        TIP_CAR_480_A00,
        cor_96_wellplate_360uL_Fb,
        hamilton_96_tiprack_10uL_filter,
        hamilton_96_tiprack_1000uL_filter,
        hamilton_96_tiprack_300uL_filter,
        nest_1_troughplate_195000uL_Vb,
    )
    from pylabrobot.resources.functional import get_all_tip_spots

    async def main():
        deck = STARLetDeck()
        tip_carrier = TIP_CAR_480_A00(name="tips")
        plate_carrier = PLT_CAR_L5AC_A00(name="plates")
        deck.assign_child_resource(plate_carrier, rails=5)
        deck.assign_child_resource(tip_carrier, rails=11)

        for i, rack in enumerate(
            (
                hamilton_96_tiprack_1000uL_filter,
                hamilton_96_tiprack_1000uL_filter,
                hamilton_96_tiprack_300uL_filter,
                hamilton_96_tiprack_300uL_filter,
                hamilton_96_tiprack_10uL_filter,
            )
        ):
            tip_carrier[i] = rack(name=f"tips_{i}")
        plate_carrier[0] = cor_96_wellplate_360uL_Fb(name="plate_0")
        plate_carrier[1] = nest_1_troughplate_195000uL_Vb(name="reservoir")

        lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(), deck=deck)
        await lh.setup()

        plate_0 = deck.get_resource("plate_0")
        plate_0.set_well_volumes([200.0] * 96)

        tips = deck.get_resource("tips_0")
        spot = get_all_tip_spots([tips])[0]
        await lh.pick_up_tips([spot])
        await lh.aspirate(plate_0["A1"], vols=[50])
        await lh.dispense(plate_0["B1"], vols=[50])
        await lh.return_tips()

        # re-use the same tip: no cross-contamination tracker in 0.2.2
        await lh.pick_up_tips([spot])
        await lh.aspirate(plate_0["A2"], vols=[25])
        await lh.dispense(plate_0["C1"], vols=[25])
        await lh.return_tips()

        await lh.stop()

    asyncio.run(main())
    print("smoke protocol OK — pylabrobot", pylabrobot.__version__)


SKIP_MARKERS = (
    # explicit marker added to teaching cells that intentionally raise
    "CI-SKIP",
    # exercise stubs that are intentionally incomplete
    "YOUR CODE HERE",
    # teaching cells that intentionally raise (e.g. LiquidHandler(), bad_name)
    "you will get an error",
    "this is ok",
    "should throw an error",
    "should throw our better error",
)


def is_stub(src):
    """A code ellipsis (`...` outside of strings/comments) is an incomplete
    exercise placeholder. Use tokenize so docstring "..." doesn't count."""
    import io
    import tokenize

    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.OP and tok.string == "...":
                return True
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return "..." in src
    return False


def neutralize(src):
    """Make interactive cells runnable headless: don't start the visualizer
    websocket server (the deck/lh are still built and returned), and run the
    demo pauses at zero.

    The pauses are now written `await asyncio.sleep(N * SLEEP)` against a SLEEP
    constant the workshops define for students, so setting the constant is
    enough -- no rewriting of sleep call sites. That matters: every regex here
    makes the notebook under test differ from the one students run, which is
    worth minimising rather than extending.

    `time.sleep` is gone from the workshops but stays covered in case one
    returns via a copy-paste from older material.
    """
    import re

    src = re.sub(r"vis\s*=\s*Visualizer\([^)]*\)", "vis = None", src)
    src = src.replace("await vis.setup()", "pass")
    src = src.replace("await vis.stop()", "pass")
    src = re.sub(r"time\.sleep\(\s*\d+(\.\d+)?\s*\)", "time.sleep(0)", src)
    # Zero the constant wherever the notebook sets it, rather than rewriting the
    # 32 call sites that use it.
    src = re.sub(r"^SLEEP\s*=\s*[0-9.]+\s*$", "SLEEP = 0", src, flags=re.M)
    # Course visualizer helpers: swap the bme590 import for headless
    # equivalents so no websocket/file servers start in CI.
    course_shim = (
        "from contextlib import asynccontextmanager\n"
        "class _Rec:\n"
        "    async def start(self): pass\n"
        "    async def stop(self): pass\n"
        "def gif_recorder(vis=None, name=None, **kw):\n"
        "    return _Rec()\n"
        "@asynccontextmanager\n"
        "async def gif_recording(vis=None, name=None, **kw):\n"
        "    yield _Rec()\n"
        "async def step(m=1.0): pass\n"
        "def set_step_delay(s): pass\n"
        "async def visualize_deck(deck, backend, **kw):\n"
        "    from pylabrobot.liquid_handling import LiquidHandler\n"
        "    lh = LiquidHandler(backend=backend, deck=deck)\n"
        "    await lh.setup()\n"
        "    lh.vis = None\n"
        "    return lh\n"
    )
    src = re.sub(
        r"^from bme590\.visualizer_ext import [^\n]*\n?(?:set_step_delay\(SLEEP\)\n?)?",
        course_shim,
        src,
        flags=re.M,
    )
    return src


def execute_notebooks():
    import nbformat
    from nbclient import NotebookClient

    failed = 0
    for path, nb in iter_notebooks():
        skipped = 0
        for cell in nb.cells:
            if cell.cell_type == "code":
                src = cell_source(cell)
                if any(m in src for m in SKIP_MARKERS) or is_stub(src):
                    cell.source = "pass  # skipped in headless CI"
                    skipped += 1
                else:
                    cell.source = neutralize(src)
        client = NotebookClient(
            nb,
            timeout=120,
            kernel_name="plr_ci",
            resources={"metadata": {"path": os.path.dirname(path)}},
        )
        try:
            client.execute()
            print(f"NOTEBOOK PASS: {os.path.basename(path)} (skipped {skipped} cells)")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"NOTEBOOK FAIL: {os.path.basename(path)} -> {type(exc).__name__}: {exc}")
    return failed


def main():
    # Register an ipykernel backed by the interpreter this script runs under,
    # so notebooks execute against the same pylabrobot we import-checked.
    subprocess.run(
        [sys.executable, "-m", "ipykernel", "install", "--user", "--name", "plr_ci",
         "--display-name", "PLR CI"],
        check=True,
    )
    exit_code = 0
    exit_code += check_imports()
    run_smoke()
    exit_code += execute_notebooks()
    print("ALL CHECKS DONE")
    return 1 if exit_code else 0


if __name__ == "__main__":
    sys.exit(main())
