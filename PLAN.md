# BME 590 Redesign Plan

Working plan for the fork at `github.com/stefangolas/bme590-fall-2025`
(upstream: `github.com/chory-lab/bme590-fall-2025`).

**Target: `pylabrobot==0.2.2`.** §3 is written against it. Sections 4–12 were written against the
vendored 0.1.6 and are being migrated — see **`PLAN-0.2.2-AUDIT.md`** for what changed, what breaks,
and which claims below are now stale (notably §9, and §11.1/§11.2 which the audit resolves).

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
  cookbook/                     <- NEW: read-only, never copied to assignments/  (see §3)
    _quarto.yml                 project: type: book — chapter list is the TOC; freeze: auto
    _theme-light.scss           paired light/dark themes
    _theme-dark.scss
    index.qmd                   landing page
    recipes.qmd                 generated listing — the task-indexed recipe index
    CHEATSHEET.qmd              flat lookup table
    part1/  01..06.qmd          robot, labware, deck, indexing, pipetting, shortcuts
    part2/  07..12.qmd          worklists, tips, moving labware, errors, state,
                                backend kwargs + hardware
    part3/  13_system_design.qmd            decorators, logging, tests, data, config
    part4/  14_custom_labware.qmd           guided vertical: define a PCR plate
            15_custom_liquid_handler.qmd    guided vertical: a single-channel backend
  workshops/                    shrunk; exercises + short recap + links into reference/
  colab_workshops/              candidate for deletion (see §10.4)
  workshop_data/
  figs/
  pylabrobot/                   vendored (see §9)
