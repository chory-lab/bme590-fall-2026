/**
 * The notebook engine for the Pyodide demo page: the cell model, the nbformat
 * round-trip, markdown rendering and the Jupyter keymap.
 *
 * Everything here is pure JavaScript with no DOM and no Pyodide, so the whole
 * of it runs under `node --test`-style checks (see test_notebook_js.mjs). The
 * page's index.html holds only the thin DOM layer that draws this model and
 * feeds cell sources to the kernel.
 */

/* ------------------------------------------------------------------ *
 * Outputs (nbformat shapes, so the .ipynb round-trip is a no-op)
 * ------------------------------------------------------------------ */

export function streamOutput(text, name = "stdout") {
  return { output_type: "stream", name, text };
}

export function resultOutput(text, execution_count = null) {
  return {
    output_type: "execute_result",
    data: { "text/plain": text },
    metadata: {},
    execution_count,
  };
}

export function errorOutput(traceback) {
  const lines = String(traceback).replace(/\s+$/, "").split("\n");
  const last = lines[lines.length - 1] || "";
  const m = /^([A-Za-z_][\w.]*)(?:: (.*))?$/.exec(last);
  return {
    output_type: "error",
    ename: m ? m[1] : "Error",
    evalue: m && m[2] ? m[2] : last,
    traceback: lines,
  };
}

/** Flatten an output into the text a terminal-ish view would show. */
export function outputText(out) {
  if (out.output_type === "stream") return out.text;
  if (out.output_type === "execute_result") return out.data["text/plain"] || "";
  if (out.output_type === "error") return out.traceback.join("\n");
  return "";
}

/* ------------------------------------------------------------------ *
 * The cell model
 * ------------------------------------------------------------------ */

let _nextId = 1;
function newId() {
  return "c" + _nextId++;
}

export function makeCell(kind = "code", source = "") {
  return {
    id: newId(),
    kind, // "code" | "markdown"
    source,
    outputs: [],
    execCount: null,
    // markdown cells start rendered; a fresh empty one starts in edit view.
    rendered: kind === "markdown" && source.trim() !== "",
  };
}

export class NotebookModel {
  constructor(cells) {
    const list = (cells && cells.length ? cells : [{ kind: "code", source: "" }]).map((c) =>
      makeCell(c.kind === "markdown" || c.kind === "md" ? "markdown" : "code", c.source || "")
    );
    if (cells) {
      // Preserve any outputs/exec counts handed in (e.g. from an .ipynb).
      cells.forEach((c, i) => {
        if (c.outputs) list[i].outputs = c.outputs;
        if (c.execCount != null) list[i].execCount = c.execCount;
      });
    }
    this.cells = list;
    this.activeId = list[0].id;
    this.execCounter = list.reduce((m, c) => Math.max(m, c.execCount || 0), 0);
    this._trash = [];
  }

  /* -- lookup -- */
  indexOf(id) {
    return this.cells.findIndex((c) => c.id === id);
  }
  get(id) {
    return this.cells[this.indexOf(id)] || null;
  }
  get active() {
    return this.get(this.activeId);
  }
  get activeIndex() {
    return this.indexOf(this.activeId);
  }

  /* -- selection -- */
  select(id) {
    if (this.indexOf(id) >= 0) this.activeId = id;
    return this.active;
  }
  selectDelta(delta) {
    const i = this.activeIndex + delta;
    if (i >= 0 && i < this.cells.length) this.activeId = this.cells[i].id;
    return this.active;
  }

  /* -- structure -- */
  insertAt(index, kind = "code", source = "") {
    const cell = makeCell(kind, source);
    const i = Math.max(0, Math.min(index, this.cells.length));
    this.cells.splice(i, 0, cell);
    this.activeId = cell.id;
    return cell;
  }
  insertAbove(kind = "code", source = "") {
    return this.insertAt(this.activeIndex, kind, source);
  }
  insertBelow(kind = "code", source = "") {
    return this.insertAt(this.activeIndex + 1, kind, source);
  }

  remove(id) {
    const i = this.indexOf(id);
    if (i < 0) return null;
    const [cell] = this.cells.splice(i, 1);
    this._trash.push({ cell, index: i });
    if (this.cells.length === 0) {
      // A notebook is never empty; Jupyter leaves one blank code cell behind.
      this.cells.push(makeCell("code", ""));
    }
    this.activeId = this.cells[Math.min(i, this.cells.length - 1)].id;
    return cell;
  }

  undoDelete() {
    const entry = this._trash.pop();
    if (!entry) return null;
    this.cells.splice(Math.min(entry.index, this.cells.length), 0, entry.cell);
    this.activeId = entry.cell.id;
    return entry.cell;
  }

