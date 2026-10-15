"""`uv run viz3d <command>`: set up, check, open, and keep the demo current with its PRs.

The demo runs against two unmerged PRs, so its environment has one moving part: which commit of
the PR branch it is pinned to. uv.lock holds the pin; `status` says how far it is behind the PRs
(and whether they have merged), `bump` moves it and proves the demo still runs on the new commit.

  setup     install the environment, register a Jupyter kernel, optionally fetch Chromium
  doctor    check everything a live demo needs, and say how to fix what is missing
  open      open the notebook (VS Code if it is installed, JupyterLab otherwise)
  check     run the demo end to end without a page; --browser adds the real-browser run
  status    the pinned pylabrobot commit against the PRs' heads
  bump      move the pin to the PR branch's newest commit (or --main once the PRs merge)
  strip     clear the notebook's outputs, as CI requires before a commit
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "demo.ipynb"
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "uv.lock"

UPSTREAM = "PyLabRobot/pylabrobot"
# Motion playback, then collision detection, which is stacked on it.
PRS = (1468, 1470)
KERNEL_NAME = "viz3d-demo"
# The viewer's default static and websocket ports; it moves up past taken ones, but a demo is
# smoother on the ports people expect.
PORTS = (1338, 2122)
# What the PRs add, importable only from a pylabrobot that carries them.
PR_MODULES = (
  "pylabrobot.hamilton.star.motion",
  "pylabrobot.resources.collision",
  "pylabrobot.hamilton.star.driver.features.star_collisions",
  "pylabrobot.hamilton.star.driver.features.iswap_transport",
)


# -- helpers --------------------------------------------------------------------------------------


def _uv() -> str:
  """uv itself: `uv run` says where it is in $UV, and otherwise it is on the path."""
  found = os.environ.get("UV") or shutil.which("uv")
  if not found:
    sys.exit("uv is not installed: see https://docs.astral.sh/uv/getting-started/installation/")
  return found


def _run(*args: str, check: bool = True) -> int:
  print("$", " ".join(Path(args[0]).name if i == 0 else a for i, a in enumerate(args)), flush=True)
  code = subprocess.call(list(args), cwd=ROOT)
  if check and code != 0:
    sys.exit(code)
  return code


def _pinned() -> tuple[str, str] | None:
  """The locked pylabrobot as (source url, commit), or None when it is not from git."""
  lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
  for package in lock.get("package", []):
    if package["name"] != "pylabrobot":
      continue
    git = package.get("source", {}).get("git")
    if not git:
      return None
    url, _, commit = git.partition("#")
    return url, commit
  return None


def _github(path: str) -> dict:
  request = urllib.request.Request(f"https://api.github.com/{path}")
  request.add_header("Accept", "application/vnd.github+json")
  token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
  if token:
    request.add_header("Authorization", f"Bearer {token}")
  with urllib.request.urlopen(request, timeout=20) as response:
    return json.loads(response.read())


def _set_source(line: str) -> None:
  """Point [tool.uv.sources] pylabrobot somewhere else, keeping the rest of pyproject as written."""
  text = PYPROJECT.read_text(encoding="utf-8")
  lines = text.splitlines(keepends=True)
  for i, current in enumerate(lines):
    if current.startswith("pylabrobot = {"):
      lines[i] = line + "\n"
      break
  else:
    sys.exit("pyproject.toml has no [tool.uv.sources] entry for pylabrobot")
  PYPROJECT.write_text("".join(lines), encoding="utf-8")


def _port_free(port: int) -> bool:
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    return s.connect_ex(("127.0.0.1", port)) != 0


def _chromium() -> str | None:
  try:
    from playwright.sync_api import sync_playwright
  except ImportError:
    return None
  try:
    with sync_playwright() as p:
      path = p.chromium.executable_path
  except Exception:
    return None
  return path if path and Path(path).exists() else None


# -- commands -------------------------------------------------------------------------------------


def setup(args: argparse.Namespace) -> None:
  groups = ["--group", "notebook"]
  if args.lab:
    groups += ["--group", "lab"]
  if args.dev or args.browser:
    groups += ["--group", "dev"]
  _run(_uv(), "sync", "--locked", *groups)
  python = str(ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
  _run(
    python,
    "-m",
    "ipykernel",
    "install",
    "--user",
    "--name",
    KERNEL_NAME,
    "--display-name",
    "Python (viz3d demo)",
  )
  if args.browser:
    _run(python, "-m", "playwright", "install", "chromium")
  print("\nready: `uv run viz3d open` to start the demo")


def doctor(_: argparse.Namespace) -> None:
  import importlib

  problems = 0

  def report(ok: bool, what: str, fix: str = "") -> None:
    nonlocal problems
    print(f"  {'ok ' if ok else 'FAIL'}  {what}" + ("" if ok else f"\n        -> {fix}"))
    problems += not ok

  print("viz3d doctor")
  report(sys.version_info >= (3, 11), f"python {sys.version.split()[0]}", "use Python 3.11+")
  pinned = _pinned()
  report(
    pinned is not None,
    f"pylabrobot pinned to {pinned[1][:10] if pinned else '?'}",
    "uv.lock does not pin pylabrobot from git: run `uv run viz3d bump`",
  )
  for module in PR_MODULES:
    try:
      importlib.import_module(module)
      report(True, f"import {module}")
    except Exception as error:  # an import that fails for any reason fails the demo
      report(False, f"import {module}: {error}", "run `uv run viz3d setup`")
  try:
    from jupyter_client.kernelspec import KernelSpecManager

    kernels = KernelSpecManager().find_kernel_specs()
    report(KERNEL_NAME in kernels, f"jupyter kernel '{KERNEL_NAME}'", "run `uv run viz3d setup`")
  except ImportError:
    report(False, "jupyter_client", "run `uv run viz3d setup`")
  for port in PORTS:
    report(
      _port_free(port),
      f"port {port} free",
      "another viewer is running: restart its kernel (or the viewer takes the next port)",
    )
  editor = shutil.which("code")
  print(f"  info  editor: {'VS Code' if editor else 'none found, `open` will use JupyterLab'}")
  print(f"  info  chromium for `check --browser`: {_chromium() or 'not installed'}")
  if problems:
    sys.exit(f"\n{problems} problem(s)")
  print("\nall good")


def open_(args: argparse.Namespace) -> None:
  code = shutil.which("code")
  if code and not args.lab:
    _run(code, str(ROOT), str(NOTEBOOK))
    return
  _run(_uv(), "sync", "--locked", "--group", "notebook", "--group", "lab")
  _run(_uv(), "run", "--group", "lab", "jupyter", "lab", str(NOTEBOOK))


def check(args: argparse.Namespace) -> None:
  marker = [] if args.browser else ["-m", "not browser"]
  _run(_uv(), "run", "--group", "dev", "pytest", *marker, *args.pytest_args)


def status(_: argparse.Namespace) -> str | None:
  """Print where the pin stands; returns the PR branch's newest commit, when there is a PR open."""
  pinned = _pinned()
  print(f"pinned: {pinned[0]} @ {pinned[1][:10]}" if pinned else "pinned: not from git")
  head: str | None = None
  try:
    for number in PRS:
      pr = _github(f"repos/{UPSTREAM}/pulls/{number}")
      state = "merged" if pr.get("merged_at") else pr["state"]
      sha = pr["head"]["sha"]
      print(f"  #{number} {state:6} {pr['head']['label']} @ {sha[:10]}  {pr['title']}")
      head = sha if state == "open" else head
  except (urllib.error.URLError, KeyError) as error:
    print(f"  could not reach GitHub: {error}")
    return None
  if pinned and head:
    print("up to date" if pinned[1] == head else "behind: `uv run viz3d bump` to move the pin")
  elif not head:
    print("the PRs are closed: `uv run viz3d bump --main` to run against pylabrobot main")
  return head


