/**
 * End-to-end check of the demo's kernel path, under a real Pyodide runtime.
 *
 * This runs what the page runs: the starter notebook's own cells, in order,
 * through `plr_workshops.browser_kernel.run_cell`, with `PyodideTransport`
 * mounted against a stub DOM so the visualizer's event stream can be asserted
 * on. It is the browser check minus the pixels — everything between "user
 * presses Run all" and "postMessage reaches the iframe".
 *
 *   node plr_workshops/test_demo_pyodide.mjs
 *
 * Needs the `pyodide` npm package; point PYODIDE_DIR at it if it is not in
 * ./node_modules.
 */

import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { STARTER_CELLS } from "./demo_notebook.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.dirname(HERE);
const PY_DIR = path.join(REPO, "demo", "py", "plr_workshops");

const CANDIDATES = [
  process.env.PYODIDE_DIR,
  path.join(REPO, "node_modules", "pyodide"),
  path.join(HERE, "node_modules", "pyodide"),
  "C:/Users/stefa/AppData/Local/Temp/opencode/pyodide-spike/node_modules/pyodide",
].filter(Boolean);
const PYODIDE_DIR = CANDIDATES.find((p) => existsSync(path.join(p, "pyodide.mjs")));
if (!PYODIDE_DIR) {
  console.error("pyodide package not found; set PYODIDE_DIR. Looked in:\n  " +
                CANDIDATES.join("\n  "));
  process.exit(2);
}
if (!existsSync(PY_DIR)) {
  console.error(`no built demo at ${PY_DIR}; run: python -m plr_workshops.build_demo --force`);
  process.exit(2);
}

let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log("  ok   " + name);
  } catch (e) {
    console.error("  FAIL " + name + "\n       " + String(e.message || e).split("\n").join("\n       "));
    process.exitCode = 1;
  }
}

/* ------------------------------------------------------------------ *
 * A stub DOM, standing in for the demo page.
 * ------------------------------------------------------------------ */
const posted = [];         // every message the transport pushed at the iframe
let messageListener = null;
const iframe = {
  id: "plr-deck-frame",
  parentNode: null,
  attrs: {},
  setAttribute(k, v) { this.attrs[k] = v; },
  contentWindow: {
    postMessage: (msg) => {
      // A real window.postMessage structured-clones its payload and would
      // throw DataCloneError on a JS Map, which is what to_js produces from a
      // dict unless it is told otherwise.
      if (msg instanceof Map) throw new Error("DataCloneError: could not be cloned");
      if (typeof msg.__plrEvent !== "string") {
        throw new Error("payload has no __plrEvent string property: " + String(msg));
      }
      posted.push(msg.__plrEvent);
    },
  },
};
const deckContainer = {
  id: "plr-deck",
  children: [],
  appendChild(child) { child.parentNode = this; this.children.push(child); },
  removeChild(child) { child.parentNode = null; },
};
globalThis.window = {
  addEventListener: (name, fn) => { if (name === "message") messageListener = fn; },
  removeEventListener: () => { messageListener = null; },
};
globalThis.document = {
  getElementById: (id) => (id === "plr-deck" ? deckContainer
                        : id === "plr-deck-frame" ? (iframe.parentNode ? iframe : null)
                        : null),
  createElement: () => iframe,
};

/* ------------------------------------------------------------------ *
 * Boot the kernel exactly as the page does.
 * ------------------------------------------------------------------ */
const { loadPyodide } = await import(pathToFileURL(path.join(PYODIDE_DIR, "pyodide.mjs")).href);

console.log("booting pyodide + pylabrobot (this takes a minute the first time)…");
const pyodide = await loadPyodide({ indexURL: PYODIDE_DIR });
await pyodide.loadPackage(["micropip", "ssl"], { messageCallback: () => {} });
await pyodide.runPythonAsync('import micropip; await micropip.install("pylabrobot==0.2.2")');

const PY_MODULES = ["__init__.py", "transport.py", "inline.py", "frontend.py",
                    "pyodide_transport.py", "browser_kernel.py"];
pyodide.FS.mkdir("/home/pyodide/plr_workshops");
for (const f of PY_MODULES) {
  pyodide.FS.writeFile(`/home/pyodide/plr_workshops/${f}`,
                       readFileSync(path.join(PY_DIR, f), "utf-8"));
}
const kernel = pyodide.pyimport("plr_workshops.browser_kernel");

// stdout routing, as index.html wires it
let stream = [];
pyodide.setStdout({ batched: (s) => stream.push(s) });
pyodide.setStderr({ batched: (s) => stream.push(s) });

