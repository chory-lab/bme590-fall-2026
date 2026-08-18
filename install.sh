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

# The astral installer claims to edit a shell profile, but its choice of file is
# unreliable (it sometimes targets ~/.profile, which zsh never reads), so a fresh
# Terminal can still report "command not found: uv" even though uv installed
# fine. Guarantee the path for future shells ourselves, and say what we changed.
#
# For whichever directory uv actually lives in, not just the default one:
# find_uv below deliberately accepts a Homebrew uv at /opt/homebrew/bin, which on
# Apple silicon is on PATH only if `brew shellenv` runs from the profile -- so
# "something else put it there, so something else handles PATH" is not a safe
# assumption, and a student in that state can re-run this forever without it
# helping.
#
# Verified, not inferred. This check used to be `grep -q 'HOME/.local/bin' ~/.zshrc`
# -- and a real student install passed that grep and still opened a new Terminal
# to "zsh: command not found: uv". The grep matches uv's own
# `. "$HOME/.local/bin/env"` line, a comment, a quoted string, or anything after
# an early `return` in the rc file, none of which put uv on PATH. Asking a login
# shell whether it can find uv is the actual question, so ask it.
uv_on_path_for_new_shells() {
  [ -n "${SHELL-}" ] || return 1
  # </dev/null so an rc file that reads input cannot hang the installer.
  "$SHELL" -lic 'command -v uv' >/dev/null 2>&1 </dev/null
}

ensure_uv_findable() {
  UV_DIR=$(CDPATH= cd -- "$(dirname -- "$UV")" && pwd) || return 0
  if uv_on_path_for_new_shells; then return 0; fi
  case "${SHELL-}" in
    *zsh*)  RC="$HOME/.zshrc" ;;
    *fish*) RC="$HOME/.config/fish/conf.d/uv-path.fish" ;;
    *bash*)
      # macOS Terminal starts *login* shells, which read .bash_profile and never
      # .bashrc -- so writing .bashrc there (what this used to do) changed
      # nothing for new windows. Creating .bash_profile when it does not exist
      # would stop bash reading an existing .profile, so prefer what is there.
      if [ "$(uname -s)" = "Darwin" ]; then
        if [ -f "$HOME/.bash_profile" ]; then RC="$HOME/.bash_profile"
        elif [ -f "$HOME/.profile" ]; then RC="$HOME/.profile"
        else RC="$HOME/.bash_profile"; fi
      else
        RC="$HOME/.bashrc"
      fi ;;
    *)      RC="$HOME/.profile" ;;
  esac
  UV_DIR_HOME=$(printf '%s' "$UV_DIR" | sed "s|^$HOME|\$HOME|")
  case "$RC" in
    *.fish) LINE="fish_add_path $UV_DIR" ;;
    *)      LINE="export PATH=\"$UV_DIR_HOME:\$PATH\"" ;;
  esac
  # The one thing still worth matching on: our own line, so re-running does not
  # stack up copies of it. Everything else is decided by the check above.
  if ! { [ -f "$RC" ] && grep -qF "$LINE" "$RC"; }; then
    mkdir -p "$(dirname "$RC")" 2>/dev/null
    # >> creates the file if a fresh Mac has no rc file yet; never truncate.
    printf '\n%s\n' "$LINE" >> "$RC" 2>/dev/null || return 0
  fi

  # Confirm the edit did what it was supposed to. If it did not -- an rc file
  # that returns early, a Terminal configured to run a different shell -- the
  # student needs the exact command, not the reassuring message.
  if uv_on_path_for_new_shells; then
    echo "  added $UV_DIR to PATH in $RC (new terminals will find it)"
  else
    echo "  NOTE: added $UV_DIR to $RC, but a fresh $SHELL still does not find uv."
    echo "  If a new terminal says 'command not found: uv', run this once:"
    echo "      export PATH=\"$UV_DIR:\$PATH\""
    echo "  and tell us -- that rc file is doing something we should know about."
  fi
}

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
ensure_uv_findable

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
#
# Not `exec`: the script already runs in a child shell (piped `curl | sh`, or
# `sh install.sh`), so exec buys nothing, and reporting the result ourselves
# makes a failure unmistakable. install.py has already printed the details and
# the transcript above; this is just the closing line.
if "$UV" run --no-project --python 3.11 "$INSTALLER" "$@"; then
  :
else
  code=$?
  printf "\n${R}INSTALL FAILED (exit code %s). See the message above, or re-run to start over.${Z}\n" "$code" >&2
  exit "$code"
fi
