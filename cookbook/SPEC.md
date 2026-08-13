# Chapter build specs

Per-chapter implementation spec. Written so a chapter can be built without making design decisions.

**Read first:** `README.md` (recipe format, house style, how to register a recipe) and
`part2/09_moving_labware.qmd` (the reference implementation — copy its structure exactly).

**Rules that apply to every chapter:**

1. Every API name must be verified against PLR 0.2.2 source before writing it down. Appendix A below
   lists the ones already verified — prefer it over memory. Deprecated shims still import and still
   work, so a wrong name will **not** necessarily fail the build.
2. Every recipe gets an entry in `recipes.yml`. No exceptions.
3. Snippets execute against `LiquidHandlerChatterboxBackend`. Use `#| eval: false` only when the
   snippet needs hardware or a resource the chapter has not built.
4. Parts I–II are **breadth-first**: cover the everyday surface, do not exhaust any topic. Examples
   illustrate and move on. If a topic wants a project, it belongs in Part III or IV.
5. No class hierarchies, no ABCs, no architecture in Parts I–II.
6. **No course material.** The cookbook contains no exercises, no assignments, no graded content,
   no BME 590 framing, and no references to workshops, points, or deliverables. It is a standalone
   manual that happens to be useful to a course. Chapters 14–15 are *guided builds* — the reader
   follows completed steps — not exercises. If a sentence would only make sense to someone enrolled
   in the class, it does not belong here.

**Deck figures are deferred.** An embeddable deck renderer is planned (`PLAN.md` §3.7) and recipes
will eventually end with `show(lh.deck)`. Until it exists, **do not hand-roll diagrams, screenshots,
or ASCII deck art** — write the chapter without figures and leave a `<!-- figure: deck after setup -->`
comment where one belongs. Retrofitting is cheap; unpicking fifteen bespoke solutions is not.

---

## Ch. 1 — Getting a robot on screen

**Goal:** a reader with nothing installed has a simulated robot running in ten minutes.

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Get a liquid handler running with no hardware | `#first-robot` | `LiquidHandler`, `LiquidHandlerChatterboxBackend`, `STARLetDeck`, `setup` | The ten-line snippet. Show the chatterbox output — that narration *is* the teaching aid |
| See the deck | `#visualizer` | `Visualizer` | Host/port config; note it needs a websocket, so it is the one thing that will not work under Pyodide |
| Inspect what is on the deck | `#summary` | `lh.summary()`, `deck.get_all_children()` | |
| Simulate a whole workcell | `#workcell` | `Thermocycler`, `Incubator` + their chatterbox backends | **The standout capability of 0.2.2** — ~15 machine types have chatterboxes. Keep it to two machines |
| Shut down cleanly | `#setup-stop` | `setup`, `stop`, `async with` | |

**Must cover:** why everything is `await`; `await` in a notebook vs a script (`asyncio.run`,
autoawait) — this is the single most common day-one blocker.

**Callout (important):** `setup()` is not optional. PLR enforces it with `@need_setup_finished` on
`aspirate`, `dispense`, `pick_up_tips`, `drop_tips`. Forward-reference ch. 13's decorator material.

**Do not cover:** backends beyond chatterbox (ch. 12), deck construction detail (ch. 3).

---

## Ch. 2 — Standard labware

**Goal:** the reader can find the labware they physically have.

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Decode a labware name | `#naming` | — | `<vendor>_<n>_<type>_<volume>uL_<bottom>`. Worked example: `nest_1_troughplate_195000uL_Vb` |
| Find a part by vendor and catalog number | `#find-labware` | 26 vendor packages under `pylabrobot.resources` | Show the docstrings carry catalog numbers (e.g. Alpaqua `A000400`) |
| Look up a resource by name | `#get-resource` | `Resource.get_resource`, `get_all_children` | Name uniqueness within a tree; `ResourceNotFoundError` |
| Search the library | `#query` | `resources.utils.query` | |