```

`reference/` is never copied into `assignments/`. It is pulled fresh with `git pull`.

---

## 3. The PLR Cookbook

> Targets **`pylabrobot==0.2.2`**. Every API claim below was verified against the 0.2.2 sdist.
> See `PLAN-0.2.2-AUDIT.md` for the version analysis and for why we pin 0.2.2 rather than track `main`.

Principle: **cookbook = how PLR works. Workshop = what you are doing and why.**
Keeps the biological reframing out of the mechanics, so nothing is duplicated.

Audience is deliberately wider than the course: someone who knows Python, has read nothing about PLR,
and wants to write a working protocol tomorrow. The course is then a *consumer* of the cookbook
rather than its owner. This is what makes the material worth more than the six workshops it serves,
and it is why Part IV (§3.6) targets professional users outright.

**Hard boundary: no course material in the cookbook.** No exercises, no assignments, no graded
content, no BME 590 framing, no point values, no deliverables. Workshops link *into* the cookbook;
nothing in the cookbook links back out to the course. Chapters 14–15 are guided builds where every
step is given — not exercises with answers withheld. Enforced as rule 6 in `cookbook/SPEC.md`.

### 3.1 Format and toolchain

Three layers, because they are read at different moments:

| Layer | Read when | Form |
|---|---|---|
| `CHEATSHEET.md` | mid-exercise, "what's the signature" | flat table: function → signature → one line |
| **Recipes** | "how do I do X" | problem → 5–15 line runnable snippet → why it works → gotchas → API links |
| Chapter narrative | before the workshop | the notebook the recipes live in |

Recipes are indexed **by task, never by module** — "aspirate from a trough with 8 channels", not
"`liquid_handling.utils`". That indexing is the whole difference between a cookbook and an API dump.

**Build: Quarto** (`project: type: book`). Evaluated against Sphinx + `myst_nb` (PLR's own docs
stack) and Jupyter Book 2 / `mystmd`. All three do the basics equally — nested TOC and sidebar,
full-text search, callouts, tabsets, cross-references, execution caching, dark mode. Quarto wins on
the two that decide it for a *book*:

- **Listings** — data-driven index pages generated from per-document YAML metadata, filterable and
  sortable. This is what makes §3.1's "indexed by task, never by module" real rather than a
  hand-maintained page that rots. Each recipe carries `task:`, `chapter:`, `apis:`, and the
  recipe index is generated from it.
- **Theming** — Bootswatch bases plus SCSS variable overrides, with paired light/dark themes. MyST
  theming is comparatively shallow.

Also gained: **code annotations** (numbered markers on individual code lines with prose beneath —
the right tool for the ch. 14–15 verticals), document-level `code-fold`, and mature PDF output
(LaTeX/Typst) if a printable edition is ever wanted.

**Execution:** `freeze: auto` caches rendered output; CI rerenders with the freeze cache cleared so
every recipe executes against `ChatterboxBackend` on a schedule. That is the anti-rot mechanism —
given that upstream deletes subsystems between minor versions (§9 and the audit), a cookbook nobody
executes is wrong within a semester.

**Authoring format:** `.qmd`. Quarto renders `.ipynb` directly and that stays available, but margin
notes, callouts, and code annotations are cleaner in `.qmd`, and those are load-bearing here. This
is a real concession — "notebook" now means executable document rather than literally the JupyterLab
UI. Accepted deliberately.

**Two things given up, recorded so they are not rediscovered as surprises:**

1. **Upstreamability.** An earlier draft chose Sphinx specifically so the cookbook could be
   contributed to PLR's docs as a section. Quarto forecloses that without a conversion. Judged worth
   it — the cookbook's audience is wider than PLR's docs and it does not need to live there.
2. **Notebook-native authoring and hover cross-reference previews**, both of which Jupyter Book 2
   does better. Revisit if the verticals ever stop being the finale.

**Deferred spike:** in-browser execution via `quarto-live` or the `quarto-pyodide` extension (the
latter explicitly supports the Book format). PLR under Pyodide is unverified — `pyserial`, `usb`,
and the visualizer websocket are the likely blockers, though the chatterbox path may touch none of
them. Half a day to find out; if it works, every recipe becomes runnable from the page.

### 3.2 Part I–II: usage (chapters 1–13)

**Broad coverage of elementary concepts, with motivating examples scattered through.** Breadth over
depth: the job of Part I–II is that nothing in PLR's everyday surface is a surprise, not that any one
topic is exhausted. Examples are there to make a concept land and move on — they are illustration,
not the spine. Anything that turns into a project belongs in Part III.

No class hierarchies, no ABCs, no architecture. Abstractions are deferred wholesale to Part III.

| # | Chapter | Covers | Anchor recipe |
|---|---|---|---|
| 1 | Getting a robot on screen | `LiquidHandler(backend, deck)`, `await setup()`, `Visualizer`, `summary()`, `async with`, chatterbox. **0.2.2 ships chatterbox backends for ~15 machine types — a full simulated workcell, zero hardware.** | empty deck → visualizer in 10 lines |
| 2 | Standard labware | 26 vendor packages, 143 plate definitions; the naming convention as a decoder ring; finding a part by vendor/catalog no.; `get_resource(name)`, name uniqueness, `ResourceNotFoundError` | "I have a Corning 3635 — what do I import" |
| 3 | Putting things on the deck | `assign_child_resource`, carriers, `carrier[0] = ...`, rails/slots, `Coordinate`, relative vs absolute location, `check_can_drop_resource_here` | build a PCR deck |
| 4 | Indexing | `plate["A1:H1"]`, lists, ints, `(row,col)`, `row()`/`column()`, `get_item(s)`, `traverse(direction, batch_size)`, `summary(occupied_func)`, `get_quadrant()` | 96 → one quadrant of a 384 |
| 5 | Pipetting | `aspirate`/`dispense` and the args that matter: `flow_rates`, `offsets`, `liquid_height`, `blow_out_air_volume`, `spread`, **`mix=` (new in 0.2.2)**. Targeting positions *within* a well via `Coordinate`, `center()`, `get_anchor()`. `ChannelsDoNotFitError`, no-go zones, `get_channel_spacings` | scrape the last 5 µL from a corner; 8 channels into one trough |
| 6 | The shortcuts | `transfer()`, `use_channels()`, `aspirate96`/`dispense96`. **`stamp()` is documented as broken — see §3.6** | replace 20 hand-rolled lines with 1 |
| 7 | **Worklists and data formats** | CSV → operations; the one-row-per-transfer contract; validating before moving a channel; grouping rows into channel-parallel batches with `sort_by_xy_and_chunk_by_x` (new in 0.2.2); pandas vs plain `csv`, honestly; results back out. **Which format for which job: CSV worklists, JSON state, log lines for audit** | drive a run from a 3-column CSV |
| 8 | Tips | `pick_up_tips`/`drop`/`return`/`discard` (+96 variants), `allow_nonzero_volume`, `move_tips`, `use_tips`, `get_mounted_tips`, `get_all_tip_spots`, `probe_`/`consolidate_tip_inventory` | stream tips across 3 racks without running out |
| 9 | Moving labware | `move_plate`, `move_lid`, `move_resource`, `GripDirection`, `ResourceStack.get_top_item()`; lids via the `Liddable` mixin, `has_lid`, `get_lid_location`. **Magnetic bead stands — see below** | SPRI cycle: bind → magnet → elute |
| 10 | When it complains | the ~19 **portable** errors (raise on any backend) + `ChannelizedError` partial-failure semantics + the `no_*_tracking()` escape hatches | read a traceback, fix it |
| 11 | Saving and loading | layout (`serialize`/`load`) vs contents (`serialize_state`/`save_state_to_file`/`load_all_state`) as two different things; telling PLR what happened off-deck; `find_subclass` only sees imported classes | reload yesterday's deck |
| 12 | Backend kwargs and real hardware | `**backend_kwargs` passthrough, `strictness`, what chatterbox accepts that a STAR rejects, `setup`/`stop`, jogging via `prepare_for_manual_channel_operation` + `move_channel_x/y/z`; **backend error families** | same protocol, chatterbox → STAR |

Logging was previously a chapter here. It moves to ch. 13 (§3.5), because it is a system-design
concern rather than a PLR API concern. §3.3 below is unchanged and feeds it.

**Chapter 9's anchor: the magnetic bead stand.** `alpaqua_96_plateadapter_magnum_flx` ships in 0.2.2
and is implemented as a `PlateAdapter`. One recipe motivates four things at once — a gripper
`move_plate()`, `PlateAdapter.compute_plate_location()`, the z-offset problem (35 mm-tall adapter),
and this comment in the definition:

```python
dz=27.5,              # refers to magnet hole bottom
plate_z_offset=0.0,   # adjust at runtime based on plate's well geometry
```

It also threads back to ch. 5: the SPRI cycle needs **off-center aspiration to avoid the pellet**,
which is exactly the anchor/offset material, now with a reason. And it carries a conceptual point:
**a magnet is not a machine.** Nothing turns it on — engagement *is* the plate's position. Same
lesson as `Incubator.take_in_plate`'s `unassign()` / `assign_child_resource()` (§5.4).
(Use the snake_case name. `Alpaqua_96_magnum_flx` is a shim marked `TODO: Remove >2026-02`.)

**Chapter 10's scope.** 0.2.2 has ~140 exception classes in two populations:

| Population | Count | Where |
|---|---:|---|
| **Portable** — raise on any backend | ~19 | `resources/errors.py` (8), `liquid_handling/errors.py` (3), `BlowOutVolumeError`, `NoFreeSiteError`, `NoPlateError`, `centrifuge/standard.py` (5), `NotCalibratedError`, `io/errors.py` |
| **Backend-specific** | ~120 | STAR **49**, Cytomat **29**, Liconic **14**, Molecular Devices 6, + Tecan, Vantage, EL406, PreciseFlex, MicroSpin, Inheco, SiLA, Mettler Toledo |

Ch. 10 teaches the portable set exhaustively. Ch. 12 teaches the *shape* of a backend family rather
than its contents — catch `STARModuleError`, not its 49 leaves. Navigation fact worth stating: errors
live in `errors.py`, in `standard.py`, or inline in the backend file, depending on package. There is
no single import.

`ChannelizedError` gets its own recipe because it is the multichannel error model and is undocumented:

```python
class ChannelizedError(Exception):
    """Contains a key for each channel that had an error, and the error that occurred."""
    def __init__(self, errors: Dict[int, Exception], **kwargs): ...
