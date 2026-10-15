"""Drive the hosted viz3d page in headless Chromium: every cell run, every motion played, every
refusal drawn.

    python jupyterlite/viz3d/drive_viz3d.py --url http://127.0.0.1:8812/ --out viz3d-run/

Needs a `build.py --probe` deploy (the driver reaches the notebook through the app handle that the
probe build exposes) served at --url. Exits non-zero naming the first gate that failed.

The gates, in the order a broken site fails them:

  bootstrap   the labextension installed the demo's packages (PLR_BOOTSTRAP_READY), and the right
              ones: a kernel that got the workshops' pylabrobot 0.2.2 has no 3D viewer at all
  cells       every code cell ran to completion without an error output
  bridge      the kernel's viewer and the page found each other (scene and state reached the page)
  motion      every motion the kernel sent was played and answered (motion_done), so commands
              really waited on the page - over the widget comm, inside JupyterLite
  collisions  nine refusals reached the page (eight channel ZA moves and the iSWAP plan), and each
              screenshot shows the overlay's red
"""

import argparse
import io
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# Text each section's cell prints once it has done what it says.
EXPECTED_OUTPUTS = (
  "destination A1 holds 50",
  "refused: channel 0's Z move (P1 ZA)",
  "destination now sits on source_carrier-3",
  "the fingers would hit: ['tip_carrier']",
  "source now sits on destination_carrier-3",
)
CELL_TIMEOUT_S = 600  # the first cell to import PyLabRobot pays for the kernel's warm-up
BOOT_TIMEOUT_S = 600


class GateFailed(Exception):
  pass


def gate(ok: bool, name: str, detail: str = "") -> None:
  print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""))
  if not ok:
    raise GateFailed(name)


def reddish(png: bytes) -> int:
  from PIL import Image

  data = Image.open(io.BytesIO(png)).convert("RGB").tobytes()
  return sum(
    1
    for r, g, b in zip(data[0::3], data[1::3], data[2::3], strict=True)
    if r > 150 and r - g > 60 and r - b > 60
  )


def lite_eval(page: Page, body: str):
  """Run `body` with `app` (the JupyterLab app in #lite) and `panel` (the open notebook) bound."""
  return page.evaluate(
    """async (body) => {
      const w = document.querySelector('#lite').contentWindow;
      const app = w.jupyterapp || w.jupyterlab;
      if (!app) return {error: 'no app global (build with --probe)'};
      let panel = null;
      for (const x of app.shell.widgets('main')) {
        if (x.content && x.content.model && x.content.model.cells) { panel = x; break; }
      }
      if (!panel) return {error: 'no notebook open'};
      return await (new Function('app', 'panel', 'return (async () => {' + body + '})()'))(app, panel);
    }""",
    body,
  )


