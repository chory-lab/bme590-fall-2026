# BME 590 Redesign Plan

Working plan for the fork at `github.com/stefangolas/bme590-fall-2025`
(upstream: `github.com/chory-lab/bme590-fall-2025`).

---

## 1. Problem statement

Findings from a full read of the six workshop notebooks and the vendored PyLabRobot 0.1.6.

### 1.1 Measured shape of the current material

| Workshop | cells | KB | teaching cells | exercise cells | things to implement | deliverable files |
|---|---:|---:|---:|---:|---:|---:|
| W0 Introduction | 17 | 16 | 17 | 0 | 0 | 2 |
| W1 Deck Setup | 44 | 21 | 34 | 10 | 4 | 8 |
| W2 Liquid Handling | 172 | 59 | 164 | 8 | 12 | 6 |
| W3 Moving Labware | 112 | 47 | 71 | 41 | 22 | 5 |
| W4 Modular Cloning | 45 | 22 | 12 | 33 | 6 | 6 |
| W5 Peripherals | 57 | 40 | 45 | 12 | 25 | 7 |

Reading burden: W2 >> W3 > W5 > W1 > W4.
Doing burden: W5 ≈ W3 > W2 > W4 > W1.

There is no light week after W2. W4 looks light only because it teaches almost nothing before it asks.

### 1.2 Structural problems

1. **W2 is a reference document wearing a workbook's clothes.** 164 of 172 cells precede the first
   exercise. Sandboxes literally read `EXPERIMENT HERE - CHANGE THESE SETTINGS`. The nine-error
   section is a lookup table.
2. **Reference material is forked per student.** The README instructs students to copy workshops into
   `assignments/` and work there. The place you would look up `traverse()` is therefore a file the
   student has already modified with their own homework.
3. **W4 is structurally hard, not long.** Only 12 teaching cells and 6 `YOUR CODE HERE` blanks; the
   only strict dependency chain in the course (Ex1 → Ex2 → Ex3 → Ex4); Ex3 is the only unscaffolded
   exercise in the course while still being graded against three inferred helpers.
4. **W3 is the longest to do.** 41 exercise cells, 22 classes/methods, 3 separate GIF recordings, two
   copy-paste submission templates.
5. **Exercises are motivated by nothing.** Dyes, `plate_1`/`plate_X`, fragments named `X076`/`Y150`.
   W3 has the best motivation section in the course and never exercises it.
6. **Deliverables are not machine-gradeable.** Screenshots and GIFs prove a protocol ran, not that it
   was correct.

---

## 2. Repository structure

```
bme590-fall-2025/
  README.md
  PLAN.md                       <- this file
  environment.yaml
  bme590/                       <- NEW: shared course package
    __init__.py
    decks.py                    visualize_deck(), shared deck builders
    reagents.py                 registry + composition ledger (optional, see §6)
    handler.py                  TrackedLiquidHandler
    checks/                     student-visible verification functions
    policy.py                   dead volume, preflight, contamination policy
  reference/                    <- NEW: read-only, never copied to assignments/
    python/
      01_async_and_await.ipynb
      02_iteration_and_comprehensions.ipynb
      03_generators.ipynb
      04_context_managers_and_decorators.ipynb
      05_errors_logging_and_paths.ipynb
    plr/
      01_resources_coordinates_and_the_tree.ipynb
      02_decks_holders_carriers_stacks.ipynb
      03_containers_and_liquid_state.ipynb
      04_traversal_and_indexing.ipynb
      05_tips_channels_and_inventory.ipynb
      06_aspirate_dispense_transfer_stamp.ipynb
      07_moving_resources.ipynb
      08_trackers_and_errors.ipynb
      09_geometry_and_custom_labware.ipynb
      10_saving_and_loading_layouts.ipynb
    CHEATSHEET.md
  workshops/                    shrunk; exercises + short recap + links into reference/
  colab_workshops/              candidate for deletion (see §10.4)
  workshop_data/
  figs/
  pylabrobot/                   vendored (see §9)
```

`reference/` is never copied into `assignments/`. It is pulled fresh with `git pull`.

---

## 3. Reference guidebook

Principle: **reference = how PLR works. Workshop = what you are doing and why.**
Keeps the biological reframing out of the mechanics, so nothing is duplicated.

Format: topic-scoped runnable notebooks, 20–40 cells each, contents cell at top.
One motivating example per topic, exactly one, in a single Jupyter cell.
Plus `CHEATSHEET.md` as a flat lookup table (function → signature → one line), because notebooks are
bad at search and that is what students will actually open mid-exercise.

### 3.1 Python topics