```

One channel failing tells you nothing about the other seven. This is also the "worklist
half-executed" case from ch. 7, so the two chapters share a recovery recipe.

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

### 3.4 Python, woven in rather than taught separately

The earlier plan had a standalone Python curriculum. For a usage-level cookbook that is the wrong
shape: it front-loads material with no referent. Instead each chapter carries a short
**"Python you need here"** sidebar. Same list, attached to the moment it is needed.

| Ch. | Sidebar | New? |
|---|---|---|
| 1 | `await` in a notebook vs a script (`asyncio.run`, autoawait) — **the day-one blocker**; `async with`, `try/finally` for `setup`/`stop` | partly |
| 2 | f-strings and format specs (plate maps, log lines) | **new** |
| 3 | `__setitem__` on carriers; mutable default arguments in deck helpers | **new** |
| 4 | slices, `__getitem__`, comprehensions, `zip`/`enumerate`, `itertools.product`, generators (`traverse`) | ✓ |
| 5 | **`None` as "backend default"** — `flow_rates=None` ≠ `flow_rates=0`; `Optional` semantics | **new** |
| 6 | list concat for resource selections (`plate["A1"] + plate2["A1"]`) | **new** |
| 7 | `csv`, `pathlib`, `dataclass`, `collections.defaultdict`; pandas only where it earns its place | ✓ |
| 8 | `collections.deque` / cycling | ✓ |
| 9 | `enum` (`GripDirection`), `typing.Literal` | ✓ |
| 10 | `try/except/else/finally`, custom exceptions, context managers, `logger.exception()` | ✓ |
| 11 | `json`, `datetime` for run IDs | ✓ |
| 12 | **`**kwargs` packing and unpacking** — `**backend_kwargs` is unreadable without it | **new** |
| 13 | `logging` (§3.3) | ✓ |
| 14 | `functools.partial`, factory functions, `super().__init__()` | partly |
| 15 | `abc` / `@abstractmethod`, frozen `dataclass`, `asyncio.gather` | partly |

The five **new** rows are the real gap in the old §3.1 list. `**kwargs` and `None`-as-default
especially: both are load-bearing for using PLR at all, and neither appeared anywhere.

Scope discipline is unchanged: **not** every stdlib utility. One example each, only where it repairs
an existing wart or unlocks a recipe. `random.seed`, `statistics`, `assert`/pytest move out of the
cookbook and into the course material that actually needs them (§7).

#### Cross-cutting threads

Two topics are too useful to confine to one sidebar, and both are *ecosystem* material — they are
about the code you write around PLR, not about PLR's API.

**Decorators.** PLR uses them itself, so the cookbook can teach from the real thing rather than a toy:

```python
def need_setup_finished(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        self = args[0]
        if not self.setup_finished:
            raise RuntimeError("The setup has not finished. See `setup`.")
        return await func(*args, **kwargs)
    return wrapper
```

It decorates `aspirate`, `dispense`, `pick_up_tips`, `drop_tips`, `Machine.stop`, and the plate
reader / imager methods. Read it once and every use case below is a variation:

| Decorator | Where it earns its place |
|---|---|
| `@need_setup_finished` (PLR's own) | ch. 1 — read it, understand why `await lh.setup()` is not optional |
| `@retry(n, backoff)` | ch. 12 — transient serial/USB failures on real hardware, the single most-wanted wrapper |
| `@log_step` / `@timed` | ch. 13 — per-step run records and protocol profiling on top of `_log_command` |
| error translation | ch. 10/12 — wrap an op to convert a vendor exception into a portable `resources/errors.py` type |
| `@dry_run` | ch. 7 — execute a worklist with motion suppressed, so a bad CSV is caught before a tip moves |
| `@contextmanager` | ch. 10 — the scoping pattern PLR itself uses for `no_volume_tracking()` / `no_tip_tracking()` |
| `@abstractmethod` | ch. 15 — the capability contract |

Plus the two gotchas that bite everyone: **an async function needs an async wrapper** (`async def
wrapper` + `await func(...)`, exactly as above), and **use `functools.wraps`** or you lose the name,
docstring, and signature that your own logging just started depending on.

**Worklists as ecosystem glue (ch. 7).** PLR ships no worklist support — no `.gwl`, no `csv` import
anywhere, `pandas` in exactly one file. That is fine and the chapter says so up front: worklists are
not a PLR feature, they are how PLR meets everything around it — LIMS exports, instrument
schedulers, ELN records, a colleague's spreadsheet. So the chapter teaches the *seam*: validate the
file before moving a channel, group rows into channel-parallel batches
(`sort_by_xy_and_chunk_by_x`), execute with a `@dry_run` pass first, recover from a half-executed
run via `ChannelizedError`, and write results back out. The decorator thread and the worklist thread
are the same lesson from two directions, and they should cross-reference each other.

### 3.5 Part III: process and system design (chapter 13)

The bridge chapter. Part I–II is *how do I call PLR*; Part IV is *how do I extend PLR*; ch. 13 is
**how do I build a system out of it**. Format is a run of small, independent microlessons — how to
use Python in lab automation — not one long build. Each is a page or two with a runnable snippet.

The organizing insight: almost everything that makes automation code robust is **cross-cutting**, so
it wants to be composed rather than inlined. Written inline it doubles the length of every protocol
and gets skipped under deadline; written as composable wrappers it is opt-in per step.

**A. Steps and composition.** A protocol as a list of steps rather than a script. `@step("name")`
registering what ran, with what inputs, and what it produced. Checkpoint and resume. Which steps are
idempotent and which are emphatically not (`aspirate` is not), and why that determines the
granularity at which you are allowed to retry.

**B. Recovery policy as composed decorators — the centrepiece.** Failures sort into three tiers that
want three different responses, and treating them all as "retry" is the classic mistake:

| Tier | Examples | Correct response |
|---|---|---|
| Transport / transient | serial timeout, USB hiccup | retry identically, with backoff |
| State / inventory | `NoTipError`, `HasTipError`, `TooLittleLiquidError`, `TooLittleVolumeError` | **change the plan**, then proceed |
| Semantic / unrecoverable | wrong labware, `ChannelsDoNotFitError` | abort, record, surface |

Written as a stack, the policy reads as policy:

```python
@retry(3, on=(SerialTimeout,), backoff=0.5)          # tier 1: try again unchanged
@recover(NoTipError, using=advance_to_next_tip_spot) # tier 2: change the plan
@recover(TooLittleLiquidError, using=switch_to_backup_source)
@recover(ChannelizedError, using=retry_failed_channels_only)
@log_step("add master mix")
async def add_master_mix(lh, plate, source): ...
```

Three microlessons fall out of this one example:

1. **Decorator order is handler precedence.** Bottom-up application, so the outermost decorator sees
   the exception last. Reordering the stack silently changes behaviour. This is the subtle bit and
   the best decorator lesson in lab automation.
2. **Partial failure needs partial retry.** `ChannelizedError` carries `Dict[int, Exception]` — a
   blind retry re-runs channels that *succeeded*, double-dispensing. Recovery must consult
   `.errors` and re-run only the failed channels. A real and expensive bug.
3. **Policy is reusable, plans are not.** `advance_to_next_tip_spot` is written once and applies to
   every step that touches tips.

**C. Dry run and simulation modes.** `@dry_run` suppressing motion so a bad worklist is caught before
a tip moves; running the whole protocol against chatterbox before hardware; the honest limits of
simulation (chatterbox validates state, not physics).

**D. Logging and the run record.** §3.3, as a microlesson: two handlers, `_log_command` giving you
most of an audit trail for free, `%(relativeCreated)d` for per-step profiling, `logger.exception()`
for tracebacks, namespace filtering. Pairs with `@log_step` and `@timed` from B.

**E. Testing without hardware.** Four levels, cheapest first:
pure functions (worklist parsing, well-ID conversion) as ordinary unit tests; deck assertions
(labware present, positions correct); whole protocols against chatterbox; and **record/replay via
`pylabrobot.io.capture`** — `start_capture(fp)` records raw device I/O, `validate(capture_file)`
replays and checks it. That last one is a professional practice, ships in 0.2.2, and is documented
nowhere. Plus: seed the RNG.
*Note:* `SaverBackend` existed in 0.1.6 and is **gone** in 0.2.2 — `io.capture` supersedes it.
There is also no `pylabrobot.testing` package in 0.2.2 (it exists only on `main`).

**F. Data management.** Run IDs and timestamped output directories; `pathlib` over string paths;
which format for which job (CSV worklists, JSON state, log lines for audit — the ch. 7 rule restated
at system level); snapshot and resume via `save_state_to_file`; provenance — tying a result back to
the worklist, the deck layout, and the run that produced it.

**G. Configuration.** `pylabrobot.config` (`load_config`, `get_config_file`, `Config`) for keeping
serial ports, device addresses, and host/port settings out of protocol code — so the same protocol
runs on the simulator and on the bench without edits.

**Where this pays off in the verticals (§3.6).** Both chapters are built to consume ch. 13:

- **Ch. 14** — a `@labware_definition` registration decorator collecting factory functions into a
  local catalog, mirroring how PLR's own library is just functions; validation at construction time
  rather than at first crash.
- **Ch. 15** — the clearest case in the book. A backend is 13 methods each wrapping transport I/O.
  Inline, that is 13 copies of retry, logging, and setup-checking. Composed, it is
  `@need_setup_finished` (reuse PLR's own), `@retry` on the transport layer, and one `@log_command`
  wrapper replacing print statements in every method — which is exactly "more robust and flexible
  without verbosity", demonstrated on real code the reader just wrote.

### 3.6 Part IV: two guided verticals (chapters 14–15)

Part III inverts the format. Where Part I–II is broad and elementary, these are **workbook-style
verticals**: one build, start to finish, in order. **Strictly hand-holding — every step is given.
No open exercises, no "now you try."** The reader follows a complete build and ends with a working
artifact they can adapt.

This is also the only place abstractions are the subject rather than the background, and they appear
only because the reader is about to implement or violate one. These two chapters are the cookbook's
largest value-add for professional users; nothing equivalent exists in PLR's docs today.

**Ch. 14 — Define a piece of custom labware: a PCR plate.**

Chosen over a more exotic subject because the geometry is genuinely non-trivial (conical wells,
skirt, `material_z_thickness`, volume ↔ height) *and* because the audit found 0.2.2 has **no PCR
plate at all** — `nest_96_wellplate_100ul_pcr_full_skirt` is gone with no replacement. So the
chapter's output is something the course then actually uses. The build:

1. Measure a real plate — what to measure and from which datum
2. Pick a base class. The decision table, which is currently written down nowhere:

   | Base | Use when | Cost |
   |---|---|---|
   | `Resource` | arbitrary children, arbitrary positions | no indexing, no volume |
   | `Container` | one addressable volume (`Liddable` since 0.2.2) | no child grid |
   | `ItemizedResource` | full rectangular grid of anything | **grid or it raises** |
   | `Plate` | grid of `Well`s, lid support | plate semantics assumed |
   | `ContainerRack` (new in 0.2.2) | grid of *holders* each taking a removable container | indirection via `ResourceHolder` |

3. Lay out wells with `create_ordered_items_2d`
4. Well geometry: `cross_section_type`, `material_z_thickness`, and one of the 21 functions in
   `height_volume_functions` — plus `supports_compute_height_volume_functions` when yours is custom
5. Wrap in a factory function, matching the `<vendor>_<n>_<type>_<volume>uL_<bottom>` convention
6. Make it sit right: `PlateHolder.pedestal_size_z` (now **required** — it raises if omitted) and
   `PlateAdapter.compute_plate_location()`, reusing the ch. 9 bead-stand material
7. Validate: `ResourceDefinitionIncompleteError` tells you what you left out
8. Contribute it upstream — `docs/contributor_guide/contributing-new-resources.md`

**The contract this exposes:** `ItemizedResource._get_grid_size()` raises
`ValueError("Not a full grid")` on any non-rectangular arrangement. Get the grid and you get
`traverse`, `row`, `column`, `get_quadrant`; violate it and you keep `num_items` and `get_item` but
lose the rest. A short closing section states the boundary in general terms — **geometry is fully
extensible, state is partially extensible, connectivity is not modeled at all** (volume trackers are
per-container and independent; nothing propagates between connected wells). That paragraph is what
generalizes the chapter to microfluidics, flow cells, and anything else with plumbing, without
having to build one.

**Ch. 15 — Define a custom instrument: a liquid handler.**

The most valuable chapter in the book for professional users, and more tractable than it looks:
`LiquidHandlerBackend` has **13 abstract methods**, not the ~20 assumed earlier. They tier cleanly,
and the worked example is a **single-channel gantry**:

| Tier | Methods | In the build |
|---|---|---|
| Core | `num_channels`, `can_pick_up_tip`, `pick_up_tips`, `drop_tips`, `aspirate`, `dispense` | implement (6) |
| 96-head | `pick_up_tips96`, `drop_tips96`, `aspirate96`, `dispense96` | `raise NotImplementedError()` (4) |
| Gripper | `pick_up_resource`, `move_picked_up_resource`, `drop_resource` | `raise NotImplementedError()` (3) |
| Optional | `move_channel_x/y/z`, `prepare_for_manual_channel_operation`, `request_tip_presence`, `get_channel_spacings` | already default to `NotImplementedError` / 9 mm |

The build: read `backends/chatterbox.py` (242 lines — a complete, correct, minimal backend), then
write your own against a simulated device, then wire a real one over `pylabrobot.io`
(`serial` / `usb` / `hid` / `ftdi`) and why those rather than raw pyserial. Then `setup`/`stop`
discipline, a `Deck` subclass, and coordinate frames / homing as its own section — that part is not
free and the chapter says so.

**The contracts this exposes**, which is the reason the chapter exists:

- **The ABC is the capability declaration.** All 13 are `@abstractmethod`, so Python refuses to
  instantiate until you have written *something* for each. You cannot accidentally ship a backend
  that silently lacks a 96-head — you had to type the `raise` yourself.
- **The op payload is the interface.** Backends receive frozen dataclasses
  (`SingleChannelAspiration(resource, offset, tip, volume, flow_rate, liquid_height,
  blow_out_air_volume, mix)`). The division of labour is explicit: **frontend owns tracking,
  validation, channel assignment and geometry resolution; backend owns motion.** By the time your
  code runs, the well is resolved, the offset applied, the tip known, and the volume tracker has
  already objected if it was going to.
- **Designing your own error contract** — reuse `resources/errors.py` types where they fit so your
  backend is interoperable; raise `ChannelizedError` for partial multichannel failures; model a
  vendor family on `STARModuleError` (one abstract base, typed leaves) so callers can catch the base.

### 3.7 Deck visualization architecture (deferred — not blocking)

**Status: decided in principle, deferred in execution.** Chapters can be written without it; figures
get retrofitted. Nobody should hand-roll a one-off diagram solution in the meantime.

**The want:** a runnable cell that builds a deck should *show* the deck, inline, in the page.

**Why the obvious thing fails.** `Visualizer` runs a websocket server plus an HTTP file server
(`index.html`, `lib.js`, `vis.js`, `main.css`) and pushes JSON commands to a browser page. An
embedded iframe pointing at `localhost` is dead by the time anyone reads the published page — the
render-time Python process is gone and readers have no kernel. Live embedding only works during a
local `quarto preview` where the reader is also executing the code.

**What makes any solution possible.** The client is cleanly layered even though it is not packaged
that way. `vis.js` exposes plain functions keyed by event — `setRootResource(data)`,
`setState(allStates)`, `removeResource(name)` — and `lib.js` deserializes a resource tree through a
~25-case class switch (`Plate`, `Well`, `TipRack`, `TipSpot`, `PlateCarrier`, `PlateAdapter`,
`TubeRack`, `Trough`, …) into Konva shapes. **The websocket is transport only; rendering takes plain
JSON.**

#### Decision: vendor an embeddable renderer

Routes considered:

| Route | Approach | Verdict |
|---|---|---|
| A | Static snapshot — embed `set_root_resource` payload, iframe + stubbed socket | stepping stone only |
| B | Record & replay with a timeline scrubber | the *target behaviour* |
| C | Build-time Playwright screenshot of the real visualizer | needed for PDF, but a second implementation |
| **D** | **Vendor PLR's renderer as an embeddable component** | **chosen** |

**Chosen: D.** Take PLR's rendering code, strip the single-page-app chrome, and repackage it as a
component we own.

Reasons, in order of weight:

1. **It inverts the dependency onto a public contract.** The component consumes
   `Resource.serialize()` — which PLR itself relies on for save/load — instead of `lib.js`
   internals, which are private and unversioned (`lib.js` changed substantially between 0.1.6 and
   0.2.2). This was the real objection to route A/B, and vendoring dissolves it.
2. **The PDF path comes free.** Quarto also builds PDF, where no JS canvas renders. Because we own
   the component, CI screenshots *it* rather than driving the full visualizer — one implementation,
   two outputs, instead of C as separate work.
3. **The scrubber becomes a design choice.** `replay(commands, t)` is something we specify, not
   something we reverse-engineer.
4. **It is reusable beyond this book** — an embeddable PLR deck renderer is useful to anyone writing
   PLR docs, notebooks, or dashboards. Plausibly worth more than the chapter that motivated it.

**Licensing:** PLR is MIT (`Copyright (c) 2018 dgretton`). Vendoring is fine; retain the notice in
every vendored file.

#### Scope, measured

| Fact | Number |
|---|---|
| `lib.js` | **5,853 lines, 251 functions** — hand-written, *not* a bundle |
| `vis.js` | 241 lines |
| Konva | **not bundled** — loaded from `https://unpkg.com/konva@8/konva.min.js` |
| Estimated keep (draw path) | ~1,500–2,500 lines |

**Drop:** the coords tool, the "with regards to" dropdown and bullseye highlights, delta lines, the
workcell grid (with its RAF-coalesced redraw and extent cache), the scale bar, tooltips, the
inspector panel, the resource tree sidebar, the GIF recorder, `openSocket()` and the status
indicator, and `index.html`'s `{{ source_filename }}` server templating.

**Keep:** `RESOURCE_COLORS`, `loadResource` and its class switch, the per-class `draw()` methods,
`setState`, stage/layer setup, `fitToViewport`.

**Vendor `konva.min.js` too.** The shipped visualizer currently requires internet; the book must not.

#### The actual work: de-globalization

Extraction is the easy half. `lib.js` is single-instance by construction:

```js
var mode;
var layer = new Konva.Layer();          // instantiated at module load
var resourceLayer = new Konva.Layer();
var gridLayer = new Konva.Layer({ listening: false });
var stage, tooltip, selectedResource, canvasWidth, canvasHeight;
```

plus `resources`, `rootResource`, and `methodRegistry` as module-level state. Supporting several
canvases on one page means wrapping all of it in a class with per-instance stage and layers, which
touches nearly every drawing function. Mechanical, but it is the bulk of the effort.

**Estimate: 2–4 focused days for a solid v1.**

#### Target API

```js
const view = PLRView.mount(el, { resource, methodRegistry });
view.setState(states);
view.replay(commands, { t: 0.4 });   // the scrubber
view.snapshot();                     // canvas → PNG, for the CI screenshot path
```

#### Python-side integration — the part that makes it smooth

The cleanest authoring experience is **not** a Quarto shortcode but a display hook. A small helper
in the cookbook's own support module returns HTML (a `<div>` plus the serialized payload), so a
recipe simply ends with:

```python
show(lh.deck)
```

and Jupyter's `_repr_html_` machinery does the rest. No per-figure markup, works identically in
`quarto preview` and `quarto render`, and degrades to the PNG in PDF. This is the difference between
"smooth" and "possible", and it should be designed in from the start rather than retrofitted.

#### Further planning notes

- **`freeze` interaction — non-obvious and important.** Captured payloads live in `_freeze/`, so the
  serialized output must be **deterministic** or every render churns the cache and CI diffs become
  noise. `Visualizer._generate_id()` produces per-message ids; those must not reach the embedded
  payload. Audit for any timestamp, random id, or dict-ordering instability before wiring this up.
- **Asset strategy:** `konva.min.js` and the component ship as Quarto `resources:`, referenced once
  per page. Never inline per figure — 213 KB × 60 recipes is not a page weight anyone wants.
- **Accessibility and search:** a canvas is opaque to screen readers and to the site's full-text
  search. Every figure needs a text summary beside it (a deck listing — resource names and
  positions). This also makes decks greppable, which is independently useful.
- **Degradation ladder:** interactive component → static PNG (PDF, JS disabled) → text summary.
  Specify all three; do not let the third be an afterthought.
- **Component testing:** golden-image tests. Render a fixed set of decks, compare against committed
  PNGs. Cheap, and it catches the class-switch regressions described below.
- **Maintenance cost, accepted deliberately:** the class switch is the extension point, so a PLR
  release adding a resource class renders it as nothing until a `case` is added. Bounded — one case
  per class — and the book is pinned to 0.2.2 regardless. Tag component releases against the PLR
  version they render.
- **Repo scoping:** start as `cookbook/_visualizer/`; extract to its own repo once it works and the
  API has stopped moving. Do not start with the extraction.

#### Spike to run first

Half a day, and it de-risks the whole approach: take one deck from ch. 9, dump `deck.serialize()`
plus the `method_registry` that rides along with `set_root_resource`, drop it into a bare HTML page
with `lib.js`, Konva, and a stubbed socket, and see whether `setRootResource` renders without the
surrounding SPA chrome. If it renders, the rest is refactoring. If it fights back, the estimate
above is wrong and we re-scope before committing.

### 3.8 Deliberately out of scope

Named so nobody re-adds them by reflex:

- **`stamp()`** — 0.2.2's implementation dispenses into `source`, not `target` (`target` is used only
  in a shape assertion). Excluded from recipes and exercises until fixed upstream. It is a clean,
  tiny first PR if we want one. Documented in `PLAN-0.2.2-AUDIT.md` §3.
- **Liquid classes** (`liquid_handling/liquid_classes/`) — real and important, but vendor-specific
  and not usable from the simulated path the cookbook is built on.
- **`standard.py` op objects as a topic** — they appear in ch. 15 where they are the interface, not
  earlier as an abstraction.
- **Writing non-liquid-handler machines** (sealer, thermocycler, plate reader backends) — the
  `Machine` + abstract-backend pattern is genuinely simpler than ch. 15, but it is the same lesson at
  lower stakes. One pointer paragraph in ch. 15, no chapter.
- **The v1b1 architecture on `main`** — see the audit. The cookbook pins 0.2.2; a migration appendix
  is deferred until v1b1 actually ships.

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