def drive(url: str, out: Path) -> None:
  out.mkdir(parents=True, exist_ok=True)
  console: list = []
  with sync_playwright() as p:
    browser = p.chromium.launch(
      args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
    # The parent page hears the bootstrap's announcements; keep them where the driver can read.
    page.add_init_script(
      """if (window === window.top) {
        window.__seen = [];
        window.addEventListener('message', (e) => {
          const d = e.data;
          if (d && typeof d.type === 'string' && d.type.startsWith('PLR_')) window.__seen.push(d);
        });
      }"""
    )
    try:
      page.goto(f"{url.rstrip('/')}/viz3d.html?motion=8")
      print("viz3d hosted page")

      deadline = time.monotonic() + BOOT_TIMEOUT_S
      state = None
      while time.monotonic() < deadline:
        seen = page.evaluate("window.__seen || []")
        state = next(
          (m for m in seen if m["type"] in ("PLR_BOOTSTRAP_READY", "PLR_BOOTSTRAP_FAILED")), None
        )
        if state:
          break
        time.sleep(1)
      gate(
        bool(state) and state["type"] == "PLR_BOOTSTRAP_READY",
        "bootstrap",
        json.dumps(state) if state else f"nothing after {BOOT_TIMEOUT_S} s",
      )

      count = lite_eval(page, "return panel.content.model.cells.length;")
      gate(isinstance(count, int), "notebook open", str(count))
      for i in range(count):
        kind = lite_eval(page, f"return panel.content.model.cells.get({i}).type;")
        if kind != "code":
          continue
        started = time.monotonic()
        result = page.evaluate(
          """async ([i, timeout]) => {
            const w = document.querySelector('#lite').contentWindow;
            const app = w.jupyterapp || w.jupyterlab;
            let panel = null;
            for (const x of app.shell.widgets('main')) {
              if (x.content && x.content.model && x.content.model.cells) { panel = x; break; }
            }
            panel.content.activeCellIndex = i;
            const run = app.commands.execute('notebook:run-cell').then(() => 'OK');
            const stop = new Promise((r) => setTimeout(() => r('TIMEOUT'), timeout * 1000));
            return Promise.race([run, stop]).catch((e) => 'ERR ' + e.message);
          }""",
          [i, CELL_TIMEOUT_S],
        )
        outputs = lite_eval(
          page,
          f"""const cell = panel.content.model.cells.get({i});
          const o = cell.toJSON().outputs || [];
          return o.map((x) => x.output_type === 'error'
            ? 'ERROR ' + x.ename + ': ' + x.evalue
            : (x.text ? [].concat(x.text).join('') : JSON.stringify(x.data || {{}}))).join('');""",
        )
        took = time.monotonic() - started
        text = outputs if isinstance(outputs, str) else json.dumps(outputs)
        (out / f"cell_{i:02}.txt").write_text(text, encoding="utf-8")
        gate(
          result == "OK" and "ERROR " not in text,
          f"cell {i} ({took:.0f} s)",
          "" if result == "OK" and "ERROR " not in text else f"{result} {text[:400]}",
        )

      every = "".join((out / f).read_text(encoding="utf-8") for f in sorted(
        p.name for p in out.glob("cell_*.txt")))
      missing = [t for t in EXPECTED_OUTPUTS if t not in every]
      gate(not missing, "outputs", f"missing {missing}" if missing else "")

      counts = page.evaluate("window.__viz3dCounts")
      (out / "relay_counts.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
      down, up = counts["down"], counts["up"]
      gate(down.get("scene", 0) >= 1 and down.get("state", 0) >= 1, "bridge", json.dumps(down))
      gate(up.get("hello", 0) >= 1, "page said hello", json.dumps(up))
      motions, played = down.get("motion", 0), up.get("motion_done", 0)
      gate(motions >= 10 and played >= motions, "motion", f"{played}/{motions} played")
      gate(down.get("collisions", 0) == 9, "collisions", f"{down.get('collisions', 0)} drawn")

      # The overlay is drawn when the refusal arrives and kept until the next scene: the deck
      # changes after it, so check it by refusing once more now, where it can be photographed.
      lite_eval(
        page,
        """const code = [
          'star.deck.unassign_child_resource(source_carrier)',
          'star.deck.assign_child_resource(source_carrier, track=7)',
          'try:',
          '  await transport.move_resource(destination, source_carrier[2])',
          'except Exception as e:',
          '  print(type(e).__name__)',
        ].join('\\n');
        const future = panel.sessionContext.session.kernel.requestExecute({code});
        await future.done;
        return true;""",
      )
      time.sleep(3)
      png = page.locator("#viewer").screenshot()
      (out / "collision_overlay.png").write_bytes(png)
      gate(reddish(png) > 500, "overlay drawn", f"{reddish(png)} red pixels")
      page.screenshot(path=str(out / "page.png"))
    finally:
      (out / "console.txt").write_text("\n".join(console), encoding="utf-8")
      try:
        page.screenshot(path=str(out / "last.png"))
      except Exception:
        pass
      browser.close()


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
  parser.add_argument("--url", default="http://127.0.0.1:8812/")
  parser.add_argument("--out", default="viz3d-run")
  args = parser.parse_args()
  try:
    drive(args.url, Path(args.out))
  except GateFailed as failed:
    sys.exit(f"viz3d hosted page: gate '{failed}' failed (see {args.out}/)")
  print("viz3d hosted page: all gates passed")


if __name__ == "__main__":
  main()
