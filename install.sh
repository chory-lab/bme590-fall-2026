#!/bin/sh
# BME 590 - install bootstrap (macOS / Linux)
#
#   curl -LsSf https://raw.githubusercontent.com/chory-lab/bme590-fall-2026/main/install.sh | sh
#
# This script does one thing: get a Python. Everything else -- fetching the
# course files, building the environment, configuring VS Code, verifying it --
# lives in scripts/install.py, which this hands off to. Keeping the shell layer
# this thin is deliberate: the logic exists once, in Python, instead of twice in
# two shell dialects that drift apart.
#
# Arguments are passed straight through, so this works:
#   sh install.sh --wheelhouse ~/Downloads/wheelhouse-macos-arm64-py311.zip
#
# POSIX sh on purpose: it must run under macOS's /bin/sh without assuming bash 4+.

set -eu

RAW='https://raw.githubusercontent.com/chory-lab/bme590-fall-2026/main'

if [ -t 1 ]; then C='\033[36m'; R='\033[31m'; Z='\033[0m'; else C=''; R=''; Z=''; fi
die() { printf "\n${R}INSTALL FAILED: %s${Z}\n" "$1" >&2; exit 1; }

printf "${C}==> Checking for uv${Z}\n"

# uv is the package manager: one static ~35 MB executable, installed per-user
# with no sudo, which also supplies the Python 3.11 the class runs on.
find_uv() {
  if command -v uv >/dev/null 2>&1; then command -v uv; return 0; fi
  for p in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    [ -x "$p" ] && { printf '%s\n' "$p"; return 0; }
  done
  return 1
}

UV=$(find_uv || true)
if [ -z "${UV:-}" ]; then
  echo "  not found - installing it (per-user, no sudo needed)"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 ||
    die "could not install uv. Behind a proxy or campus firewall? Download it from
https://github.com/astral-sh/uv/releases, put it on your PATH, and run this again."
  # uv's installer edits your shell profile for future shells; make it visible now.
  PATH="$HOME/.local/bin:$PATH"; export PATH
  UV=$(find_uv || true)
  [ -n "${UV:-}" ] ||
    die 'uv installed but is not on PATH. Close this terminal, open a new one, and run the command again.'
fi
echo "  OK  uv at $UV"
UV_BIN="$UV"; export UV_BIN

# The installer proper: use the copy beside this script when there is one (a real
# checkout), otherwise fetch the single file it needs.
SCRIPT_DIR=''
case "${0:-}" in */*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) ;; esac

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/scripts/install.py" ]; then
  INSTALLER="$SCRIPT_DIR/scripts/install.py"
else
  TMP=$(mktemp -d)
  INSTALLER="$TMP/install.py"
  curl -LsSf "$RAW/scripts/install.py" -o "$INSTALLER" ||
    die 'could not download the installer - check your network connection.'
fi

# --no-project: run against a bare interpreter, not the class environment, which
# does not exist yet. uv downloads that interpreter if the machine has none.
exec "$UV" run --no-project --python 3.11 "$INSTALLER" "$@"
