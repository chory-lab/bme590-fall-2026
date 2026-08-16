/**
 * Unit tests for the notebook engine (demo_notebook.js).
 *
 * Everything the demo page does that is not drawing pixels lives in that
 * module, so this covers the cell model, the nbformat round-trip, markdown
 * rendering and the Jupyter keymap without a browser.
 *
 *   node plr_workshops/test_notebook_js.mjs
 */

import assert from "node:assert/strict";
import {
  NotebookModel, Keymap, STARTER_CELLS, makeCell,
  renderMarkdown, toIpynb, fromIpynb, splitLines, joinLines,
  streamOutput, resultOutput, errorOutput, outputText,
} from "./demo_notebook.js";

let passed = 0;
function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log("  ok   " + name);
  } catch (e) {
    console.error("  FAIL " + name + "\n       " + (e.message || e).split("\n").join("\n       "));
    process.exitCode = 1;
  }
}

/* ------------------------------------------------------------------ *
 * Cell model
 * ------------------------------------------------------------------ */
console.log("\ncell model");

test("cells get stable ids that survive reordering", () => {
  const m = new NotebookModel([
    { kind: "code", source: "a" }, { kind: "code", source: "b" }, { kind: "code", source: "c" },
  ]);
  const ids = m.cells.map((c) => c.id);
  assert.equal(new Set(ids).size, 3, "ids must be unique");
  m.move(ids[2], -2);
  assert.deepEqual(m.cells.map((c) => c.source), ["c", "a", "b"]);
  assert.equal(m.get(ids[2]).source, "c", "id still resolves after a move");
});

test("md is normalised to markdown, unknown kinds become code", () => {
  const m = new NotebookModel([{ kind: "md", source: "# hi" }, { kind: "code", source: "1" }]);
  assert.equal(m.cells[0].kind, "markdown");
  assert.equal(m.cells[0].rendered, true, "existing markdown starts rendered");
});

test("insert above/below lands in the right slot and selects the new cell", () => {
  const m = new NotebookModel([{ kind: "code", source: "a" }, { kind: "code", source: "b" }]);
  m.select(m.cells[1].id);
  const below = m.insertBelow("code", "z");
  assert.deepEqual(m.cells.map((c) => c.source), ["a", "b", "z"]);
  assert.equal(m.activeId, below.id);
  m.select(m.cells[0].id);
  m.insertAbove("markdown", "top");
  assert.deepEqual(m.cells.map((c) => c.source), ["top", "a", "b", "z"]);
});

test("delete selects a neighbour and dd-undo restores in place", () => {
  const m = new NotebookModel([
    { kind: "code", source: "a" }, { kind: "code", source: "b" }, { kind: "code", source: "c" },
  ]);
  const b = m.cells[1].id;
  m.select(b);
  m.remove(b);
  assert.deepEqual(m.cells.map((c) => c.source), ["a", "c"]);
  assert.equal(m.active.source, "c", "selection moves to the next cell");
  m.undoDelete();
  assert.deepEqual(m.cells.map((c) => c.source), ["a", "b", "c"]);
  assert.equal(m.active.source, "b", "restored cell is selected");
});

test("deleting the last cell leaves an empty code cell behind", () => {
  const m = new NotebookModel([{ kind: "code", source: "only" }]);
  m.remove(m.cells[0].id);
  assert.equal(m.cells.length, 1);
  assert.equal(m.cells[0].source, "");
  assert.equal(m.activeId, m.cells[0].id);
});

test("move refuses to walk off either end", () => {
  const m = new NotebookModel([{ kind: "code", source: "a" }, { kind: "code", source: "b" }]);
  assert.equal(m.move(m.cells[0].id, -1), false);
  assert.equal(m.move(m.cells[1].id, 1), false);
  assert.deepEqual(m.cells.map((c) => c.source), ["a", "b"]);
});

test("selectDelta clamps at the ends", () => {
  const m = new NotebookModel([{ kind: "code", source: "a" }, { kind: "code", source: "b" }]);
  m.selectDelta(-1);
  assert.equal(m.active.source, "a");
  m.selectDelta(1); m.selectDelta(1);
  assert.equal(m.active.source, "b");
});

test("changing a cell's type clears its stale outputs", () => {
  const m = new NotebookModel([{ kind: "code", source: "print(1)" }]);
  const id = m.cells[0].id;
  m.beginExec(id);
  m.addOutput(id, streamOutput("1\n"));
  m.setKind(id, "markdown");
  assert.deepEqual(m.cells[0].outputs, []);
  assert.equal(m.cells[0].execCount, null);
});

