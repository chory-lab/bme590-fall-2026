"""Generate content/probe_00.ipynb: workshop 00 with execution probes inserted.

The question this answers is narrow and comes first: do the workshop's *async*
cells actually complete? Everything downstream -- anywidget mounting, the
postMessage relay, the deck -- is only worth instrumenting once that is known.

Three probes, in order:

1. ``SYNC_EXEC_OK``  -- a plain print, ahead of the notebook's first code cell.
2. ``ASYNC_EXEC_OK`` -- an awaited sleep. If 1 prints and 2 does not, the
   top-level-await path is broken and nothing else matters.
3. ``DECK_EXISTS`` / ``SUMMARY`` -- straight after the deck is built. If these
   do not appear, the protocol cells are not completing and the bridge is not
   the suspect.

Each probe prints to stdout *and* to the browser console via ``js.console``.
The driver reads cell outputs out of the DOM, and JupyterLab windows the
notebook -- cells below the fold have no output area to read, so a silent cell
and an unrendered one look identical. The console line is immune to that.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "content", "workshops", "00_plr_introduction.ipynb")
# Beside the workshop it copies, not at the drive root: it inherits workshop
# 00's `../figs/` and `os.path.join(os.path.dirname(cwd), "data", ...)`
# references, which only resolve from inside workshops/.
OUT = os.path.join(HERE, "content", "workshops", "probe_00.ipynb")


def _cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": "probe-" + str(abs(hash(source)))[:8],
        "metadata": {"tags": ["probe"]},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


_REPORT = '''
def _probe(*parts):
    """Print to stdout and to the browser console -- see module docstring."""
    line = " ".join(str(p) for p in parts)
    print(line)
    try:
        import js
        js.console.log("PROBE " + line)
    except Exception:
        pass
'''

SYNC_PROBE = _REPORT + '\n_probe("SYNC_EXEC_OK")\n'

ASYNC_PROBE = '''import asyncio
await asyncio.sleep(0.1)
_probe("ASYNC_EXEC_OK")
'''

DECK_PROBE = '''_probe("DECK_EXISTS", deck)
_probe("SUMMARY", deck.summary())
'''


def main() -> None:
    with open(SRC, encoding="utf-8") as fh:
        nb = json.load(fh)

    cells = nb["cells"]

    def index_of(needle: str) -> int:
        for i, c in enumerate(cells):
            if c["cell_type"] == "code" and needle in "".join(c["source"]):
                return i
        raise SystemExit(f"probe anchor not found: {needle!r}")

    # Anchored on source text, not position: the workshop is coursework and
    # will be edited, and a probe silently landing in the wrong place is worse
    # than a build that stops and says so.
    #
    # The probes used to sit after the notebook's bootstrap cell. There is no
    # bootstrap cell any more -- the labextension prepares the kernel -- so they
    # go ahead of the first code cell instead, which is also a better test: if
    # SYNC_EXEC_OK prints, the extension had the kernel ready before the
    # notebook's own code ran.
    deck_built = index_of("deck = await make_deck_with_carriers_and_contents()")
    first_code = next(i for i, c in enumerate(cells) if c["cell_type"] == "code")

    # Insert from the bottom up so the earlier index stays valid.
    cells.insert(deck_built + 1, _cell(DECK_PROBE))
    cells.insert(first_code, _cell(ASYNC_PROBE))
    cells.insert(first_code, _cell(SYNC_PROBE))

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, indent=1)
    print(f"wrote probe_00.ipynb ({len(cells)} cells): "
          f"sync+async at cell {first_code}, deck probe after cell {deck_built + 2}")


if __name__ == "__main__":
    main()
