# PyLabRobot in 3D: motion playback and collision detection

A short community demo of two open PyLabRobot pull requests, run on a simulated Hamilton STARlet:

- [#1468](https://github.com/PyLabRobot/pylabrobot/pull/1468) adds **motion playback**: each firmware command is played in the 3D viewer with measured motion profiles.
- [#1470](https://github.com/PyLabRobot/pylabrobot/pull/1470) adds **collision detection**: channel, 96-head and iSWAP moves are swept against the deck before they are sent, and a move that would hit something raises `CollisionError` instead of reaching the device.

[`demo.ipynb`](demo.ipynb) covers both in five short sections: pipetting, a channel crash that never happens, an iSWAP plate move, a packed deck that refuses the move, and the fix. It also runs in the browser on the [course's hosted site](https://chory-lab.github.io/bme590-fall-2026/), with nothing to install.

## Run it locally

```sh
./install.sh          # macOS / Linux
.\install.ps1         # Windows
uv run viz3d open     # opens the notebook (VS Code, or JupyterLab with --lab)
```

The installers only install [uv](https://docs.astral.sh/uv/) if it is missing, then run `uv run viz3d setup`. Run the cells in order with the viewer tab beside the notebook. Add `?motion=2` to the viewer's address to double the playback speed.

This project is separate from the course environment one level up. That one pins `pylabrobot==0.2.2`; this one pins the PR branch.

## `uv run viz3d`

| Command | What it does |
|---|---|
| `setup [--lab] [--dev] [--browser]` | `uv sync --locked`, register the `viz3d-demo` Jupyter kernel, optionally fetch Chromium |
| `doctor` | check the PR modules import, the kernel is registered and the viewer's ports are free |
| `open [--lab]` | open the notebook |
| `check [--browser]` | run the notebook end to end with no page; `--browser` also drives it in headless Chromium |
| `status` | compare the pinned pylabrobot commit with both PRs' heads, and show whether they have merged |
| `bump [--rev SHA \| --main]` | move the pin to the PR branch's newest commit (or a given one, or `main` after merge), then re-run `check` |
| `strip` | clear the notebook's outputs; CI rejects a committed notebook with outputs |

## CI

`.github/workflows/viz3d-demo.yml` runs on every change under `demos/viz3d/`:

- **lint**: ruff check and format, plus a check that the committed notebook has no outputs.
- **notebook**: runs the notebook headless on Linux, macOS and Windows. The collision gates don't need a page, so every refusal is checked here.
- **browser**: runs the notebook while headless Chromium watches the page. It asserts that every motion was played (`motion_done` for every `motion`) and that every refusal was drawn, then uploads screenshots of the red overlays as artifacts.
- **upstream** (nightly): runs `viz3d bump` against the PR branch's newest commit and repeats the checks. A red nightly means the PRs moved in a way that breaks the demo.
- **bridge**: `tests/test_bridge.py` runs every cell of the notebook through the hosted site's transport (`viz3d_demo/bridge.py`), with a fake page answering the way the browser shim does.

The hosted page is built and tested by `.github/workflows/workshops-site.yml`, which deploys on pushes to `main`. Its `viz3d page integration test` step runs the notebook in headless Chromium on the built site, and a commit that changes `demo.ipynb`, `uv.lock` or `src/` redeploys it. See [`jupyterlite/viz3d/README.md`](../../jupyterlite/viz3d/README.md) for how the viewer runs without a server.