test("execution counter is global and monotonic, like a kernel's", () => {
  const m = new NotebookModel([
    { kind: "code", source: "a" }, { kind: "code", source: "b" },
  ]);
  const [a, b] = m.cells.map((c) => c.id);
  assert.equal(m.beginExec(a), 1);
  assert.equal(m.beginExec(b), 2);
  assert.equal(m.beginExec(a), 3, "re-running a cell gets the next number, not its old one");
  assert.equal(m.get(b).execCount, 2, "other cells keep their number");
});

test("beginExec clears the previous run's outputs", () => {
  const m = new NotebookModel([{ kind: "code", source: "x" }]);
  const id = m.cells[0].id;
  m.beginExec(id);
  m.addOutput(id, streamOutput("old\n"));
  m.beginExec(id);
  assert.deepEqual(m.get(id).outputs, []);
});

test("consecutive stdout chunks coalesce, stderr stays separate", () => {
  const m = new NotebookModel([{ kind: "code", source: "x" }]);
  const id = m.cells[0].id;
  m.beginExec(id);
  m.addOutput(id, streamOutput("one\n"));
  m.addOutput(id, streamOutput("two\n"));
  m.addOutput(id, streamOutput("bad\n", "stderr"));
  const outs = m.get(id).outputs;
  assert.equal(outs.length, 2);
  assert.equal(outs[0].text, "one\ntwo\n");
  assert.equal(outs[1].name, "stderr");
});

test("runnable() skips markdown and blank cells", () => {
  const m = new NotebookModel([
    { kind: "markdown", source: "# title" },
    { kind: "code", source: "   " },
    { kind: "code", source: "print(1)" },
  ]);
  assert.deepEqual(m.runnable().map((c) => c.source), ["print(1)"]);
});

test("resetExecution wipes counters and outputs (restart kernel)", () => {
  const m = new NotebookModel([{ kind: "code", source: "x" }, { kind: "code", source: "y" }]);
  m.cells.forEach((c) => { m.beginExec(c.id); m.addOutput(c.id, streamOutput("hi\n")); });
  m.resetExecution();
  assert.deepEqual(m.cells.map((c) => c.execCount), [null, null]);
  assert.deepEqual(m.cells.map((c) => c.outputs.length), [0, 0]);
  assert.equal(m.beginExec(m.cells[0].id), 1, "counter restarts at 1");
});

/* ------------------------------------------------------------------ *
 * nbformat
 * ------------------------------------------------------------------ */
console.log("\nnbformat round-trip");

test("splitLines/joinLines match nbformat's line convention", () => {
  assert.deepEqual(splitLines("a\nb"), ["a\n", "b"]);
  assert.deepEqual(splitLines("a\n"), ["a\n"]);
  assert.deepEqual(splitLines(""), []);
  assert.equal(joinLines(["a\n", "b"]), "a\nb");
  assert.equal(joinLines("plain"), "plain");
});

test("toIpynb emits a valid nbformat 4.5 document", () => {
  const m = new NotebookModel(STARTER_CELLS);
  const nb = toIpynb(m);
  assert.equal(nb.nbformat, 4);
  assert.equal(nb.nbformat_minor, 5);
  assert.equal(nb.metadata.kernelspec.language, "python");
  assert.equal(nb.cells.length, STARTER_CELLS.length);
  for (const c of nb.cells) {
    assert.ok(["code", "markdown"].includes(c.cell_type));
    assert.ok(Array.isArray(c.source));
    assert.ok(c.source.every((l) => typeof l === "string"));
    if (c.cell_type === "code") {
      assert.ok(Array.isArray(c.outputs));
      assert.ok("execution_count" in c);
    } else {
      assert.ok(!("outputs" in c), "markdown cells must not carry outputs");
    }
  }
});

test("outputs survive the round-trip with their execution counts", () => {
  const m = new NotebookModel([{ kind: "code", source: "1 + 1" }]);
  const id = m.cells[0].id;
  m.beginExec(id);
  m.addOutput(id, streamOutput("working\n"));
  m.addOutput(id, resultOutput("2", 1));
  const back = fromIpynb(JSON.parse(JSON.stringify(toIpynb(m))));
  const cell = back.cells[0];
  assert.equal(cell.source, "1 + 1");
  assert.equal(cell.execCount, 1);
  assert.equal(cell.outputs.length, 2);
  assert.equal(cell.outputs[0].text, "working\n");
  assert.equal(cell.outputs[1].data["text/plain"], "2");
  assert.equal(cell.outputs[1].execution_count, 1);
});

