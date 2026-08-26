# Visualizer Test Suite — Handoff

**Repo:** `bme590-fall-2025` · **Branch:** `main` @ `bec4278` · **Drafted:** 2026-08-24

**Status: unverified draft — nothing in `tests/` has ever been executed.**

Two test files are written but never run: pytest and playwright are not installed
in `.venv`. Treat every assertion in them as a hypothesis until step 01 passes.
Expect real failures — the fixtures make assumptions about pylabrobot 0.2.2
internals that have not been checked against the installed package.

| | |
|---|---|
| Drafted | 469 lines, 3 files, 35 tests (Python side only) |
| Verified | 0 |
| Not started | Playwright browser layer; CI job |

---

## Why this work exists

The audit findings that motivated the suite, so they don't need re-deriving.

- **Zero test infrastructure.** `git ls-files` matches no test, spec, or conftest
  file, and no test runner appears in `pyproject.toml`. The only test-shaped files
  on disk are seven orphaned `.pyc` files in `bme590/__pycache__/` whose sources
  were deleted in `fd2ca37`.
- **CI stubs out the thing under test.** `.github/scripts/check_workshops.py:158`
  (`neutralize()`) rewrites each notebook's `from bme590.visualizer_ext import ...`
  line into no-op fakes. The ~41 `gif_recorder`/`gif_recording` call sites across
  6 workshops and 2 assignments execute against those fakes, so not one line of the
  real implementation runs.
- **Declutter has no coverage of any kind.** `declutter` appears in exactly one
  file in the repo: its own implementation. No notebook passes it; no script
  references it.
- **Grading doesn't cover it either.** `bme590/grading/rubric.py:27` marks `.gif`
  recordings explicitly "not machine gradeable".

---

## What is on disk right now

Working tree: `pyproject.toml` modified, `tests/` untracked. Nothing committed.

### `pyproject.toml` — edited

Added a `dev` dependency-group (pytest, pytest-asyncio, playwright), deliberately
kept out of `default-groups` so a student `uv sync` never pays for it. Added
`[tool.pytest.ini_options]` with `testpaths`, `asyncio_mode = "auto"`, and a
`browser` marker.

### `tests/conftest.py` — unrun

Builds a real `RecordingVisualizer` but never calls `setup()`, so no websocket
server starts — `Visualizer.__init__` only registers resource callbacks and stores
ports. A `serve` fixture calls `_run_file_server()` alone on an OS-assigned free
port. `FakeConnection` replaces `send_command` and `has_connection` on a genuine
`Visualizer` instance, which is required because `GifRecorder` type-checks its
argument with `isinstance`.

### `tests/test_gif_recorder.py` — unrun

18 tests on the Python half of the command protocol: `class_start_gif` /
`class_stop_gif` payloads, `stop()` idempotency, the watchdog (fires, detaches
itself before calling `stop()`, is cancelled by an explicit stop, disabled by
`max_duration=None`), the browser-connect wait and its timeout message,
`gif_recording` unwinding on exception, and `set_step_delay` clamping.

### `tests/test_page_injection.py` — unrun

17 tests fetching the real served page over HTTP: recorder script always present,
template placeholders substituted, static assets falling through to the stock
handler, the flag-before-CSS ordering constraint, kwarg vs.
`?minimal`/`?clean`/`?deck-only` independence, `show_machine_tools_at_start`
setdefault behaviour, plus two guard tests asserting upstream `index.html` still
has the `</body>` anchor and the ids the CSS targets.

### `tests/test_recorder_js.py` — not written

The Playwright layer. See step 03 — this is the whole reason playwright was added.

---

## The plan

Ordered by dependency: each step needs the one before it. Steps 01 and 02 are the
gate — until they pass, the rest is building on unverified ground.

### 01 · Install the dev group and run what exists — *gate*

Nothing has executed yet. This is the first real signal.

```
uv sync --group dev
uv run pytest tests/ -v
```

### 02 · Fix the failures, and expect several — *gate*

Three places are most likely to break, in rough order of probability:

**The `serve` fixture's teardown.** It calls `httpd.shutdown()` on `vis._httpd`,
but `_run_file_server` sets that attribute inside a daemon thread and releases its
lock before assigning. If teardown races the thread, tests hang or leak servers.