def bump(args: argparse.Namespace) -> None:
  before = _pinned()
  if args.main:
    _set_source(f'pylabrobot = {{ git = "https://github.com/{UPSTREAM}", branch = "main" }}')
  else:
    # Wherever the PR's head lives now: a PR can be moved to another branch or fork.
    pr = _github(f"repos/{UPSTREAM}/pulls/{PRS[-1]}")
    if pr.get("merged_at") or pr["state"] != "open":
      sys.exit(f"#{PRS[-1]} is {pr['state']}: `uv run viz3d bump --main` to follow main")
    repo = pr["head"]["repo"]["html_url"]
    if args.rev:
      _set_source(f'pylabrobot = {{ git = "{repo}", rev = "{args.rev}" }}')
    else:
      _set_source(f'pylabrobot = {{ git = "{repo}", branch = "{pr["head"]["ref"]}" }}')
  _run(_uv(), "lock", "--upgrade-package", "pylabrobot")
  after = _pinned()
  old, new = (p[1][:10] if p else "?" for p in (before, after))
  if before == after:
    print(f"pylabrobot already at the newest commit ({new})")
    return
  print(f"pylabrobot {old} -> {new}")
  _run(_uv(), "sync", "--locked", "--all-groups")
  if not args.no_check:
    check(argparse.Namespace(browser=args.browser, pytest_args=[]))


def strip(_: argparse.Namespace) -> None:
  import nbformat

  nb = nbformat.read(NOTEBOOK, as_version=4)
  for cell in nb.cells:
    if cell.cell_type == "code":
      cell.outputs, cell.execution_count = [], None
    cell.metadata.pop("execution", None)
  nbformat.write(nb, NOTEBOOK)
  print(f"stripped {NOTEBOOK.name}")


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(prog="viz3d", description=__doc__.split("\n")[0])
  sub = parser.add_subparsers(dest="command", required=True)

  p = sub.add_parser("setup", help="install the environment and register the kernel")
  p.add_argument("--lab", action="store_true", help="also install JupyterLab")
  p.add_argument("--dev", action="store_true", help="also install the test tools")
  p.add_argument("--browser", action="store_true", help="also fetch Chromium for browser checks")
  p.set_defaults(func=setup)

  sub.add_parser("doctor", help="check a live demo will work").set_defaults(func=doctor)

  p = sub.add_parser("open", help="open the notebook")
  p.add_argument("--lab", action="store_true", help="JupyterLab even when VS Code is installed")
  p.set_defaults(func=open_)

  p = sub.add_parser("check", help="run the demo end to end")
  p.add_argument("--browser", action="store_true", help="also run it with a real page watching")
  p.add_argument("pytest_args", nargs="*", help="passed on to pytest")
  p.set_defaults(func=check)

  sub.add_parser("status", help="the pin against the PRs").set_defaults(func=status)

  p = sub.add_parser("bump", help="move the pin to the PRs' newest commit")
  where = p.add_mutually_exclusive_group()
  where.add_argument("--rev", help="pin this commit of the PR branch instead of its newest")
  where.add_argument("--main", action="store_true", help="track pylabrobot main (PRs merged)")
  p.add_argument("--browser", action="store_true", help="include the real-browser check")
  p.add_argument("--no-check", action="store_true", help="skip running the demo afterwards")
  p.set_defaults(func=bump)

  sub.add_parser("strip", help="clear the notebook's outputs").set_defaults(func=strip)

  args = parser.parse_args(argv)
  args.func(args)


if __name__ == "__main__":
  main()