test("error outputs keep ename/evalue/traceback", () => {
  const m = new NotebookModel([{ kind: "code", source: "1/0" }]);
  const id = m.cells[0].id;
  m.beginExec(id);
  m.addOutput(id, errorOutput(
    "Traceback (most recent call last):\n  File \"<exec>\", line 1\nZeroDivisionError: division by zero"));
  const back = fromIpynb(JSON.parse(JSON.stringify(toIpynb(m))));
  const err = back.cells[0].outputs[0];
  assert.equal(err.output_type, "error");
  assert.equal(err.ename, "ZeroDivisionError");
  assert.equal(err.evalue, "division by zero");
  assert.equal(err.traceback.length, 3);
});

test("a full model round-trips to identical sources and kinds", () => {
  const m = new NotebookModel(STARTER_CELLS);
  const back = fromIpynb(JSON.parse(JSON.stringify(toIpynb(m))));
  assert.deepEqual(back.cells.map((c) => c.kind), m.cells.map((c) => c.kind));
  assert.deepEqual(back.cells.map((c) => c.source), m.cells.map((c) => c.source));
});

test("fromIpynb reads a foreign notebook (string sources, display_data, raw cells)", () => {
  const nb = {
    cells: [
      { cell_type: "raw", source: "ignored" },
      { cell_type: "markdown", source: "# Hi\n" },
      { cell_type: "code", execution_count: 7, source: ["x = 1\n", "x\n"],
        outputs: [{ output_type: "display_data", data: { "text/plain": "1" } }] },
    ],
    metadata: {}, nbformat: 4, nbformat_minor: 4,
  };
  const m = fromIpynb(nb);
  assert.equal(m.cells.length, 2, "raw cells are dropped");
  assert.equal(m.cells[0].kind, "markdown");
  assert.equal(m.cells[1].source, "x = 1\nx\n");
  assert.equal(m.cells[1].execCount, 7);
  assert.equal(m.execCounter, 7, "counter resumes above the highest imported count");
  assert.equal(m.cells[1].outputs[0].data["text/plain"], "1");
});

test("fromIpynb rejects things that are not notebooks", () => {
  assert.throws(() => fromIpynb({}), /no cells/);
  assert.throws(() => fromIpynb(null), /no cells/);
});

test("an empty notebook still opens with one code cell", () => {
  const m = fromIpynb({ cells: [], nbformat: 4, nbformat_minor: 5, metadata: {} });
  assert.equal(m.cells.length, 1);
  assert.equal(m.cells[0].kind, "code");
});

/* ------------------------------------------------------------------ *
 * Markdown
 * ------------------------------------------------------------------ */
console.log("\nmarkdown");

test("headings, emphasis, code and links render", () => {
  const html = renderMarkdown("# Title\n\nSome **bold** and *thin* and `code`.\n\n[docs](https://x.y)");
  assert.match(html, /<h1>Title<\/h1>/);
  assert.match(html, /<strong>bold<\/strong>/);
  assert.match(html, /<em>thin<\/em>/);
  assert.match(html, /<code>code<\/code>/);
  assert.match(html, /<a href="https:\/\/x\.y" target="_blank" rel="noopener">docs<\/a>/);
});

test("lists group into a single ul/ol and close again", () => {
  const html = renderMarkdown("- one\n- two\n\ntext\n\n1. first\n2. second");
  assert.equal((html.match(/<ul>/g) || []).length, 1);
  assert.equal((html.match(/<\/ul>/g) || []).length, 1);
  assert.equal((html.match(/<li>/g) || []).length, 4);
  assert.match(html, /<ol>/);
});

