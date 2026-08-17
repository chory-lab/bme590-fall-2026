# JupyterLite spike (hosted demo plan of record)

Proof that the hosted site can be a real JupyterLab in the browser — JupyterLite —
with the PyLabRobot deck in a **sibling div**, driven by anywidget comms that hop
up to the parent page via `postMessage`. See `plr-workshops-architecture.md` §4 for
the full reasoning (why JupyterLite, revised 2026-08-16).

## Layout

| Path | What |
|---|---|
| `site/jupyter_lite_config.json` | JupyterLite build config |
| `content/` | Notebooks the site ships (starts with `counter.ipynb`, the bridge proof) |
| `pypi/` | Wheels pre-indexed for piplite (offline install: anywidget, traitlets) |
| `outer.html` | Our page: JupyterLite iframe (left) + a message panel (right) |
| `drive.cjs` | Headless Chrome/CDP driver: boots the page, runs cells, asserts bridge |
| `build.py` | Reproducible `jupyterlite build` |
| `output/` | **Generated.** JupyterLite site; gitignored |

## The long-path constraint (Windows only)

`jupyterlab-widgets` ships static files with very deep paths. pip refuses to write
them anywhere that exceeds Windows' 260-char `MAX_PATH`. The venv therefore lives
in a **short root, outside the repo**: `C:\plrlite\venv`. `build.py` knows about
it. Linux (CI) has no such limit; `build.py` falls back to `python` on PATH.

Set up the venv once:

```
py -3.13 -m venv C:\plrlite\venv
C:\plrlite\venv\Scripts\python.exe -m pip install -r jupyterlite\requirements-build.txt
```

**Install from `requirements-build.txt`, never by naming packages ad hoc.** The
`jupyterlite-pyodide-kernel` pin is load-bearing: unpinned, pip resolves 0.8.3,
which is built against JupyterLab 4.6.1 while `jupyterlite-core==0.8.1` ships
4.6.0. The federation runtime then declines to load the kernel extension — with
nothing but a console *warning* — and the built site registers **zero kernels**.
It looks completely normal until you try to run a cell. The file has the full
story.

Build + serve + drive:

```
python jupyterlite/build.py --refresh-wheels        # from repo root
C:\plrlite\venv\Scripts\python.exe -m http.server 8812 --directory C:\plrlite
node jupyterlite/drive.cjs                          # needs server on 8812
```

`drive.cjs` hardcodes the server URL + output path under `C:\plrlite`; adjust if
you move the build output. (The repo copy of `drive.cjs` is the source of truth;
`C:\plrlite\drive.cjs` is a scratch copy for iterating.)

## What the spike proves

All of it, end-to-end in a headless Chrome (`drive.cjs`):

1. Python executes in a JupyterLite (Pyodide worker) kernel.
2. `piplite.install("bme590-workshops==0.1.0")` resolves hermetically — the
   package's metadata is now the browser-truthful set (`anywidget`,
   `pylabrobot==0.2.2`), so no `deps=False`; numpy/pandas/pillow ship in
   Pyodide's own lockfile.
3. `JupyterLiteBridgeTransport` mounts and forwards every event to the parent.
4. The deck iframe renders the protocol: **16 events acked `success:true`,
   754 Konva shapes** (STARLet deck, 96-tip rack, head state, volumes).

The two channels: `jupyter-iframe-commands` drives `notebook:run-all-cells`
(control), and the bridge widget's `postMessage` carries the visualizer events
(app). The parent owns a ready queue so no timing race.

`deck.ipynb` is the synthetic protocol used to prove the bridge; the real
workshops are the next milestone (their `time.sleep()`s must become
`await asyncio.sleep()` first).
