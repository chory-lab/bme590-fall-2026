"""Write the editor config: .vscode/settings.json and bme590.code-workspace.

The installer does this once, at install time. That is not enough: an editor
setting added mid-semester would then only reach students who install *after*
it landed, and nobody re-runs the installer once the class is running. So
`bme590 start` repairs both files on every workshop open (see
`repair_editor_config` in bme590/cli.py), and this script is what it calls.

The content lives in scripts/install.py and is imported, not copied -- a second
copy of PYLANCE_PACKAGE_DEPTHS would drift from the first, and the drift would
show up as "labware autocomplete works on my machine".

    uv run python scripts/configure_editor.py [--root DIR]

Idempotent: both writers merge into what is already there, and nothing here
touches the network, VS Code, or the environment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import install  # noqa: E402 - needs the sys.path line above


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="the class folder")
    args = parser.parse_args(argv)
    install.configure_editor(args.root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
