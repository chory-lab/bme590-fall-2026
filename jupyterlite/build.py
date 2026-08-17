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

# The real workshops, browser-ready. Each is copied into content/ with a
# bootstrap cell prepended; data/ and figs/ ship alongside so `../data` and
# `../figs` resolve in the kernel's virtual filesystem.
WORKSHOPS = [REPO / "workshops" / p for p in
             ("00_plr_introduction.ipynb", "01_deck_setup.ipynb",
              "02_liquid_handling.ipynb", "03_moving_labware.ipynb",
              "04_modular_cloning.ipynb", "05_interfacing_with_peripherals.ipynb")]

_BOOTSTRAP = """\
# Browser bootstrap: install the package and swap the stock Visualizer for the
# bridge-backed one, so the workshop cells below run unmodified.
import piplite
await piplite.install("bme590-workshops==0.1.0")
from plr_workshops.jupyterlite_bridge import patch_visualizer
patch_visualizer()
print("BOOTSTRAP_OK")
"""

_DATA_BOOTSTRAP = """\
# Mount ../data (workshop CSVs) into the kernel's virtual filesystem so
# `os.path.join(os.path.dirname(cwd), "data", ...)` resolves.
import os, json
_DATA = %s
_cwd = os.getcwd()
for _rel, _text in _DATA.items():
    _p = os.path.join(_cwd, "..", "data", _rel)
    os.makedirs(os.path.dirname(_p), exist_ok=True)
    with open(_p, "w", encoding="utf-8") as _fh:
        _fh.write(_text)
print("DATA_OK")
"""


def python():
    """The interpreter to run JupyterLite with.

    Always the interpreter that invoked this script. CI provisions whatever
    host-side dependencies are needed; the build must not guess at local venv
    names. On Windows the caller is expected to run this from an environment
    with jupyterlite installed (see README for the short-path venv note).
    """
    return sys.executable


def _workshops() -> None:
    """Copy the real workshops into content/ with browser bootstraps prepended.

    ``content/`` is the config's ``content_files`` target (relative to the
    config's directory), which jupyterlite copies into the output. The build
    env's ``--contents`` points at the same directory.
    """
    content = HERE / "content"
    content.mkdir(parents=True, exist_ok=True)

    data_files = {
        p.name: p.read_text(encoding="utf-8")
        for p in (REPO / "data").glob("*.csv")
    }
    data_bootstrap = (
        _DATA_BOOTSTRAP % repr(data_files)
        if data_files else ""
    )

    for src in WORKSHOPS:
        if not src.is_file():
            print(f"  (skip missing {src.name})")
            continue
        nb = nbformat.read(src, as_version=4)
        bootstrap = nbformat.v4.new_code_cell(_BOOTSTRAP)
        if data_files:
            bootstrap.source += "\n" + data_bootstrap
        # The workshop's first cell is a markdown title; insert before it so the
        # bootstrap runs first.
        nb.cells.insert(0, bootstrap)
        nbformat.write(nb, content / src.name)
        print(f"  workshop -> content/{src.name} ({len(nb.cells)} cells)")
    # figs referenced by markdown; ship so relative refs resolve.
    if (REPO / "figs").is_dir():
        shutil.copytree(REPO / "figs", content / "figs", dirs_exist_ok=True)
        print(f"  figs -> content/figs")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(HERE / "output"))
    parser.add_argument("--deploy", default=None,
                        help="Assemble a Pages-servable root here after building")
    parser.add_argument("--refresh-wheels", action="store_true",
                        help="Re-download wheels into pypi/ from PyPI")
    args = parser.parse_args()

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
