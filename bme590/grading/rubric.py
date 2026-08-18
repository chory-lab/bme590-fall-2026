"""What each exercise asks for, expressed as checks.

One entry per graded exercise. Each `source` runs inside the student's kernel
after their notebook has executed, and appends `(label, passed, detail)` rows to
`results` -- so a student learns *which* requirement failed without being handed
the answer.

Three rules this file follows, all of them learned the hard way:

  * **Check the ask, not a reference.** The prompts state requirements ("six
    plate carriers, one rail apart, 0 to 5 plates"), so the checks state
    requirements too. That accepts every correct solution, needs no reference
    notebook for most exercises, and cannot be broken by PyLabRobot changing an
    unrelated serialization detail.
  * **Never grade what was not specified.** Resource names, assignment order and
    extra labware are free choices. A check that constrains them fails correct
    work.
  * **A missing definition is a distinct outcome from a wrong answer.** Probes
    catch NameError separately so "not attempted" never reads as "attempted and
    wrong".

Not covered here, deliberately:
  * **02.2 (colour mixing)** -- PyLabRobot 0.2.2's volume tracker discards liquid
    identity (`set_liquids([(WATER, 50), (DMSO, 50)])` reads back as
    `[(None, 100.0)]`), so which dye reached which well is simply not in the
    final state. Grading it needs an operation log from a recording backend.
  * **Write-ups, .png deck shots and .gif recordings** -- not machine gradeable.
  * **"in four lines of code or less"** -- a property of the notebook source, not
    of the kernel; the runner could add it, the probes cannot.
  * **Anything the workshop hands the student.** 05's `GeneralPlateReader.__init__`
    is pre-written, so a check on it passes for every submission including an
    empty one. A check that cannot fail is not a check.
"""

from __future__ import annotations

# Every probe is prefixed with this: the helper imports plus the result-collecting
# harness, so each check below is only the requirement it encodes.
PREAMBLE = r'''
import inspect, json
from bme590.grading import deck as D

results = []

async def check(label, fn):
    """Run one requirement. A missing name is reported as not attempted.

    Async-aware: the deck exercises are `async def exercise_N()` and can only be
    run with await. The probe cell is executed by IPython, which allows top-level
    await, so callers write `await check(...)`.
    """
    try:
        outcome = fn()
        if inspect.isawaitable(outcome):
            outcome = await outcome
        if isinstance(outcome, tuple):
            passed, detail = outcome
        else:
            passed, detail = bool(outcome), ""
        results.append((label, bool(passed), detail))
    except NameError as exc:
        results.append((label, False, f"not attempted ({exc})"))
    except Exception as exc:
        results.append((label, False, f"{type(exc).__name__}: {exc}"))
'''

EPILOGUE = '\nprint("###GRADE###" + json.dumps(results))\n'


