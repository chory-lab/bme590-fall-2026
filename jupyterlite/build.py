"""Build the JupyterLite spike site.

Usage:
  python build.py [--out DIR] [--refresh-wheels]

The build environment (jupyterlite-core, anywidget, etc.) must already be
installed. On this Windows box it lives in a *short* venv at C:\\plrlite\\venv
-- NOT inside the repo -- because pip's jupyterlab-widgets ships deeply nested
static files that blow past Windows' 260-char MAX_PATH limit. See README.md.

On Linux (e.g. CI) the path limit does not exist, so the same layout works
with a venv anywhere.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import nbformat

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# The real workshops, browser-ready. Each is copied into content/workshops/
# with a bootstrap cell prepended.
WORKSHOPS = [REPO / "workshops" / p for p in
             ("00_plr_introduction.ipynb", "01_deck_setup.ipynb",
              "02_liquid_handling.ipynb", "03_moving_labware.ipynb",
              "04_modular_cloning.ipynb", "05_interfacing_with_peripherals.ipynb")]

# The notebooks are written against the repo layout: they reach their assets as
# `../figs/x.png` and `os.path.join(os.path.dirname(cwd), "data", "x.csv")`.
# Shipping them into content/workshops/ -- with data/ and figs/ as siblings, as
# in the repo -- makes both resolve verbatim in the kernel's virtual filesystem.
# Flattening them to the drive root is what previously forced two workarounds: a
# 7.8 KB dict literal of inlined CSVs in the bootstrap cell, and figure requests
# that 404 once before JupyterLab retries them under /files/.
WORKSHOP_SUBDIR = "workshops"

# Set by main() from --probe; see _make_probe.py.
_PROBE = False

_BOOTSTRAP = """\
# Browser bootstrap: install the package and swap the stock Visualizer for the
# bridge-backed one, so the workshop cells below run unmodified.
import piplite
await piplite.install("bme590-workshops==0.1.0")
from plr_workshops.jupyterlite_bridge import patch_visualizer
patch_visualizer()
"""

# The Pyodide kernel, as JupyterLite registers it. The repo notebooks carry the
# desktop kernelspec ("lab-automation"), which the browser cannot match -- so
# JupyterLab opens a modal asking the student to pick a kernel before they can
# run anything.
_BROWSER_KERNELSPEC = {
  "display_name": "Python (Pyodide)",
  "language": "python",
  "name": "python",
}


def python():
    """The interpreter to run JupyterLite with.

    Always the interpreter that invoked this script. CI provisions whatever
    host-side dependencies are needed; the build must not guess at local venv
    names. On Windows the caller is expected to run this from an environment
    with jupyterlite installed (see README for the short-path venv note).
    """
    return sys.executable


def _workshops() -> None:
    """Copy the real workshops into content/workshops/ with bootstraps prepended.

    ``content/`` is the config's ``content_files`` target (relative to the
    config's directory), which jupyterlite copies into the output. The build
    env's ``--contents`` points at the same directory. The tree mirrors the
    repo: ``workshops/`` beside ``data/`` and ``figs/``.
    """
    content = HERE / "content"
    # A stale content/ would keep serving notebooks at the old drive-root paths
    # alongside the new ones, so the file browser shows each workshop twice.
    if content.exists():
        shutil.rmtree(content)
    workshops = content / WORKSHOP_SUBDIR
    workshops.mkdir(parents=True, exist_ok=True)

    for src in WORKSHOPS:
        if not src.is_file():
            print(f"  (skip missing {src.name})")
            continue
        nb = nbformat.read(src, as_version=4)
        bootstrap = nbformat.v4.new_code_cell(_BOOTSTRAP)
        # Hidden by default: this is plumbing, not coursework. Students see the
        # workshop title first; the cell still runs, and the disclosure arrow
        # opens it for anyone who wants to read it.
        bootstrap.metadata["jupyter"] = {"source_hidden": True}
        bootstrap.metadata["tags"] = ["browser-bootstrap"]
        # The workshop's first cell is a markdown title; insert before it so the
        # bootstrap runs first.
        nb.cells.insert(0, bootstrap)
        _strip_outputs(nb)
        nb.metadata["kernelspec"] = dict(_BROWSER_KERNELSPEC)
        nbformat.write(nb, workshops / src.name)
        print(f"  workshop -> content/{WORKSHOP_SUBDIR}/{src.name} ({len(nb.cells)} cells)")

    # Siblings of workshops/, exactly as in the repo, so `../figs/x.png` and
    # `os.path.join(os.path.dirname(cwd), "data", "x.csv")` resolve unmodified.
    for name in ("figs", "data"):
        if (REPO / name).is_dir():
            shutil.copytree(REPO / name, content / name, dirs_exist_ok=True)
            print(f"  {name} -> content/{name}")

    # The synthetic bridge fixture. Small, known-good, and independent of the
    # workshops: when the real notebooks stop painting the deck, running this
    # one says immediately whether the bridge broke or the workshop did. It was
    # previously an untracked leftover in content/, so a clean rebuild lost it.
    subprocess.run([str(python()), str(HERE / "_make_deck.py")], cwd=HERE, check=True)

    # Execution probes. Diagnostic only, and off by default -- students should
    # not find a probe_00.ipynb next to their coursework.
    if _PROBE:
        subprocess.run([str(python()), str(HERE / "_make_probe.py")], cwd=HERE, check=True)


# Federated extensions the site cannot work without. A JupyterLite build does
# not fail, or even warn, when one of these is simply not installed in the build
# environment -- it produces a complete, healthy-looking site with a piece of
# the machinery quietly missing.
#
# That is not hypothetical: CI's dependency list omitted `anywidget`, so the
# deployed site had no anywidget labextension. The bridge widget *is* an
# anywidget, so it could not render, so it never posted __plrBridgeUp, so the
# parent page never flushed its event queue and the deck stayed blank. Kernel
# fine, deck fine, wire missing -- and every artifact check CI ran still passed.
REQUIRED_EXTENSIONS = {
    "@jupyterlite/pyodide-kernel-extension":  "the Python kernel",
    "@jupyter-widgets/jupyterlab-manager":    "ipywidgets rendering",
    "anywidget":                              "the deck bridge widget",
    "jupyter-iframe-commands":                "the host control channel",
}


def _check_extensions(out_dir: Path) -> None:
    """Fail the build if a load-bearing labextension did not make it in."""
    import json as _json

    config = _json.loads((out_dir / "jupyter-lite.json").read_text(encoding="utf-8"))
    built = {e["name"] for e in config["jupyter-config-data"].get("federated_extensions", [])}
    missing = {k: v for k, v in REQUIRED_EXTENSIONS.items() if k not in built}
    if missing:
        raise SystemExit(
            "federated extensions missing from the build:\n"
            + "".join(f"  {name}  ({why})\n" for name, why in missing.items())
            + "  Install the build environment from jupyterlite/requirements-build.txt."
        )
    print(f"  extensions OK: {len(built)} federated, all {len(REQUIRED_EXTENSIONS)} required present")


def _expose_app(out_dir: Path) -> None:
    """Set ``exposeAppInBrowser`` so a driver can read the notebook model.

    Without it there is no ``window.jupyterapp``, and the only way to see what
    a cell did is to scrape ``.jp-Cell-outputArea`` out of the DOM -- which
    lies, because JupyterLab windows the notebook and a cell below the fold has
    no output area at all. Printing from Python does not help either: the
    Pyodide kernel runs in a Web Worker, so ``js.console.log`` never reaches the
    page console a CDP driver is attached to.

    Diagnostic builds only. The student site should not hand a global handle on
    the whole application to any script on the page.
    """
    import json as _json

    path = out_dir / "jupyter-lite.json"
    config = _json.loads(path.read_text(encoding="utf-8"))
    config["jupyter-config-data"]["exposeAppInBrowser"] = True
    path.write_text(_json.dumps(config, indent=2), encoding="utf-8")
    print(f"  probe: exposeAppInBrowser -> {path.name}")


def _strip_outputs(nb) -> None:
    """Clear saved outputs and execution counts.

    Shipping outputs makes a *failed* run look successful: JupyterLite restores
    the notebook from IndexedDB on load, so stale `BOOTSTRAP_OK` text appears
    under cells that never executed -- which is exactly how a dead kernel went
    unnoticed. An empty notebook cannot lie about what it has run.
    """
    for cell in nb.cells:
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(HERE / "output"))
    parser.add_argument("--deploy", default=None,
                        help="Assemble a Pages-servable root here after building")
    parser.add_argument("--refresh-wheels", action="store_true",
                        help="Re-download wheels into pypi/ from PyPI")
    parser.add_argument("--probe", action="store_true",
                        help="Also ship probe_00.ipynb (execution probes; diagnostic)")
    args = parser.parse_args()

    global _PROBE
    _PROBE = args.probe

    if args.refresh_wheels:
        subprocess.run([sys.executable, "-c", _FETCH_WHEELS], cwd=HERE, check=True)

    # The browser wheel: build from the explicit KERNEL_MODULES list, never the
    # whole repo (stale pip caches keep resurrecting deleted files).
    _build_kernel_wheel()
    contents = _wheel_contents()
    expected = {"plr_workshops/" + m for m in KERNEL_MODULES}
    if set(contents) != expected:
        raise SystemExit(f"kernel wheel contents mismatch:\n  {sorted(contents)}")
    print(f"  kernel wheel: {sorted(contents)}")

    # The deck iframe document is built host-side (pylabrobot installed on this
    # machine), never inside the kernel. Generated, not committed.
    _build_deck()

    out_dir = Path(args.out)
    # A stale output/ causes doit task-target collisions on the piplite wheels
    # (post_init copy vs build copy share a target). Rebuild is cheap; start clean.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    _workshops()

    cmd = [
        str(python()), "-m", "jupyterlite", "build",
        "--output-dir", str(out_dir),
        "--config", str(HERE / "site" / "jupyter_lite_config.json"),
        "--contents", str(HERE / "content"),
        # No --piplite-wheels: jupyterlite auto-discovers wheels in the lite
        # dir's pypi/ (HERE/pypi). Passing the flag AND having pypi/ makes the
        # post_init and build copy tasks share a target and abort.
    ]
    print("running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"jupyterlite build failed: rc={proc.returncode}")
    print(f"\nbuilt -> {out_dir}")

    _check_extensions(out_dir)

    if _PROBE:
        _expose_app(out_dir)

    if args.deploy:
        _assemble_deploy(Path(args.deploy), out_dir)


def _assemble_deploy(deploy: Path, out_dir: Path) -> None:
    """Lay out a Pages-servable root: index.html (our page) beside the
    JupyterLite output, the deck page, and the host bridge.

    The result is a static directory a file server (or GitHub Pages) can serve
    directly; ``index.html`` is ``outer.html`` which iframes ``output/lab`` and
    ``deck.html`` and loads ``bridge.js``.
    """
    if deploy.exists():
        shutil.rmtree(deploy)
    deploy.mkdir(parents=True, exist_ok=True)

    shutil.copy2(HERE / "outer.html", deploy / "index.html")
    shutil.copy2(HERE / "bridge.js", deploy / "bridge.js")
    shutil.copy2(HERE / "deck.html", deploy / "deck.html")
    shutil.copytree(out_dir, deploy / "output")
    print(f"deploy root -> {deploy} (index.html + output/ + deck.html + bridge.js)")


def _build_deck() -> None:
    """Regenerate the deck iframe document in-process.

    Requires ``pylabrobot`` (for ``frontend.build_page``) importable in the
    interpreter that invoked this script, with ``plr_workshops/_vendored/``
    present (the pinned konva + shrunk logo, committed). This is a host-side
    artifact -- never inside the kernel.

    Failure is fatal: a deploy root containing a zero-byte deck.html is worse
    than no build, so a missing/empty deck aborts the build.
    """
    out = HERE / "deck.html"
    sys.path.insert(0, str(REPO))
    try:
        from plr_workshops.frontend import build_page

        html = build_page(name="Deck", chrome="deck")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"deck.html generation failed: {type(exc).__name__}: {exc}\n"
            "  The build interpreter needs pylabrobot and plr_workshops; the "
            "pinned visualizer assets must be in plr_workshops/_vendored/."
        ) from exc
    out.write_text(html, encoding="utf-8")
    if out.stat().st_size == 0:
        raise SystemExit("deck.html generated but is empty; aborting")
    print(f"  deck.html -> {out} ({out.stat().st_size:,} bytes)")


_FETCH_WHEELS = r"""
import json, urllib.request
from pathlib import Path
dest = Path("pypi")
dest.mkdir(exist_ok=True)
for project in ("anywidget", "traitlets"):
    with urllib.request.urlopen(f"https://pypi.org/pypi/{project}/json") as r:
        data = json.load(r)
    for entry in data["urls"]:
        if entry["packagetype"] == "bdist_wheel" and \
           entry["filename"].endswith("py3-none-any.whl"):
            body = urllib.request.urlopen(entry["url"]).read()
            (dest / entry["filename"]).write_bytes(body)
            print("saved", entry["filename"], len(body))
            break
