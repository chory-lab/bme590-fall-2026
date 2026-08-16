"""The ``plr-workshops`` command: one-command JupyterLab for the workshops.

Copies the workshops (and their ``../figs`` / ``../data`` dependencies, which
must stay in the same relative layout) into a fresh workspace, installs an
IPython startup hook there so the stock ``Visualizer`` renders inline in a
docked sidecar, and launches JupyterLab pointed at that workspace.

Run ``plr-workshops --help`` for options.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .startup import HOOK_SNIPPET

DEFAULT_PORT = 8888

# Paths that must exist next to the workshops so their relative refs resolve.
_ASSET_DIRS = ("workshops", "data", "figs")


def _package_root() -> Path:
  return Path(__file__).resolve().parent


def _repo_root() -> Path:
  """The checkout containing workshops/ next to the package, if any."""
  for candidate in (_package_root().parent, _package_root().parent.parent):
    if (candidate / "workshops").is_dir() and (candidate / "data").is_dir():
      return candidate
  return None


def _find_assets() -> Path:
  """Locate the directory holding workshops/, data/, figs/.

  Order: the environment variable, a repo checkout (package sits beside the
  assets), then the data-files install location. Raises if none resolve.
  """
  env = os.environ.get("PLR_WORKSHOPS_ASSETS")
  if env:
    return Path(env)

  repo = _repo_root()
  if repo is not None:
    return repo

  for prefix in (sys.prefix, sys.base_prefix):
    candidate = Path(prefix) / "share" / "bme590-workshops"
    if (candidate / "workshops").is_dir():
      return candidate

  raise FileNotFoundError(
    "Could not locate the workshop assets. If you are running from the repo "
    "checkout, keep the package next to the workshops/ directory; if "
    "installed, reinstall bme590-workshops so the data files are included."
  )


def _check_deps():
  missing = []
  for module in ("jupyterlab", "anywidget", "sidecar", "pylabrobot"):
    try:
      __import__(module)
    except ImportError:
      missing.append(module)
  if missing:
    sys.stderr.write(
      "Missing dependencies: {}. Install them with:\n"
      "  pip install bme590-workshops\n".format(", ".join(missing))
    )
    sys.exit(2)


def _prepare_workspace(assets: Path, workspace: Path, force: bool):
  workspace.mkdir(parents=True, exist_ok=True)

  if force:
    for name in _ASSET_DIRS:
      shutil.rmtree(workspace / name, ignore_errors=True)

  missing = []
  for name in _ASSET_DIRS:
    src = assets / name
    dst = workspace / name
    if dst.is_dir():
      continue
    if not src.is_dir():
      missing.append(str(src))
      continue
    shutil.copytree(src, dst)

  if missing:
    sys.stderr.write("Missing asset directories:\n  " + "\n  ".join(missing) + "\n")
    sys.exit(2)

  # Startup hook: kernels launched from this server inherit IPYTHONDIR, so the
  # stock Visualizer is swapped for the inline docked widget automatically.
  # The file must NOT be named plr_workshops.py: IPython imports startup files
  # as modules by basename, which would shadow the plr_workshops package.
  ipython_dir = workspace / ".ipython"
  startup_dir = ipython_dir / "profile_default" / "startup"
  startup_dir.mkdir(parents=True, exist_ok=True)
  hook = startup_dir / "zz_plr_inline.py"
  hook.write_text(HOOK_SNIPPET, encoding="utf-8")

  return workspace, ipython_dir


def _launch(workspace: Path, ipython_dir: Path, port: int, no_browser: bool):
  env = dict(os.environ)
  env["IPYTHONDIR"] = str(ipython_dir)

  # Kernels launched by this server inherit PYTHONPATH, and the startup hook
  # imports plr_workshops. When running from a checkout (not pip-installed),
  # that package is only importable if its parent is on the path.
  pkg_root = _package_root()
  existing = env.get("PYTHONPATH", "")
  env["PYTHONPATH"] = os.pathsep.join([p for p in (str(pkg_root.parent), existing) if p])

  cmd = [
    sys.executable,
    "-m",
    "jupyter",
    "lab",
    "--notebook-dir",
    str(workspace),
    f"--port={port}",
  ]
  if no_browser:
    cmd.append("--no-browser")

  print(f"Launching JupyterLab for the workshops...\n  workspace: {workspace}")
  if no_browser:
    print(f"  open http://localhost:{port} in your browser")

  try:
    subprocess.run(cmd, env=env, check=True)
  except FileNotFoundError:
    sys.stderr.write("jupyter lab was not found on PATH.\n")
    sys.exit(2)


def main(argv=None):
  parser = argparse.ArgumentParser(
    prog="plr-workshops",
    description="Launch a JupyterLab preconfigured for the BME 590 workshops.",
  )
  parser.add_argument(
    "--workspace",
    "-w",
    default="plr-workshops",
    help="Directory to prepare and launch in (default: ./plr-workshops).",
  )
  parser.add_argument(
    "--port",
    type=int,
    default=DEFAULT_PORT,
    help=f"JupyterLab port (default: {DEFAULT_PORT}).",
  )
  parser.add_argument(
    "--no-browser",
    action="store_true",
    help="Start the server but do not open a browser.",
  )
  parser.add_argument(
    "--force",
    action="store_true",
    help="Re-copy workshops/, data/, and figs/ even if present.",
  )
  parser.add_argument(
    "--assets",
    help="Override where the workshop assets are found.",
  )
  args = parser.parse_args(argv)

  if args.assets:
    os.environ["PLR_WORKSHOPS_ASSETS"] = args.assets

  _check_deps()
  assets = _find_assets()
  workspace = Path(args.workspace).resolve()
  workspace, ipython_dir = _prepare_workspace(assets, workspace, args.force)
  _launch(workspace, ipython_dir, args.port, args.no_browser)


if __name__ == "__main__":
  main()
