"""Structural checks for the cookbook, run in CI after `quarto render`.

Quarto catches broken code. These are the things it does not catch:

  1. a cross-reference pointing at a heading anchor that no longer exists
  2. a recipes.yml entry whose anchor no longer exists
  3. duplicate element ids in the rendered HTML, which happens when a code
     cell's label collides with a heading anchor

Exits non-zero with a list of problems, so the workflow fails loudly.
"""

from __future__ import annotations

import collections
import glob
import pathlib
import re
import sys

COOKBOOK = pathlib.Path(__file__).resolve().parents[2] / "cookbook"

# Quarto emits these twice per page by design; they are not authored content.
IGNORED_DUPLICATE_IDS = {
    "quarto-text-highlighting-styles",
    "quarto-bootstrap",
}

problems: list[str] = []


def qmd_files() -> list[pathlib.Path]:
    return sorted(COOKBOOK.glob("*.qmd")) + sorted(COOKBOOK.glob("part*/*.qmd"))


def anchors_in(path: pathlib.Path) -> set[str]:
    return set(re.findall(r"\{#([A-Za-z0-9_-]+)\}", path.read_text(encoding="utf8")))


def check_cross_references() -> None:
    for f in qmd_files():
        text = f.read_text(encoding="utf8")
        own = anchors_in(f)

        for link in re.findall(r"\]\(([^)\s]+\.qmd(?:#[A-Za-z0-9_-]+)?)\)", text):
            target, _, anchor = link.partition("#")
            resolved = (f.parent / target).resolve()
            if not resolved.exists():
                problems.append(f"{f.name}: link to missing file -> {link}")
            elif anchor and anchor not in anchors_in(resolved):
                problems.append(f"{f.name}: link to missing anchor -> {link}")

        for anchor in re.findall(r"\]\(#([A-Za-z0-9_-]+)\)", text):
            if anchor not in own:
                problems.append(f"{f.name}: same-page link to missing anchor -> #{anchor}")


def check_registry() -> None:
    registry = COOKBOOK / "recipes.yml"
    entries = re.findall(r"path:\s*(\S+)", registry.read_text(encoding="utf8"))
    if not entries:
        problems.append("recipes.yml: no entries found")
    for entry in entries:
        target, _, anchor = entry.partition("#")
        path = COOKBOOK / target
        if not path.exists():
            problems.append(f"recipes.yml: missing file -> {entry}")
        elif anchor not in anchors_in(path):
            problems.append(f"recipes.yml: missing anchor -> {entry}")
    print(f"recipes.yml: {len(entries)} entries")


def check_rendered_html() -> None:
    pages = glob.glob(str(COOKBOOK / "_site" / "**" / "*.html"), recursive=True)
    if not pages:
        problems.append("_site: no rendered HTML found - did quarto render run?")
        return
    for page in pages:
        html = pathlib.Path(page).read_text(encoding="utf8", errors="replace")
        counts = collections.Counter(re.findall(r'\sid="([^"]+)"', html))
        duplicates = {
            element_id: n
            for element_id, n in counts.items()
            if n > 1 and element_id not in IGNORED_DUPLICATE_IDS
        }
        if duplicates:
            name = pathlib.Path(page).relative_to(COOKBOOK)
            problems.append(f"{name}: duplicate element ids -> {duplicates}")
    print(f"_site: {len(pages)} pages checked")


def main() -> int:
    check_cross_references()
    check_registry()
    check_rendered_html()

    if problems:
        print(f"\n{len(problems)} problem(s):\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("\nAll structural checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