"""

# The browser kernel imports exactly these modules of plr_workshops. Everything
# else in the repo package (frontend/vendor are host-side build tools; the old
# hand-rolled demo, the tests) is dead weight in the browser -- and a stale pip
# build silently re-includes deleted files. Build the kernel wheel from this
# explicit list so the browser installs only the glue.
KERNEL_MODULES = ("__init__.py", "transport.py", "inline.py", "jupyterlite_bridge.py")

# A browser-focused __init__: the repo one eagerly imports frontend +
# pyodide_transport (host-side), which the kernel does not need.
_KERNEL_INIT = '''"""bme590-workshops: the PyLabRobot browser glue.

Only what a JupyterLite kernel needs. Import submodules explicitly::

    from plr_workshops.inline import InlineVisualizer
    from plr_workshops.jupyterlite_bridge import patch_visualizer

This namespace stays importable with no side effects (no eager pylabrobot
import), which is what makes it safe in the browser.
"""

__version__ = "0.1.0"
'''


def _build_kernel_wheel() -> None:
    """Rebuild the browser wheel from KERNEL_MODULES into pypi/.

    Staging into a temp dir (not the repo) keeps the explicit module list honest
    and immune to stale pip caches.
    """
    import tempfile

    pypi = HERE / "pypi"
    pypi.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pkg = tmp / "plr_workshops"
        pkg.mkdir()
        for name in KERNEL_MODULES:
            src = REPO / "plr_workshops" / name
            if not src.is_file():
                raise SystemExit(f"kernel module missing: {src}")
            shutil.copy2(src, pkg / name)
        (pkg / "__init__.py").write_text(_KERNEL_INIT, encoding="utf-8")
        (tmp / "pyproject.toml").write_text(
            "[build-system]\n"
            'requires = ["setuptools>=68", "wheel"]\n'
            'build-backend = "setuptools.build_meta"\n'
            "\n"
            "[project]\n"
            'name = "bme590-workshops"\n'
            'version = "0.1.0"\n'
            'description = "PyLabRobot browser glue (JupyterLite kernel runtime)"\n'
            'requires-python = ">=3.11"\n'
            'dependencies = ["anywidget>=0.9", "pylabrobot==0.2.2"]\n'
            "\n"
            "[tool.setuptools]\n"
            'packages = ["plr_workshops"]\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            [str(python()), "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(pypi), str(tmp)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            raise SystemExit("kernel wheel build failed")
        print("  kernel wheel rebuilt -> pypi/")


def _wheel_contents() -> list:
    """Names inside the current kernel wheel (for build-time verification)."""
    import zipfile

    wheel = next((HERE / "pypi").glob("bme590_workshops-*.whl"))
    with zipfile.ZipFile(wheel) as z:
        return [n for n in z.namelist() if n.startswith("plr_workshops/")]


if __name__ == "__main__":
    main()
