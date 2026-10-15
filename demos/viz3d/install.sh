#!/bin/sh
# One-line setup for the viz3d demo on macOS/Linux: installs uv if it is missing, then lets
# `viz3d setup` build the environment from uv.lock and register the Jupyter kernel.
set -eu
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
fi
uv run viz3d setup "$@"
uv run viz3d doctor
