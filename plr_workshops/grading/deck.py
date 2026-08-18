"""Introspection helpers for grading: what is on a deck, where, and how full.

These run inside the student's kernel, against their live objects, after their
notebook has executed. They exist so a rubric check reads like the exercise
prompt -- "six plate carriers, one rail apart, holding 0..5 plates" -- rather
than like a tree walk.

Design rule, carried from what the exercises actually ask: check the *thing that
was asked for* and nothing else. Resource names, the order things were assigned,
and any labware the student added beyond the requirement are not graded, because
none of them were specified. Positions are matched by rail or slot rather than by
raw coordinates, so a correct layout built any way at all still passes.
"""

from __future__ import annotations

from typing import Iterable, Optional


def walk(resource) -> Iterable:
    """Every resource under `resource`, including itself."""
    yield resource
    for child in getattr(resource, "children", []) or []:
        yield from walk(child)


def kind(resource) -> str:
    return type(resource).__name__


def named_like(resource, *fragments: str) -> bool:
    """True if the resource's class or model name contains all fragments.

    Matching on names rather than identity because the exercises specify labware
    in prose ("a 12x15 mL reservoir"), and several PyLabRobot definitions satisfy
    a given prose description.
    """
    haystack = f"{kind(resource)} {getattr(resource, 'model', '') or ''} {resource.name}".lower()
    return all(fragment.lower() in haystack for fragment in fragments)


def find(deck, *fragments: str) -> list:
    return [r for r in walk(deck) if r is not deck and named_like(r, *fragments)]


def count(deck, *fragments: str) -> int:
    return len(find(deck, *fragments))


def plates(deck) -> list:
    from pylabrobot.resources import Plate

    return [r for r in walk(deck) if isinstance(r, Plate)]


def tip_racks(deck) -> list:
    from pylabrobot.resources import TipRack

    return [r for r in walk(deck) if isinstance(r, TipRack)]


def carriers(deck, plate_only: bool = False, tip_only: bool = False) -> list:
    from pylabrobot.resources import Carrier, PlateCarrier, TipCarrier

    wanted = PlateCarrier if plate_only else TipCarrier if tip_only else Carrier
    return [r for r in walk(deck) if isinstance(r, wanted)]


def item_holders(deck) -> list:
    """Labware that holds a countable grid of positions: plates, tube racks,
    reservoirs, troughs, tip racks.

    Grading by position count rather than by vendor name, because the prompts
    specify labware as "a 24-count tube rack" and several PyLabRobot definitions
    satisfy any given description.
    """
    from pylabrobot.resources import ItemizedResource

    return [r for r in walk(deck) if isinstance(r, ItemizedResource) and getattr(r, "num_items", 0)]


def rail_of(deck, resource) -> Optional[int]:
    """Which STAR rail a resource sits on, or None if it is not on a rail."""
    location = resource.get_absolute_location() if hasattr(resource, "get_absolute_location") else None
    if location is None or not hasattr(deck, "rails_to_location"):
        return None
    for rail in range(1, 56):
        try:
            if abs(deck.rails_to_location(rail).x - location.x) < 0.5:
                return rail
        except Exception:  # noqa: BLE001 - past the end of this deck
            break
    return None


def slot_of(deck, resource) -> Optional[int]:
    """Which OT-2 slot a resource sits in, or None."""
    if not hasattr(deck, "slot_locations"):
        return None
    location = resource.get_absolute_location()
    for index, slot in enumerate(deck.slot_locations, start=1):
        if abs(slot.x - location.x) < 0.5 and abs(slot.y - location.y) < 0.5:
            return index
    return None


def occupied_rails(deck, plate_only: bool = False, tip_only: bool = False) -> list[int]:
    found = [rail_of(deck, c) for c in carriers(deck, plate_only, tip_only)]
    return sorted(r for r in found if r is not None)


def volume(well) -> float:
    """Liquid volume in a single well.

    PyLabRobot 0.2.2 keeps volume on the well's tracker; `serialize_state()` on
    the *plate* returns only rotation, which is a trap worth not falling into.
    """
    try:
        return float(well.tracker.get_used_volume())
    except Exception:  # noqa: BLE001 - a tracker that was disabled or never set
        return 0.0


def well_volume(plate, well_id: str) -> float:
    return volume(plate.get_item(well_id))


def filled_wells(plate, minimum: float = 0.01) -> dict[str, float]:
    """{well_id: volume} for every well holding more than `minimum`."""
    out = {}
    for item in plate.get_all_items():
        held = volume(item)
        if held > minimum:
            out[item.name.split("_")[-1] if "_" in item.name else item.name] = held
    return out


def volumes_by_id(plate) -> dict[str, float]:
    """{'A1': 100.0, ...} for every well, using plate coordinates, not names."""
    out = {}
    for row in range(plate.num_items_y):
        for col in range(plate.num_items_x):
            well_id = f"{chr(ord('A') + row)}{col + 1}"
            try:
                out[well_id] = volume(plate.get_item(well_id))
            except Exception:  # noqa: BLE001 - plate smaller than the sweep
                pass
    return out


def total_volume(resource) -> float:
    """All liquid anywhere under a resource -- e.g. a whole reservoir."""
    return sum(volume(r) for r in walk(resource) if hasattr(r, "tracker"))


def close(a: float, b: float, tolerance: float = 1.0) -> bool:
    """Volumes compared with a tolerance, because floats and pipetting."""
    return abs(a - b) <= tolerance
