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
C:\plrlite\venv\Scripts\python.exe -m pip install \
  "jupyterlite-core==0.8.1" "jupyterlite-pyodide-kernel" \
  anywidget sidecar jupyterlab-widgets ipywidgets jupyter-server
```

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

1. anywidget comms work in a JupyterLite (Pyodide **worker**) kernel — the
   `BridgeProbe` widget in `content/counter.ipynb` mounts and displays.
2. The widget's JS reaches the parent page: each `probe.ping(...)` call forwards
   a message to `outer.html`'s right panel. That is exactly the hop our deck
   iframe will consume.

Next milestone: replace the message panel with the real deck iframe
(`frontend.build_page()`) and swap `BridgeProbe` for `InlineVisualizer` +
`AnyWidgetTransport` forwarding to `parent`.
