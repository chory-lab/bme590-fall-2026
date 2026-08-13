# PLAN.md audited against PyLabRobot 0.2.2

Companion to `PLAN.md`. Every claim below was checked against the **0.2.2 sdist from PyPI**
(released 2026-07-30) and against `PyLabRobot/pylabrobot@main` as of 2026-08-12.
The course currently vendors **0.1.6**.

Statements are marked **[verified]** (read in 0.2.2 source), **[inferred]** (follows from verified
facts but not executed), or **[unchecked]**.

---

## 0. The headline: "current version" is ambiguous, and it matters

There is no `v0.2.2` git tag. The tag list ends at `v0.2.1`. `main`'s `version.txt` says `0.2.2`,
but `main` contains commits *after* the 0.2.2 release, and one of them is enormous:

```
160bfe5 feat(cole_parmer): add GenoGrinder plate shaker driver (#1192)
798cab8 fix(byonoy): ...                                       (#1191)
14a7766 v1b1 changes                                           (#1000)   <-- 759 files, +75307 / -53054
dd79c4c 0.2.2                                                            <-- the release
```

**PR #1000 moved every machine frontend into `pylabrobot/legacy/`** and restructured the package by
vendor. On `main` today: **[verified]**

| | 0.2.2 (PyPI) | main (post-#1000) |
|---|---|---|
| `LiquidHandler` | `pylabrobot.liquid_handling` | `pylabrobot.legacy.liquid_handling` |
| `pylabrobot/liquid_handling/` | full stack | only `backends/`, `liquid_classes/`, `standard.py` |
| `pylabrobot/machines/` | `Machine`, `MachineBackend` | empty (`__init__.py` only) |
| top level | ~28 packages by function | ~50 packages **by vendor** (`hamilton`, `inheco`, `brooks`, `byonoy`, `keyence`, `ufactory`, …) |
| thermocycling, storage, sealing, arms | top level | under `legacy/` |

This is the Device/Driver/CapabilityBackend migration that `PLAN.md` §6.3 anticipated as a future
risk. **It has landed on `main`.**

### Recommendation

**Pin `pylabrobot==0.2.2` for both the course and the cookbook. Do not track `main`.**

- 0.2.2 is the last coherent released state; `main` is mid-migration with the entire course surface
  sitting under a package literally named `legacy`.
- Pinning is a one-line `environment.yaml` change, not vendoring — students `pip install` it, so
  §9's "do not let anyone bump the vendored copy" hazard disappears along with the vendored tree.
- Revisit when v1b1 actually ships. The cookbook's chapter boundaries survive the migration; the
  import paths do not, which is an argument for keeping import paths in one place (see §7 below).

---

## 1. Course code that will not run on 0.2.2

Ordered by blast radius. All API facts **[verified]**; the claim that the course *calls* these is
taken from `PLAN.md` §9.2 and was not re-checked against the notebooks **[unchecked]**.

| Symbol | Status in 0.2.2 | Effect |
|---|---|---|
| `set_cross_contamination_tracking(...)` | **gone** — no such function anywhere in the package | `ImportError`/`NameError` in the setup cell of W2, W3, W4, W5 |
| `no_cross_contamination_tracking()` | **gone** | ditto |
| `tracker.liquid_history` | **gone** | `AttributeError` |
| `CrossContaminationError` | **class still exists in `resources/errors.py`, but nothing raises it** | W2's cross-contamination section runs and never triggers — worse than an error |
| `tracker.set_liquids([...])` | present, **deprecated shim**: `set_volume(sum(v for _, v in liquids))` + `DeprecationWarning` | runs, but silently discards liquid identity |
| `tracker.get_liquids(top_volume)` | present, **deprecated**, always returns `[(None, top_volume)]` | any code reading back a liquid name gets `None` |

The dead `CrossContaminationError` is the nastiest item: it makes W2's contamination material look
alive while it is inert. It should be removed from the course, not repaired.

### Consequence for the plan

§11.1 is effectively decided. Moving to a current PLR means the §6 ledger is **required**, not
optional — 0.2.2 has no composition model at all, so `bme590.reagents` becomes the only source of
"what is in this well". That also settles §11.2 (build the ledger: yes).

---

## 2. §6.6's four unknowns — all four resolved

`PLAN.md` §6.6 listed four things to verify before writing ledger code. All now checked **[verified]**:

1. **`aspirate` / `dispense` signatures** — unchanged from 0.1.6 **plus one new argument**:
   ```python
   async def aspirate(self, resources, vols, use_channels=None, flow_rates=None,
                      offsets=None, liquid_height=None, blow_out_air_volume=None,
                      spread="wide", mix=None, **backend_kwargs)
   ```
   `mix: Optional[List[Mix]]` is new (`Mix(volume, repetitions, flow_rate, surface_following_distance)`
   in `liquid_handling/standard.py`). The `**kwargs`-passthrough defence in §6.3 was the right call.

2. **`lh.head[c].get_tip()`** — survives. `self.head: Dict[int, TipTracker]`; `TipTracker.get_tip()`
   is present. There is also a new, nicer `lh.get_mounted_tips() -> List[Optional[Tip]]`.

3. **Do `transfer` / `stamp` route through `aspirate`/`dispense`?** — **Yes, both.** This was flagged
   as "the one failure mode that would silently under-track"; it does not occur.
   - `transfer()` calls `await self.aspirate(...)` then `await self.dispense(...)`
   - `stamp()` calls `await self.aspirate96(...)` then `await self.dispense96(...)`

4. **`aspirate96` / `dispense96`** — separate code paths, so the §6.3 plan to override all four
   (`aspirate`, `dispense`, `aspirate96`, `dispense96`) is correct and sufficient.

**§6.6 can be struck from the plan.** The estimate was "half a day reading `liquid_handler.py`"; the
answers are above.

---

## 3. Upstream bug found: `LiquidHandler.stamp()` dispenses into the source

**[verified]** in 0.2.2, `liquid_handling/liquid_handler.py`:

```python
async def stamp(self, source: Plate, target: Plate, volume, ...):
    assert (source.num_items_x, source.num_items_y) == (target.num_items_x, target.num_items_y), \
        "Source and target plates must be the same shape"
    await self.aspirate96(resource=source, volume=volume, flow_rate=aspiration_flow_rate)
    await self.dispense96(resource=source, volume=volume, flow_rate=dispense_flow_rate)
    #                              ^^^^^^ should be `target`
```

`target` is used only in the shape assertion. The signature even carries a bare `source: Plate,  # TODO`.

Implications: do not put `stamp()` in a cookbook recipe or an exercise until this is fixed; it is a
clean, tiny first upstream PR if you want one; and it is a good worked example for the cookbook's
"read the source, don't trust the docstring" habit.

---

## 4. Claims in PLAN.md that hold up

**[verified]** against 0.2.2 unless noted.

- §9.1 volume-tracker findings — correct. `VolumeTracker` is scalar (`volume`, `pending_volume`);
  `set_volume` is the setter; `commit`/`rollback`/`register_callback` present.
- §6.1's rejection of tracker `register_callback` for the ledger — still right; it is a zero-arg
  callback with no source→destination pairing.
- §3.3 logging — `_log_command` is called **exactly 25 times** in `liquid_handler.py`, still
  `logger.debug("%s(%s)", name, params)` with `_format_param` rendering resources by name. The
  "audit log for free" argument is intact. (Files using `getLogger` is now **60**, not 26.)
- §5.4 incubator — `Incubator` still exposes `fetch_plate_to_loading_tray`, `take_in_plate`,
  `get_num_free_sites`, `get_site_by_plate_name`, `find_smallest_site_for_plate`, `set_temperature`,
  `open_door`/`close_door`, `start_shaking`. **`take_in_plate` still ends with exactly the two lines
  the plan builds its lesson on:**
  ```python
  plate.unassign()
  site.assign_child_resource(plate)
  ```
  One move: the package is now `pylabrobot.storage`, not `pylabrobot.incubators`. `find_random_site`
  replaces the `"random"` internals; a `NoFreeSiteError` was added.
- §3.2 Tier 1 — every entry survives: `move_plate`, `move_lid`, `move_resource`, `pick_up_resource`,
  `move_picked_up_resource`, `drop_resource`, `transfer`, `stamp`, `use_channels`,
  `probe_tip_inventory`, `consolidate_tip_inventory`, `probe_tip_presence_via_pickup`,
  `serialize`/`load`, `prepare_for_manual_channel_operation`, `move_channel_x/y/z`.
- §3.2 Tier 2 — `ResourceStack.get_top_item`, `PlateAdapter.compute_plate_location`, `Rotation`,
  `Coordinate`, `Tube`/`TubeRack`/`Trough`/`PetriDish`/`Trash`, `barcode.py` all present.
- §3.2 Tier 3 — `create_ordered_items_2d`, `create_equally_spaced_2d/x/y`, `utils.query`,
  `resources.errors`, `liquid_handling.strictness`, `no_volume_tracking()`, `no_tip_tracking()`
  all present.

---

## 5. Corrections to specific PLAN.md sections

| § | Claim | Correction |
|---|---|---|
| §9.3 | pyserial breaks `deserialize` because `get_plr_class_from_string` imports every subpackage | **Obsolete.** 0.2.2 uses `utils.object_parsing.find_subclass`, which walks `cls.__subclasses__()` — no mass import, no `serial` dependency. **New gotcha instead:** it only finds classes already imported, so deserializing a resource whose module was never imported returns `None`. Worth one cookbook paragraph; the `pyserial` line in `environment.yaml` is no longer needed for this reason. |
| §3.2 Tier 3 | `height_volume_functions` has "~12 functions" | **21** |
| §3.3 | "26 files" use logging | **60** |
| §6.1 | container is a "LIFO stack of unmixed layers" | True of 0.1.6 only. In 0.2.2 there are no layers at all — a container is one float. The §6.2 ledger design is unaffected (it stores mass itself and reads only volume from PLR), which was its stated advantage. |
| §5.4 | `pylabrobot.incubators.Incubator` | now `pylabrobot.storage.incubator` |
| §5.3 | five proposed W1 labware names | **3 of 5 no longer resolve** — see §6 below |
| §10.1 #1–12 | line-level errata in the notebooks | **Not re-verified.** These are course-side and unaffected by the PLR bump, but they were established against notebooks that will need editing anyway. Re-check after the migration edit, not before. |

---

## 6. Labware naming migration — affects §5.3 directly

0.2.2 is mid-rename to a `<vendor>_<n>_<type>_<volume>uL_<bottom>` convention, with old names kept as
shims marked `# remove v1b1`. **[verified]** Shim counts: `agenbio` 4, `celltreat` 8, `cellvis` 4,
`corning` 3, and 1 each across `agilent`, `azenta`, `bioer`, `biorad`, `btx`, and others.

Example, `resources/btx/plates.py`:
```python
def btx_96_wellplate_125uL_Fb_2mm(name: str) -> Plate: ...
def BTX_96_wellplate_125ul_Fb_2mm(name: str) -> Plate:  # remove v1b1
```

§5.3's proposed W1 swap re-checked against 0.2.2:

| PLAN.md §5.3 name | Status |
|---|---|
| `opentrons_96_filtertiprack_20ul` | ✓ exists |
| `opentrons_96_filtertiprack_200ul` | ✓ exists |
| `opentrons_24_aluminumblock_nest_1point5ml_snapcap` | ✗ → `opentrons_24_aluminumblock_nest_1_5ml_snapcap` |
| `opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap_acrylic` | ✗ → `opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap` |
| `nest_1_reservoir_195ml` | ✗ → `nest_1_troughplate_195000uL_Vb` |
| `nest_96_wellplate_100ul_pcr_full_skirt` | ✗ **no replacement found** — no plate in 0.2.2 matches `pcr` or `full_skirt` outside Tecan-specific `PCR_Plate_96_Well` |

The last row needs a decision: use Tecan's `PCR_Plate_96_Well`, pick another 96-well plate and call it
the PCR plate, or **define one as the worked example in the custom-labware chapter** — which is the
most useful option, since the course through-line is PCR and the cookbook needs a real custom-labware
subject anyway.

Vendor packages also churned: gone are `corning_axygen`, `corning_costar`, `ml_star`, `stanley`
(consolidated); new are `bioer`, `btx`, `diy`, `greiner`, `imcs`, `perkin_elmer`. 143 plate
definitions total across vendors. Note **`resources/diy/`** (`davidnedrud`, `grindbio`) — community
3D-printed labware, a natural cookbook pointer.

---

## 7. What 0.2.2 adds that the plan should exploit

New since 0.1.6 **[verified]**, with the section each one bears on:

| New in 0.2.2 | Bears on |
|---|---|
| `pylabrobot.thermocycling` — `Thermocycler(ResourceHolder, Machine)` with `run_pcr_profile()`, `run_protocol()`, `set_block_temperature`, `wait_for_block`, `get_current_cycle_index` | §5.2's through-line. W3's "plate goes to a thermocycler" is now a **real driver with a chatterbox**, not a narrative device. `run_pcr_profile` is the single best motivating call in the whole course. |
| `pylabrobot.arms` — `precise_flex/`, `scara.py`, `standard.py` | §5.4 / W3. PLR now ships a real arm abstraction, which sharpens the honest framing: the hand-built gripper is a teaching fiction, and here is what the real one looks like. |
| Chatterbox backends for **~15 machine types** (thermocycling, storage, centrifuge, sealing, plate_reading, shaking, tilting, pumps, scales, temperature_controlling, heating_shaking, powder_dispensing, only_fans, …) | Cookbook ch. 1 and the whole course. A **complete simulated workcell** is now possible with zero hardware. This is the single biggest new capability. |
| `Mix` in `standard.py` + `mix=` on aspirate/dispense | Cookbook ch. 5. Built-in mixing replaces hand-rolled aspirate/dispense loops. |
| `Liddable` mixin (`resources/lid.py`); `Lid` no longer lives in `plate.py`; containers can take lids | Cookbook ch. 8 (lids). Import path change for any code touching `Lid`. |
| `Plate.set_well_volumes()` | The **non-deprecated** replacement for `set_well_liquids` throughout the course. |
| `lh.move_tips()`, `lh.use_tips()`, `lh.get_mounted_tips()`, `lh.get_picked_up_resource()` | Cookbook ch. 7. |
| `resources/utils.py`: `row_index_to_label`, `label_to_row_index`, `split_identifier`, `sort_by_xy_and_chunk_by_x` | Cookbook ch. 4, and **W4 Ex2 asks students to write `convert_well_id` — which is now `label_to_row_index` + `split_identifier`.** Decide whether that exercise stays. |
| `Plate.get_quadrant()`, `check_can_drop_resource_here()` | Cookbook ch. 4 and ch. 3. |
| `SerializableMixin`, `find_subclass` | Cookbook ch. 10. |
| `PlateHolder.pedestal_size_z` now **required** (raises if omitted) | Cookbook ch. 12. A custom holder that omits it fails loudly — good teaching. |
| New machine categories: `peeling`, `plate_washing`, `barcode_scanners`, `storage` | Cookbook ch. 13's survey. |

**Chapter 13 instrument choice:** `btx` now exists as a *labware* vendor (BTX is an electroporation
company), but there is **no electroporator machine class** — `resources/btx/` contains only plates.
So an electroporator is still a genuinely absent instrument and remains viable as the worked example.
Verify once more before committing, since 0.2.2 also added `peeling` and `plate_washing`, and the
absent-machine list is shrinking release over release.

---

## 8. Revised open decisions (replaces PLAN.md §11)

| # | Decision | Status now |
|---|---|---|
| 1 | PLR version | **Resolved: pin `pylabrobot==0.2.2`, un-vendor.** Not `main` — see §0. |
| 2 | Build the ledger? | **Resolved: yes, required.** 0.2.2 has no composition model, so nothing else can answer W2's acceptance criteria. §6.6's blockers are all cleared. |
| 3 | Capstone placement | Unchanged (open). |
| 4 | W5 imager | Unchanged (open). |
| 5 | W1 open-source-navigation objective | Unchanged (open) — though the vendor-package churn makes "navigate the library" a moving target; prefer the cookbook's naming-convention chapter. |
| 6 | `submission.json` | Unchanged (open). |
| 7 | Public fork | Unchanged (noted). |
| **8** | **New: which PCR plate?** | §6 above. Recommend defining one as the custom-labware worked example. |
| **9** | **New: does W4 Ex2 survive?** | `label_to_row_index` / `split_identifier` now ship upstream; the exercise asks students to reimplement them. |
| **10** | **New: `stamp()` upstream fix** | Report it; decide whether to PR it (§3). |

---

## 9. Sequencing impact on PLAN.md §12

Phase 0 grows a mandatory item that gates everything else:

**Phase 0a — the version migration (new, blocking).**
1. `environment.yaml`: drop the vendored tree, pin `pylabrobot==0.2.2`.
2. Delete all cross-contamination material and `set_cross_contamination_tracking` calls (W2–W5 setup cells).
3. `set_liquids` → `set_well_volumes` / `set_volume` throughout.
4. `pylabrobot.incubators` → `pylabrobot.storage`; `Lid` import path.
5. Fix the §5.3 labware names; decide the PCR plate.
6. Re-run every notebook end to end and collect the real failures — the list above is static analysis
   **[inferred]**, not execution.

Only then do §10.1's errata (they will be re-touched by step 6 anyway), then Phase 1 onward as written.

Phases 2–5 are unaffected in substance. Phase 4 loses §6.6 (done) and gains confidence: the
interception design is verified correct against 0.2.2.