**Must cover:** the rename migration in progress. Old names survive as shims marked
`# remove v1b1` — ~10 vendor packages have them. Prefer snake_case current names.

**Callout (warning):** a deprecated name imports cleanly and behaves correctly, so nothing tells you
that you are on a name scheduled for deletion.

**Facts:** 26 vendor packages, 143 plate definitions. New in 0.2.2: `bioer`, `btx`, `diy`,
`greiner`, `imcs`, `perkin_elmer`. Gone: `corning_axygen`, `corning_costar`, `ml_star`, `stanley`
(consolidated into `corning`). `resources/diy/` holds community 3D-printed labware — worth a pointer.

---

## Ch. 3 — Putting things on the deck

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Build a deck from carriers | `#build-deck` | `deck.assign_child_resource(resource, rails=)`, `PLT_CAR_L5AC_A00`, `carrier[0] = plate` | `rails=` is Hamilton; `OTDeck` uses slots. Show both |
| Where is this thing, really | `#locations` | `.location`, `get_absolute_location()` | `.location` is **parent-relative** — the classic confusion |
| Will it fit | `#collisions` | `check_can_drop_resource_here`, `get_highest_known_point` | New in 0.2.2 |
| Rotate a plate | `#rotation` | `Rotation`, `Resource.rotated()` | Landscape vs portrait |

**Python sidebar:** `__setitem__` on carriers; mutable default arguments in deck-builder functions.

**Do not cover:** anchors in depth (ch. 5), custom labware geometry (ch. 14).

---

## Ch. 4 — Indexing

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Select wells | `#select` | `plate["A1:H1"]`, `["A1","B2"]`, ints, `(row, col)` | The full grammar in one table |
| Rows and columns | `#rows-cols` | `row()`, `column()`, `get_item`, `get_items` | |
| Walk a plate in batches | `#traverse` | `traverse(direction, batch_size, repeat)` | Generator — show `itertools.islice` rather than a manual loop |
| Map 96 into a 384 quadrant | `#quadrant` | `Plate.get_quadrant()` | The motivating example for this chapter |
| Convert between labels and indices | `#labels` | `row_index_to_label`, `label_to_row_index`, `split_identifier` | New in 0.2.2 |
| Print an occupancy map | `#summary-map` | `summary(occupied_func=...)` | Custom predicate |

**Python sidebar:** slices, `__getitem__`, comprehensions, `zip`/`enumerate`, generators.

---

## Ch. 5 — Pipetting

**The most important chapter in Part I.** The arguments, not just the call.

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Aspirate and dispense | `#basics` | `lh.aspirate`, `lh.dispense` | |
| Control speed and height | `#flow-height` | `flow_rates`, `liquid_height`, `blow_out_air_volume` | |
| Target a position within a well | `#offsets` | `offsets=[Coordinate(...)]`, `center()`, `get_anchor()` | Motivations: last 5 µL from a corner; dispense on the side wall; avoid a bead pellet |
| Aspirate from one trough with 8 channels | `#spread` | `spread="wide"/"tight"`, `use_channels` | Backed by `get_wide_/get_tight_single_resource_liquid_op_offsets` |
| Mix during a transfer | `#mix` | `mix=[Mix(volume, repetitions, flow_rate, surface_following_distance)]` | **New in 0.2.2** — replaces hand-rolled aspirate/dispense loops |
| When channels do not fit | `#channel-spacing` | `ChannelsDoNotFitError`, `get_channel_spacings`, no-go zones | Default spacing 9 mm |

**Python sidebar (critical):** `None` means "backend default", not zero. `flow_rates=None` ≠
`flow_rates=0`. This trips up nearly everyone.

**Cross-ref:** the bead-pellet offset recipe in ch. 9 reuses this material — link both ways.

---

## Ch. 6 — The shortcuts

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| One call instead of twenty lines | `#transfer` | `lh.transfer(source, targets, source_vol=, ratios=, target_vols=)` | Routes through `aspirate`/`dispense` |
| Set default channels | `#use-channels` | `lh.use_channels([...])` | |
| 96-head operations | `#head96` | `aspirate96`, `dispense96`, `pick_up_tips96`, `drop_tips96` | |