| Topic | Justification |
|---|---|
| `async`/`await` | Used from W0 cell 7, never explained. Five workshops of cargo-culted `await`. |
| Generators | Consumed in W2, authored in W4, never introduced. |
| Comprehensions, `zip`, `enumerate` | All appear in given code (`[chr(i) for i in range(65,73)]`, `zip(names, constructors)`), none explained. |
| Context managers, `@contextmanager` | PLR ships `no_cross_contamination_tracking()`. Also the fix for the bare `except:` blocks. |
| Decorators, `functools.wraps` | `@retry` for flaky hardware ops, `@timed`, `@log_step`. PLR itself uses `@need_setup_finished`. |
| `pathlib` | Fixes the fragile `os.path.dirname(os.getcwd())` in W4/W5. |
| `logging` | See §3.3. |
| `try/except/else/finally`, custom exceptions | The course catches exceptions constantly, incl. two bare `except:` it teaches by example. |
| `assert` + pytest basics | On-ramp to the student-visible checkers (§7). |
| `dataclass` | Reagent and Sample definitions; gentler intro to classes than W3. |
| Type hints | All over the given code, never mentioned. |
| `enum` | `Liquid` is an enum. |
| `typing.Literal` | `traverse(direction=...)` allowed values. |
| `__getitem__` / slices | Explains `plate["A1:H1"]` and `tip_carrier[0] = HTF(...)`. |
| `abc` | Backends are ABCs; the door to writing your own. |
| `collections`: `defaultdict`, `Counter`, `deque` | Grouping wells, counting tips/outcomes, queueing plates. |
| `itertools`: `product`, `islice`, `chain`, `groupby`, `batched` | `product` *is* a combinatorial library design; `islice` replaces `[await anext(g) for _ in range(N)]`. |
| `statistics` | Triplicate analysis without reaching for numpy. |
| `datetime` | Run IDs, timestamped output dirs, TAT arithmetic. |
| `random.seed` | Reproducibility; prerequisite for checkers. |
| `json` / `csv` | `csv` as the contrast case — a two-column file does not need pandas. |

Scope discipline: **not** every stdlib utility. One example each, and only where it repairs an
existing wart or unlocks an exercise.

### 3.2 PLR topics the course currently omits

Verified present in vendored 0.1.6.

**Tier 1 — core API never mentioned**

| API | Note |
|---|---|
| `lh.move_plate()`, `lh.move_lid()`, `lh.move_resource()` | **W3 has students hand-build a gripper that PLR already ships.** Must be closed out in the reference. |
| `lh.pick_up_resource()`, `move_picked_up_resource()`, `drop_resource()` | Lower-level gripper API. |
| `lh.transfer()` | Students hand-roll aspirate+dispense every time. |
| `lh.stamp()` | 96-head plate-to-plate. |
| `lh.use_channels(channels)` | Sets default channels; course passes `use_channels=[...]` manually dozens of times. |
| `probe_tip_inventory()`, `consolidate_tip_inventory()`, `probe_tip_presence_via_pickup()` | Real consumable management. |
| `lh.serialize()` / `LiquidHandler.load(path)` | Save/reload deck layouts as JSON — the real answer to "functionalize your deck setup". |
| `prepare_for_manual_channel_operation`, `move_channel_x/y/z` | Manual jogging / calibration. |

**Tier 2 — resource abstractions**

- `ResourceStack` (`get_top_item()`) — plate hotels, lid stacks
- `PlateAdapter.compute_plate_location()` — W1 Ex3 already asks students to place a "PCR Plate Adapter"
- `ResourceHolder` / `PlateHolder` (`pedestal_size_z`) — the mechanism behind carrier slots and incubator sites
- `Rotation` — landscape/portrait
- `Coordinate`, relative vs absolute, `get_absolute_location()`, `center()` — W1 prints `.location` without saying it is parent-relative
- `Tube`, `TubeRack`, `Trough`, `PetriDish`, `Trash`
- `barcode.py` — sample tracking, ties to W4 work orders and the capstone
- **`pylabrobot.incubators.Incubator`** + `IncubatorChatterboxBackend` — see §5.4

**Tier 3 — geometry and custom labware**

- `utils.create_ordered_items_2d`, `create_equally_spaced_2d/x/y` — how every plate definition is built
- `height_volume_functions` — ~12 functions, volume ↔ liquid height for flat/V/U, round/square
- `utils.query()`, `resources.errors`, `liquid_handling.strictness`
- `no_volume_tracking()` / `no_tip_tracking()` — course only shows the cross-contamination one

### 3.3 Logging (expand)

PLR already uses stdlib `logging`: 26 files, logger namespace `pylabrobot`, sub-loggers
(`pylabrobot.resources`, `pylabrobot.plate_reading.biotek`).

`LiquidHandler._log_command` is called **25 times — essentially every public operation**:

```python
def _log_command(self, name: str, **kwargs) -> None:
    params = ", ".join(f"{k}={self._format_param(v)}" for k, v in kwargs.items())
    logger.debug("%s(%s)", name, params)
```

`_format_param` renders resources as names. Consequences:

- Three lines of `basicConfig` + a `FileHandler` yields a complete timestamped machine-readable trace
  of every operation a student's protocol performed. **This is most of the audit log, for free.**
