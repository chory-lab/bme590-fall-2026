# The PyLabRobot Cookbook — authoring guide

Quarto book. Chapter list lives in `_quarto.yml`; the per-chapter build spec is `SPEC.md`.
The book targets **PyLabRobot 0.2.2**; every API name is verified against the pinned install.

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

## Writing

Style, voice, and the recipe format: `SPEC.md`.

Every recipe is registered in `recipes.yml`. `path` must match the `{#anchor}` on the heading;
`apis` is free text so the listing's filter box matches on API names.

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