**`Deck(name="test-deck")`.** Unverified against pylabrobot 0.2.2 — `Deck` may
require size arguments. If so, use a concrete deck from `pylabrobot.resources`
instead, matching whatever the workshops import.

**Port fixtures.** `_free_port()` binds and closes before the server binds, so a
collision is possible though unlikely. If it flakes, note that the visualizer's own
increment-until-free loop will silently move the port and the test's URL goes stale.

### 03 · Write the Playwright layer — *main work*

**Do not load the real visualizer page for the recorder tests.** The stock
`index.html` pulls konva from unpkg and jszip/html2canvas from cdnjs, and `vis.js`
expects a live websocket. Instead serve a harness page that stubs the four globals
the injected script wraps — `processCentralEvent`, `startRecording`,
`stopRecording`, `renderedGifBlob` — plus the two elements it touches,
`#current-value` and `#gif-frame-rate`. Then inject the real `_RECORDER_JS` string
imported from the module, so the shipped code is what runs.

Assertions worth having:

- Frame interval **clamps to 1–96** and rounds; the slider value and the
  `Frame Interval:` label both update.
- `class_start_gif` clears a stale `renderedGifBlob` before starting — otherwise
  the previous recording downloads again.
- `waitForRenderedBlob` polls and fires the download once the blob appears; it
  gives up after 1200 attempts at 100ms.
- The **`.gif` suffix is appended** when the filename lacks it, and not doubled when
  it has it. Assert via a captured Playwright `download` event and
  `suggested_filename()`.
- Unknown events still fall through to the original `processCentralEvent` — the
  wrapper must not swallow the stock protocol.

For declutter, a **separate** browser test can load the genuine served page, since
the elements it hides (`aside`, `#sidepanel`, `#sidepanel-resize-handle`,
`#home-button`) are static markup. Use `page.route` to abort the three CDN URLs so
it works offline, then assert `body.class-minimal` is applied and that computed
style is actually `display: none` — not merely that the CSS text is present, which
`test_page_injection.py` already covers.

### 04 · Wire it into CI

Add a `tests` job to `.github/workflows/workshops.yml`. The existing `paths:`
filters already include `bme590/**`, so they need no change.

```yaml
- run: uv sync --group dev
- run: uv run playwright install --with-deps chromium
- run: uv run pytest tests/ -v
```

Ubuntu only is fine — the code under test is a string-splicing HTTP handler and
browser JS, neither platform-sensitive. The existing three-OS matrix covers the
installer, which is where platform actually matters.

### 05 · Clean up and commit

Delete the seven orphaned `.pyc` files in `bme590/__pycache__/`
(`test_browser_kernel`, `test_chrome`, `test_demo`, `test_inline`,
`test_pyodide_transport`, `test_startup`, `test_vendor`) — dead bytecode from the
removed browser-kernel architecture that makes the repo look tested when it isn't.

Currently on `main` with no branch. Branch before committing.

---

## Decisions already made

Settled last session — reopen only with a reason, don't re-litigate.

- **Playwright over a JS test runner.** Half of `visualizer_ext.py` ships as browser
  code unreachable from Python. A DOM shim would test a copy, not the artifact.
- **Real visualizer, faked transport.** `GifRecorder` rejects non-`Visualizer`
  arguments, so a free-standing mock can't be used. Fixtures build the genuine
  object and swap only its two transport methods.
- **Dev group excluded from `default-groups`.** Students run `uv sync` with no
  flags; adding pytest and a browser binary to that path would meaningfully slow a
  cold install for no student benefit.
- **Guard tests against upstream drift.** `_run_file_server` splices on `</body>`
  and the CSS targets stock ids. A pylabrobot upgrade could break both while every
  behavioural test still passed, so the assumptions are asserted directly.

---

## Definition of done

- [ ] `uv run pytest tests/ -v` passes locally on Windows and in CI on Ubuntu.
- [ ] Every branch of the declutter logic is covered: kwarg, each of the three query
      aliases, both off, and the flag-ordering constraint.
- [ ] The injected browser JS runs in a real Chromium, with the `.gif` download
      filename asserted from a captured download event.
- [ ] `pytest -m "not browser"` still passes with no browser installed, so a
      contributor without Chromium isn't blocked.
- [ ] Stale `.pyc` files gone; work committed on a branch off `main`.
