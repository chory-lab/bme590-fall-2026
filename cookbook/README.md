# The PyLabRobot Cookbook — authoring guide

Quarto book. Scope, chapter list, and rationale live in `../PLAN.md` §3.
Version facts live in `../PLAN-0.2.2-AUDIT.md`.

## Build

Build in a dedicated venv. Do **not** render against a system-wide PLR: an editable dev checkout of
PLR on this machine shadows the pinned version, and its `liquid_handling.backends` package imports
the Festo backend eagerly, which fails with `ModuleNotFoundError: application_services` — that is
the first import of every setup cell in the book.

```bash
py -3.13 -m venv .venv-cookbook                                        # from the repo root
.venv-cookbook/Scripts/python -m pip install "pylabrobot==0.2.2" jupyter

export QUARTO_PYTHON=".../.venv-cookbook/Scripts/python.exe"           # point Quarto at it
quarto preview            # live reload while writing
quarto render             # full build to _site/
```

Requires [Quarto](https://quarto.org/docs/get-started/) ≥ 1.4 (built with 1.10.18). On Windows
Quarto installs to `C:\Program Files\Quarto\bin`, which is not always on `PATH`.

`execute.freeze: auto` caches rendered output, so a normal `render` will not re-run cells whose
source is unchanged. **CI should clear the cache** so every recipe actually executes against the
pinned PLR:

```bash
rm -rf _freeze/ && quarto render
```

That is the anti-rot mechanism. PLR removes subsystems across minor versions; a cookbook nobody
executes is wrong within a semester.

## The recipe format

A recipe is the unit of this book. Every one has the same five parts, in this order:

1. **The task** — phrased as the reader would search for it, not as the API is named
2. **A runnable snippet** — 5–15 lines, executes against `ChatterboxBackend`
3. **Why it works** — one paragraph, wrapped in `[...]{.why}`
4. **Gotchas** — `::: {.callout-warning}` per gotcha, each one a real failure mode
5. **See also** — related recipes and the APIs one level down

Wrap the whole thing in `::: {.recipe}` so it gets the left rule, and give the heading an explicit
anchor:

```markdown
## Move a plate onto a magnetic bead stand {#move-plate-to-magnet}

::: {.recipe}

### The task
...
:::
```

`part2/09_moving_labware.qmd` is the reference implementation. Copy its structure.

## Registering a recipe in the index

Recipes live inline in their chapter — they are not separate files — so that they stay in narrative
context. The task-indexed listing on `recipes.qmd` is driven by an explicit registry, `recipes.yml`:

```yaml
- title: "Move a plate onto a magnetic bead stand"
  path: part2/09_moving_labware.qmd#move-plate-to-magnet
  chapter: 9
  apis: "lh.move_plate, PlateAdapter, alpaqua_96_plateadapter_magnum_flx"
```

**Adding a recipe means adding an entry here.** `path` must match the `{#anchor}` on the heading.
`apis` is free text and exists so the listing's filter box matches on API names — put in everything
a reader might search for.

## Scope boundary

The cookbook is a **standalone manual**. It contains no exercises, no assignments, no graded
content, and no course framing. Workshops link *into* it; nothing course-specific links *out of*
it. Chapters 14–15 are guided builds where every step is given — a reader follows along and ends
with working code — not exercises with answers withheld.

## House style

- **Second person, present tense.** "Move the lid first", not "the lid should be moved first".
- **Code annotations over comments** for anything that needs a sentence. Use `# <1>` markers and a
  numbered list beneath; they render as hover markers.
- **Margin notes** (`::: {.column-margin}`) for the "Python you need here" asides. Skippable by
  construction — never put load-bearing information there.
- **Callouts carry meaning:**
  - `callout-warning` — a gotcha, a way this bites people
  - `callout-important` — a conceptual point that changes how you read the rest
  - `callout-note` — context, adjacent features, scope limits
- **Tabsets** for the same task on different backends or scales, not for unrelated content.
- **Every API name verified against 0.2.2 before it is written down.** The library is mid-rename to
  `<vendor>_<n>_<type>_<volume>uL_<bottom>`; deprecated shims still import and still work, so a
  wrong name will not necessarily fail the build. Check the source, not your memory.

## Directory layout

```
_quarto.yml           book config, chapter list, theme pairing, freeze
_theme-light.scss     paired themes — keep structural rules identical between them
_theme-dark.scss
index.qmd             landing page
recipes.qmd           the listing page (reads recipes.yml)
recipes.yml           recipe registry — edit when adding a recipe
CHEATSHEET.qmd        flat API lookup
part1/                ch 1–6    getting things done
part2/                ch 7–12   working protocols
part3/                ch 13     building systems
part4/                ch 14–15  extending PLR — guided builds, every step given
```

## Deferred

In-browser execution via [`quarto-live`](https://r-wasm.github.io/quarto-live/) or
[`quarto-pyodide`](https://quarto.thecoatlessprofessor.com/pyodide/). Unverified whether PLR imports
under Pyodide — `pyserial`, `usb`, and the visualizer websocket are the likely blockers, though the
chatterbox path may touch none of them. Worth a half-day spike; if it works, every recipe becomes
runnable from the page.
