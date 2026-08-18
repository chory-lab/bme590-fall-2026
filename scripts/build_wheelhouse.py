"""Build an offline install bundle ("wheelhouse") for the platform it runs on.

    uv run python scripts/build_wheelhouse.py            # -> dist/wheelhouse-<tag>.zip

The bundle holds every wheel the class environment needs plus the exported,
hash-pinned requirements file, so `install.sh --wheelhouse <zip>` can build the
environment with **no network access at all** in about a minute. That matters in
two situations the online path handles badly: a classroom whose Wi-Fi collapses
under thirty simultaneous installs, and a network that intercepts TLS.

Run once per platform -- wheels for numpy, pandas, pyzmq and friends are
compiled per OS/architecture/Python version. The GitHub workflow
(.github/workflows/wheelhouse.yml) does this across a runner matrix; running it
by hand is for testing, or for building a bundle for your own machine.

Why `pip download` rather than something uv-native: uv has no download
subcommand, and `uv sync --find-links` will not substitute local files for the
registry URLs recorded in uv.lock. `uv pip install --no-index --find-links`
does, which is what the installers use to consume this bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "uv.lock"
PYTHON_VERSION = (ROOT / ".python-version").read_text(encoding="utf-8").strip()


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def platform_tag() -> str:
    """A short, stable name for "the wheels that work on this machine".

    Only the parts that actually change which wheel is chosen: the OS, the CPU
    architecture, and the Python minor version.
    """
    system = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(
        platform.system(), platform.system().lower()
    )
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{arch}-py{PYTHON_VERSION.replace('.', '')}"


def lock_digest() -> str:
    """Identifies the exact dependency set a bundle was built from.

    The installers compare this against their own uv.lock and refuse a bundle
    that does not match, so a stale wheelhouse produces a clear message instead
    of a mysteriously wrong environment.
    """
    return hashlib.sha256(LOCK.read_bytes()).hexdigest()


def fetch_python(stage: Path) -> str:
    """Add the Python interpreter itself to the bundle.

    Without this, an offline install still needs the network the first time, to
    fetch a Python -- which makes the bundle useless in exactly the case it
    exists for (a machine with no working connection at all).

    uv can install an interpreter from a local mirror, laid out the same way its
    download URLs are: <mirror>/<release>/<filename>. `uv python list` reports
    those URLs, so the layout is read from uv rather than hardcoded here.
    """
    listing = run(
        ["uv", "python", "list", "--only-downloads", "--output-format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    wanted = f"{PYTHON_VERSION}."
    candidates = [
        entry
        for entry in json.loads(listing)
        if entry.get("url")
        and entry.get("implementation") == "cpython"
        and entry.get("variant") == "default"
        and str(entry.get("version", "")).startswith(wanted)
    ]
    if not candidates:
        raise SystemExit(f"uv lists no downloadable CPython {PYTHON_VERSION} for this platform")

    # Highest patch version, matching what `uv python install 3.11` would pick.
    entry = max(candidates, key=lambda e: tuple(e["version_parts"].values()))
    url = entry["url"]
    release, filename = (urllib.parse.unquote(part) for part in url.rsplit("/", 2)[-2:])

    target = stage / "python" / release / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"$ download {url}")
    with urllib.request.urlopen(url) as response, target.open("wb") as fh:
        shutil.copyfileobj(response, fh)
    return f"{release}/{filename}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="directory for the zip (default: dist/)")
    parser.add_argument("--keep-dir", action="store_true", help="also leave the unzipped bundle in place")
    args = parser.parse_args(argv)

    if not LOCK.exists():
        print(f"no uv.lock at {LOCK} -- run this from a checkout of the course repo")
        return 1

    tag = platform_tag()
    stage = args.out / f"wheelhouse-{tag}"
    wheels = stage / "wheels"
    if stage.exists():
        shutil.rmtree(stage)
    wheels.mkdir(parents=True)

    # --no-emit-project: the course package itself is built from the checkout,
    # not downloaded. --no-dev keeps developer tooling out of a student bundle.
    requirements = stage / "requirements.txt"
    exported = run(
        ["uv", "export", "--frozen", "--no-emit-project", "--no-dev", "--format", "requirements-txt"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    requirements.write_text(exported, encoding="utf-8")

    # setuptools and wheel are not in the lock: uv needs them to build the
    # course package from the checkout, and without them in the bundle that
    # build reaches for the network and defeats the point.
    run(
        [
            "uv", "run", "--with", "pip", "--python", PYTHON_VERSION, "--",
            "python", "-m", "pip", "download", "-q",
            "-r", str(requirements), "-d", str(wheels), "--only-binary", ":all:",
        ],
        cwd=ROOT,
    )
    run(
        [
            "uv", "run", "--with", "pip", "--python", PYTHON_VERSION, "--",
            "python", "-m", "pip", "download", "-q",
            "setuptools", "wheel", "-d", str(wheels), "--only-binary", ":all:",
        ],
        cwd=ROOT,
    )

    python_archive = fetch_python(stage)

    files = sorted(p.name for p in wheels.iterdir())
    manifest = {
        "platform_tag": tag,
        "python_version": PYTHON_VERSION,
        "lock_sha256": lock_digest(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_on": platform.platform(),
        "wheel_count": len(files),
        "python_archive": python_archive,
        "wheels": files,
    }
    (stage / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    archive = args.out / f"wheelhouse-{tag}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(stage))

    if not args.keep_dir:
        shutil.rmtree(stage)

    size_mb = archive.stat().st_size / 1e6
    print(f"\n{archive}  ({len(files)} wheels, {size_mb:.0f} MB)")
    print(f"lock_sha256 {manifest['lock_sha256'][:12]}...  -- rebuild this bundle whenever uv.lock changes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