test("fenced code blocks are literal, not re-parsed", () => {
  const html = renderMarkdown("```python\nx = **1**\n# not a heading\n```");
  assert.match(html, /<pre class="md-code"><code>x = \*\*1\*\*\n# not a heading<\/code><\/pre>/);
});

test("html in markdown is escaped", () => {
  const html = renderMarkdown('<img src=x onerror="alert(1)">');
  assert.ok(!html.includes("<img"), "raw tags must not survive");
  assert.match(html, /&lt;img/);
});

test("an unterminated fence still closes", () => {
  const html = renderMarkdown("```\nleft open");
  assert.match(html, /<\/code><\/pre>/);
});

test("the starter notebook's markdown renders without leaking markers", () => {
  for (const c of STARTER_CELLS.filter((c) => c.kind === "markdown")) {
    const html = renderMarkdown(c.source);
    assert.ok(!/\*\*/.test(html), `unrendered bold in: ${c.source.slice(0, 40)}`);
    assert.ok(!/^#/m.test(html), `unrendered heading in: ${c.source.slice(0, 40)}`);
  }
});

/* ------------------------------------------------------------------ *
 * Keymap
 * ------------------------------------------------------------------ */
console.log("\nkeymap");

const key = (k, opts = {}) => ({ key: k, ctrlKey: false, metaKey: false,
                                 shiftKey: false, altKey: false, ...opts });

test("the three run bindings match Jupyter", () => {
  const km = new Keymap();
  assert.equal(km.handle(key("Enter", { shiftKey: true }), "edit"), "run-select-below");
  assert.equal(km.handle(key("Enter", { ctrlKey: true }), "edit"), "run");
  assert.equal(km.handle(key("Enter", { metaKey: true }), "edit"), "run");
  assert.equal(km.handle(key("Enter", { altKey: true }), "edit"), "run-insert-below");
});

test("Enter and Esc switch modes; a plain Enter in the editor is a newline", () => {
  const km = new Keymap();
  assert.equal(km.handle(key("Enter"), "command"), "enter-edit");
  assert.equal(km.handle(key("Enter"), "edit"), null);
  assert.equal(km.handle(key("Escape"), "edit"), "enter-command");
});

test("command-mode letters are inert while editing", () => {
  const km = new Keymap();
  for (const k of ["a", "b", "d", "m", "y", "z", "j", "k"]) {
    assert.equal(km.handle(key(k), "edit"), null, `${k} must type a character, not run a command`);
  }
});

test("dd deletes, but a single d does nothing", () => {
  const km = new Keymap();
  assert.equal(km.handle(key("d"), "command"), null);
  assert.equal(km.handle(key("d"), "command"), "delete");
  assert.equal(km.handle(key("d"), "command"), null, "the pair resets after firing");
});

test("d followed by another key does not delete later", () => {
  const km = new Keymap();
  assert.equal(km.handle(key("d"), "command"), null);
  assert.equal(km.handle(key("j"), "command"), "select-next");
  assert.equal(km.handle(key("d"), "command"), null, "the pending d was cancelled");
});

test("navigation, insertion, type changes and undo", () => {
  const km = new Keymap();
  const cases = {
    a: "insert-above", b: "insert-below", z: "undo-delete",
    m: "to-markdown", y: "to-code",
    k: "select-prev", ArrowUp: "select-prev",
    j: "select-next", ArrowDown: "select-next",
    J: "move-down", K: "move-up",
  };
  for (const [k, cmd] of Object.entries(cases)) {
    assert.equal(km.handle(key(k), "command"), cmd, `${k} -> ${cmd}`);
  }
});

test("ctrl/cmd+S saves from either mode", () => {
  const km = new Keymap();
  assert.equal(km.handle(key("s", { ctrlKey: true }), "edit"), "save");
  assert.equal(km.handle(key("s", { metaKey: true }), "command"), "save");
  assert.equal(km.handle(key("s"), "command"), null, "a bare s is not a shortcut");
});

/* ------------------------------------------------------------------ *
 * Output helpers
 * ------------------------------------------------------------------ */
console.log("\noutputs");

test("errorOutput parses the exception line off a traceback", () => {
  const out = errorOutput("Traceback (most recent call last):\n  ...\nValueError: bad thing\n");
  assert.equal(out.ename, "ValueError");
  assert.equal(out.evalue, "bad thing");
  const bare = errorOutput("KeyboardInterrupt");
  assert.equal(bare.ename, "KeyboardInterrupt");
});

test("outputText flattens every output kind", () => {
  assert.equal(outputText(streamOutput("hi\n")), "hi\n");
  assert.equal(outputText(resultOutput("42", 3)), "42");
  assert.equal(outputText(errorOutput("ValueError: x")), "ValueError: x");
});

/* ------------------------------------------------------------------ *
 * The starter notebook itself
 * ------------------------------------------------------------------ */
console.log("\nstarter notebook");

test("starter cells are well formed", () => {
  assert.ok(STARTER_CELLS.length >= 6);
  for (const c of STARTER_CELLS) {
    assert.ok(["code", "markdown"].includes(c.kind), `bad kind ${c.kind}`);
    assert.ok(c.source.trim().length > 0, "no blank starter cells");
  }
});

test("the starter protocol builds the deck before it uses it", () => {
  const code = STARTER_CELLS.filter((c) => c.kind === "code").map((c) => c.source);
  const joined = code.join("\n");
  assert.ok(joined.includes("set_volume_tracking(True)"), "tracking must be on");
  const deckAt = joined.indexOf("lh = LiquidHandler");
  const visAt = joined.indexOf("InlineVisualizer(");
  const pipetteAt = joined.indexOf("pick_up_tips");
  assert.ok(deckAt > 0 && visAt > deckAt && pipetteAt > visAt,
            "order must be: deck, visualizer, pipetting");
  assert.ok(!/time\.sleep/.test(joined),
            "time.sleep blocks the single-threaded Pyodide runtime");
});

console.log(`\n${passed} checks passed.`);
if (process.exitCode) console.error("SOME CHECKS FAILED");
