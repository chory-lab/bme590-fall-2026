// Drive the JupyterLite bridge spike in a real Chrome via the DevTools protocol.
// Uses jupyter-iframe-commands (not keyboard synthesis) to run the notebook,
// and watches console output for the five gate markers.
//
// Usage: node drive.cjs   (needs the spike served on http://127.0.0.1:8812)
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const path = require("path");

// PLR_CHROME overrides; otherwise the first path that exists. Linux entries
// come first so CI (ubuntu-latest, where `google-chrome` is preinstalled)
// needs no configuration.
const CHROME = process.env.PLR_CHROME || [
  "/usr/bin/google-chrome",
  "/usr/bin/chromium-browser",
  "/usr/bin/chromium",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
].find((p) => fs.existsSync(p)) || "google-chrome";
const PORT = 9333;
const NOTEBOOK = process.env.PLR_NB || "workshops/00_plr_introduction.ipynb";
const BASE = process.env.PLR_URL || "http://127.0.0.1:8812/outer.html";
const URL = `${BASE}?nb=${NOTEBOOK}`;

let ws = null;
let msgId = 0;
const pending = new Map();
const handlers = {};

function connect(url) {
  return new Promise((resolve, reject) => {
    const ws = new (require("ws"))(url, { maxPayload: 256 * 1024 * 1024 });
    ws.on("open", () => resolve(ws));
    ws.on("error", reject);
  });
}
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
function onMessage(data) {
  if (data instanceof ArrayBuffer || Buffer.isBuffer(data)) {
    data = Buffer.from(data).toString("utf8");
  }
  let msg;
  try {
    msg = JSON.parse(data);
  } catch {
    return;
  }
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
  }
  handlers[msg.method] && handlers[msg.method](msg.params);
}
function listen(method, fn) {
  handlers[method] = fn;
}
function get(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (r) => {
      let data = "";
      r.on("data", (c) => (data += c));
      r.on("end", () => resolve(data));
    }).on("error", reject);
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(fn, timeout = 60000, interval = 500, label = "condition") {
  const start = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - start > timeout) throw new Error(`timeout waiting for ${label}`);
    await sleep(interval);
  }
}
async function evalJS(expr) {
  const r = await send("Runtime.evaluate", {
    expression: expr,
    awaitPromise: true,
    returnByValue: true,
  });
  if (r.exceptionDetails) {
    throw new Error("eval failed: " + (r.exceptionDetails.exception?.description || JSON.stringify(r.exceptionDetails)));
  }
  return r.result.value;
}