**Callout (warning) — required:** `lh.stamp()` is **broken in 0.2.2**. It dispenses into `source`,
not `target`; `target` is used only in a shape assertion. Document it, show the workaround
(`aspirate96` + `dispense96` explicitly), do not build a recipe on it.

---

## Ch. 7 — Worklists and data formats

**Framing, stated in the opening paragraph:** PLR ships no worklist support — no `.gwl`, no `csv`
import anywhere, `pandas` in exactly one file. That is fine. Worklists are not a PLR feature; they
are how PLR meets everything around it (LIMS exports, schedulers, ELNs, a colleague's spreadsheet).
This chapter teaches the seam.

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Drive a run from a CSV | `#csv-run` | `csv`, `lh.transfer` | One row per transfer |
| Validate before moving a channel | `#validate` | — | Check wells exist, volumes fit, sources have enough. Pure Python |
| Group rows into channel-parallel batches | `#batching` | `sort_by_xy_and_chunk_by_x` | New in 0.2.2, purpose-built for this |
| Write results back out | `#results` | `csv`, `pathlib` | Plate maps, run records |
| Pick a format | `#formats` | — | **CSV for worklists, JSON for state, log lines for audit.** Three jobs, do not mix |

**Must cover:** pandas vs plain `csv`, honestly — a three-column worklist does not need a DataFrame.

**Cross-ref:** `@dry_run` (ch. 13) and `ChannelizedError` recovery (ch. 10) — a half-executed
worklist is the shared failure case.

---

## Ch. 8 — Tips

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Pick up and put back | `#pickup` | `pick_up_tips`, `drop_tips`, `return_tips`, `discard_tips` | The distinction between the last three is the chapter's core |
| Drop a tip that still has liquid | `#nonzero` | `allow_nonzero_volume` | |
| Stream tips across several racks | `#streaming` | `functional.get_all_tip_spots` | |
| Find out what tips are where | `#inventory` | `probe_tip_inventory`, `consolidate_tip_inventory`, `probe_tip_presence_via_pickup` | |
| What is on the head right now | `#head-state` | `get_mounted_tips`, `update_head_state`, `clear_head_state` | `get_mounted_tips` is the friendly one |

**Errors to name:** `NoTipError`, `HasTipError` (full treatment in ch. 10).

---

## Ch. 9 — Moving labware ✅ WRITTEN

Reference implementation. Do not modify without updating `README.md`'s format description.

---

## Ch. 10 — When it complains

**Scope:** the ~19 **portable** errors only. Backend families are ch. 12.

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Read a PLR traceback | `#reading` | — | |
| The portable errors | `#catalog` | see Appendix B | Table: error → what you did → fix |
| Recover from a partial multichannel failure | `#channelized` | `ChannelizedError.errors` | **The important one.** Blind retry re-runs channels that succeeded → double dispense. Retry only failed channels |
| Turn tracking off deliberately | `#no-tracking` | `no_volume_tracking()`, `no_tip_tracking()` | Context managers |

**Callout (important):** `CrossContaminationError` still exists as a class but **nothing raises it**.
The cross-contamination tracker and `no_cross_contamination_tracking()` were removed before 0.2.2.
Do not build anything on it.

---

## Ch. 11 — Saving and loading

**The chapter exists because these are two different things and people conflate them.**

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Save a deck layout | `#layout` | `lh.serialize()`, `LiquidHandler.load(path)`, `Resource.save`, `load_from_json_file` | Structure |
| Save and restore contents | `#state` | `serialize_state`, `save_state_to_file`, `load_state_from_file`, `load_all_state` | Volumes, tips |
| Set well contents directly | `#set-volumes` | `Plate.set_well_volumes()` | The non-deprecated one. `set_well_liquids` is deprecated |
| Resume a run | `#resume` | both of the above | |

**Callout (warning):** `find_subclass` only finds classes that have already been imported.
Deserializing a resource whose module was never imported returns `None`. (The old pyserial
import-everything bug is gone — different mechanism in 0.2.2.)

---

## Ch. 12 — Backend kwargs and real hardware

| Recipe | Anchor | APIs | Notes |
|---|---|---|---|
| Pass vendor-specific options | `#backend-kwargs` | `**backend_kwargs` on every op | |
| Control what unknown options do | `#strictness` | `liquid_handling.strictness` | What chatterbox accepts that a STAR rejects |
| Move from simulator to bench | `#going-live` | swap the backend | Checklist form |
| Jog a channel by hand | `#jogging` | `prepare_for_manual_channel_operation`, `move_channel_x/y/z` | Calibration |
| Read a backend error family | `#backend-errors` | `STARModuleError`, `STARFirmwareError`, `star_firmware_string_to_error` | **Catch the abstract base, not the 49 leaves** |

**Python sidebar (critical):** `**kwargs` packing and unpacking. `**backend_kwargs` is unreadable
without it.

**Facts:** STAR 49 error classes, Cytomat 29, Liconic 14, Molecular Devices 6. Errors live in
`errors.py`, `standard.py`, or inline in the backend file depending on package — there is no single
import.

---

## Ch. 13 — Process and system design

**Format:** seven independent microlessons, each a page or two. Not one long build.
Full rationale in `PLAN.md` §3.5.

| § | Microlesson | Key content |
|---|---|---|
| A | Steps and composition | Protocol as a list of steps; `@step`; checkpoint/resume; **`aspirate` is not idempotent**, so retry granularity matters |
| B | **Recovery policy as composed decorators** — the centrepiece | Three failure tiers (transport / state / semantic) wanting three responses. Decorator order = handler precedence. Partial retry for `ChannelizedError`. Policy is reusable, plans are not |
| C | Dry run and simulation modes | `@dry_run`; the honest limits of simulation (state, not physics) |
| D | Logging and the run record | `PLAN.md` §3.3 as a microlesson: two handlers, `_log_command` (called 25×), `%(relativeCreated)d`, `logger.exception()`, namespace filtering |
| E | Testing without hardware | Four levels: pure functions → deck assertions → protocols vs chatterbox → **record/replay via `io.capture`** (`start_capture`, `validate`). Seed the RNG. **`SaverBackend` is gone in 0.2.2; no `pylabrobot.testing` package either** |
| F | Data management | Run IDs, timestamped dirs, `pathlib`, provenance, snapshot/resume |
| G | Configuration | `pylabrobot.config`: `load_config`, `get_config_file`, `Config` — device addresses out of protocol code |

**The decorator stack to build in §B** (this exact example, it is the chapter's spine):

```python
@retry(3, on=(SerialTimeout,), backoff=0.5)
@recover(NoTipError, using=advance_to_next_tip_spot)
@recover(TooLittleLiquidError, using=switch_to_backup_source)
@recover(ChannelizedError, using=retry_failed_channels_only)
@log_step("add master mix")
async def add_master_mix(lh, plate, source): ...
```

**Must cover:** async decorators need `async def wrapper` + `await func(...)`; use `functools.wraps`.
Read PLR's own `need_setup_finished` (`machines/machine.py`) as the worked example — it is exactly
this shape and it is applied to `aspirate`, `dispense`, `pick_up_tips`, `drop_tips`, `Machine.stop`,
and the plate reader methods.

---

## Ch. 14 — Define custom labware: a PCR plate

**Format change:** guided vertical. One build, start to finish, in order.
**Strictly hand-holding — every step given. No open exercises.**

Chosen because the geometry is genuinely non-trivial *and* 0.2.2 has no PCR plate at all
(`nest_96_wellplate_100ul_pcr_full_skirt` is gone, no replacement). The chapter's output is usable.

**Build order:**

1. Measure a real plate — what to measure, from which datum
2. Choose a base class — reproduce this table:

   | Base | Use when | Cost |
   |---|---|---|
   | `Resource` | arbitrary children, arbitrary positions | no indexing, no volume |
   | `Container` | one addressable volume (`Liddable` since 0.2.2) | no child grid |
   | `ItemizedResource` | full rectangular grid of anything | **grid or it raises** |
   | `Plate` | grid of `Well`s, lid support | plate semantics assumed |
   | `ContainerRack` | grid of *holders* each taking a removable container | indirection via `ResourceHolder` |

3. Lay out wells — `create_ordered_items_2d`
4. Well geometry — `cross_section_type`, `material_z_thickness`, one of the 21 functions in
   `height_volume_functions`, `supports_compute_height_volume_functions`
5. Wrap in a factory function following the naming convention
6. Make it sit right — `PlateHolder.pedestal_size_z` (**required** in 0.2.2, raises if omitted),
   `PlateAdapter.compute_plate_location()`; reuse ch. 9's magnet material
7. Validate — `ResourceDefinitionIncompleteError` tells you what you left out
8. Contribute upstream — `docs/contributor_guide/contributing-new-resources.md`

**The contract this exposes:** `ItemizedResource._get_grid_size()` raises
`ValueError("Not a full grid")` on any non-rectangular arrangement. Get the grid and you get
`traverse`, `row`, `column`, `get_quadrant`; violate it and you keep `num_items` and `get_item` and
lose the rest.

**Closing section (short, generalising):** geometry is fully extensible, state is partially
extensible, **connectivity is not modelled at all** — volume trackers are per-container and
independent, nothing propagates between connected wells. This is what generalises the chapter to
microfluidics and flow cells without building one.

**Decorator payoff (ties to ch. 13):** a `@labware_definition` registration decorator collecting
factory functions into a local catalog, mirroring how PLR's own library is just functions.

---

## Ch. 15 — Define a custom liquid handler

Guided vertical, same rules. **The most valuable chapter in the book for professional users.**

Worked example: a **single-channel gantry**. `LiquidHandlerBackend` has **13 abstract methods**:

| Tier | Methods | In the build |
|---|---|---|
| Core | `num_channels`, `can_pick_up_tip`, `pick_up_tips`, `drop_tips`, `aspirate`, `dispense` | implement (6) |
| 96-head | `pick_up_tips96`, `drop_tips96`, `aspirate96`, `dispense96` | `raise NotImplementedError()` (4) |
| Gripper | `pick_up_resource`, `move_picked_up_resource`, `drop_resource` | `raise NotImplementedError()` (3) |
| Optional (already default to raising) | `move_channel_x/y/z`, `prepare_for_manual_channel_operation`, `request_tip_presence`, `get_channel_spacings` | leave alone |

**Build order:** read `backends/chatterbox.py` (242 lines, complete and minimal) → implement against
a simulated device → wire real transport via `pylabrobot.io` (`serial`/`usb`/`hid`/`ftdi`, and why
those rather than raw pyserial) → `setup`/`stop` discipline → a `Deck` subclass → coordinate frames
and homing **as its own section, flagged as not free**.

**The two contracts, which are why the chapter exists:**

1. **The ABC is the capability declaration.** All 13 are `@abstractmethod`, so Python refuses to
   instantiate until you have written *something* for each. You cannot accidentally ship a backend
   silently lacking a 96-head — you had to type the `raise` yourself.
2. **The op payload is the interface.** Backends receive frozen dataclasses:
   `SingleChannelAspiration(resource, offset, tip, volume, flow_rate, liquid_height,
   blow_out_air_volume, mix)`. **Frontend owns tracking, validation, channel assignment and geometry
   resolution; backend owns motion.** By the time your code runs, the well is resolved, the offset
   applied, the tip known, and the volume tracker has already objected if it was going to.

**Third section — designing your own error contract:** reuse `resources/errors.py` types where they
fit so your backend is interoperable; raise `ChannelizedError` for partial multichannel failures;
model a vendor family on `STARModuleError` (one abstract base, typed leaves).

**Decorator payoff (ties to ch. 13):** 13 methods each wrapping transport I/O is the ideal decorator
target. Inline that is 13 copies of retry, logging, and setup-checking; composed it is
`@need_setup_finished` (reuse PLR's own), `@retry` on transport, one `@log_command` wrapper. Robust
and flexible without verbosity, demonstrated on code the reader just wrote.

**One-paragraph pointer, not a chapter:** writing a non-liquid-handler machine (sealer,
thermocycler, plate reader) uses the same `Machine` + abstract backend pattern at lower stakes.
`sealing/` is 26 lines of frontend over a 6-method backend if you want to read one.

---

# Appendix A — Verified 0.2.2 names

Checked against the 0.2.2 sdist. Use these rather than memory.

**Imports** — all of the following are re-exported from `pylabrobot.resources`:

```python
from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
from pylabrobot.resources import (
    STARLetDeck, PLT_CAR_L5AC_A00, Coordinate, ResourceStack,
    cor_96_wellplate_360uL_Fb, cor_96_wellplate_360uL_Fb_lid, cor_96_wellplate_2mL_Vb,
    alpaqua_96_plateadapter_magnum_flx,
    opentrons_96_filtertiprack_20ul, opentrons_96_filtertiprack_200ul,
    opentrons_24_aluminumblock_nest_1_5ml_snapcap,
    opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap,
    nest_1_troughplate_195000uL_Vb, nest_12_troughplate_15000uL_Vb,
)
```

**Renamed since 0.1.6** — the old names in `PLAN.md` §5.3 do **not** resolve:

| Old | Current |
|---|---|
| `opentrons_24_aluminumblock_nest_1point5ml_snapcap` | `opentrons_24_aluminumblock_nest_1_5ml_snapcap` |
| `opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap_acrylic` | `opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap` |
| `nest_1_reservoir_195ml` | `nest_1_troughplate_195000uL_Vb` |
| `nest_96_wellplate_100ul_pcr_full_skirt` | **no replacement — ch. 14 builds one** |
| `pylabrobot.incubators` | `pylabrobot.storage` |
| `Lid` in `resources/plate.py` | `resources/lid.py` (+ `Liddable` mixin) |
| `set_well_liquids` | `set_well_volumes` (old one deprecated) |
| `SaverBackend` | gone — use `pylabrobot.io.capture` |

**Signatures worth having exact:**

```python
lh.aspirate(resources, vols, use_channels=None, flow_rates=None, offsets=None,
            liquid_height=None, blow_out_air_volume=None, spread="wide",
            mix=None, **backend_kwargs)

lh.move_plate(plate, to, intermediate_locations=None, pickup_offset=Coordinate.zero(),
              destination_offset=Coordinate.zero(), drop_direction=GripDirection.FRONT,
              pickup_direction=GripDirection.FRONT, pickup_distance_from_top=13.2-3.33,
              **backend_kwargs)

deck.assign_child_resource(resource, location=None, reassign=False, rails=None,
                           replace=False, ignore_collision=False)   # HamiltonDeck
```

**Confirmed routing:** `transfer()` → `aspirate`/`dispense`; `stamp()` → `aspirate96`/`dispense96`.
`lh.head[c]` is a `TipTracker`; `.get_tip()` works.

# Appendix B — The portable errors

Raise on any backend. For ch. 10's catalog table.

| Error | Module |
|---|---|
| `ResourceNotFoundError`, `TooLittleLiquidError`, `TooLittleVolumeError`, `HasTipError`, `NoTipError`, `CrossContaminationError` (dead), `ResourceDefinitionIncompleteError`, `NoLocationError` | `resources/errors.py` |
| `NoChannelError`, `ChannelsDoNotFitError`, `ChannelizedError` | `liquid_handling/errors.py` |
| `BlowOutVolumeError` | `liquid_handling/liquid_handler.py` |
| `NoFreeSiteError` | `storage/incubator.py` |
| `NoPlateError` | `plate_reading/standard.py` |
| `LoaderNoPlateError`, `CentrifugeDoorError`, `NotAtBucketError`, `BucketNoPlateError`, `BucketHasPlateError` | `centrifuge/standard.py` |
| `NotCalibratedError` | `pumps/errors.py` |
| `ValidationError` | `io/errors.py` |

# Appendix C — Working with the PLR source

**You will need the source.** Every rule in this spec says "verify the name against 0.2.2", and the
installed package is the only authority. Read this appendix before writing any chapter.

## Getting 0.2.2

```bash
# Option 1 — the exact release, no git needed (preferred)
pip download pylabrobot==0.2.2 --no-deps --no-binary :all: -d /tmp/plr
cd /tmp/plr && tar xzf pylabrobot-0.2.2.tar.gz
# source is then at pylabrobot-0.2.2/pylabrobot/

# Option 2 — installed into the environment you are rendering with
pip install "pylabrobot==0.2.2"
python -c "import pylabrobot, pathlib; print(pathlib.Path(pylabrobot.__file__).parent)"
```

### ⚠ Three ways to end up reading the wrong code

1. **There is no `v0.2.2` git tag.** Tags stop at `v0.2.1`. Cloning the repo does *not* get you the
   release.
2. **`main` is not 0.2.2.** Commit `14a7766` ("v1b1 changes", 759 files, +75k/−53k) landed after the
   0.2.2 release and **moved the entire liquid handling stack into `pylabrobot/legacy/`**, then
   re-cut the package by vendor. On `main`, `LiquidHandler` is at
   `pylabrobot.legacy.liquid_handling` and `pylabrobot/machines/` is an empty `__init__.py`. If you
   find yourself reading a path with `legacy/` in it, you are in the wrong tree.
3. **docs.pylabrobot.org may reflect a newer version than 0.2.2.** Version-pinned URLs exist
   (`/0.2.1/...`). Treat the live docs as a hint and the source as the answer.

Full analysis in `../PLAN-0.2.2-AUDIT.md`.

## Package map (0.2.2)

```
pylabrobot/
  liquid_handling/
    liquid_handler.py       LiquidHandler — the frontend, ~2700 lines
    standard.py             the op dataclasses backends receive (Pickup, SingleChannelAspiration, Mix, …)
    errors.py               NoChannelError, ChannelsDoNotFitError, ChannelizedError
    strictness.py           how unknown **backend_kwargs are handled
    backends/
      backend.py            LiquidHandlerBackend — the 13-method ABC
      chatterbox.py         LiquidHandlerChatterboxBackend — 242 lines, minimal complete backend
      hamilton/STAR_backend.py   49 error classes + firmware string parsing
    liquid_classes/         vendor liquid classes (out of scope for this book)
  resources/
    resource.py             Resource — tree, anchors, callbacks, serialization
    itemized_resource.py    grid indexing, traverse, the full-grid contract
    plate.py, well.py, lid.py, container.py, container_rack.py, tube_rack.py, trough.py
    carrier.py              PlateCarrier, TipCarrier, PlateHolder (pedestal_size_z lives here)
    plate_adapter.py        magnets, thermocycler blocks, on-deck modules
    resource_holder.py, resource_stack.py, coordinate.py, rotation.py
    utils.py                create_ordered_items_2d, query, label helpers, chunking
    height_volume_functions.py   21 volume↔height functions
    errors.py               the portable resource errors
    volume_tracker.py, tip_tracker.py
    <vendor>/               26 vendor packages: corning, nest, opentrons, alpaqua, hamilton, diy, …
  machines/machine.py       Machine, MachineBackend, need_setup_finished
  io/                       serial, usb, hid, ftdi + capture.py / validation.py (record-replay)
  config/                   load_config, get_config_file, Config
  storage/                  Incubator (was pylabrobot.incubators in 0.1.6), cytomat, liconic, inheco
  thermocycling/  arms/  sealing/  plate_reading/  centrifuge/  peeling/  plate_washing/  …
```

**Tests are colocated and are the best usage examples in the repo.** `*_tests.py` sits next to the
module it tests (`plate_tests.py`, `volume_tracker_tests.py`, `chatterbox_tests.py`). When a
docstring is thin, read the test.

## How to verify things yourself

```bash
# Does this name exist, and where?
grep -rn "^def alpaqua_96_plateadapter_magnum_flx" pylabrobot/resources/

# Is a name a deprecated shim? (~10 vendor packages carry them)
grep -rn "remove v1b1" pylabrobot/resources/<vendor>/plates.py

# Current (non-deprecated) definitions in a vendor package
grep -n "^def " pylabrobot/resources/corning/plates.py | grep -v "remove v1b1"

# Exact signature of a method
grep -n "async def aspirate" pylabrobot/liquid_handling/liquid_handler.py   # then sed -n 'START,+15p'

# What errors does a subsystem define?
grep -rn "^class .*\(Error\|Exception\).*:" pylabrobot/<pkg>/

# What is actually exported from a package
cat pylabrobot/resources/__init__.py

# Is a deprecated method still callable?
grep -n "DeprecationWarning" pylabrobot/resources/volume_tracker.py
```

## File:line anchors for claims made in this spec

Line numbers are from the **0.2.2 sdist** and will drift on other builds; the symbol names will not.

| Claim | Location |
|---|---|
| `LiquidHandlerBackend`, 13 `@abstractmethod` | `liquid_handling/backends/backend.py:27` |
| Minimal complete backend, 242 lines | `liquid_handling/backends/chatterbox.py` |
| `stamp()` dispenses into `source` — **bug** | `liquid_handling/liquid_handler.py:2001` |
| `aspirate` / `dispense` signatures | `liquid_handler.py:878` / `:1070` |
| `transfer` routes through aspirate/dispense | `liquid_handler.py:1273` |
| `move_plate` / `move_lid` | `liquid_handler.py:2439` / `:2379` |
| `_log_command` called 25× | `liquid_handler.py` (grep `_log_command(`) |
| `ChannelizedError(errors: Dict[int, Exception])` | `liquid_handling/errors.py:18` |
| `Mix` dataclass | `liquid_handling/standard.py:76` |
| `need_setup_finished` — async decorator w/ `functools.wraps` | `machines/machine.py:20` |
| Full-grid contract, `ValueError("Not a full grid")` | `resources/itemized_resource.py:451` |
| `traverse` / `__getitem__` | `resources/itemized_resource.py:239` / `:111` |
| `Plate.get_quadrant` | `resources/plate.py:181` |
| `Liddable` mixin / `Lid` | `resources/lid.py:62` / `:15` |
| `create_ordered_items_2d` / `query` / `sort_by_xy_and_chunk_by_x` | `resources/utils.py:213` / `:263` / `:311` |
| `VolumeTracker` scalar; `set_liquids` deprecated shim | `resources/volume_tracker.py:36` / `:74` |
| Magnum FLX definition + the `plate_z_offset` comment | `resources/alpaqua/magnetic_racks.py:8` |
| `Incubator.take_in_plate` — unassign/assign | `storage/incubator.py:115` |
| `start_capture` / `validate` | `io/capture.py:124` / `io/validation.py:13` |
| `find_subclass` (only sees imported classes) | `utils/object_parsing.py:6` |

# Appendix D — Known upstream bugs

| Bug | Effect | Chapter |
|---|---|---|
| `stamp()` dispenses into `source`, not `target` | plate-to-plate stamping is wrong | ch. 6 — document, do not build on |
| `CrossContaminationError` exists but is never raised | dead API looks alive | ch. 10 — warn |
| `Alpaqua_96_magnum_flx` shim marked `TODO: Remove >2026-02` | overdue for deletion | ch. 9 — done |
