"""The BME 590 installer.

Students do not run this directly -- `install.ps1` / `install.sh` fetch a Python
and hand off to it (see README Step 1). Run it by hand while developing:

    uv run --no-project scripts/install.py [--wheelhouse PATH] [--root DIR]

Everything the install actually does lives here, in one file, on purpose. The
shell bootstraps used to duplicate all of it in PowerShell *and* POSIX sh, which
meant every fix had to be written and tested twice and the two drifted. Their job
is now only the part that cannot be done in Python: obtaining a Python.

Standard library only. It runs under the interpreter uv just fetched, before any
project environment exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO_URL = "https://github.com/chory-lab/bme590-fall-2026"
REPO_NAME = "bme590-fall-2026"
BRANCH = "main"

WINDOWS = os.name == "nt"
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

# Line-buffer our own output. Subprocesses write straight to the same terminal
# unbuffered, so with the default block buffering (which is what you get the
# moment this is piped to a file, as support transcripts are) our step headings
# would all appear at the end, after the output they are supposed to introduce.
# utf-8 for the same reason doctor.py sets it: PyLabRobot prints "µL", and a piped
# stdout on Windows still defaults to a legacy codepage.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - very old or odd streams
        pass


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def say(message: str) -> None:
    print(f"  {message}")


def step(message: str) -> None:
    print("\n" + _c("36", f"==> {message}"))


def ok(message: str) -> None:
    print(f"  {_c('32', 'OK')}  {message}")


class InstallError(Exception):
    """A failure worth showing the student, with the transcript above it."""


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, letting its output through to the student's terminal.

    The transcript is the support artifact -- we ask students to paste it -- so
    nothing here is captured or hidden unless a caller asks for it.
    """
    return subprocess.run([str(part) for part in cmd], **kwargs)