async function main() {
  const userData = fs.mkdtempSync(path.join(require("os").tmpdir(), "chrome-lite-"));
  const chrome = spawn(CHROME, [
    `--remote-debugging-port=${PORT}`,
    `--remote-allow-origins=*`,
    `--user-data-dir=${userData}`,
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-size=1600,1000",
    "about:blank",
  ], { stdio: "ignore" });

  // Watch the CONSOLE for the gate markers the notebook emits.
  const consoleLines = [];
  let messages = [];

  try {
    await waitFor(async () => {
      try { return await get(`http://127.0.0.1:${PORT}/json/version`); } catch { return null; }
    }, 30000, 500, "chrome debugger");

    const targets = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));
    const page = targets.find((t) => t.type === "page");
    ws = await connect(page.webSocketDebuggerUrl);
    ws.binaryType = "arraybuffer";
    ws.on("message", (d) => onMessage(d));

    await send("Page.enable");
    await send("Runtime.enable");
    await send("Log.enable");

    listen("Runtime.consoleAPICalled", (p) => {
      const text = p.args?.map((a) => a.value ?? a.description ?? "").join(" ");
      if (text) consoleLines.push(text);
    });
    listen("Runtime.exceptionThrown", (p) =>
      consoleLines.push("[EXCEPTION] " + (p.exceptionDetails?.exception?.description || "")));
    listen("Log.entryAdded", (p) => {
      if (p.entry.level === "error") consoleLines.push("[LOG] " + p.entry.text);
    });

    console.log("navigating to", URL);
    await send("Page.navigate", { url: URL });
    await sleep(3000);

    console.log("waiting for the JupyterLab shell...");
    await waitFor(async () => {
      try {
        return await evalJS(`!!document.querySelector('#lite')?.contentDocument?.querySelector('#jp-main-dock-panel')`);
      } catch { return false; }
    }, 60000, 1000, "jupyterlab shell");
    console.log("JupyterLab shell present.");

    await evalJS(`(() => {
      const doc = document.querySelector('#lite').contentDocument;
      window.__nbInfo = {
        title: doc.title,
        hash: doc.location.hash,
        cells: doc.querySelectorAll('.jp-Cell').length,
      };
      return window.__nbInfo;
    })()`).then((t) => console.log("  notebook:", JSON.stringify(t)));

    await evalJS(`
      (() => {
        window.__spikeMessages = [];
        window.__plrBootstrap = [];
        window.addEventListener("message", (e) => {
          const d = e.data;
          if (!d) return;
          if (d.source === "bridge-probe") window.__spikeMessages.push(d);
          if (typeof d.__plrEvent === "string") window.__spikeMessages.push(d);
          // Runtime setup from the plr-workshops:bootstrap labextension.
          if (typeof d.type === "string" && d.type.indexOf("PLR_BOOTSTRAP") === 0) {
            window.__plrBootstrap.push(d);
          }
        });
        return true;
      })()
    `);

    console.log("waiting for the iframe-commands bridge to come up...");
    await waitFor(async () => {
      try {
        return await evalJS(`window.__liteBridge ? true : false`);
      } catch { return false; }
    }, 60000, 1000, "bridge object");
    console.log("bridge object present; waiting for its ready promise...");
    await waitFor(async () => {
      try {
        return await evalJS(`window.__liteBridge.ready.then(() => true).catch(() => false)`);
      } catch { return false; }
    }, 60000, 1000, "bridge ready");
    console.log("command bridge is ready.");

    console.log("listing commands to confirm the bridge talks to JupyterLab...");
    let cmds = [];
    try {
      cmds = await evalJS(`window.__liteBridge.listCommands().then((c) => c.slice(0, 5))`);
    } catch (e) {
      console.log("  listCommands failed:", e.message);
    }
    console.log("  sample commands:", JSON.stringify(cmds));

    // No fixed boot sleep. PLR_BOOTSTRAP_READY below is emitted from inside the
    // kernel, so it already implies the kernel booted -- sleeping first just
    // added 25s to every run for a fact the next wait establishes properly.

    // Then wait for the runtime bootstrap to finish.
    //
    // The labextension installs the wheel, patches the Visualizer and seeds the
    // Opentrons cache on each new kernel. `notebook:run-cell` does not resolve
    // until the kernel is free, so firing cells during that install looks
    // exactly like a hang -- the first cell never returns, and without a
    // timeout the whole suite stops with no output at all. Wait for the
    // extension to say it is done instead of racing it.
    console.log("waiting for PLR_BOOTSTRAP_READY...");
    const bootstrapState = await waitFor(async () => {
      const seen = (await evalJS(`window.__plrBootstrap || []`)) || [];
      const done = seen.find((m) => m.type === "PLR_BOOTSTRAP_READY");
      const failed = seen.find((m) => m.type === "PLR_BOOTSTRAP_FAILED");
      return done || failed || null;
    }, 180000, 1000, "runtime bootstrap").catch(() => null);

    if (!bootstrapState) {
      console.log("  no bootstrap signal (older build without the extension?); continuing");
    } else if (bootstrapState.type === "PLR_BOOTSTRAP_FAILED") {
      console.log("  BOOTSTRAP FAILED:", bootstrapState.error);
    } else {
      console.log("  runtime ready.");
    }

    // Run cells one at a time, mirroring a student session and tolerating the
    // workshops' intentional-error / exercise-stub cells. Cells matching the CI
    // skip markers are skipped; every other code cell (plus the bootstrap at
    // index 0) is selected and run, waiting briefly between runs.
    console.log("running cells individually (skipping CI markers/stubs)...");
    // Cells the workshops intend NOT to run: exercise stubs students fill in, and