const run = async (src) => JSON.parse(await kernel.run_cell(src));

/* ------------------------------------------------------------------ *
 * 1. Kernel semantics the notebook UI depends on
 * ------------------------------------------------------------------ */
console.log("\nkernel semantics");

{
  stream = [];
  const r = await run("x = 41");
  check("a statement produces no Out[n] value", () => {
    assert.equal(r.ok, true);
    assert.equal(r.repr, null);
  });

  const r2 = await run("x + 1");
  check("a trailing expression comes back as its repr", () => {
    assert.equal(r2.repr, "42");
  });

  const r3 = await run("print('hello'); 'value'");
  check("stdout and the value are reported separately", () => {
    assert.equal(r3.repr, "'value'");
    assert.equal(stream.join(""), "hello", "print reached the stdout hook");
  });

  check("stdout arrives newline-stripped, so the UI must re-add it", () => {
    assert.ok(!stream.some((s) => s.endsWith("\n")),
              `pyodide batched chunks: ${JSON.stringify(stream)}`);
  });

  const r4 = await run("def f():\n  return 3\n\nf()");
  check("multi-line cells with a trailing call still yield a value", () => {
    assert.equal(r4.repr, "3");
  });

  const r5 = await run("import asyncio\nawait asyncio.sleep(0)\n'awaited'");
  check("top-level await works", () => assert.equal(r5.repr, "'awaited'"));

  const err = await run("1/0");
  check("an exception returns a Python traceback, not a JS message", () => {
    assert.equal(err.ok, false);
    assert.equal(err.ename, "ZeroDivisionError");
    assert.equal(err.evalue, "division by zero");
    assert.match(err.traceback, /Traceback \(most recent call last\)/);
    assert.match(err.traceback, /ZeroDivisionError: division by zero$/);
  });

  const syn = await run("def broken(:");
  check("a syntax error is reported the same way", () => {
    assert.equal(syn.ok, false);
    assert.match(syn.ename, /SyntaxError/);
  });

  const survives = await run("x");
  check("the namespace survives a failed cell", () => assert.equal(survives.repr, "41"));

  kernel.reset();
  const gone = await run("x");
  check("restart clears the namespace", () => {
    assert.equal(gone.ok, false);
    assert.equal(gone.ename, "NameError");
  });
  const stillThere = await run("import json; json.dumps([1])");
  check("restart keeps imported modules cached", () => {
    assert.equal(stillThere.repr, '\'[1]\'');
  });
  kernel.reset();

  const big = await run("'x' * 50000");
  check("an enormous repr is truncated rather than freezing the page", () => {
    assert.ok(big.repr.length < 11000, `repr was ${big.repr.length} chars`);
    assert.match(big.repr, /more characters/);
  });

  const weird = await run(
    "class Bad:\n  def __repr__(self): raise RuntimeError('nope')\n\nBad()");
  check("a broken __repr__ does not break the cell", () => {
    assert.equal(weird.ok, true);
    assert.match(weird.repr, /unrepresentable Bad/);
  });
  kernel.reset();
}

/* ------------------------------------------------------------------ *
 * 2. The starter notebook, run in order like "Run all"
 * ------------------------------------------------------------------ */
console.log("\nstarter notebook under the kernel");

const codeCells = STARTER_CELLS.filter((c) => c.kind === "code");
stream = [];
const results = [];
for (const [i, cell] of codeCells.entries()) {
  const r = await run(cell.source);
  results.push(r);
  if (!r.ok) {
    console.error(`  FAIL cell ${i} raised:\n${r.traceback}`);
    process.exitCode = 1;
    break;
  }
  // The visualizer only mounts once the transport's iframe reports ready;
  // the page gets that from the iframe's load event.
  if (messageListener && posted.length === 0) {
    messageListener({ data: { __plrReady: true } });
  }
}

check("every starter code cell runs clean", () => {
  assert.equal(results.length, codeCells.length);
  assert.ok(results.every((r) => r.ok), "a cell raised");
});

check("the LiquidHandler cell shows a value, as In/Out expects", () => {
  const reprs = results.map((r) => r.repr).filter(Boolean);
  assert.ok(reprs.some((r) => /LiquidHandler/.test(r)), `saw: ${JSON.stringify(reprs)}`);
});

check("the pipetting cell reports the volume A1 has left", () => {
  assert.ok(results.some((r) => r.repr === "150.0"),
            `expected 150.0 uL left in A1, got ${JSON.stringify(results.map((r) => r.repr))}`);
});

check("the chatterbox backend narrates the protocol on stdout", () => {
  const text = stream.join("\n");
  for (const phrase of ["Picking up tips", "Aspirating", "Dispensing", "Dropping tips"]) {
    assert.match(text, new RegExp(phrase));
  }
});