  move(id, delta) {
    const i = this.indexOf(id);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= this.cells.length) return false;
    const [cell] = this.cells.splice(i, 1);
    this.cells.splice(j, 0, cell);
    this.activeId = cell.id;
    return true;
  }

  setKind(id, kind) {
    const cell = this.get(id);
    if (!cell || cell.kind === kind) return cell;
    cell.kind = kind;
    cell.outputs = [];
    cell.execCount = null;
    cell.rendered = false; // switching to markdown drops you into its editor
    return cell;
  }

  setSource(id, source) {
    const cell = this.get(id);
    if (cell) cell.source = source;
    return cell;
  }

  /* -- execution bookkeeping -- */
  /** Mark a cell as running: clears outputs, returns the new execution count. */
  beginExec(id) {
    const cell = this.get(id);
    if (!cell) return null;
    cell.outputs = [];
    cell.execCount = ++this.execCounter;
    return cell.execCount;
  }
  addOutput(id, output) {
    const cell = this.get(id);
    if (!cell) return null;
    const last = cell.outputs[cell.outputs.length - 1];
    // Consecutive stream chunks on the same fd coalesce, as Jupyter does.
    if (last && last.output_type === "stream" && output.output_type === "stream" &&
        last.name === output.name) {
      last.text += output.text;
      return last;
    }
    cell.outputs.push(output);
    return output;
  }

  resetExecution() {
    this.execCounter = 0;
    for (const c of this.cells) {
      c.execCount = null;
      c.outputs = [];
    }
  }

  /** The cells a "run all" would execute, in order. */
  runnable() {
    return this.cells.filter((c) => c.kind === "code" && c.source.trim() !== "");
  }

  /* -- persistence -- */
  toJSON() {
    return {
      cells: this.cells.map((c) => ({
        kind: c.kind,
        source: c.source,
        outputs: c.outputs,
        execCount: c.execCount,
      })),
    };
  }
}

/* ------------------------------------------------------------------ *
 * nbformat 4.5 round-trip
 * ------------------------------------------------------------------ */

/** nbformat stores text as a list of lines, each keeping its trailing \n. */
export function splitLines(text) {
  if (!text) return [];
  const parts = String(text).split("\n");
  const out = [];
  for (let i = 0; i < parts.length; i++) {
    const last = i === parts.length - 1;
    if (last && parts[i] === "") break; // a trailing \n does not make a new line
    out.push(last ? parts[i] : parts[i] + "\n");
  }
  return out;
}

export function joinLines(source) {
  return Array.isArray(source) ? source.join("") : String(source || "");
}

export function toIpynb(model) {
  return {
    cells: model.cells.map((c) =>
      c.kind === "code"
        ? {
            cell_type: "code",
            execution_count: c.execCount,
            metadata: {},
            outputs: c.outputs.map((o) =>
              o.output_type === "stream"
                ? { output_type: "stream", name: o.name, text: splitLines(o.text) }
                : o.output_type === "execute_result"
                ? {
                    output_type: "execute_result",
                    data: { "text/plain": splitLines(o.data["text/plain"]) },
                    metadata: {},
                    execution_count: o.execution_count,
                  }
                : {
                    output_type: "error",
                    ename: o.ename,
                    evalue: o.evalue,
                    traceback: o.traceback,
                  }
            ),
            source: splitLines(c.source),
          }
        : { cell_type: "markdown", metadata: {}, source: splitLines(c.source) }
    ),
    metadata: {
      kernelspec: { display_name: "Python (Pyodide)", language: "python", name: "python" },
      language_info: { name: "python", version: "3.12", mimetype: "text/x-python",
                       file_extension: ".py" },
    },
    nbformat: 4,
    nbformat_minor: 5,
  };
}

export function fromIpynb(nb) {
  if (!nb || !Array.isArray(nb.cells)) throw new Error("not a notebook: no cells array");
  const cells = nb.cells
    .filter((c) => c.cell_type === "code" || c.cell_type === "markdown")
    .map((c) => {
      const source = joinLines(c.source);
      if (c.cell_type === "markdown") return { kind: "markdown", source };
      const outputs = (c.outputs || []).map((o) => {
        if (o.output_type === "stream") {
          return streamOutput(joinLines(o.text), o.name || "stdout");
        }
        if (o.output_type === "execute_result" || o.output_type === "display_data") {
          const data = (o.data && o.data["text/plain"]) || "";
          return resultOutput(joinLines(data), o.execution_count ?? null);
        }
        if (o.output_type === "error") {
          return { output_type: "error", ename: o.ename, evalue: o.evalue,
                   traceback: o.traceback || [] };
        }
        return null;
      }).filter(Boolean);
      return { kind: "code", source, outputs, execCount: c.execution_count ?? null };
    });
  return new NotebookModel(cells.length ? cells : [{ kind: "code", source: "" }]);
}

