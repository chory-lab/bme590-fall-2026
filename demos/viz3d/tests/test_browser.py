"""The demo with a real page watching: every motion is played, and every refusal is drawn.

The notebook runs in a kernel exactly as it would for a person; this test plays the person's
browser. Headless Chromium draws in software (SwiftShader), so it needs no GPU. The assertions are
on the wire - what the server sent and what the page answered - plus a screenshot of each refusal,
checked for the collision overlay's red and kept as a CI artifact.
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from .conftest import run_notebook

playwright_api = pytest.importorskip("playwright.async_api")

pytestmark = pytest.mark.browser

ARTIFACTS = Path(os.environ.get("VIZ3D_ARTIFACTS", Path(__file__).parent / "artifacts"))
# The overlay's colour, COLLISION in the viewer's static/constants.js.
COLLISION_RGB = (0xD0, 0x34, 0x2C)
# Fast enough to keep CI short, slow enough that every motion is really stepped through.
MOTION_SPEED = 8


def _reddish_pixels(png: bytes) -> int:
  """How many pixels are tinted towards the overlay's red: a 25%-opaque red box over the deck."""
  import io

  from PIL import Image

  data = Image.open(io.BytesIO(png)).convert("RGB").tobytes()
  count = 0
  for r, g, b in zip(data[0::3], data[1::3], data[2::3], strict=True):
    if r > 150 and r - g > 60 and r - b > 60:
      count += 1
  return count


async def test_every_motion_is_played_and_every_refusal_is_drawn():
  ARTIFACTS.mkdir(parents=True, exist_ok=True)
  url_file = Path(tempfile.mkdtemp()) / "url"
  env = {"VIZ3D_OPEN_BROWSER": "0", "VIZ3D_URL_FILE": str(url_file)}
  run = asyncio.create_task(asyncio.to_thread(run_notebook, env))

  deadline = time.monotonic() + 120
  while not url_file.exists():
    assert not run.done(), run.exception() if run.done() else ""
    assert time.monotonic() < deadline, "the notebook never started a viewer"
    await asyncio.sleep(0.2)
  url = url_file.read_text(encoding="utf-8")
  base, fragment = url.split("#", 1)
  url = f"{base}?motion={MOTION_SPEED}#{fragment}"

  received, sent, shots, console_errors = [], [], [], []
  async with playwright_api.async_playwright() as p:
    browser = await p.chromium.launch(
      args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"]
    )
    page = await browser.new_page(viewport={"width": 1400, "height": 900})
    # Only while the demo runs: when its kernel shuts down the page loses the server and says so.
    page.on(
      "console", lambda m: m.type == "error" and not run.done() and console_errors.append(m.text)
    )

    def on_socket(ws):
      ws.on("framereceived", lambda payload: received.append(json.loads(payload)))
      ws.on("framesent", lambda payload: sent.append(json.loads(payload)))

    page.on("websocket", on_socket)
    await page.goto(url)

    seen_collisions = 0
    while not run.done():
      events = [m for m in received if m.get("event") == "collisions"]
      if len(events) > seen_collisions:
        seen_collisions = len(events)
        await asyncio.sleep(0.5)  # a frame or two for the boxes to be drawn
        png = await page.screenshot()
        (ARTIFACTS / f"collision_{seen_collisions}.png").write_bytes(png)
        shots.append(png)
      await asyncio.sleep(0.1)
    outputs = run.result()
    (ARTIFACTS / "final.png").write_bytes(await page.screenshot())
    await browser.close()

  (ARTIFACTS / "outputs.txt").write_text("\n---\n".join(outputs), encoding="utf-8")
  (ARTIFACTS / "wire.json").write_text(json.dumps({"received": received, "sent": sent}), "utf-8")

  hello = [m for m in sent if m.get("event") == "hello"]
  assert hello, "the page never said hello: it could not draw"
  assert not hello[0]["data"].get("error"), hello[0]

  motions = [m["data"]["id"] for m in received if m.get("event") == "motion"]
  played = {m["data"]["id"] for m in sent if m.get("event") == "motion_done"}
  assert len(motions) >= 10, f"only {len(motions)} motions were sent"
  assert set(motions) <= played, f"motions never played: {sorted(set(motions) - played)}"

  # Section 2 lowers eight channels with one ZA each, sent together: each is judged and refused on
  # its own, so each draws. Section 4's iSWAP plan is refused once, as a whole.
  events = [m["data"]["collisions"] for m in received if m.get("event") == "collisions"]
  *lowering, packed = events
  assert len(lowering) == 8, [sorted({c["resource"] for c in e}) for e in events]
  assert all("destination" in {c["resource"] for c in e} for e in lowering)
  channels = {c["group"] for e in lowering for c in e}
  assert channels == {f"STARlet_pipette_channel_{i}" for i in range(8)}, channels
  assert {c["resource"] for c in packed} == {"tip_carrier"}

  assert shots, "no refusal was screenshotted"
  for i, png in enumerate(shots, 1):
    assert _reddish_pixels(png) > 500, f"refusal screenshot {i} shows no overlay"

  assert "refused: channel 0's Z move (P1 ZA)" in "".join(outputs)
  assert not console_errors, console_errors