RUBRIC: dict[str, list[dict]] = {
    # ------------------------------------------------------------------ 01
    "01_deck_setup.ipynb": [
        {
            "id": "01.1",
            "points": 10,
            "ask": "OT-2 deck with 1 Eppendorf 24-tube rack, 1 NEST 15 mL 15-tube rack, "
                   "1 12x15 mL reservoir, 3 96-well 360 uL plates",
            "source": r'''
async def _one():
    d = await exercise_1()
    # Matched by shape, not by vendor name: what the prompt actually pins down is
    # "24 tubes", "15 tubes", "12 troughs", "three 96-well 360 uL plates". Name
    # matching also catches wells and plate holders, which are not labware.
    holders = D.item_holders(d)
    missing = []
    for label, wanted_count, positions in [("Eppendorf 24-tube rack", 1, 24),
                                           ("NEST 15 mL 15-tube rack", 1, 15),
                                           ("12x15 mL reservoir", 1, 12)]:
        got = len([h for h in holders if h.num_items == positions])
        if got < wanted_count:
            missing.append(f"{label}: expected {wanted_count} with {positions} positions, found {got}")
    plates_360 = [p for p in D.plates(d) if p.num_items == 96 and D.close(p.get_item(0).max_volume, 360.0, 40.0)]
    if len(plates_360) != 3:
        missing.append(f"96-well 360 uL plates: expected 3, found {len(plates_360)}")
    return (not missing), "; ".join(missing)
await check("01.1 deck contents", _one)
''',
        },
        {
            "id": "01.2",
            "points": 10,
            "ask": "STAR plate staircase: 6 plate carriers from rail 7, >=1 rail gap, 0..5 plates left to right",
            "source": r'''
async def _two():
    d = await exercise_2()
    cars = D.carriers(d, plate_only=True)
    if len(cars) != 6:
        return False, f"expected 6 plate carriers, found {len(cars)}"
    placed = sorted(((D.rail_of(d, c), c) for c in cars), key=lambda p: (p[0] is None, p[0]))
    rails = [r for r, _ in placed]
    if rails[0] != 7:
        return False, f"leftmost carrier is on rail {rails[0]}, not 7"
    gaps = [b - a for a, b in zip(rails, rails[1:])]
    if any(g < 2 for g in gaps):
        return False, f"carriers must be at least one rail apart; rails are {rails}"
    counts = [len(D.plates(c)) for _, c in placed]
    if counts != [0, 1, 2, 3, 4, 5]:
        return False, f"plate counts left to right are {counts}, not 0,1,2,3,4,5"
    return True, ""
await check("01.2 plate staircase", _two)
''',
        },
        {
            "id": "01.3",
            "points": 10,
            "ask": "OT-2: adapter in 10, adapter+PCR plate in 11, most-wells labware on odd slots 1-9, fewest on even",
            "source": r'''
async def _three():
    d = await exercise_3()
    problems = []
    if not D.find(d, "adapter"):
        problems.append("no PCR plate adapter found")
    odd  = [D.slot_of(d, r) for r in D.plates(d)]
    counts = {}
    for r in D.plates(d):
        s = D.slot_of(d, r)
        if s is not None:
            counts[s] = max(counts.get(s, 0), r.num_items)
    on_x = [counts.get(s) for s in (1, 3, 5, 7, 9)]
    on_o = [counts.get(s) for s in (2, 4, 6, 8)]
    if any(c is None for c in on_x):
        problems.append(f"slots 1,3,5,7,9 must all hold labware; found {on_x}")
    if any(c is None for c in on_o):
        problems.append(f"slots 2,4,6,8 must all hold labware; found {on_o}")
    if not problems:
        # "Most" and "fewest" are relative to what PyLabRobot ships, so derive
        # them rather than hardcoding a number that a library update invalidates.
        if min(on_x) <= max(on_o):
            problems.append("the X slots must hold strictly more wells than the O slots")
        if len(set(on_x)) != 1 or len(set(on_o)) != 1:
            problems.append("all X slots (and all O slots) should hold the same labware")
    return (not problems), "; ".join(problems)
await check("01.3 alternating grid", _three)
''',
        },
        {
            "id": "01.4",
            "points": 10,
            "ask": "Any deck able to support 8-point serial dilutions of 3 dyes in triplicate, <=500 uL per transfer",
            "source": r'''
async def _four():
    d = await exercise_4()
    problems = []
    # Open-ended by design ("a deck of your choice"), so only the stated
    # constraints are checked: enough wells, enough tips, big enough stocks.
    wells = sum(p.num_items for p in D.plates(d))
    if wells < 8 * 3 * 3:
        problems.append(f"needs room for 8 dilutions x 3 colours x 3 replicates = 72 wells; deck has {wells}")
    tips = sum(t.num_items for t in D.tip_racks(d))
    if tips < 72:
        problems.append(f"needs at least 72 tips for 72 transfers; deck has {tips}")
    if not D.find(d, "reservoir") and not D.find(d, "trough"):
        problems.append("no reservoir or trough for the stock solutions")
    biggest = max([p.get_item(0).max_volume for p in D.plates(d)] or [0])
    if biggest < 500:
        problems.append(f"wells must hold a 500 uL transfer; largest well is {biggest} uL")
    return (not problems), "; ".join(problems)
await check("01.4 serial dilution deck", _four)
''',
        },
    ],

    # ------------------------------------------------------------------ 02
    "02_liquid_handling.ipynb": [
        {
            "id": "02.1",
            "points": 20,
            "ask": "STAR deck + protocol producing the six specified transfers",
            "source": r'''
async def _deck1():
    d = await deck_exercise_1()
    problems = []
    if not (D.find(d, "reservoir") or D.find(d, "trough")):
        problems.append("no 12x15 mL reservoir")
    deep = [p for p in D.plates(d) if p.get_item(0).max_volume >= 2000]
    if not deep:
        problems.append("no 96-well 2 mL deep plate")
    caps = sorted({t.get_item(0).tracker.get_tip().maximal_volume for t in D.tip_racks(d)}) \
           if D.tip_racks(d) else []
    if not any(c >= 1000 for c in caps):
        problems.append("no 1000 uL tip rack")
    if not any(200 <= c < 1000 for c in caps):
        problems.append("no 300 uL tip rack")
    return (not problems), "; ".join(problems)
await check("02.1a deck contents", _deck1)

async def _protocol1():
    # Re-run the protocol on a fresh deck rather than reading the notebook's
    # `deck`: by the time the probe runs, that name belongs to exercise 3, and
    # grading exercise 1 against exercise 3's deck fails every submission.
    global deck, lh
    deck = await deck_exercise_1()
    lh = await visualize_deck(deck, LiquidHandlerChatterboxBackend())
    await run_protocol_exercise_1(deck, lh)

    # The 96-well plate, not "the plate with the biggest wells" -- the 12 x 15 mL
    # reservoir wins that comparison by a factor of six.
    plate = next((p for p in D.plates(deck) if p.num_items == 96), None)
    if plate is None:
        return False, "no 96-well plate on the deck"
    got = D.volumes_by_id(plate)
    problems = []

    # Only two wells have a volume the prompt fixes outright. The rest are
    # bounded rather than exact, because the last two steps take liquid back off
    # the plate: A3 is filled with 50 uL of Dye 1 *plus 50 uL out of D12*, and
    # F12 needs 25 uL more Dye 1 than the reservoir still holds, which the
    # prompt's own hint says to make up "somewhere else on the plate". Where
    # that 25 uL comes from is the student's choice, so it cannot be pinned.
    for well, want in (("B7", 200.0), ("F12", 1800.0)):
        if not D.close(got.get(well, 0.0), want, 1.0):
            problems.append(f"{well}: expected {want:.0f} uL, found {got.get(well, 0.0):.1f}")
    for well, low, high in (("A1", 75.0, 100.0), ("C9", 75.0, 100.0),
                            ("A3", 75.0, 100.0), ("D12", 25.0, 50.0)):
        if not low - 1 <= got.get(well, 0.0) <= high + 1:
            problems.append(f"{well}: expected {low:.0f}-{high:.0f} uL, found {got.get(well, 0.0):.1f}")

    # What the six transfers put on the plate, in total, is fixed even though
    # the individual wells are not: 100 + 200 + 100 + 100 + 50 + 1775 uL came
    # out of the reservoir, and moving liquid between plate wells cannot change
    # the sum.
    total = sum(got.values())
    if not D.close(total, 2325.0, 2.0):
        problems.append(f"the plate holds {total:.1f} uL in total, expected 2325")

    return (not problems), "; ".join(problems[:4])
await check("02.1b transfers", _protocol1)
''',
        },
        {
            "id": "02.3",
            "points": 40,
            "ask": "12-point 1:7 serial dilutions in triplicate: red A-C plate 1, blue E-G plate 1, yellow A-C plate 2",
            "source": r'''
async def _dilutions():
    # Same reason as 02.1b: build the deck and run the protocol here rather than
    # reading whatever globals the notebook finished with.
    global deck, lh
    deck = await deck_exercise_3()
    lh = await visualize_deck(deck, LiquidHandlerChatterboxBackend())
    await run_protocol_exercise_3(deck, lh)

    # The dilution plates, in deck order. Filtering to 96 wells drops the
    # single-well stock troughs, which are Plates too.
    ps = [p for p in D.plates(deck) if p.num_items == 96]
    ps.sort(key=lambda p: (D.slot_of(deck, p) is None, D.slot_of(deck, p)))
    if len(ps) < 2:
        return False, f"expected at least 2 dilution plates, found {len(ps)}"
    first, second = ps[0], ps[1]
    problems = []
    def band(plate, rows, label):
        vols = D.volumes_by_id(plate)
        for row in rows:
            series = [vols.get(f"{row}{c}", 0.0) for c in range(1, 13)]
            filled = [v for v in series if v > 1.0]
            if len(filled) < 12:
                problems.append(f"{label} row {row}: expected 12 concentrations, found {len(filled)}")
                return
            # A finished row does not read 480 uL across. Every well but the
            # last has passed 60 uL on to its neighbour, so the row is
            # 420 ... 420, 480 -- and the first well is 60 uL lower again if the
            # student followed the recipe's 420 uL start rather than the
            # protocol section's 480 uL (the prompt states both).
            final = series[-1]
            if not D.close(final, 480.0, 30.0):
                problems.append(f"{label} row {row}: last well holds {final:.0f} uL, expected ~480")
                return
            carried = final - 60.0
            off = [c for c in range(2, 12) if not D.close(series[c - 1], carried, 30.0)]
            if off:
                problems.append(f"{label} row {row}: {len(off)} well(s) not ~{carried:.0f} uL "
                                "after passing 60 uL on")
            if not (D.close(series[0], carried, 30.0) or D.close(series[0], carried - 60.0, 30.0)):
                problems.append(f"{label} row {row}: stock well holds {series[0]:.0f} uL, "
                                f"expected ~{carried:.0f}")
    band(first, "ABC", "red")
    band(first, "EFG", "blue")
    band(second, "ABC", "yellow")
    return (not problems), "; ".join(problems[:4])
await check("02.3 serial dilutions", _dilutions)
''',
        },
    ],

    # ------------------------------------------------------------------ 03
    "03_moving_labware.ipynb": [
        {
            "id": "03.1",
            "points": 40,
            "ask": "OT-2 gripper: add_plate, add_reservoir, move_labware_row_wise, and the layouts they build",
            "source": r'''
# Exercise 1's gripper only works on an OT-2, and the notebook's `lh` is a STAR
# by the time the probe runs -- exercise 2 rebuilt it. Each check below gets its
# own empty OT-2, which also means the checks cannot disturb each other.
async def _ot2_handler():
    # Imported here, not taken from the notebook: which labware the student
    # imported is their choice, and a probe must not depend on it.
    from pylabrobot.resources.opentrons import OTDeck
    return await visualize_deck(OTDeck(), LiquidHandlerChatterboxBackend())

async def _add_plate():
    g = Exercise_1A_Gripper(lh=await _ot2_handler())
    g.add_plate(6, "graded_probe_plate")
    hit = [p for p in D.plates(g.lh.deck) if p.name == "graded_probe_plate"]
    if not hit:
        return False, "add_plate did not put a plate on the deck"
    if D.slot_of(g.lh.deck, hit[0]) != 6:
        return False, f"plate landed in slot {D.slot_of(g.lh.deck, hit[0])}, not the slot requested"
    if not D.named_like(hit[0], "cor", "360"):
        return False, f"expected a cor_96_wellplate_360uL_Fb, got {type(hit[0]).__name__}"
    return True, ""
await check("03.1a add_plate", _add_plate)

async def _add_reservoir():
    g = Exercise_1B_Gripper(lh=await _ot2_handler())
    g.add_reservoir(3, "graded_probe_res", "water", 5000)
    hit = [r for r in D.walk(g.lh.deck) if r.name == "graded_probe_res"]
    if not hit:
        return False, "add_reservoir did not put a reservoir on the deck"
    if D.slot_of(g.lh.deck, hit[0]) != 3:
        return False, "reservoir landed in the wrong slot"
    if not D.close(D.total_volume(hit[0]), 5000.0, 50.0):
        return False, f"reservoir holds {D.total_volume(hit[0]):.0f} uL, expected the volume requested"
    return True, ""
await check("03.1b add_reservoir", _add_reservoir)

async def _row_wise():
    # Build the layout the exercise builds -- plates on 1, 4, 7, 10 and
    # reservoirs on 2, 5, 8 -- then call the student's mover, rather than
    # inspecting whatever the notebook's globals ended up holding.
    from pylabrobot.resources import cor_96_wellplate_360uL_Fb, VWR_1_troughplate_195000uL_Ub
    g = Exercise_1C_Gripper(lh=await _ot2_handler())
    plate_slots, reservoir_slots = (1, 4, 7, 10), (2, 5, 8)
    for slot in plate_slots:
        g.lh.deck.assign_child_at_slot(cor_96_wellplate_360uL_Fb(name=f"graded_plate_{slot}"), slot)
    for slot in reservoir_slots:
        g.lh.deck.assign_child_at_slot(VWR_1_troughplate_195000uL_Ub(name=f"graded_res_{slot}"), slot)

    for slot in plate_slots:
        g.move_labware_row_wise(f"graded_plate_{slot}", "right")
    for slot in reservoir_slots:
        g.move_labware_row_wise(f"graded_res_{slot}", "left")

    # The OT-2's rows are 1-3, 4-6, 7-9, 10-11. Which free slot a labware lands
    # in depends on how the student skips over occupied ones, so what is checked
    # is the requirement: everything moved, in the right direction, without
    # leaving its row.
    def row_of(slot):
        return next(r for r in ([1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11]) if slot in r)

    problems = []
    for label, slots, direction in (("plate", plate_slots, "right"),
                                    ("reservoir", reservoir_slots, "left")):
        for slot in slots:
            name = f"graded_{'plate' if label == 'plate' else 'res'}_{slot}"
            moved = g.lh.deck.get_slot(g.lh.deck.get_resource(name))
            if moved not in row_of(slot):
                problems.append(f"{name} left its row: {slot} -> {moved}")
            elif (moved <= slot) if direction == "right" else (moved >= slot):
                problems.append(f"{name} did not move {direction}: {slot} -> {moved}")
    return (not problems), "; ".join(problems[:4])
await check("03.1c move_labware_row_wise", _row_wise)
''',
        },
        {
            "id": "03.2",
            "points": 60,
            "ask": "STAR gripper: move_plate, move_carrier_to_rails, add_lids, and the T-P-T-P-T-P staircase from rail 7",
            "source": r'''
def _gripper_api():
    g = Exercise_2D_Gripper(lh)
    missing = [m for m in ("get_labware_by_name", "move_plate", "move_carrier_to_rails", "add_lids")
               if not callable(getattr(g, m, None))]
    return (not missing), (f"not implemented: {', '.join(missing)}" if missing else "")
await check("03.2a gripper methods", _gripper_api)

def _staircase():
    d = lh.deck
    tip_rails   = D.occupied_rails(d, tip_only=True)
    plate_rails = D.occupied_rails(d, plate_only=True)
    if not tip_rails or not plate_rails:
        return False, "expected alternating tip and plate carriers"
    if min(tip_rails) != 7:
        return False, f"the staircase should start with a tip carrier at rail 7; found {min(tip_rails)}"
    order = sorted([(r, "T") for r in tip_rails] + [(r, "P") for r in plate_rails])
    letters = "".join(kind for _, kind in order)
    if "TPTPTP" not in letters:
        return False, f"carriers should alternate T-P-T-P-T-P; found {letters}"
    return True, ""
await check("03.2b alternating staircase", _staircase)

def _lids():
    from pylabrobot.resources import Plate
    lidded = [p for p in D.plates(lh.deck) if getattr(p, "lid", None) is not None]
    if len(lidded) < 4:
        return False, f"expected at least 4 lidded plates, found {len(lidded)}"
    return True, ""
await check("03.2c lids", _lids)
''',
        },
    ],

    # ------------------------------------------------------------------ 04
    "04_modular_cloning.ipynb": [
        {
            "id": "04.1",
            "points": 15,
            "ask": "add_fragments() puts each fragment's volume in its well",
            "source": r'''
async def _add_fragments():
    import pandas as pd, os
    # A fresh deck: the notebook's `deck` has been through exercise 3, which
    # takes 30 uL out of the fragment wells this check is about. And the 288
    # fragments live on *three* plates of 96, so there is no one plate holding
    # them all.
    d = await make_golden_gate_ot2()
    add_fragments(d, os.path.join(os.path.dirname(os.getcwd()), "data", "fragments.csv"))

    df = pd.read_csv(os.path.join(os.path.dirname(os.getcwd()), "data", "fragments.csv"))
    plates = [p for p in D.plates(d) if p.num_items == 96]
    problems = []
    # Which deck plate a plate_id maps to is the student's choice, so each group
    # of fragments only has to match *some* plate, one group per plate.
    unclaimed = list(plates)
    for plate_id, group in df.groupby("plate_id"):
        wanted = {r["well_id"]: float(r["volume (uL)"]) for _, r in group.iterrows()}
        match = next((p for p in unclaimed
                      if all(D.close(D.volumes_by_id(p).get(w, 0.0), v, 1.0)
                             for w, v in wanted.items())), None)
        if match is None:
            problems.append(f"no plate holds the volumes fragments.csv lists for plate {plate_id}")
        else:
            unclaimed.remove(match)
    return (not problems), "; ".join(problems[:3])
await check("04.1 add_fragments", _add_fragments)
''',
        },
        {
            "id": "04.2",
            "points": 20,
            "ask": "convert_well_id, get_well and extract_fragment_combinations",
            "source": r'''
# The ask is a *string* in the plate's own format -- "A01" -> "A1" -- not an
# index. Ten and twelve are in here because stripping the zero as text rather
# than through int() gets those wrong.
CASES = {"A01": "A1", "B01": "B1", "H01": "H1", "A02": "A2", "A10": "A10", "H12": "H12"}
def _convert():
    got = {k: convert_well_id(k) for k in CASES}
    wrong = [f"{k} -> {got[k]!r}, expected {v!r}" for k, v in CASES.items() if got[k] != v]
    return (not wrong), "; ".join(wrong[:3])
await check("04.2a convert_well_id", _convert)

def _get_well():
    import pandas as pd, os
    df = pd.read_csv(os.path.join(os.path.dirname(os.getcwd()), "data", "fragments.csv"))
    misses = []
    for fragment_id in df["fragment_id"].head(10):
        result = get_well(fragment_id, df)
        # The ask is `well_id, plate_name`, and a fragment in several wells may
        # come back as any one of them -- get_well samples. So: a pair, whose
        # first element is one of the wells this fragment is actually in.
        well = result[0] if isinstance(result, tuple) else result
        if well not in set(df[df["fragment_id"] == fragment_id]["well_id"]):
            misses.append(f"{fragment_id} -> {result!r}")
    if misses:
        return False, f"{len(misses)} of 10 resolved wrong: " + "; ".join(misses[:3])
    # A fragment that is not in the table at all is the case the work orders
    # depend on: it has to be reported, not invented.
    absent = get_well("NOT_A_FRAGMENT", df)
    if absent != (None, None):
        return False, f"a fragment that is not in the table returned {absent!r}, expected (None, None)"
    return True, ""
await check("04.2b get_well", _get_well)

def _extract():
    import pandas as pd, os
    base = os.path.dirname(os.getcwd())
    out = extract_fragment_combinations(os.path.join(base, "data", "cloning.csv"),
                                        os.path.join(base, "data", "fragments.csv"))
    if out is None:
        return False, "returned None"
    yielded = list(out)  # a generator has no len(); consuming it is the point

    # How many orders *should* come through: the ones whose three fragments are
    # all in the table. Derived from the data, so the check survives an edit to
    # either CSV.
    fragments = pd.read_csv(os.path.join(base, "data", "fragments.csv"))
    known = set(fragments["fragment_id"])
    orders = pd.read_csv(os.path.join(base, "data", "cloning.csv"))
    valid = [row for _, row in orders.iterrows()
             if all(f in known for f in row["fragment_tuple"].strip("()").split(","))]
    if len(yielded) != len(valid):
        return False, (f"yielded {len(yielded)} work orders; {len(valid)} of the "
                       f"{len(orders)} have all three fragments in fragments.csv")
    if yielded and any("0" == str(well)[1:2] for well, _ in yielded):
        return False, "well ids should be converted: 'A01' becomes 'A1'"
    return True, ""
await check("04.2c extract_fragment_combinations", _extract)
''',
        },
        {
            "id": "04.4",
            "points": 15,
            "ask": "verify_results() reports per-order completion",
            "source": r'''
def _verify():
    import os, pandas as pd
    base = os.path.dirname(os.getcwd())
    out = verify_results(os.path.join(base, "data", "cloning.csv"), deck)
    if out is None:
        return False, "returned None"
    try:
        n = len(out)
    except TypeError:
        return False, f"expected something iterable per work order, got {type(out).__name__}"

    # The orders that could not be filled are exactly the ones naming a fragment
    # that is not in fragments.csv -- computed from the data rather than written
    # down, so an edit to either CSV cannot silently invalidate this.
    fragments = pd.read_csv(os.path.join(base, "data", "fragments.csv"))
    known = set(fragments["fragment_id"])
    orders = pd.read_csv(os.path.join(base, "data", "cloning.csv"))
    unfillable = sum(1 for _, row in orders.iterrows()
                     if not all(f in known for f in row["fragment_tuple"].strip("()").split(",")))
    if n != unfillable:
        return False, (f"reported {n} incomplete orders; {unfillable} of the {len(orders)} "
                       "name a fragment that is not on the deck")
    return True, ""
await check("04.4 verify_results", _verify)
''',
        },
    ],

    # ------------------------------------------------------------------ 05
    "05_interfacing_with_peripherals.ipynb": [
        {
            "id": "05.1",
            "points": 60,
            "ask": "GeneralPlateReader works on any plate size; make_deck builds the dilution deck; "
                   "pipette_vols_careful skips impossible transfers",
            "source": r'''

def _general():
    # The point of the exercise is "any size plate", so check a non-96 plate.
    from pylabrobot.resources import cor_96_wellplate_360uL_Fb
    import tempfile
    r = GeneralPlateReader(tempfile.mkdtemp())
    p = cor_96_wellplate_360uL_Fb(name="graded_probe_reader_plate")
    r.read_plate(p) if len(inspect.signature(r.read_plate).parameters) == 1 else r.read_plate(p, 1.0, 0.1)
    df = getattr(r, "df", None)
    if df is None:
        return False, "read_plate did not populate self.df"
    if df.size == 0:
        return False, "self.df is empty"
    # "Any size plate" means the frame has to match the plate it was handed,
    # which is the whole point of the exercise.
    if df.shape != (p.num_items_y, p.num_items_x):
        return False, (f"self.df is {df.shape[0]}x{df.shape[1]} for a "
                       f"{p.num_items_y}x{p.num_items_x} plate")
    return True, ""
await check("05.1b reads a plate", _general)

def _deck_2():
    d = make_deck() if callable(globals().get("make_deck")) else None
    if d is None:
        return False, "not attempted"
    problems = []
    if not (D.find(d, "reservoir") or D.find(d, "trough")):
        problems.append("no water reservoir")
    if not D.tip_racks(d):
        problems.append("no tips")
    if not D.plates(d):
        problems.append("no DNA plate")
    return (not problems), "; ".join(problems)
await check("05.1c make_deck", _deck_2)

async def _careful():
    # The signature is pre-written in the stub, so checking it grades nothing.
    # What the exercise asks for is the three refusals, so make each of them
    # happen on a real deck and watch whether the well changes.
    from pylabrobot.resources import TipRack
    if not callable(globals().get("pipette_vols_careful")):
        return False, "not attempted"

    d = make_deck(plate_type="24_well", initial_vol=2000)
    handler = await visualize_deck(d, LiquidHandlerChatterboxBackend())
    plate = next(p for p in D.plates(d) if p.num_items == 24)
    reservoir = next(r for r in D.plates(d) if r.num_items == 1)
    racks = [r for r in D.tip_racks(d)]
    tips = prepare_tip_generator(racks)
    biggest_tip = max(r.get_item(0).make_tip().maximal_volume for r in racks)
    well = plate.get_well("A1")
    headroom = well.max_volume - D.volume(well)

    problems = []
    async def unchanged(volume, label):
        before = D.volume(well)
        await pipette_vols_careful(handler, reservoir, plate, tips, "A", "1", volume)
        if not D.close(D.volume(well), before, 0.1):
            problems.append(f"{label} was pipetted anyway ({volume:.0f} uL)")

    await unchanged(-50.0, "a negative volume")
    await unchanged(biggest_tip + 100.0, "a volume larger than the biggest tip")
    await unchanged(headroom + 100.0, "a volume that would overflow the well")

    # ...and one that is fine, so "skip everything" does not pass.
    before = D.volume(well)
    await pipette_vols_careful(handler, reservoir, plate, tips, "A", "1", 100.0)
    if not D.close(D.volume(well), before + 100.0, 1.0):
        problems.append("a 100 uL dilution that breaks none of the rules was skipped")
    return (not problems), "; ".join(problems)
await check("05.1d pipette_vols_careful", _careful)
''',
        },
        {
            "id": "05.2",
            "points": 40,
            "ask": "GrowthSimulatedCellImager simulates growth over days; make_deck_2B builds the passaging deck",
            "source": r'''
def _imager():
    # __init__'s signature is pre-written, so it proves nothing. What the
    # exercise asks for is that the parameters are kept and used: growth from
    # the initial confluency at the given rate, clipped to the maximum.
    import tempfile
    imager = GrowthSimulatedCellImager(tempfile.mkdtemp(),
                                       initial_confluency=10.0,
                                       growth_rate=1.6,
                                       max_confluency=120.0,
                                       per_well_variability=30.0)
    if not isinstance(getattr(imager, "confluent_wells", None), set):
        return False, "confluent_wells should be a set of the wells already confluent"

    early = [float(imager._simulate_confluency(1)) for _ in range(60)]
    late = [float(imager._simulate_confluency(5)) for _ in range(60)]
    problems = []
    if sum(late) / len(late) <= sum(early) / len(early):
        problems.append("confluency should grow with the time point")
    if min(early + late) < 0 or max(early + late) > 120.0:
        problems.append("confluency should be clipped to 0..max_confluency")
    # 10 * 1.6 = 16, plus at most 30 of noise: a reading of 60 at t=1 means the
    # growth equation is not the one the exercise gives.
    if max(early) > 10.0 * 1.6 + 30.0 + 1:
        problems.append(f"at t=1 confluency reached {max(early):.0f}%, more than I*r^t + noise")
    return (not problems), "; ".join(problems)
await check("05.2a GrowthSimulatedCellImager", _imager)

def _confluency():
    # predict_cell_confluency is the decision the passaging protocol is driven
    # by, so it gets its own check: one nearly empty well, one nearly full one.
    import tempfile, os
    imager = GrowthSimulatedCellImager(tempfile.mkdtemp())
    paths = {}
    for well_name, confluency in (("A1", 2.0), ("B1", 100.0)):
        path = os.path.join(imager.image_output_dir, f"graded_{well_name}.png")
        imager._generate_cell_image(confluency=confluency).save(path)
        paths[well_name] = path

    ready = imager.predict_cell_confluency(paths, 80.0)
    ready = list(ready or [])
    problems = []
    if "A1" in ready:
        problems.append("an almost empty well was reported ready for passaging")
    if "B1" not in ready:
        problems.append("a fully confluent well was not reported ready for passaging")
    if "B1" not in imager.confluent_wells:
        problems.append("a confluent well was not recorded in self.confluent_wells")
    return (not problems), "; ".join(problems)
await check("05.2c predict_cell_confluency", _confluency)

def _deck_2b():
    d = make_deck_2B()
    if d is None:
        return False, "not attempted"
    problems = []
    reservoirs = D.find(d, "reservoir") + D.find(d, "trough")
    if len(reservoirs) < 1:
        problems.append("no reservoirs for PBS, trypsin and media")
    if not D.tip_racks(d):
        problems.append("no tips")
    if not D.plates(d):
        problems.append("no cell culture plate")
    return (not problems), "; ".join(problems)
await check("05.2b make_deck_2B", _deck_2b)
''',
        },
    ],
}


def probe_for(notebook: str) -> str | None:
    """The full probe source for one notebook, or None if it is not graded."""
    entries = RUBRIC.get(notebook)
    if not entries:
        return None
    return PREAMBLE + "\n".join(entry["source"] for entry in entries) + EPILOGUE


def points_for(notebook: str) -> int:
    return sum(entry["points"] for entry in RUBRIC.get(notebook, []))


def score_for(notebook: str, results) -> tuple[float, int]:
    """(points earned, points available) for one notebook's probe results.

    Points are stated per *exercise*, because that is how the workshops state
    them, and an exercise's points are split evenly across its checks. That is
    what makes the finer-grained checks worth having: a submission whose gripper
    moves plates but not carriers earns part of exercise 3.2 instead of nothing.

    A check belongs to the entry whose id its label starts with -- labels are
    written "03.1a add_plate" against an entry id of "03.1".
    """
    earned = available = 0.0
    for entry in RUBRIC.get(notebook, []):
        mine = [ok for label, ok, _ in results if label.split()[0].startswith(entry["id"])]
        available += entry["points"]
        if mine:
            earned += entry["points"] * sum(1 for ok in mine if ok) / len(mine)
    return round(earned, 1), int(available)