/* ------------------------------------------------------------------ *
 * Markdown (a small, predictable subset — headings, emphasis, code,
 * links, lists, rules)
 * ------------------------------------------------------------------ */

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inlineMd(s) {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, (_, c) => "<code>" + c + "</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g,
             '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

export function renderMarkdown(src) {
  const lines = String(src).split("\n");
  const html = [];
  let list = null; // "ul" | "ol"
  let fence = null; // language while inside ```
  let fenceBuf = [];

  const closeList = () => {
    if (list) { html.push(`</${list}>`); list = null; }
  };

  for (const line of lines) {
    if (fence !== null) {
      if (/^```/.test(line)) {
        html.push(`<pre class="md-code"><code>${escapeHtml(fenceBuf.join("\n"))}</code></pre>`);
        fence = null;
        fenceBuf = [];
      } else {
        fenceBuf.push(line);
      }
      continue;
    }
    const fenceOpen = /^```(\w*)\s*$/.exec(line);
    if (fenceOpen) { closeList(); fence = fenceOpen[1] || ""; fenceBuf = []; continue; }

    if (/^\s*$/.test(line)) { closeList(); continue; }

    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      closeList();
      const level = h[1].length;
      html.push(`<h${level}>${inlineMd(h[2])}</h${level}>`);
      continue;
    }

    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { closeList(); html.push("<hr>"); continue; }

    const ul = /^\s*[-*+]\s+(.*)$/.exec(line);
    if (ul) {
      if (list !== "ul") { closeList(); html.push("<ul>"); list = "ul"; }
      html.push(`<li>${inlineMd(ul[1])}</li>`);
      continue;
    }
    const ol = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (ol) {
      if (list !== "ol") { closeList(); html.push("<ol>"); list = "ol"; }
      html.push(`<li>${inlineMd(ol[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${inlineMd(line)}</p>`);
  }
  if (fence !== null) {
    html.push(`<pre class="md-code"><code>${escapeHtml(fenceBuf.join("\n"))}</code></pre>`);
  }
  closeList();
  return html.join("\n");
}

/* ------------------------------------------------------------------ *
 * The keymap — Jupyter's command/edit modes
 * ------------------------------------------------------------------ */

/**
 * Translates key events into command names. Stateful only for the `dd`
 * two-stroke delete, which is why it is a class.
 *
 * Commands: enter-edit, enter-command, run, run-select-below,
 * run-insert-below, insert-above, insert-below, delete, undo-delete,
 * to-markdown, to-code, select-prev, select-next, move-up, move-down, save,
 * interrupt-hint.
 */
export class Keymap {
  constructor() {
    this._pendingD = 0;
  }

  handle(evt, mode) {
    const key = evt.key;
    const mod = evt.ctrlKey || evt.metaKey;

    if (mod && (key === "s" || key === "S")) return "save";

    if (key === "Enter") {
      if (evt.shiftKey) return "run-select-below";
      if (mod) return "run";
      if (evt.altKey) return "run-insert-below";
      if (mode === "command") return "enter-edit";
      return null; // a plain Enter in the editor is a newline
    }

    if (mode === "edit") {
      if (key === "Escape") return "enter-command";
      return null;
    }

    // -- command mode --
    if (key !== "d") this._pendingD = 0;

    switch (key) {
      case "a": return "insert-above";
      case "b": return "insert-below";
      case "d":
        this._pendingD += 1;
        if (this._pendingD >= 2) { this._pendingD = 0; return "delete"; }
        return null;
      case "z": return "undo-delete";
      case "m": return "to-markdown";
      case "y": return "to-code";
      case "k": case "ArrowUp": return "select-prev";
      case "j": case "ArrowDown": return "select-next";
      case "J": return "move-down";
      case "K": return "move-up";
      case "i": return "interrupt-hint";
      default: return null;
    }
  }
}

/* ------------------------------------------------------------------ *
 * The starter notebook
 * ------------------------------------------------------------------ */

export const STARTER_CELLS = [
  { kind: "markdown", source:
    "# PyLabRobot in your browser\n" +
    "\n" +
    "This page runs a **real pylabrobot 0.2.2 protocol** entirely in your browser — " +
    "CPython on WebAssembly via Pyodide. No server, no install.\n" +
    "\n" +
    "Run the cells in order (**Shift+Enter**, or *Run all* above); the deck renders on the right.\n" +
    "\n" +
    "- `Esc` / `Enter` switch between command and edit mode, like Jupyter\n" +
    "- `a` / `b` insert a cell, `dd` deletes one, `m` / `y` change its type\n" },
  { kind: "code", source: [
    "# Volume and tip tracking drive the deck view; without them nothing animates.",
    "from pylabrobot.resources import set_volume_tracking, set_tip_tracking",
    "",
    "set_volume_tracking(True)",
    "set_tip_tracking(True)",
  ].join("\n") },
  { kind: "markdown", source:
    "## 1. Build the deck\n" +
    "\n" +
    "A Hamilton STARLet deck with a tip carrier and a plate carrier, driven by the " +
    "`LiquidHandlerChatterboxBackend` — the backend that prints each command instead " +
    "of talking to a real machine." },
  { kind: "code", source: [
    "from pylabrobot.liquid_handling import LiquidHandler",
    "from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend",
    "from pylabrobot.resources import (",
    "  STARLetDeck, TIP_CAR_480_A00, PLT_CAR_L5AC_A00,",
    "  cor_96_wellplate_360uL_Fb, hamilton_96_tiprack_1000uL_filter,",
    ")",
    "",
    "deck = STARLetDeck()",
    "tip_carrier = TIP_CAR_480_A00(name=\"tips\")",
    "plate_carrier = PLT_CAR_L5AC_A00(name=\"plates\")",
    "deck.assign_child_resource(plate_carrier, rails=5)",
    "deck.assign_child_resource(tip_carrier, rails=11)",
    "tip_carrier[0] = hamilton_96_tiprack_1000uL_filter(name=\"tips_0\")",
    "plate_carrier[0] = cor_96_wellplate_360uL_Fb(name=\"plate_0\")",
    "",
    "lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(), deck=deck)",
    "await lh.setup()",
    "lh",
  ].join("\n") },
  { kind: "markdown", source:
    "## 2. Mount the visualizer\n" +
    "\n" +
    "`InlineVisualizer` is the stock PyLabRobot visualizer with its websocket swapped " +
    "for a transport. Here the transport posts events straight into the deck panel. " +
    "Run it once; it stays mounted for the rest of the session." },
  { kind: "code", source: [
    "from plr_workshops.inline import InlineVisualizer",
    "from plr_workshops.pyodide_transport import PyodideTransport",
    "",
    "vis = InlineVisualizer(resource=lh, transport=PyodideTransport(container_id=\"plr-deck\"))",
    "await vis.setup()",
  ].join("\n") },
  { kind: "markdown", source:
    "## 3. Fill the plate, then pipette\n" +
    "\n" +
    "Watch the right-hand panel: the plate fills, a tip leaves the rack and lands on the " +
    "pipetting head, 50 µL moves from A1 to B1, then the tip goes back.\n" +
    "\n" +
    "The `await asyncio.sleep(...)` calls are what let you see it happen. The browser runs " +
    "Python on a single thread, so a cell that never yields draws nothing until it finishes — " +
    "and `time.sleep()` would freeze the page outright. Yielding hands the frame back to the " +
    "renderer between steps." },
  { kind: "code", source: [
    "import asyncio",
    "",
    "plate = deck.get_resource(\"plate_0\")",
    "tips = deck.get_resource(\"tips_0\")",
    "",
    "plate.set_well_volumes([200.0] * 96)",
    "await asyncio.sleep(0.4)",
    "",
    "await lh.pick_up_tips(tips[\"A1\"])",
    "await asyncio.sleep(0.4)",
    "",
    "await lh.aspirate(plate[\"A1\"], vols=[50])",
    "await asyncio.sleep(0.4)",
    "",
    "await lh.dispense(plate[\"B1\"], vols=[50])",
    "await asyncio.sleep(0.4)",
    "",
    "await lh.return_tips()",
    "",
    "# A1 gave up 50 uL of its 200 uL.",
    "plate.get_well(\"A1\").tracker.get_used_volume()",
  ].join("\n") },
  { kind: "markdown", source:
    "## 4. Your turn\n" +
    "\n" +
    "Edit any cell and re-run it, or add your own below. Everything is autosaved to this " +
    "browser; **Download .ipynb** gives you a notebook that opens in JupyterLab unchanged." },
  { kind: "code", source: [
    "# e.g. move a whole column with a 96-head-style loop",
    "for row in \"ABCDEFGH\":",
    "  await lh.pick_up_tips(tips[f\"{row}2\"])",
    "  await lh.aspirate(plate[f\"{row}1\"], vols=[25])",
    "  await lh.dispense(plate[f\"{row}12\"], vols=[25])",
    "  await lh.return_tips()",
    "  await asyncio.sleep(0.2)",
    "",
    "print(\"done\")",
  ].join("\n") },
];
