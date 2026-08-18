"""Copy a workshop into assignments/ so it is safe to work in and to `git pull` over.

    uv run python scripts/start_workshop.py 01
    uv run python scripts/start_workshop.py          # lists what is available

Two things make this worth a script rather than a copy-paste `cp`:

  * It never overwrites work. Copying over your own edited notebook is the one
    way to lose a whole workshop's worth of effort.
  * It keeps the copy in assignments/, directly under the repo root. The
    notebooks reach their inputs with `os.path.dirname(cwd)` + `data/` and
    `../figs/...`, so a copy on the Desktop loads no figures and no CSVs. That
    failure looks like a broken install, and isn't one.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "workshops"
DEST = ROOT / "assignments"


def available() -> list[Path]:
    return sorted(SOURCE.glob("*.ipynb"))


def resolve(token: str) -> Path | None:
    """Accept '1', '01', '01_deck_setup', a filename, or a unique substring."""
    token = token.strip().removesuffix(".ipynb").lower()
    candidates = available()
    padded = token.zfill(2) if token.isdigit() else token
    exact = [p for p in candidates if p.stem.lower() == padded or p.stem.lower().startswith(f"{padded}_")]
    if len(exact) == 1:
        return exact[0]
    partial = [p for p in candidates if padded in p.stem.lower()]
    return partial[0] if len(partial) == 1 else None


def main(argv: list[str]) -> int:
    if not SOURCE.is_dir():
        print(f"No workshops/ directory at {SOURCE} -- are you running this inside the course folder?")
        return 1

    if not argv:
        print("Workshops available:\n")
        for path in available():
            marker = "  (already in assignments/)" if (DEST / path.name).exists() else ""
            print(f"  {path.stem.split('_')[0]}  {path.stem}{marker}")
        print("\nStart one with, for example:  uv run bme590 start 01")
        return 0

    source = resolve(argv[0])
    if source is None:
        print(f"'{argv[0]}' does not match exactly one workshop. Run with no arguments to see the list.")
        return 1

    DEST.mkdir(exist_ok=True)
    target = DEST / source.name
    if target.exists():
        print(
            f"{target.relative_to(ROOT)} already exists -- keeping your version, nothing copied.\n"
            f"If you truly want to start over, rename or delete that file first."
        )
        return 1

    shutil.copy2(source, target)
    print(f"Copied {source.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
    print("Open that copy in VS Code and work there. Your edits survive every `git pull`.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
