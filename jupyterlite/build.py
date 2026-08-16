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

HERE = Path(__file__).resolve().parent
DEFAULT_VENV = Path(r"C:\plrlite\venv") if sys.platform == "win32" else None


def python():
    if DEFAULT_VENV and DEFAULT_VENV.is_dir():
        return DEFAULT_VENV / "Scripts" / "python.exe" if sys.platform == "win32" \
            else DEFAULT_VENV / "bin" / "python"
    if shutil.which("python"):
        return "python"
    raise SystemExit(
        "no build venv found. Expected one of:\n"
        f"  {DEFAULT_VENV} (Windows short-path venv)\n"
        "  a 'python' on PATH with jupyterlite-core installed"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(HERE / "output"))
    parser.add_argument("--refresh-wheels", action="store_true",
                        help="Re-download wheels into pypi/ from PyPI")
    args = parser.parse_args()

    if args.refresh_wheels:
        subprocess.run([sys.executable, "-c", _FETCH_WHEELS], cwd=HERE, check=True)

    # The deck iframe document is built host-side (pylabrobot installed on this
    # machine), never inside the kernel. Generated, not committed.
    _build_deck()

    cmd = [
        str(python()), "-m", "jupyterlite", "build",
        "--output-dir", args.out,
        "--config", str(HERE / "site" / "jupyter_lite_config.json"),
        "--contents", str(HERE / "content"),
        "--piplite-wheels", str(HERE / "pypi"),
    ]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, cwd=HERE, check=True)
    print(f"\nbuilt -> {args.out}")


def _build_deck() -> None:
    """Regenerate the deck iframe document from the installed PyLabRobot.

    Requires ``pylabrobot`` + ``plr_workshops`` importable from the *build*
    interpreter (the one running this script), with the vendored inline assets
    populated (``python -m plr_workshops.vendor``). The deck is a generated
    artifact like the wheels -- kept out of git, rebuilt with the site.
    """
    out = HERE / "deck.html"
    try:
        import plr_workshops.frontend as frontend
    except Exception as exc:  # noqa: BLE001
        print(f"  (skip deck.html: could not import plr_workshops.frontend: {exc})")
        return
    html = frontend.build_page(name="Deck", chrome="deck")
    out.write_text(html, encoding="utf-8")
    print(f"  deck.html -> {out} ({len(html):,} bytes)")


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


if __name__ == "__main__":
    main()