def which_uv() -> str:
    """Locate uv. The bootstrap normally passes its path in UV_BIN."""
    candidates = [os.environ.get("UV_BIN"), shutil.which("uv")]
    home = Path.home()
    candidates += [
        home / ".local" / "bin" / ("uv.exe" if WINDOWS else "uv"),
        home / ".cargo" / "bin" / ("uv.exe" if WINDOWS else "uv"),
        Path("/opt/homebrew/bin/uv"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise InstallError(
        "uv is not installed. Close this window, open a new terminal, and run the "
        "install command from the README again."
    )


# ------------------------------------------------------------------- preflight
# Every package in uv.lock has a prebuilt wheel for Windows x86_64/arm64, macOS
# x86_64/arm64 and Linux x86_64/arm64 -- verified by resolving the exported lock
# for each of those targets with source builds forbidden (`uv pip install
# --dry-run --no-build --python-platform ...`). So a dependency install failing
# for lack of a wheel is not a risk *on those platforms*; it is a risk off them,
# where pip would fall back to compiling from source and fail slowly and
# confusingly. Checking up front turns that into one clear sentence.
#
# The floors below come from the wheels themselves: numpy and pandas ship
# macosx_10_15_x86_64 as their oldest Intel build, and macosx_11_0_arm64 for
# Apple silicon (which is the oldest macOS any such Mac runs anyway).
MACOS_MINIMUM = (10, 15)


def preflight() -> list[str]:
    """Refuse platforms where the install cannot work; warn where it may not.

    Returns advisory warnings. Raises InstallError for a hard stop.
    """
    warnings: list[str] = []
    machine = platform.machine().lower()
    is_64bit = sys.maxsize > 2**32

    if machine in {"i386", "i686", "x86"} or not is_64bit:
        raise InstallError(
            "this looks like a 32-bit system, which the class packages do not ship builds for.\n"
            "    Use a 64-bit machine, a lab computer, or the browser version of the workshops."
        )

    if sys.platform == "darwin":
        release = platform.mac_ver()[0]
        try:
            version = tuple(int(part) for part in release.split(".")[:2])
        except ValueError:
            version = ()
        if version and version < MACOS_MINIMUM:
            raise InstallError(
                f"macOS {release} is older than 10.15 (Catalina), and NumPy/pandas publish no\n"
                "    builds for it. Options, in order of preference: update macOS, borrow a lab\n"
                "    machine, or use the browser version of the workshops (no install at all)."
            )

    if sys.platform.startswith("linux"):
        # A musl system (Alpine and friends) can install these wheels, but the
        # managed CPython uv fetches is glibc-linked and will not run there.
        libc, _ = platform.libc_ver()
        if not libc and not Path("/lib/x86_64-linux-gnu").exists():
            warnings.append(
                "this may be a musl-based Linux (Alpine). If the install fails, use the "
                "Conda path in the README instead."
            )

    # .venv is ~200 MB and uv's package cache another ~300 MB. Running out of
    # space mid-install leaves exactly the half-written .venv that the rebuild
    # step below has to clean up, so say so before starting.
    try:
        free_gb = shutil.disk_usage(Path.home()).free / 1e9
        if free_gb < 1.5:
            raise InstallError(
                f"only {free_gb:.1f} GB free on this disk. The environment needs about 0.5 GB, "
                "plus room to unpack it -- free up some space and run this again."
            )
        if free_gb < 3:
            warnings.append(f"only {free_gb:.1f} GB free on this disk - it will fit, but not by much")
    except OSError:
        pass

    return warnings


# --------------------------------------------------------------- course files
def download_zip(root: Path) -> None:
    """Fetch the course files without Git.

    A zip of the branch is a complete, working checkout for everything the
    workshops need; updating then means re-running the installer. This exists so
    that Git is never a prerequisite -- on a fresh Mac, invoking git at all can
    raise a GUI dialog for the Command Line Tools.
    """
    say(f"downloading the course files into {root}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "repo.zip"
        with urllib.request.urlopen(f"{REPO_URL}/archive/refs/heads/{BRANCH}.zip") as response:
            archive.write_bytes(response.read())
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
        inner = next((p for p in Path(tmp).iterdir() if p.is_dir() and p.name.startswith(REPO_NAME)), None)
        if inner is None:
            raise InstallError("the download looks incomplete -- try again")
        root.mkdir(parents=True, exist_ok=True)
        for item in inner.iterdir():
            target = root / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)


def git_works() -> bool:
    """True only if git can actually answer.

    `git` exists on a fresh Mac as a stub that pops the Command Line Tools
    installer, so presence on PATH is not enough -- it has to respond.
    """
    if not shutil.which("git"):
        return False
    try:
        return run(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def locate_course_files(explicit_root: Path | None) -> Path:
    here = Path(__file__).resolve().parent.parent
    if explicit_root:
        return explicit_root.resolve()
    if (here / "uv.lock").exists():
        say("running from inside a checkout")
        return here
    if (Path.cwd() / "uv.lock").exists():
        return Path.cwd()

    # Not Documents or Desktop: those are the folders OneDrive and iCloud Drive
    # sync by default, and letting a sync client walk a .venv (tens of thousands
    # of small files, some locked while Python runs) is slow and can break it.
    root = Path.home() / REPO_NAME
    if (root / "uv.lock").exists():
        say(f"found an existing copy at {root}")
        if git_works() and (root / ".git").exists():
            say("updating it with git pull")
            if run(["git", "-C", root, "pull", "--ff-only"]).returncode != 0:
                say("git pull did not fast-forward (you have local edits) - keeping your copy as is")
    elif git_works():
        say(f"cloning into {root}")
        if run(["git", "clone", "--depth", "1", f"{REPO_URL}.git", root]).returncode != 0:
            raise InstallError("git clone failed - check your network connection")
    else:
        download_zip(root)

    if not (root / "uv.lock").exists():
        raise InstallError(f"no uv.lock in {root} - delete that folder and run the installer again")
    return root


# ------------------------------------------------------------- offline bundle
def find_bundle(root: Path, explicit: str | None) -> Path | None:
    """Resolve an offline bundle: an argument, an env var, or a zip lying around."""
    candidate = explicit or os.environ.get("BME590_WHEELHOUSE")
    if not candidate:
        for directory in (root, Path(__file__).resolve().parent.parent, Path.cwd()):
            matches = sorted(directory.glob("wheelhouse-*.zip"))
            if matches:
                candidate = str(matches[0])
                break
        else:
            extracted = root / ".wheelhouse"
            if (extracted / "MANIFEST.json").exists():
                candidate = str(extracted)
    if not candidate:
        return None

    path = Path(candidate)
    if not path.exists():
        raise InstallError(f"no offline bundle at {path}")
    if path.is_dir():
        bundle = path
    else:
        say(f"unpacking offline bundle {path.name}")
        bundle = root / ".wheelhouse"
        shutil.rmtree(bundle, ignore_errors=True)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(bundle)

    manifest_path = bundle / "MANIFEST.json"
    if not manifest_path.exists():
        raise InstallError(f"{path} is not a course bundle (no MANIFEST.json)")

    # A bundle built from a different uv.lock installs a package set this
    # checkout does not pin. Refuse it out loud rather than produce an
    # environment nobody can reason about.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
    if manifest.get("lock_sha256") != actual:
        say("the offline bundle was built from a different uv.lock - ignoring it, installing from the network")
        return None
    return bundle


# ----------------------------------------------------------------- environment
def venv_python(root: Path) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")


def build_environment(uv: str, root: Path, bundle: Path | None) -> None:
    # A .venv that exists but holds no interpreter makes `uv sync` refuse to run
    # ("not a valid Python environment"), and re-running never fixes it. That
    # state is easy to reach: interrupt the installer, or sleep the laptop
    # mid-download. `uv venv --clear` replaces it -- and does the deleting
    # itself, because site-packages nests deep enough that Windows tooling hits
    # the 260-character MAX_PATH limit and leaves the directory behind.
    if (root / ".venv").exists() and not venv_python(root).exists():
        say("found an incomplete environment from an earlier run - rebuilding it")
        if run([uv, "venv", "--clear"], cwd=root).returncode != 0:
            raise InstallError(
                "could not replace .venv (a program may be using it). Close VS Code "
                "and any Python terminals, then run the installer again."
            )

    if bundle:
        install_from_bundle(uv, root, bundle)
    else:
        install_from_network(uv, root)

    if not venv_python(root).exists():
        raise InstallError("no interpreter in .venv after installing - see the transcript above")
    ok(f"environment at {root / '.venv'}")


def install_from_network(uv: str, root: Path) -> None:
    """Install from PyPI, with the three retries that cover what actually fails.

    Every package in uv.lock has a wheel for this platform (see preflight), so
    failures here are essentially always the network rather than the packages.
    Each attempt therefore changes one network variable instead of repeating the
    same request:

      1. plain -- covers a transient reset, and resumes from the cache, so a
         second attempt only fetches what the first did not finish.
      2. fewer parallel downloads -- congested Wi-Fi with thirty students
         installing at once times out at high concurrency and succeeds at low.
      3. the OS certificate store -- campus and corporate networks intercept TLS
         (Zscaler, Netskope and friends), which uv's bundled certificates reject
         but the OS trusts, because IT installed the interception root there.
    """
    env = dict(os.environ)
    # The default per-read timeout is 30 s, which a slow network trips while the
    # transfer is still alive and making progress.
    env.setdefault("UV_HTTP_TIMEOUT", "120")

    # --frozen: install exactly what uv.lock pins, never re-resolve. The whole
    # class then runs byte-identical versions, which is what makes "works on my
    # machine" debuggable.
    attempts = [
        ([], None, env),
        ([], "retrying with fewer parallel downloads (slow or congested network)",
         {**env, "UV_CONCURRENT_DOWNLOADS": "4"}),
        (["--native-tls"], "retrying with the system certificate store (--native-tls)", env),
    ]
    for flags, message, attempt_env in attempts:
        if message:
            say(message)
        if run([uv, "sync", "--frozen", *flags], cwd=root, env=attempt_env).returncode == 0:
            return
    raise InstallError(
        "could not install the packages after three attempts - the transcript above says which one.\n"
        "    If your network is the problem, the README's offline bundle installs with no network at all."
    )


def install_from_bundle(uv: str, root: Path, bundle: Path) -> None:
    say("installing from the offline bundle (no network)")
    env = dict(os.environ)
    python_dir = bundle / "python"
    if python_dir.is_dir():
        # The bundle carries the interpreter too, laid out the way uv's own
        # download URLs are, so pointing uv's mirror at it installs Python with
        # no network. Best effort: if a suitable Python is already present, uv
        # uses that instead and this is a no-op.
        env["UV_PYTHON_INSTALL_MIRROR"] = python_dir.resolve().as_uri()
        version = (root / ".python-version").read_text(encoding="utf-8").strip()
        run([uv, "python", "install", version], cwd=root, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if run([uv, "venv", "--offline"], cwd=root, env=env).returncode != 0:
        raise InstallError(
            "could not create .venv from the offline bundle - it may not include a Python for this platform"
        )
    # --no-index: never contact a registry. The bundled requirements file carries
    # hashes, so the wheels are still verified.
    common = ["--offline", "--no-index", "--find-links", str(bundle / "wheels")]
    if run([uv, "pip", "install", *common, "-r", str(bundle / "requirements.txt")], cwd=root, env=env).returncode != 0:
        raise InstallError("installing from the offline bundle failed - it may be for a different platform")
    if run([uv, "pip", "install", *common, "--no-deps", "-e", "."], cwd=root, env=env).returncode != 0:
        raise InstallError("installing the course package from the offline bundle failed")


# --------------------------------------------------------------------- VS Code
def configure_vscode(root: Path) -> None:
    # The step students most often got wrong by hand: the old README walked them
    # through Python: Select Interpreter. Writing it removes the choice.
    settings_dir = root / ".vscode"
    settings_dir.mkdir(exist_ok=True)
    interpreter = "${workspaceFolder}\\.venv\\Scripts\\python.exe" if WINDOWS else "${workspaceFolder}/.venv/bin/python"
    settings = {
        "python.defaultInterpreterPath": interpreter,
        "python.terminal.activateEnvironment": True,
        "jupyter.kernels.filter": [],
    }
    (settings_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    ok(".vscode/settings.json written")

    # Skipped, not failed, when the `code` CLI is absent: VS Code offers these
    # itself on first opening a notebook, and a missing editor must not fail an
    # otherwise-good Python environment. On macOS the CLI is not on PATH until
    # the user runs "Shell Command: Install 'code' command in PATH", so this is
    # often skipped there.
    code = shutil.which("code")
    if not code:
        say("VS Code not found on PATH - install it from https://code.visualstudio.com/,")
        say('then add the "Python" and "Jupyter" extensions from the Extensions panel.')
        return
    for extension in ("ms-python.python", "ms-toolsai.jupyter"):
        result = run([code, "--install-extension", extension, "--force"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            ok(f"VS Code extension {extension}")
        else:
            say(f"could not install {extension} - add it from the Extensions panel")


# ----------------------------------------------------------------------- main
def register_kernel(root: Path) -> None:
    # A registered kernel means a notebook opened from anywhere -- JupyterLab, or
    # a copy outside the folder -- can still find this environment.
    result = run(
        [venv_python(root), "-m", "ipykernel", "install", "--user", "--name", "bme590",
         "--display-name", "BME 590 (lab automation)"],
        cwd=root, stdout=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise InstallError("registering the Jupyter kernel failed")
    ok('kernel "BME 590 (lab automation)" available')


def next_steps(root: Path) -> str:
    sep = "\\" if WINDOWS else "/"
    return f"""
=================================================
 Done. Next steps:
=================================================
  1. Open VS Code, then File > Open Folder... and choose:
       {root}
  2. Accept the "Python" and "Jupyter" extensions if VS Code offers them.
  3. Make your own copy of the workshop you are starting:
       uv run python scripts{sep}start_workshop.py 01
     (it lands in assignments{sep}, where class updates cannot overwrite it)
  4. Open that copy and pick the kernel "BME 590 (lab automation)" if asked.

If anything ever looks wrong:  uv run python scripts{sep}doctor.py
To update the course materials later, run the installer again.
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Install the BME 590 class environment.")
    parser.add_argument("--wheelhouse", help="offline bundle (zip or directory) to install from")
    parser.add_argument("--root", type=Path, help="install into this folder instead of the default")
    parser.add_argument("--skip-vscode", action="store_true", help="do not write .vscode/settings.json")
    args = parser.parse_args(argv)

    print(
        "=================================================\n"
        " BME 590 Laboratory Automation - environment setup\n"
        "================================================="
    )
    try:
        # The bootstrap already reported which uv it found; no need to repeat it.
        uv = which_uv()
        for warning in preflight():
            say(f"note: {warning}")

        step("Locating the course files")
        root = locate_course_files(args.root)
        ok(f"course files at {root}")

        step("Building the Python environment (this is the slow part: 1-3 minutes)")
        bundle = find_bundle(root, args.wheelhouse)
        build_environment(uv, root, bundle)

        if not args.skip_vscode:
            step("Pointing VS Code at the environment")
            configure_vscode(root)

        step("Registering the Jupyter kernel")
        register_kernel(root)
        (root / "assignments").mkdir(exist_ok=True)

        step("Verifying the install")
        if run([venv_python(root), "scripts/doctor.py"], cwd=root).returncode != 0:
            raise InstallError("the verification step found a problem - see above")
    except InstallError as exc:
        print(_c("31", f"\nINSTALL FAILED: {exc}"))
        print(
            "\nCopy everything above this line into the #pylabrobot Slack channel, along with:\n"
            f"  - your operating system ({platform.platform()})\n"
            "  - what you had already installed before running this\n\n"
            "That transcript is enough for us to fix it; a screenshot of one line usually is not."
        )
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Re-run the installer when ready - it picks up from where it stopped.")
        return 130

    print(_c("32", next_steps(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