/* ------------------------------------------------------------------ *
 * 3. The event stream that draws the deck
 * ------------------------------------------------------------------ */
console.log("\nvisualizer event stream");

const events = posted.map((m) => JSON.parse(m));

// DUMP_EVENTS=1 prints the stream the frontend actually receives — the fastest
// way to see why a deck did not draw what you expected.
if (process.env.DUMP_EVENTS) {
  for (const [i, e] of events.entries()) {
    const keys = e.event === "set_state" ? Object.keys(e.data) : Object.keys(e.data || {});
    console.log(`  #${i} ${e.event}: ${keys.slice(0, 8).join(", ")}${keys.length > 8 ? " …" : ""}`);
  }
  const sample = events.find((e) => e.event === "set_state");
  console.log("  sample set_state:", JSON.stringify(sample && sample.data).slice(0, 1200));
  for (const e of events.filter((x) => x.event === "set_state" && x.data.plate_0_well_A1)) {
    console.log("  well A1:", JSON.stringify(e.data.plate_0_well_A1));
  }
}

check("the transport mounted a self-contained visualizer page", () => {
  assert.equal(iframe.parentNode, deckContainer, "iframe not appended to #plr-deck");
  assert.match(iframe.attrs.style, /height: 100%/, "deck must fill its pane");
  assert.ok(iframe.attrs.srcdoc.includes("processCentralEvent"), "srcdoc is not the visualizer");
});

check("every message is a well-formed wire event", () => {
  assert.ok(events.length > 0, "no events reached the iframe");
  for (const e of events) {
    assert.deepEqual(Object.keys(e).sort(), ["data", "event", "id", "version"]);
    assert.equal(typeof e.id, "string");
  }
});

check("the stream opens with the deck, then streams state", () => {
  assert.equal(events[0].event, "set_root_resource");
  assert.ok(events.some((e) => e.event === "set_state"), "no set_state events");
});

check("the deck the frontend receives holds the plate and the tip rack", () => {
  const root = JSON.stringify(events[0].data);
  for (const name of ["plate_0", "tips_0", "plates", "tips"]) {
    assert.ok(root.includes(`"${name}"`), `deck missing ${name}`);
  }
});

const states = events.filter((e) => e.event === "set_state").map((e) => e.data);
// A well's state is its volume tracker: {volume, pending_volume, max_volume}.
const volumeOf = (well) => well.volume;

check("A1's volume reaches the frontend, filled and then drawn down", () => {
  const a1 = states.filter((s) => s.plate_0_well_A1).map((s) => volumeOf(s.plate_0_well_A1));
  assert.ok(a1.length > 0, "no plate_0_well_A1 state was ever sent");
  assert.ok(a1.includes(200), `A1 never showed the 200 uL fill: ${JSON.stringify(a1)}`);
  assert.ok(a1.includes(150), `A1 never dropped to 150 uL: ${JSON.stringify(a1)}`);
});

check("B1 receives the 50 uL that A1 gave up", () => {
  const b1 = states.filter((s) => s.plate_0_well_B1).map((s) => volumeOf(s.plate_0_well_B1));
  assert.ok(b1.includes(250), `B1 never reached 250 uL: ${JSON.stringify(b1)}`);
});

check("the tip leaves the rack and comes back", () => {
  const spot = states.filter((s) => s.tips_0_tipspot_A1).map((s) => s.tips_0_tipspot_A1);
  assert.ok(spot.length > 0, "tip spot A1 never changed state");
  assert.ok(spot.some((v) => v.tip === null), "the tip never left the rack");
  assert.ok(spot.some((v) => v.tip !== null), "the tip never came back");
});

check("the deck animates: each step lands as its own frame", () => {
  // A cell that never yields to the event loop delivers one collapsed state at
  // the end and the deck appears to teleport. The starter protocol's
  // asyncio.sleep calls are what break it into visible steps.
  assert.ok(states.length >= 5,
            `only ${states.length} state frames; the protocol is not yielding`);
});

/* ------------------------------------------------------------------ *
 * 4. Teardown
 * ------------------------------------------------------------------ */
console.log("\nteardown");

const stopped = await run("await vis.stop()");
check("stopping the visualizer removes the iframe and its listener", () => {
  assert.equal(stopped.ok, true, stopped.traceback);
  assert.equal(iframe.parentNode, null);
  assert.equal(messageListener, null);
});

console.log(`\n${passed} checks passed.`);
if (process.exitCode) console.error("SOME CHECKS FAILED");
