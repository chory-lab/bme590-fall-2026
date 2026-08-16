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
const URL = "http://127.0.0.1:8812/index.html";

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

    // Wait for the kernel to boot (Pyodide from CDN is the slow part), then run
    // the whole notebook through the command bridge -- no keyboard simulation.
    console.log("waiting for Pyodide/kernel boot (~30s)...");
    await sleep(25000);

    console.log("running notebook:run-all-cells via the command bridge...");
    const run = await evalJS(`window.__liteBridge.execute('notebook:run-all-cells').then(() => 'OK')`)
      .catch((e) => "ERR " + e.message);
    console.log("  run-all-cells:", run);

    // Wait for execution + deck rendering. The pip-install cell is the slow part.
    console.log("waiting for execution to finish...");
    await sleep(45000);

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
    console.log("=== cell outputs ===");
    for (const o of cellOutputs) console.log("  ", o);

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

    const gates = {
      gate1_python: consoleLines.some((l) => l.includes("PYTHON_EXECUTES")) ||
        cellOutputs.some((l) => l.includes("PYTHON_EXECUTES")) ||
        cellOutputs.some((l) => l.includes("PLR")),
      gate2_anywidget: consoleLines.some((l) => l.includes("ANYWIDGET")) ||
        cellOutputs.some((l) => l.includes("ANYWIDGET")),
      gate3_render: consoleLines.some((l) => l.includes("DECK_PROBE_RENDERED")) ||
        cellOutputs.some((l) => l.includes("VIS_MOUNTED")),
      gate4_msg: consoleLines.some((l) => l.includes("PROBE_MESSAGE")) ||
        cellOutputs.some((l) => l.includes("PROTOCOL_DONE")),
      gate5_parent: messages.length > 0,
      gate6_deck: deckState && (deckState.hasStage || (deckState.shapes || 0) > 0),
    };
    console.log("\n=== gates ===");
    for (const [k, v] of Object.entries(gates)) console.log(`  ${k}: ${v ? "PASS" : "FAIL"}`);
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
