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

# Seed PyLabRobot's Opentrons labware cache. Its loader fetches definitions
# from raw.githubusercontent.com on first use and caches them at /tmp/<name>.json;
# in Pyodide that fetch raises "RuntimeError: TLS not supported in this
# environment". Putting the files where it already looks means it never tries.
import shutil, os
for _name in %(ot_names)r:
    _dst = f"/tmp/{_name}.json"
    if not os.path.exists(_dst):
        shutil.copyfile(os.path.join(os.path.dirname(os.getcwd()), "otdefs", f"{_name}.json"), _dst)
"""

# Opentrons labware the workshops use. PyLabRobot pins this commit in
# resources/opentrons/load.py; keep them in step when upgrading pylabrobot.
_OT_DEFS = ("opentrons_96_tiprack_1000ul", "opentrons_96_tiprack_300ul")
_OT_COMMIT = "5b51a98ce736b2bb5aff780bf3fdf91941a038fa"

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
        # No bootstrap cell.
        #
        # Installing the wheel, patching the Visualizer and seeding the
        # Opentrons cache are all done by the plr-workshops:bootstrap
        # labextension, once per kernel id -- so it also survives Restart
        # Kernel, which a notebook cell never did.
        #
        # The cell had no good form. Visible, it was boilerplate above the title
        # of every workshop. Hidden, it became a one-line strip students scroll
        # past, and skipping it made every later cell fail with "No module named
        # pylabrobot", which reads as a broken site. Leaving it in *alongside*
        # the extension is worse still: two concurrent piplite.install() calls
        # in one kernel.
        _strip_desktop_sections(nb, src.name)
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

    _opentrons_defs(content / "otdefs")

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
    "plr-workshops-bootstrap":                "per-kernel workshop setup",
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


def _build_bootstrap_extension() -> Path:
    """Build the plr-workshops:bootstrap labextension; return its output folder.

    The extension prepares each Pyodide kernel (installs the wheel, patches the
    Visualizer, seeds the Opentrons cache) so the workshop notebooks carry no
    environment-management code at all.

    Built here rather than committed so the JupyterLab versions it shares
    singletons with cannot drift from the ones the site ships. That drift is
    not a hypothetical -- an extension built against 4.6.3 against an app
    serving 4.6.0 fails to activate with nothing but a console warning.
    """
    ext = HERE / "bootstrap-extension"
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise SystemExit("npm is required to build the bootstrap extension")

    if not (ext / "node_modules").is_dir():
        subprocess.run([npm, "install"], cwd=ext, check=True)

    # `npm run build` calls `jupyter labextension`, which lives beside the
    # interpreter running this script -- not necessarily on PATH. Without this
    # the build fails with "Jupyter command `jupyter-labextension` not found"
    # even though jupyterlab is installed in the very environment invoking it.
    import os as _os

    env = dict(_os.environ)
    scripts = str(Path(sys.executable).parent)
    env["PATH"] = scripts + _os.pathsep + env.get("PATH", "")
    subprocess.run([npm, "run", "build"], cwd=ext, check=True, env=env)

    built = ext / "labextension"
    if not (built / "package.json").is_file():
        raise SystemExit(f"bootstrap extension build produced nothing at {built}")

    # jupyterlite's federated_extensions accepts a folder directly
    # (copy_one_folder_extension); it rejects .tgz, so do not pack one.
    for stale in ext.glob("*.tgz"):
        stale.unlink()
    print(f"  bootstrap extension -> {built}")
    return built


def _opentrons_defs(dest: Path) -> None:
    """Fetch the Opentrons labware definitions the workshops use, at build time.

    Cached under .vendor-cache/ so repeat builds -- and CI with a warm cache --
    do no network at all, matching how the rest of the vendored assets work.
    """
    import urllib.request

    cache = REPO / ".vendor-cache" / "otdefs"
    cache.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)

    for name in _OT_DEFS:
        cached = cache / f"{name}.json"
        if not cached.is_file():
            url = ("https://raw.githubusercontent.com/Opentrons/opentrons/"
                   f"{_OT_COMMIT}/shared-data/labware/definitions/2/{name}/1.json")
            with urllib.request.urlopen(url) as response:
                cached.write_bytes(response.read())
            print(f"  fetched {name}.json")
        shutil.copyfile(cached, dest / f"{name}.json")
    print(f"  otdefs -> {dest.relative_to(dest.parent.parent)} ({len(_OT_DEFS)} definitions)")


# Sections that only make sense on a desktop install, stripped from the browser
# build. The site *is* the environment here: telling a student to run the
# notebook locally in VS Code, or to paste an extraPaths hack into settings.json
# for an interpreter they do not have, is at best noise and at worst sends them
# off to fix a machine that is working.
#
# Matched on marker text and fail-loud: if a heading is reworded, the build stops
# rather than quietly shipping installation instructions to the browser.
_DESKTOP_CELLS = (
    "### Getting Started",                              # PLR installation prose
    "#### Auto-complete / Pylance Missing Imports Issue",
    '"python.analysis.extraPaths"',                     # the settings.json cell
)

# (cell marker, cut everything before this) -- for cells that mix desktop-only
# advice with content worth keeping.
_DESKTOP_TRIMS = (("### Usage Note", "### Welcome to PyLabRobot!"),)


def _strip_desktop_sections(nb, name: str) -> None:
    """Drop desktop-install sections from a notebook destined for the browser."""
    kept, dropped = [], 0
    for cell in nb.cells:
        source = "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
        if any(marker in source for marker in _DESKTOP_CELLS):
            dropped += 1
            continue
        for marker, keep_from in _DESKTOP_TRIMS:
            if marker in source and keep_from in source:
                cell["source"] = source[source.index(keep_from):]
                dropped += 1
        kept.append(cell)
    nb.cells = kept

    if name.startswith("00_") and dropped < len(_DESKTOP_CELLS) + len(_DESKTOP_TRIMS):
        raise SystemExit(
            f"{name}: expected to strip "
            f"{len(_DESKTOP_CELLS) + len(_DESKTOP_TRIMS)} desktop sections, stripped "
            f"{dropped}. The headings in _DESKTOP_CELLS/_DESKTOP_TRIMS have moved; "
            "update them rather than shipping install instructions to the browser."
        )
    if dropped:
        print(f"    stripped {dropped} desktop-only section(s)")


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
    # Modules plus the Opentrons definitions the bootstrap seeds. Both halves are
    # asserted: a wheel missing otdefs/ builds and installs perfectly well, then
    # fails at runtime inside a silent bootstrap. That shipped once already, and
    # the only reason it surfaced is that the extension reports
    # PLR_BOOTSTRAP_FAILED out to the page.
    expected = {"plr_workshops/" + m for m in KERNEL_MODULES}
    expected |= {f"plr_workshops/otdefs/{name}.json" for name in _OT_DEFS}
    if set(contents) != expected:
        raise SystemExit(
            "kernel wheel contents mismatch:\n"
            f"  missing: {sorted(expected - set(contents))}\n"
            f"  unexpected: {sorted(set(contents) - expected)}"
        )
    print(f"  kernel wheel: {len(contents)} entries incl. {len(_OT_DEFS)} otdefs")

    # The deck iframe document is built host-side (pylabrobot installed on this
    # machine), never inside the kernel. Generated, not committed.
    _build_deck()

    out_dir = Path(args.out)
    # A stale output/ causes doit task-target collisions on the piplite wheels
    # (post_init copy vs build copy share a target). Rebuild is cheap; start clean.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    _workshops()

    bootstrap_ext = _build_bootstrap_extension()

    cmd = [
        str(python()), "-m", "jupyterlite", "build",
        "--output-dir", str(out_dir),
        "--config", str(HERE / "site" / "jupyter_lite_config.json"),
        "--contents", str(HERE / "content"),
        f"--LiteBuildConfig.federated_extensions={bootstrap_ext}",
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
KERNEL_MODULES = ("__init__.py", "transport.py", "inline.py", "jupyterlite_bridge.py",
                  "jupyterlite_bootstrap.py")

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

        # Opentrons definitions travel inside the wheel, so the bootstrap reads
        # them through importlib.resources instead of guessing at the notebook's
        # working directory.
        otdefs = pkg / "otdefs"
        _opentrons_defs(otdefs)
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
            'packages = ["plr_workshops"]\n'
            "include-package-data = true\n"
            "\n"
            "[tool.setuptools.package-data]\n"
            'plr_workshops = ["otdefs/*.json"]\n',
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
