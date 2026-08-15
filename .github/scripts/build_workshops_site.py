"""Render the workshop notebooks into a static Pages site.

Executes each notebook headless (same neutralization/skip rules as
check_workshops.py), converts it to HTML with nbconvert, and writes a
landing page plus one HTML page per workshop. Output goes to site/.
"""
import glob
import json
import os
import subprocess
import sys

import nbformat


def cell_source(cell):
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def is_stub(src):
    import io
    import tokenize

    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.OP and tok.string == "...":
                return True
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return "..." in src
    return False


SKIP_MARKERS = (
    "CI-SKIP",
    "YOUR CODE HERE",
    "you will get an error",
    "this is ok",
    "should throw an error",
    "should throw our better error",
)
SKIP_NOTE = "# [Interactive / student exercise — complete this in a local run of the notebook.]"


def neutralize(src):
    """Make interactive cells runnable headless: don't start the visualizer
    websocket server (the deck/lh are still built and returned), and drop the
    demo sleeps so execution stays fast."""
    import re

    src = re.sub(r"vis\s*=\s*Visualizer\([^)]*\)", "vis = None", src)
    src = src.replace("await vis.setup()", "pass")
    src = src.replace("await vis.stop()", "pass")
    src = re.sub(r"time\.sleep\(\s*\d+(\.\d+)?\s*\)", "time.sleep(0)", src)
    return src


def prepare(nb):
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        src = cell_source(cell)
        if any(m in src for m in SKIP_MARKERS) or is_stub(src):
            cell.source = SKIP_NOTE
        else:
            cell.source = neutralize(src)


def main():
    out_dir = os.path.join("site", "workshops")
    os.makedirs(out_dir, exist_ok=True)

    subprocess.run(
        [sys.executable, "-m", "ipykernel", "install", "--user", "--name", "plr_ci",
         "--display-name", "PLR CI"],
        check=True,
    )

    from nbclient import NotebookClient
    from nbconvert import HTMLExporter

    exporter = HTMLExporter(template_name="classic")
    titles = {}
    order = sorted(glob.glob(os.path.join("workshops", "*.ipynb")))
    for path in order:
        nb = nbformat.read(path, as_version=4)
        prepare(nb)
        client = NotebookClient(nb, timeout=180, kernel_name="plr_ci",
                                resources={"metadata": {"path": os.path.dirname(path)}})
        client.execute()

        title = " ".join(path.rsplit("/", 1)[-1].rsplit(".", 1)[0].split("_")[1:]).title()
        titles[os.path.basename(path)] = title

        (body, _resources) = exporter.from_notebook_node(nb)
        stem = os.path.basename(path).rsplit(".", 1)[0]
        with open(os.path.join(out_dir, stem + ".html"), "w", encoding="utf-8") as fh:
            fh.write(body)
        print("rendered", stem)

    index_path = os.path.join("site", "index.html")
    links = []
    for path in order:
        stem = os.path.basename(path).rsplit(".", 1)[0]
        title = titles[os.path.basename(path)]
        download = (
            "https://github.com/chory-lab/bme590-fall-2026/raw/main/workshops/"
            + os.path.basename(path)
        )
        links.append(
            f'<li><a href="workshops/{stem}.html">{title}</a>'
            f' &nbsp;<small>(<a href="{download}">download .ipynb</a>)</small></li>'
        )
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>BME 590 Fall 2026 — Workshops</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;"
        "padding:0 1rem;line-height:1.5}li{margin:.5rem 0}</style></head><body>"
        "<h1>BME 590 Fall 2026 — Workshops</h1>"
        "<p>Rendered copies of the workshop notebooks. Download the <code>.ipynb</code> to "
        "run locally in VS Code with the <code>lab-automation</code> environment.</p>"
        "<ul>" + "\n".join(links) + "</ul></body></html>"
    )
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote site/index.html")


if __name__ == "__main__":
    main()