// cells that deliberately raise to make a teaching point. `import ... from ...`
// is a literal exercise placeholder and a SyntaxError if executed.
const SKIP_RE = /CI-SKIP|YOUR CODE HERE|you will get an error|this is ok|should throw an error|should throw our better error|import \.\.\. from \.\.\.|# Function N Code:|add any imports needed|# Test code here|=\s*\.\.\.|\(\.\.\.\)/;
    // Enumerate from the model, not the DOM. `.jp-CodeCell` only matches cells
    // JupyterLab has actually rendered -- the notebook is windowed -- so a DOM
    // walk silently misses everything below the fold and reports a short
    // notebook as complete. The model also gives the cell's true index among
    // all cells, which is what running a specific cell requires.
    const nbCells = await evalJS(`(() => {
      const w = document.querySelector('#lite').contentWindow;
      const app = w.jupyterapp || w.jupyterlab;
      if (!app) return [{ err: "no app global (build with --probe)" }];
      let panel = null;
      for (const x of app.shell.widgets("main")) {
        if (x.content && x.content.model && x.content.model.cells) { panel = x; break; }
      }
      if (!panel) return [{ err: "no notebook widget" }];
      const model = panel.content.model;
      const info = [];
      let code = 0;
      for (let i = 0; i < model.cells.length; i++) {
        const cell = model.cells.get(i);
        if (cell.type !== "code") continue;
        const text = cell.sharedModel.getSource();
        info.push({
          i: code++, domIndex: i,
          skip: ${SKIP_RE}.test(text),
          // Does this cell actually CREATE a visualizer when run?
          //
          // Plain string logic rather than a regex, and no backticks in this
          // comment: the whole block is injected through a template literal, where
          // a backslash needs doubling and a backtick ends the string outright.
          //
          // A call at top level counts; a def does not, nor anything indented inside
          // one. Workshop 05 defines visualize_deck but only calls it from skipped
          // exercise stubs, so its run legitimately has no deck and the deck gates
          // must not fail it.
          // No regex: this is inside a template literal, where a lone
          // backslash-s collapses to a literal s. /^SLEEPs*=/m is a *valid*
          // regex that simply never matches -- a silent wrong answer rather
          // than an error.
          setsSleep: text.split(String.fromCharCode(10))
            .some((line) => line.trimStart().indexOf("SLEEP =") === 0),
          usesVis: text.split(String.fromCharCode(10)).some((line) => {
            const t = line.trimStart();
            if (line.length - t.length > 3) return false;
            if (t.startsWith("def ") || t.startsWith("async def ")) return false;
            return t.includes("visualize_deck(") || t.includes("Visualizer(");
          }),
        });
      }
      return info;
    })()`).catch((e) => [{ err: e.message }]);
    if (nbCells[0] && nbCells[0].err) throw new Error("cell enumeration failed: " + nbCells[0].err);
    const codeCells = nbCells.filter((x) => !x.skip || x.i === 0);
    console.log(`  ${codeCells.length} runnable cells (${nbCells.length - codeCells.length} skipped)`);

    // Select each cell by index through the notebook widget, then run exactly
    // that cell.
    //
    // This used to be `notebook:select-cell` with a positional index followed
    // by `notebook:run-cell-and-select-next`. There is no such signature for
    // select-cell, so it threw and the `.catch(() => {})` swallowed it -- every
    // iteration simply ran the active cell and advanced by one. The loop runs
    // once per *code* cell, but "select next" steps through *all* cells, and
    // the workshops alternate markdown and code. So it walked half the notebook
    // and stopped: for a 10-cell fixture with code at 1,3,5,7,9 it executed
    // exactly two code cells, then reported "cell 0 OK" through "cell 4 OK" for
    // all five, because its OK meant "the command dispatched", not "the cell
    // ran".
    //
    // Everything downstream then looked broken -- no visualizer, no bridge
    // messages, an empty deck -- when the cell that builds the visualizer had
    // simply never executed.
    const runOne = (i) => evalJS(`(async () => {
      const w = document.querySelector('#lite').contentWindow;
      const app = w.jupyterapp || w.jupyterlab;
      if (!app) return "ERR no app global (build with --probe)";
      let panel = null;
      for (const x of app.shell.widgets("main")) {
        if (x.content && x.content.model && x.content.model.cells) { panel = x; break; }
      }
      if (!panel) return "ERR no notebook widget";
      panel.content.activeCellIndex = ${i};
      return app.commands.execute("notebook:run-cell").then(() => "OK").catch((e) => "ERR " + e.message);
    })()`);

    // A cell that never finishes must not take the suite with it.
    //
    // `notebook:run-cell` resolves when the cell *completes*, so anything that
    // wedges the kernel -- a bootstrap that never returns, an await that never
    // settles -- leaves this promise pending forever. CDP has no timeout of its
    // own, so the run simply stopped, printing nothing: no console lines, no
    // model dump, no gates. Hours of "it stalled again" with zero evidence.
    //
    // Now a stuck cell is reported and the run carries on to the diagnostics,
    // which is where the answer lives.
    const CELL_TIMEOUT_MS = Number(process.env.PLR_CELL_TIMEOUT || 90000);
    // Iteration speed only. A fast run skips the pauses that let the deck
    // render between events, so it can hide a timing bug the real pacing would
    // expose -- keep at least one full-timing run before shipping.
    const FAST = !!process.env.PLR_FAST;
    if (FAST) console.log("PLR_FAST: workshop pauses will be zeroed");
    let timedOut = 0;
    for (const cell of codeCells) {
      const label = `cell ${cell.i} (nb index ${cell.domIndex})`;
      try {
        const r = await Promise.race([
          runOne(cell.domIndex),
          sleep(CELL_TIMEOUT_MS).then(() => "TIMEOUT")
        ]);
        if (r === "TIMEOUT") timedOut++;
        // `notebook:run-cell` resolves when the cell *completes*, so there is
        // nothing left to wait for -- only a short settle so the output area
        // and model are updated before the next read. These used to be 15s and
        // 2.5s, from when the driver could not tell whether a cell had finished
        // and padding was the only defence; on a 68-cell workshop that was four
        // minutes of sleeping against ~30s of work.
        await sleep(250);
        console.log(`  ${label} ${r}`);

        // PLR_FAST: run the workshop at full speed by setting its own SLEEP
        // constant to 0, in the kernel, right after the cell that defines it.
        //
        // Deliberately not a rewrite of the notebook source: CI should execute
        // the same bytes students do. The workshops expose SLEEP for students
        // who have already watched the animation; this just turns the same knob
        // from outside.
        if (FAST && cell.setsSleep) {
          const set = await evalJS(`(async () => {
            const w = document.querySelector('#lite').contentWindow;
            const app = w.jupyterapp || w.jupyterlab;
            let panel = null;
            for (const x of app.shell.widgets("main")) {
              if (x.content && x.content.model && x.content.model.cells) { panel = x; break; }
            }
            const kernel = panel && panel.sessionContext.session && panel.sessionContext.session.kernel;
            if (!kernel) return "ERR no kernel";
            const fut = kernel.requestExecute({
              code: "SLEEP = 0", silent: true, store_history: false
            });
            const reply = await fut.done;
            return reply.content.status;
          })()`).catch((e) => "ERR " + e.message);
          console.log(`  (PLR_FAST: SLEEP = 0 -> ${set})`);
        }
      } catch (e) {
        console.log(`  ${label} driver-error: ${e.message}`);
      }
    }
    if (timedOut) {
      console.log(`  (${timedOut} cell(s) exceeded ${CELL_TIMEOUT_MS}ms -- see console lines below)`);
    }

    // Probe tab completion: JupyterLab's completer is a core plugin; confirm the
    // kernel-backed popup appears.
    await sleep(2000);
    const completionProbe = await evalJS(`(async () => {
      const doc = document.querySelector('#lite').contentDocument;
      const all = await window.__liteBridge.listCommands();
      const comp = (all || []).filter((c) => /complet|completer/i.test(c));
      const cell = doc.querySelectorAll('.jp-CodeCell')[0];
      if (!cell) return { compCmds: comp.slice(0, 4), err: "no code cell" };
      const cm = cell.querySelector('.cm-content');
      if (!cm) return { compCmds: comp.slice(0, 4), err: "no cm content" };
      const view = cm.cmView?.view || null;
      if (!view) return { compCmds: comp.slice(0, 4), err: "no cm view" };
      view.dispatch({ changes: { from: 0, to: 0, insert: "from pylabrobot import " } });
      view.focus();
      view.dispatch({ selection: { anchor: view.state.doc.length } });
      const target = comp.find((c) => /invoke-notebook/.test(c)) || comp.find((c) => /invoke/i.test(c));
      const res = target ? await window.__liteBridge.execute(target).then(() => 'OK').catch((e) => "ERR " + e.message)
                         : "no completer command";
      await new Promise((r) => setTimeout(r, 1200));
      const popup = doc.querySelector('.jp-Completer, .cm-tooltip-autocomplete');
      return {
        compCmds: comp.slice(0, 8),
        used: target || null,
        res,
        popupVisible: !!popup,
        popupText: popup ? (popup.textContent || "").replace(/\\s+/g, " ").slice(0, 160) : "",
      };
    })()`).catch((e) => ({ err: e.message }));
    console.log("  completion probe:", JSON.stringify(completionProbe));

    await sleep(5000);
    messages = (await evalJS(`window.__spikeMessages`)) || [];

    // Python `print()` goes to cell outputs, not the browser console -- read the
    // notebook's outputs for the text gates (PYTHON_EXECUTES, ANYWIDGET ...).
    const cellOutputs = await evalJS(`(() => {
      const doc = document.querySelector('#lite').contentDocument;
      const out = [];
      doc.querySelectorAll('.jp-Cell-outputArea').forEach((area, i) => {
        out.push(i + ":" + (area.innerText || "").replace(/\\s+/g, " ").slice(0, 500));
      });
      return out;
    })()`).catch((e) => ["read failed: " + e.message]);
    console.log("=== cell outputs (DOM -- windowed, incomplete) ===");
    for (const o of cellOutputs) console.log("  ", o);

    // The authoritative read. The DOM version above only sees cells JupyterLab
    // has rendered: the notebook is windowed, so a cell below the fold has no
    // output area at all and is indistinguishable from a cell that ran and
    // printed nothing. That ambiguity is worth several hours if you meet it
    // unaware -- it reads exactly like the protocol cells silently failing.
    //
    // The model carries every cell regardless of what is on screen, plus the
    // execution count and the error name/value that the DOM read drops.
    const cellModel = await evalJS(`(() => {
      const w = document.querySelector('#lite').contentWindow;
      const app = w.jupyterapp || w.jupyterlab;
      if (!app) return { err: "no app global on the JupyterLite window" };
      // Not shell.currentWidget: by the time we read, focus may have moved to
      // the completer probe's target or a launcher tab. Search the main area
      // for the notebook instead.
      let panel = null;
      for (const w of app.shell.widgets("main")) {
        if (w.content && w.content.model && w.content.model.cells) { panel = w; break; }
      }
      const model = panel && panel.content.model;
      if (!model) return { err: "no notebook widget in the main area" };
      const cells = [];
      for (let i = 0; i < model.cells.length; i++) {
        const cell = model.cells.get(i);
        if (cell.type !== "code") continue;
        const outputs = cell.outputs;
        const texts = [];
        let ename = null, evalue = null;
        for (let j = 0; j < outputs.length; j++) {
          const o = outputs.get(j).toJSON();
          if (o.output_type === "stream") texts.push(String(o.text).slice(0, 300));
          else if (o.output_type === "error") { ename = o.ename; evalue = o.evalue; }
          else if (o.data && o.data["text/plain"]) texts.push(String(o.data["text/plain"]).slice(0, 300));
        }
        cells.push({
          i,
          exec: cell.executionCount,
          nOut: outputs.length,
          stdout: texts.join(" | ").replace(/\\s+/g, " ").slice(0, 300),
          ename, evalue,
          src: cell.sharedModel.getSource().split("\\n")[0].slice(0, 60),
        });
      }
      return { cells };
    })()`).catch((e) => ({ err: e.message }));

    console.log("=== cell model (authoritative) ===");
    if (cellModel.err) {
      console.log("   unavailable:", cellModel.err);
    } else {
      for (const c of cellModel.cells) {
        const err = c.ename ? `  ERROR ${c.ename}: ${c.evalue}` : "";
        console.log(`   [${c.exec === null ? " " : c.exec}] outs=${c.nOut} ${JSON.stringify(c.src)}${err}`);
        if (c.stdout) console.log(`        stdout: ${c.stdout}`);
      }
    }

    // The real proof: did the DECK iframe render? Check the Konva stage inside it.
    const deckState = await evalJS(`(() => {
      const doc = document.querySelector('#deck')?.contentDocument;
      if (!doc) return { err: "no deck iframe" };
      const w = doc.defaultView;
      const stage = w.stage;
      return {
        hidden: doc.visibilityState,
        ready: !!w.__plrSocket,
        hasStage: !!stage,
        shapes: stage ? stage.find('Shape').length : 0,
        canvas: !!doc.querySelector('canvas'),
      };
    })()`).catch((e) => ({ err: e.message }));
    console.log("=== deck iframe state (backgrounded) ===");
    console.log("  ", JSON.stringify(deckState));

    // Force a foreground frame: the HANDOFF notes rAF/ResizeObserver are
    // suspended in backgrounded automation, so a screenshot interleaves a real
    // frame. Then re-probe.
    const shot = await send("Page.captureScreenshot", { format: "png" });
    const shotPath = process.env.PLR_SHOT ||
      path.join(require("os").tmpdir(), "plr-deck.png");
    fs.writeFileSync(shotPath, Buffer.from(shot.data, "base64"));
    console.log("  screenshot ->", shotPath);
    await sleep(1000);

    const deckState2 = await evalJS(`(() => {
      const doc = document.querySelector('#deck')?.contentDocument;
      const w = doc.defaultView;
      const stage = w.stage;
      return {
        hidden: doc.visibilityState,
        shapes: stage ? stage.find('Shape').length : 0,
        layers: stage ? stage.getLayers().map((l) => l.children.length) : [],
      };
    })()`).catch((e) => ({ err: e.message }));
    console.log("=== deck iframe state (after foreground frame) ===");
    console.log("  ", JSON.stringify(deckState2));

    console.log("\n=== console lines from the iframe ===");
    for (const line of consoleLines) console.log("  ", line);
    console.log("\n=== bridge messages received by the outer page ===");
    console.log(JSON.stringify(messages, null, 2));

    // Gates read the notebook MODEL, never the DOM.
    //
    // They used to grep `cellOutputs` (windowed -- misses every cell below the
    // fold) and console markers left over from `counter.ipynb`, a probe
    // notebook that no longer ships. The result was a suite that reported
    // gate1_python FAIL on a run where Python demonstrably executed and the
    // deck painted 4556 shapes. A gate that fails while the thing it measures
    // works is worse than no gate: it trains you to ignore it.
    const model = cellModel.cells || [];
    const byIndex = new Map(model.map((c) => [c.i, c]));
    const expected = codeCells.map((c) => c.domIndex);   // what we tried to run
    const ran = model.filter((c) => c.exec !== null);
    const errored = model.filter((c) => c.ename);
    const stdout = model.map((c) => c.stdout || "").join(" ");

    // Whether the deck gates apply at all. Workshop 05 defines visualize_deck
    // but only ever calls it from "YOUR CODE HERE" exercise stubs, which are
    // skipped -- so an automated run legitimately mounts no visualizer, and
    // failing it for that is noise. Decide from the cells actually run, not
    // from the notebook text.
    const usesVisualizer = codeCells.some((c) => c.usesVis);
    if (!usesVisualizer) {
      console.log("  (no visualizer in the cells run -- deck gates not applicable)");
    }

    const gates = {
      // Every cell the driver actually ran came back with an execution count.
      // Skipped cells (exercise stubs) never run, so they must not count
      // against this -- an earlier version compared against every code cell and
      // failed workshop 04 for the five stubs it had correctly declined to run.
      gate1_cells_executed: expected.length > 0 &&
        expected.every((i) => byIndex.has(i) && byIndex.get(i).exec !== null),
      // ...and none of them raised. Workshops with intentional-error cells are
      // filtered by SKIP_RE before they are ever run.
      gate2_no_errors: errored.filter((c) => expected.includes(c.i)).length === 0,
      // The visualizer mounted (its transport displayed the bridge widget).
      gate3_vis_mounted: !usesVisualizer || /VIS_MOUNTED|JupyterLiteBridgeWidget/.test(stdout),
      // The protocol produced events, and they crossed into the parent page.
      gate4_parent_messages: !usesVisualizer || messages.length > 0,
      // The deck actually drew them.
      gate5_deck_painted: !usesVisualizer || (!!deckState && (deckState.shapes || 0) > 1),
    };
    console.log("\n=== gates ===");
    for (const [k, v] of Object.entries(gates)) console.log(`  ${k}: ${v ? "PASS" : "FAIL"}`);
    if (!gates.gate1_cells_executed) {
      const missed = expected.filter((i) => !byIndex.has(i) || byIndex.get(i).exec === null);
      console.log(`  (cells with no execution count: ${JSON.stringify(missed)})`);
    }
    for (const c of errored) console.log(`  (cell ${c.i} raised ${c.ename}: ${c.evalue})`);
    if (Object.values(gates).some((v) => !v)) process.exitCode = 1;
    if (messages.length > 0) {
      console.log(`\nSUCCESS: ${messages.length} message(s) crossed from the kernel to the parent page.`);
    } else if (usesVisualizer) {
      console.log("\nNO BRIDGE MESSAGES.");
      process.exitCode = 1;
    } else {
      // Not every workshop drives the deck. Silence here is the correct result
      // for one that never builds a visualizer, and failing it would train
      // people to ignore a red run.
      console.log("\nNo bridge messages, and none expected: this run built no visualizer.");
    }
  } finally {
    try { ws && ws.close(); } catch {}
    // Kill the whole tree of THIS headless Chrome only. Never touch the user's
    // real browser: the headless instance is identifiable by its temp profile.
    try {
      const { execSync } = require("child_process");
      execSync(`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*--user-data-dir=${userData}*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"`, { stdio: "ignore" });
    } catch {}
    try { chrome.kill(); } catch {}
    await sleep(500);
  }
}

main().catch((e) => {
  console.error("FAILED:", e.message);
  process.exit(1);
});
