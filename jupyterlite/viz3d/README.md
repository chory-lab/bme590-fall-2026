# viz3d: the 3D viewer on the hosted site

`viz3d.html` puts the [viz3d community demo](../../demos/viz3d/) next to PyLabRobot's 3D viewer, running entirely in the browser. It's published at `<site>/viz3d.html`.

| File | What it is |
|---|---|
| `viz3d.html` | The page: JupyterLite (`viz3d/demo.ipynb`) on the left, the viewer on the right. `?motion=2` doubles the playback speed. |
| `viz3d_shim.js` | Loaded ahead of the viewer's own scripts. It replaces `WebSocket` with a `BroadcastChannel` to the kernel. |
| `drive_viz3d.py` | The CI check: runs every cell in headless Chromium and gates on bootstrap, cells, bridge, motion and collisions. |

`build.py` assembles the rest from `demos/viz3d/uv.lock`, so the site, the desktop demo and its CI all run one pinned commit of the PR branch:

- It builds that commit's pylabrobot wheel (cached in `.cache/viz3d/<sha>/`) and a `viz3d-demo` wheel. Both go in `pypi/` and are gitignored.
- It copies `visualizer3D/static/` and every `.glb` out of the same wheel into `deploy/viz3d/viewer/`.
- The bootstrap labextension installs `viz3d-demo` for notebooks under `viz3d/` and `bme590-workshops` for everything else. The two pylabrobot versions never share a kernel.

## Why a BroadcastChannel and not the widget comm

JupyterLite hands a kernel its messages one at a time. A comm message from the page would wait until the running cell finished, and motion playback is a cell waiting for the page to say it has played each move, so that would deadlock. The kernel is a Pyodide worker on the page's origin, and while a cell awaits, the worker's event loop is free. A channel message is an event on that worker, so it arrives mid-cell the way a socket's would.

`viz3d_demo/bridge.py` has the kernel's half and the message shapes. `demos/viz3d/tests/test_bridge.py` runs the whole notebook through it against a fake page.

## Build and drive locally

```sh
python jupyterlite/build.py --probe --deploy deploy-test     # see ../README.md for the Windows venv
python -m http.server 8812 --directory deploy-test
python jupyterlite/viz3d/drive_viz3d.py --url http://127.0.0.1:8812/ --out viz3d-run
```