- A run log is a better deliverable than a GIF: greppable, diffable, gradeable.
- Levels map onto the domain: DEBUG = per step, INFO = phases, WARNING = skipped wells
  (exactly W5's `pipette_vols_careful`), ERROR = aborted run.
- Two handlers: console at INFO, file at DEBUG.
- `%(relativeCreated)d` in the formatter gives per-step elapsed time — protocol profiling for free.
- `logger.exception()` captures the traceback, fixing `print(f"Error! Got excpetion: {e}")`.
- Namespace filtering to quiet `pylabrobot.resources` while keeping student code at DEBUG.

---

## 4. Workshop restructure

W2's 164 exposition cells move to `reference/`. W2 drops to roughly 25 cells: short recap, three
exercises, explicit links to the reference sections each exercise draws on. Same points, same
difficulty, reading moved out of the graded artifact and into assignable pre-reading.

Keep 2–3 deliberately triggered errors in the workshop so students *experience* them; the reference
catalogues all nine.

Risk: students skip the reference. Mitigations: each exercise names its dependency sections; the
first exercise is a near-direct application of one section.

Other length relief:
- W3 → two GIFs, not three (`exercise_2.gif` and `exercise_2_part_e.gif` cover the same class).
- W3 → drop the copy-paste submission templates if checkers emit `submission.json` (§7).
- W5 → renumber its two exercises as four. Same work; students plan their week correctly.

---

## 5. Biological reframing

### 5.1 Hard constraint

**Framing only.** No task may become harder or more open-ended. Specifically:

- Do **not** make students derive labware from a protocol. Specifications stay exactly as specific as
  they are now.
- Do **not** add master-mix overage calculations, dead-volume arithmetic, fmol/equimolar addition,
  standard-curve fitting, plotting, or preflight checks to existing exercises.
- Items may be *swapped* for coherent ones; the number and specificity of items stays the same.

If W1's "practice navigating open-source code" objective is dropped, drop it deliberately or move it
to an ungraded guided-tour cell — do not let it vanish silently.

### 5.2 Through-line

One cloning campaign, each workshop a real step:

```
W0  demo deck = the PCR deck built in W1
W1  lay out a deck for PCR amplification
W2  set up the PCRs: master mix, primers, template, standard curve
W3  move the plate: seal -> thermocycler -> magnet (SPRI cleanup)
W4  Golden Gate assembly from a combinatorial work order
W5  quantify, normalize, transform, read
```

### 5.3 Per workshop

**W0** — demo deck becomes the W1 PCR deck. Identical code.

**W1** — item swap, verified against the vendored library:

| Currently | PCR version | Rationale |
|---|---|---|
| Eppendorf 24-tube rack | `opentrons_24_aluminumblock_nest_1point5ml_snapcap` | Aluminium block = chilled; master mix and enzyme live there |
| NEST 15 mL conical rack | `opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap_acrylic` | Primer stocks and templates |
| 12×15 mL reservoir | `nest_1_reservoir_195ml` | One reagent, one well |
| 3× 96-well 360 µL plates | `nest_96_wellplate_100ul_pcr_full_skirt` | Full skirt = thermocycler/gripper compatible |
| — | `opentrons_96_filtertiprack_20ul` / `_200ul` | Filter tips = barrier against aerosol carryover |

Ex4 write-up question: replace "most sterile → least sterile" with **pre-PCR / post-PCR zoning**.
Same question format, real constraint.

Ex2 (staircase) and Ex3 (max/min well counts) have no honest biological analogue. Keep and label as
coordinate/library-exploration drills, or cut.

**W2** — rename reagents (master mix, primers, template) and the plate (PCR plate). Traversal demos
become a plate map with zero code change:

| Currently | Reads as |
|---|---|
| Fill all 96 | Master mix distribution |
| Every other column | Alternating primer panel / NTC placement |
| Specific rows | Template per row |
| `traverse()` batches | 8-channel column-wise addition |

Cross-contamination acquires a true rule: same reagent into empty wells may reuse a tip; anything
that has touched template may not.

Ex1: six transfers → six reactions. The "1800 µL when only 1775 remains" puzzle reframes as running
short of master mix and topping up from a second aliquot.
Ex2: rainbow → optional swap to a checkerboard assay (drug A across columns, drug B down rows);
same operations, no dependence on colour the visualizer cannot render.
Ex3: serial dilution → 10-fold qPCR standard curve.

**W3** — class evolution untouched. Plate moves because it is going to a sealer, a thermocycler, and
a magnet; SPRI bead cleanup is the honest answer to "why move a plate". Ex1B's water/ethanol/bleach
becomes ethanol wash / elution buffer / waste. Lids become plate seals, with the caveat stated —
a seal is not a lid, but the state-tracking lesson is identical, and saying so *is* the lesson about
telling PLR what happened off-deck.

**W4** — pure renaming, highest return of the set. `X076`/`Y150`/`Z216` → promoter / RBS / CDS.
Work order → combinatorial library design (3 promoters × 4 RBS × 2 CDS = 24 constructs).
Missing parts → parts that failed sequencing QC. Ex4 output → a QC report.

**W5** — name the plate reader work post-assembly plasmid quantification, connecting it to W4.
Note: the synthetic image (discrete red circles on a plain background) is a better model of
**colonies on a transformation plate** than of confluent adherent cells. Reframing to colony counting
is code-identical, but Ex2's passaging protocol (PBS/trypsin/media) is mammalian and would not
follow. That is a two-part change, not a reskin. Deferred — see §11.

### 5.4 Incubator as the motivating object for resource movement

`pylabrobot.incubators.Incubator` is exactly "a storage device with an integrated arm":

```python
class Incubator(Machine, Resource):
    racks: List[PlateCarrier]
    loading_tray: PlateHolder
    async def fetch_plate_to_loading_tray(plate_name) -> Plate
    async def take_in_plate(site: PlateHolder | "random" | "smallest")
    def get_num_free_sites(); get_site_by_plate_name(name)
    def find_smallest_site_for_plate(plate)
    async def set_temperature / open_door / close_door / start_shaking
```

`IncubatorChatterboxBackend` exists, so it simulates like the liquid handler.

The payoff: `take_in_plate` is implemented as

```python
plate.unassign()
site.assign_child_resource(plate)
```

which is the same two lines as the students' hand-rolled `Gripper.move_labware`. Replace W3's
hardware survey (which links out to untouchable equipment) with a live ~15-cell demo, then frame the
exercises truthfully: PLR has a Cytomat driver, your lab's storage device does not, so you are
writing the class that moves plates between it and the deck.

Reframes cleanly: Ex1 (staging to/from storage), Ex2.B (deck ↔ storage rack).
Does not reframe: Ex2.C (rail arithmetic), Ex2.E (staircase).

---

## 6. Reagent state accounting

### 6.1 Why it is needed

PLR 0.1.6 models a container as a **LIFO stack of unmixed layers**. `remove_liquid` docstring:
"Remove liquid from the container. Top to bottom." Demonstrated:

```
contents      : [('DNA', 100), ('Water', 100)]
aspirate 50 ->: [('Water', 50.0)]
well-mixed would give: [('DNA', 25), ('Water', 25)]
```

Consequence: no serial dilution in the course currently produces meaningful composition, which is why
W2 Ex3 has students type concentrations into a comment.

`Liquid` is a bare enum (18 members, only `name`/`value`/`from_str`) — no density, no MW, no hook.

Upstream deleted the whole model rather than fixing it (§9).

### 6.2 Design

**Canonical stored quantity is mass in grams, not moles.** Moles need a molecular weight; W4's DNA
fragments and W5's ng/µL have none. Mass is always defined and always conserved; moles are a
one-line derivation where MW is known.

**Ledger stores amount only. Volume is always read from PLR. Concentration is always derived.**
This is what keeps it small and what makes it survive upstream's volume-model changes.

```
bme590/reagents.py
  Solute(name, mw: float | None = None)
  Reagent(name, composition: dict[str, float],   # g/L
          density: float = 1.0)
  Reagent.from_molarity(...) / Reagent.from_mass_conc(..., unit="ng/uL")
  Registry

  Ledger:
    mass: dict[Container | Tip, dict[str, float]]   # grams; both are hashable
    load(container, reagent_name)
    load_mass(container, solute, grams)
    move(src, dst, volume_ul, v0_ul)                # THE only mutator
    volume / mass / moles / molarity / mass_conc / composition / total / inventory
    snapshot() -> dict   (keyed by resource NAME)
    restore(data, deck)  (re-resolves via deck.get_resource)
    events: list[...]    (optional; largely superseded by PLR logging, §3.3)
```

`move()` requires `v0` explicitly. **Sampling volumes after the operation is the failure mode** — it
was hit twice in two independent prototypes and fails silently: moles vanish into a tip while deck
totals still look plausible.

Internal unit is g/L throughout; `ng/µL == µg/mL == mg/L`, so every conversion is a power of ten.

`molarity()` raises on a mass-only solute rather than inventing a number.

### 6.3 Integration

Subclass, not monkeypatch, not facade:

```python
class TrackedLiquidHandler(LiquidHandler):
    def __init__(self, backend, deck, registry=None, **kwargs)
    def _sample(self, resources, vols, use_channels, source="resource")
        -> list[tuple[resource, vol, tip, v0]]      # ONLY place pre-volumes are read
    async def aspirate / dispense / aspirate96 / dispense96
```

Every override: sample → `await super()` → apply.

- `**kwargs` passthrough is the signature-drift defence (upstream is mid-migration to a
  Device/Driver/CapabilityBackend architecture).
- Apply **after** `super()` so a raised `TooLittleLiquidError` leaves the ledger consistent — W2
  deliberately triggers nine such errors.
- Overriding beats a facade because PLR's internal `self.aspirate` callers are intercepted too.
- Subclassing also mirrors W3's own lesson (`FixedGripper` overriding `get_labware_by_name`).

Rejected: tracker `register_callback`. It fires per-container on state change with **no
source→destination pairing**, so transfers cannot be reconstructed.

### 6.4 Deck-recreation hazard

The ledger is keyed by resource objects. Every workshop rebuilds the deck repeatedly
(`deck = await make_liquid_handling_deck()` — five or six times in W2 alone), creating fresh `Well`
objects. A separately constructed ledger would be silently orphaned.

Fix structurally: construct the ledger inside `TrackedLiquidHandler.__init__`, and have the deck
helper return the handler. Students never construct a ledger, so they cannot mismatch one.

```python
async def visualize_deck(deck, backend, registry=None):
    lh = TrackedLiquidHandler(backend=backend, deck=deck, registry=registry)
    vis = Visualizer(resource=lh, ...)
    await lh.setup(); await vis.setup()
    return lh          # and no bare except swallowing the error
```

One helper, already called from every notebook, now carries the ledger, the visualizer host/port
config, and the exception fix.

### 6.5 Verified prototype result

Sidecar ledger driving a real 1:8 serial dilution through `LiquidHandler`:

```
well     volume    [red_dye]        mass   total mol on deck
B1         480uL    0.125000M     9.000mg   2.000000e-03
C1         480uL    0.015625M     1.125mg   2.000000e-03
A2         480uL    0.001953M     0.141mg   2.000000e-03
```

Exact, with mass conserved throughout. ~50 lines, no PLR internals touched.

### 6.6 Unverified before writing code

Against current upstream `main`:

1. `LiquidHandler.aspirate` / `dispense` signatures.
2. `lh.head[c].get_tip()` survival through the v1b1 migration.
3. Whether higher-level helpers (`transfer`, `stamp`) route through `aspirate`/`dispense` or call the
   backend directly. **This is the one failure mode that would silently under-track.**
4. `aspirate96` / `dispense96` code paths.

Half a day reading `liquid_handler.py` on `main` settles all four.

### 6.7 Effort

| Piece | Size |
|---|---|
| Registry + ledger + 2 interceptors + queries | ~50–80 lines |
| Invariant tests | ~40 lines |
| Policy layer (dead volume, preflight, contamination) | ~60 lines |
| Snapshot/restore as plain JSON | ~20 lines |

Rolling our own JSON persistence sidesteps PLR's serializer entirely, which means the pyserial
problem (§9.3) never arises.

---

## 7. Student-visible verification functions

### 7.1 Rationale

The deck state *is* the output, so there is a real object to assert against. This is why the course
currently substitutes screenshots and GIFs; a GIF proves a protocol ran, not that it was correct.

Checkers are shipped in the repo and runnable by students — not hidden — so they can self-check.

### 7.2 Design rules

- **Check state, never structure.** Volumes, occupancy, composition, tip counts, slot positions.
  Never function decomposition or comment quality; those stay human-graded (the course already grades
  them explicitly).
- **Assert invariants, not exact solutions.** W1 says layout is not graded "as long as all the
  requisite pieces of labware are present" — so check presence and category, not slots. Where the
  spec really is exact (W3 Ex2.E), check exactly.
- **Feedback is the product.** `assert failed` is worthless; "Well D12 contains 75 µL, expected
  100 µL" is the entire value. Budget most effort here.
- **Necessary but not sufficient.** Green means the protocol did the right thing; the grade still
  includes the human read.

### 7.3 Anti-gaming

A visible checker can be satisfied by `set_volume()`-ing the final state instead of pipetting.
Defence: also assert that work happened — tip consumption, aspirate/dispense counts, source
depletion. Faking all of those consistently is more work than doing the protocol.

### 7.4 Coverage

| | Checkable | Needs |
|---|---|---|
| W1 Ex1–3 | Labware present by category; staircase geometry; alternating grid | plain PLR |
| W1 Ex4 | ✗ judgment + written justification; correctly stays human | — |
| W2 Ex1 | Every reaction totals 25 µL; master mix 1× final; correct primer/template per well | ledger |
| W2 Ex2 | Reaction composition per column; mixing occurred | ledger |
| W2 Ex3 | 10-fold spacing across the series; triplicates agree | ledger |
| W3 Ex1 | Final slot positions after row-wise moves | plain PLR |
| W3 Ex2.B/D | Plate locations, lid presence | plain PLR |
| **W3 Ex2.E** | Carrier order, gaps, 0-1-2-3-4-5 counts, lid placement | plain PLR |
| W4 Ex1 | Fragment volumes match the CSV | plain PLR |
| **W4 Ex2** | `convert_well_id`, `get_well`, generator output — pure unit tests | none |
| W4 Ex3/4 | Final cloning-plate state; output CSV | plain PLR |
| W5 Ex1A, 2A | Methods with defined I/O | seeded RNG |
| W5 Ex1B/C, 2B | Final volumes; passage decisions | seeded RNG |

**W3 Ex2.E is the highest-return checker** — the most rule-laden exercise in the course, fully
mechanical to verify, currently graded by squinting at a GIF.
**W4 Ex2 needs no infrastructure at all** — three functions with defined I/O, checkable today.

Most rows need nothing but PLR. Ship W1/W3/W4 checkers without writing a line of ledger code.

### 7.5 PCR-specific acceptance criteria

Under the PCR reframing the checkers stop asking "did you complete the exercise" and start asking
"would this run have worked":

1. **No-template controls contain no template.** The classic PCR failure; invalidates a plate.
2. **No tip that touched template was reused.** Checkable from the operation log; enforces the
   cross-contamination rule the course currently demonstrates once.
3. **Every reaction sums to 25 µL.** Catches the most common student error (forgetting the water).

### 7.6 Prerequisites

- **Seed the RNG.** W5 uses `np.random` throughout; nothing there is reproducible. One line, and it
  makes grading reproducible too.
- Composition checks need the ledger. This is the argument that makes the ledger worth building.

### 7.7 Interface

```python
from bme590.checks import check
check.w2_ex1(lh)      # prints a ✓/✗ checklist, returns a Report
```

Optionally the report also writes `submission.json` (final state + check results) as a
machine-gradeable artifact alongside the GIF. If adopted, W3's copy-paste submission templates can go.

---

## 8. Capstone: COVID-19 sample accessioning

### 8.1 Scope

**Only** the transfer of individual patient tubes into 96-well plates. No qPCR station, no pooling,
no controls, no deconvolution.

Framing for the intro (verbatim intent): sample accessioning was not the bottleneck in 2020 because
labs batched properly. This exercise is what happens if they had not.

### 8.2 Model

One station. The tension is entirely contained in a fixed per-run cost plus a marginal per-sample
cost:

```
time(n) = S + n·m       S ≈ 10 min setup (load tube racks, fresh plate, deck prep)
                        m ≈ 10 s/sample  (the transfer)
```

| batch size | run time | throughput |
|---|---|---|
| 1 | 10.2 min | 6 /hr |
| 24 | 14 min | 103 /hr |
| 96 | 26 min | 221 /hr |

A 36× swing from one policy decision.

### 8.3 Algorithmic core

Stability requires `n / (S + n·m) ≥ λ`, hence:

```
n_min = λS / (1 − λm)          valid while λ < 1/m
```

- λ = 100/hr → n ≥ 24
- λ = 200/hr → n ≥ 75
- λ = 221/hr → full plates, no headroom

Derivable in two lines, then confirmable empirically from the student's own run log.

Ceilings worth discovering: 221/hr from the 96-well plate, 360/hr from the transfer time itself.

Counter-pressure: larger batches mean the first tube waits longer. Honest policy is
**flush when full, or when the oldest sample has waited > T**; *T* is what students must justify.

### 8.4 Implementation basis

`asyncio.Queue` + worker coroutine(s), not a discrete-event engine:

- ~30 lines of machinery instead of a heapq event loop
- matches PLR's native paradigm
- finally teaches the async that five workshops cargo-cult
- time compressed by scaling sleeps (1 sim-minute = 10 ms)

Cost: wall-clock async is somewhat nondeterministic, so checkers assert **properties** (queue
bounded, all jobs accounted for, throughput within a band) rather than exact numbers. Better
assertion design regardless.

### 8.5 Data tracking

One-to-one: every tube goes to exactly one (plate, well). Trivial to implement, must be exactly
right — the correct level for a data-integrity lesson.

Invariants:

1. Every accessioned sample maps to exactly one well, or is still queued at end of run
2. No well assigned twice
3. No sample assigned twice
4. Timestamps monotonic; TAT derived correctly

(1) is the same conservation property as the reagent ledger, one level up.

### 8.6 Given vs written

**Given:** seeded arrival generator, station timing model, `Sample` dataclass, the deck.
**Written:** batching policy, plate map, logging, plots.

Four artifacts — comparable to W3 Exercise 1, not a semester project.

### 8.7 Deliverables

- `run.log` — one structured record per run started and completed
- `plate_maps/` — well → accession ID, per plate
- `samples.csv` — accession, received, plated, TAT
- **Plots:** queue depth over time, TAT distribution, for at least two policies

Queue depth over time makes stable-vs-diverging visually unmistakable and supplies the plotting
content the course currently lacks entirely.

### 8.8 Placement

Two options:

- **Surgical:** replace W3 Exercise 2 (60 pts). Inherits the resource-movement theme, removes Ex2.C
  and Ex2.E (the two least motivatable items), keeps Ex1's OOP lesson.
- **Capstone (preferred):** new final workshop, using the session freed by moving W2's exposition
  into `reference/`. Presumes everything before it.

Caveats to accept deliberately: it teaches less PLR than any other workshop, and queueing will be
unfamiliar to most BME students — the guidebook needs a single-station warm-up example before it.

---

## 9. PyLabRobot version strategy

### 9.1 Upstream has deleted liquid tracking

- Forum thread "Are people using the cross contamination tracker?" (rickwierenga, 2025-10-11):
  2 likes, **zero replies**.
- PR #744 "remove Liquid tracking from volume tracker, delete contamination tracker", merged
  2025-12-03. 28 files, +286 / −666. Stated rationale: the syntax is useless and does not work well.

Current `main`:

| | Status |
|---|---|
| `VolumeTracker` | scalar — `self.volume`, `self.pending_volume` |
| `get_used_volume()` / `get_free_volume()` | present |
| `set_volume()` | the new setter |
| `set_liquids()` | deprecated → `set_volume` |
| `get_liquids()` | deprecated — "no longer tracks individual liquids" |
| `liquid_history`, cross-contamination, `CrossContaminationError` | **removed** |
| `commit` / `rollback` / `register_callback` | present |

Nobody ever filed the LIFO behaviour as a bug; the maintainer reached a stronger conclusion without
it being written down.

### 9.2 Consequence for this course

Vendoring 0.1.6 is **load-bearing, not convenience**. The course depends on three things that no
longer exist upstream:

- `tracker.set_liquids()` — used in every workshop from W2 on
- `liquid_history`
- the entire cross-contamination section of W2, plus the `set_cross_contamination_tracking(True)`
  calls in the W3/W4/W5 setup cells

**Decision required (§11.1).** Either pin 0.1.6 permanently and document why, or move to upstream and
rewrite W2's back half on top of `bme590.reagents`. The ledger design in §6 works on both, which is
its main advantage — against 0.1.6 it layers on existing composition; against upstream it supplies
the only composition model there is.

Do not let anyone "helpfully" bump the vendored copy without reading this section.

### 9.3 pyserial

`deserialize()` calls `get_plr_class_from_string()`, which imports **every** PLR subpackage to build a
name→class lookup, then linear-scans. Two subpackages hard-fail without the `fw` extra:

```
FAIL incubators -> No module named 'serial'
FAIL pumps      -> No module named 'serial'
```

`incubators` appears in tracebacks purely by alphabetical accident. This breaks
`save_state_to_file` / `load_state_from_file` for any deck containing tip racks. Known upstream
(issue #214).

Fix if state persistence is ever taught — add to `environment.yaml`:

```yaml
  - pyserial
```

Not currently a live bug: no workshop calls serialization. Existing students would need
`conda env update -f environment.yaml`.

Note also: name matching is first-match-wins across 20 packages, so name collisions resolve by import
order, silently.

---

## 10. Errata and infrastructure fixes

### 10.1 Instruction/answer mismatches

| # | Where | Issue |
|---|---|---|
| 1 | W0 deck cell | `for i in range(3)` creates 3 tip racks; comment says 2 and the expected `summary()` output two cells later lists 2 + 3 empties. W1 uses `range(2)` and matches. |
| 2 | W1 conclusion | Asks for a `.txt` for **exercise 5**; only 4 exist. |
| 3 | W1 | Only workshop with no point values on its exercises. |
| 4 | W2 Ex3 | Stock volume is **420 µL** in the setup bullets, **480 µL** in the protocol bullets. Also "4x mL Reservoir" typo. "1:7" vs the arithmetic (60 into 60+420 = 8-fold) needs one clarifying sentence. |
| 5 | W3 Ex1.A | Says "add **three** plates", lists **four** (incl. `plate_X`), in ≤4 lines. |
| 6 | W3 Ex2.B | Prose says `move_plates()`, stub defines `move_plate()`, submission template says `move_labware()` with renamed args — under a "do not change function names" rule. |
| 7 | W3 Ex2.C | "Move the tip rack on the left" — `make_deck()` (DO NOT MODIFY) creates only two *plate* carriers. No tip carrier exists on that deck. |
| 8 | W4 conclusion | Lists `exercise_2.txt` twice (second "for exercise 3"); `exercise_1.gif` for exercise 3's GIF. |
| 9 | W4 Ex2.C vs Ex3 | Spec says return `None, None` for invalid combos; scaffold only yields inside `if all_fragments_valid`. Ex3's `if fragments is not None` can never be false. Pick one contract — the fix changes what Ex4 verifies. |
| 10 | W4 path cells | Markdown says `cwd` should be `bme590-fall-2025`; the comment one cell later says `bme590-fall-2025/assignments`. |
| 11 | README vs env | README says Python 3.13; `environment.yaml` pins 3.11. |
| 12 | All notebooks | ~40 recurring typos. `excpetion` appears in 5 of 6 — **inside taught code**, so students copy it into graded submissions. Also `sumamry`, `gneeral`, `exercses`, `keep in minde`, `rightmorst`, `Impelment`, `abosrbance`, `conmbinations`. |

### 10.2 Code smells in taught code

| Issue | Detail |
|---|---|
| `visualize_deck` swallows errors | Duplicated verbatim in all six notebooks; catches everything, prints, returns `None`. Next line dies with `AttributeError: 'NoneType' object has no attribute 'deck'` — the error students report instead of the real one. **Highest-value single fix.** |
| `reset_tip_box_and_pipette_head` | Bare `except:`. |
| `NewGripper.move_labware_column_up` | Reads module-global `deck` for the occupancy check while using `self.lh.deck` for the start slot. Works only because the notebook rebinds `deck` alongside `lh`. `NewNamedGripper` silently fixes it — an unused teachable moment. |
| Same method | Prints `Moving X to spot i` *before* the occupancy check, so the log claims moves that were skipped. |
| `time.sleep()` inside `async def` | W0's `visualize_deck_with_time_delay` and every exercise that tells students to sleep between steps. Blocks the event loop; harmless against chatterbox, stalls all I/O on real hardware including the visualizer websocket. Should be `asyncio.sleep()`. |
| Hidden cross-cell globals | `red_dye`, `plate_0`, `reader`, `csv_path`, `deck`. Out-of-order execution fails confusingly. W2 warns once; others do not. |
| Path handling | `os.path.dirname(os.getcwd())` in W4/W5 breaks when run from the repo root. |
| Unseeded `df.sample(n=1)` | W4. Same buggy code fails differently each run — brutal debugging for six-weeks-in students. |

### 10.3 W4 difficulty relief

In order of return:

1. **Break the dependency chain.** Provide a reference `add_fragments` (or a saved state) so a wrong
   Ex1 costs 15 points instead of 95. A checker at the end of Ex1 pays for itself immediately.
2. **Scaffold Ex3 like everything else** — give the three helper signatures. Stays a 40-point
   protocol; stops being a guessing game about grading.
3. **Seed the sampling.**
4. Fix the `None` contract; make path resolution robust.

None reduce rigor.

Separately, W4 Ex4 is two things under one name: the missing-fragment case is *recorded* to CSV, the
wrong-contents case `assert`s and crashes, so a genuine mismatch never reaches the report. Decide
whether it is a QC report (both paths recorded) or a hard check (both raise).

### 10.4 Infrastructure

- `.gitignore` — add generated output dirs (`workshop_5_plate_reader_output/`,
  `workshop_5_imager_data/`, `exercise_4.csv`). Currently only `__pycache__`, `*.egg-info`,
  `.vscode`, `.DS_Store`, `assignments/`.
- Consolidate `visualize_deck` into `bme590/decks.py` — one place for the exception fix, the ledger
  wiring, and visualizer host/port config.
- `colab_workshops/` — six duplicate notebooks (~4.5 MB with outputs baked in) that the README admits
  are less tested. Candidate for deletion once the local path is solid, or keep and accept the
  dual-maintenance cost. Docker/devcontainer was considered as a replacement and **rejected as too
  much work for now**.

---

## 11. Open decisions

1. **PLR version.** Pin 0.1.6 permanently, or track upstream and rewrite W2's cross-contamination
   material on `bme590.reagents`? Blocks §6 and parts of §5.
2. **Build the ledger at all?** W1/W3/W4 checkers do not need it. W2's PCR acceptance criteria do.
3. **Capstone placement.** Replace W3 Ex2, or add as a final workshop.
4. **W5 imager.** Keep mammalian passaging, or move to colony counting (two-part change).
5. **W1's open-source-navigation objective.** Drop deliberately, or relocate to an ungraded tour.
6. **`submission.json`.** Adopt as a deliverable and retire the copy-paste templates?
7. Fork is public — GitHub does not allow private forks of public repos. Fine for a public course
   repo; noted for the record.

---

## 12. Sequencing

**Phase 0 — free wins, no design decisions**
- Errata §10.1 (typos, filename lists, "exercise 5", the W3 Ex2.C missing tip carrier)
- `visualize_deck` into `bme590/decks.py`, exception fix
- Seed all RNG
- `.gitignore`
- W4 relief items 3 and 4

These are small and uncontroversial. Send upstream as one PR to `chory-lab`, separate from anything
architectural.

**Phase 1 — reference extraction**
- Move W2's 164 exposition cells into `reference/plr/`
- Write `CHEATSHEET.md`
- Shrink W2 to ~25 cells with links
- Python guidebook: start with `logging`, `__getitem__`/`enum`/`Literal`, and the async cluster

**Phase 2 — checkers (no ledger)**
- `bme590/checks/` for W1, W3 (esp. Ex2.E), W4
- Establishes the pattern and the feedback style before composition work

**Phase 3 — biological reframing**
- W4 first (pure renaming, highest return)
- Then W2's plate-map framing (text-only, and the cheapest test of whether the approach lands)
- Then W1 item swap, W3 incubator demo + SPRI framing

**Phase 4 — reagent ledger**
- Resolve §11.1 and §11.2 first
- Verify the four upstream API unknowns (§6.6)
- `reagents.py` standalone → `handler.py` → invariant tests → PCR acceptance checkers

**Phase 5 — capstone**
- Single-station warm-up in the guidebook
- COVID accessioning workshop

Pilot rule: do **one** workshop end to end before committing to all five. W1 or W4 are the natural
pilots — W1 because the motivation problem is worst there, W4 because the change is pure renaming.
