// Drive the JupyterLite bridge spike in a real Chrome via the DevTools protocol.
// Uses jupyter-iframe-commands (not keyboard synthesis) to run the notebook,
// and watches console output for the five gate markers.
//
// Usage: node drive.cjs   (needs the spike served on http://127.0.0.1:8812)
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const path = require("path");

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
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
        window.addEventListener("message", (e) => {
          const d = e.data;
          if (!d) return;
          if (d.source === "bridge-probe") window.__spikeMessages.push(d);
          if (typeof d.__plrEvent === "string") window.__spikeMessages.push(d);
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

    // Wait for the kernel to boot (Pyodide from CDN is the slow part).
    console.log("waiting for Pyodide/kernel boot (~25s)...");
    await sleep(25000);

    // Run cells one at a time, mirroring a student session and tolerating the
    // workshops' intentional-error / exercise-stub cells. Cells matching the CI
    // skip markers are skipped; every other code cell (plus the bootstrap at
    // index 0) is selected and run, waiting briefly between runs.
    console.log("running cells individually (skipping CI markers/stubs)...");
    const SKIP_RE = /CI-SKIP|YOUR CODE HERE|you will get an error|this is ok|should throw an error|should throw our better error/;
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
        info.push({ i: code++, domIndex: i, skip: ${SKIP_RE}.test(text) });
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

    for (const cell of codeCells) {
      try {
        const r = await runOne(cell.domIndex);
        await sleep(cell.i === 0 ? 15000 : 2500);  // bootstrap (piplite.install) is slow
        console.log(`  cell ${cell.i} (nb index ${cell.domIndex}) ${r}`);
      } catch (e) {
        console.log(`  cell ${cell.i} driver-error: ${e.message}`);
      }
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
    const shotPath = "C:/plrlite/deck.png";
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
    const ran = model.filter((c) => c.exec !== null);
    const errored = model.filter((c) => c.ename);
    const stdout = model.map((c) => c.stdout || "").join(" ");

    const gates = {
      // Every code cell reached the kernel and came back with a count.
      gate1_cells_executed: model.length > 0 && ran.length === model.length,
      // ...and none of them raised. Workshops with intentional-error cells are
      // filtered by SKIP_RE before they are ever run.
      gate2_no_errors: errored.length === 0,
      // The visualizer mounted (its transport displayed the bridge widget).
      gate3_vis_mounted: /VIS_MOUNTED|JupyterLiteBridgeWidget/.test(stdout),
      // The protocol produced events, and they crossed into the parent page.
      gate4_parent_messages: messages.length > 0,
      // The deck actually drew them.
      gate5_deck_painted: !!deckState && (deckState.shapes || 0) > 1,
    };
    console.log("\n=== gates ===");
    for (const [k, v] of Object.entries(gates)) console.log(`  ${k}: ${v ? "PASS" : "FAIL"}`);
    if (!gates.gate1_cells_executed) {
      const missed = model.filter((c) => c.exec === null).map((c) => c.i);
      console.log(`  (cells with no execution count: ${JSON.stringify(missed)})`);
    }
    for (const c of errored) console.log(`  (cell ${c.i} raised ${c.ename}: ${c.evalue})`);
    if (Object.values(gates).some((v) => !v)) process.exitCode = 1;
    if (messages.length === 0) {
      console.log("\nNO BRIDGE MESSAGES.");
      process.exitCode = 1;
    } else {
      console.log(`\nSUCCESS: ${messages.length} message(s) crossed from the kernel to the parent page.`);
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
