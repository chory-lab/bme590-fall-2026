// The 3D viewer's WebSocket, on the hosted site: a BroadcastChannel to the notebook's kernel.
//
// Loaded before the viewer's own scripts, which are the PR's files copied unchanged: they open
// `new WebSocket(WS_URL)`, and this is what they get. The kernel (a Pyodide worker on this origin)
// listens on the same channel; viz3d_demo/bridge.py has its side and the message shapes. Every
// message is a JSON string.
//
// A socket opens when a kernel's viewer accepts it. Until then it stays CONNECTING, which the page
// reads as "not yet" rather than a failure to give up on, so it waits as long as the reader takes
// to reach the viewer cell. When a viewer starts - the cell run, the cell run again, the kernel
// restarted - it announces itself: open sockets close, the page's own reconnect opens new ones,
// and sockets still waiting ask again.
(function () {
  "use strict";

  const CHANNEL = "plr-viz3d";
  const CONNECTING = 0;
  const OPEN = 1;
  const CLOSING = 2;
  const CLOSED = 3;
  const channel = new BroadcastChannel(CHANNEL);
  const sockets = new Map();
  const post = (message) => channel.postMessage(JSON.stringify(message));

  class BridgeSocket extends EventTarget {
    constructor(url) {
      super();
      this.url = String(url);
      // Random rather than counted: a reloaded page must not reuse an id a kernel still holds.
      this.id = Math.floor(Math.random() * 2 ** 31);
      this.readyState = CONNECTING;
      this.onopen = null;
      this.onmessage = null;
      this.onclose = null;
      this.onerror = null;
      sockets.set(this.id, this);
      post({ open: this.id });
    }

    send(data) {
      if (this.readyState !== OPEN) throw new DOMException("not open", "InvalidStateError");
      post({ id: this.id, message: String(data) });
    }

    close() {
      if (this.readyState >= CLOSING) return;
      post({ close: this.id });
      this._closed();
    }

    _fire(type, init) {
      const event = type === "message" ? new MessageEvent("message", init) : new Event(type);
      const handler = this["on" + type];
      if (typeof handler === "function") handler.call(this, event);
      this.dispatchEvent(event);
    }

    _closed() {
      sockets.delete(this.id);
      this.readyState = CLOSED;
      // On a later turn, as a real socket's close event arrives.
      setTimeout(() => this._fire("close"), 0);
    }
  }
  BridgeSocket.CONNECTING = CONNECTING;
  BridgeSocket.OPEN = OPEN;
  BridgeSocket.CLOSING = CLOSING;
  BridgeSocket.CLOSED = CLOSED;
  window.WebSocket = BridgeSocket;
  window.__viz3dHosted = true;

  channel.onmessage = (event) => {
    let d;
    try {
      d = JSON.parse(event.data);
    } catch {
      return;
    }
    if (!d || typeof d !== "object") return;
    if (d.viewer !== undefined) {
      for (const socket of [...sockets.values()]) {
        if (socket.readyState === OPEN) socket._closed();
        else if (socket.readyState === CONNECTING) post({ open: socket.id });
      }
      return;
    }
    const socket = sockets.get(d.to);
    if (!socket) return;
    if (d.opened && socket.readyState === CONNECTING) {
      socket.readyState = OPEN;
      socket._fire("open");
    } else if (typeof d.message === "string" && socket.readyState === OPEN) {
      socket._fire("message", { data: d.message });
    }
  };

  window.addEventListener("pagehide", () => {
    for (const socket of [...sockets.values()]) socket.close();
  });

  // The page's own diagnosis for a server that has not answered talks about ports and SSH tunnels,
  // which is right for a script and wrong here: here it means the notebook has not got that far.
  const HOSTED_HINT =
    "Run the notebook's cells from the top. The viewer connects when the cell that calls " +
    "open_viewer(...) runs; the first run also installs PyLabRobot in your browser, which takes " +
    "a little while.";
  new MutationObserver(() => {
    const panel = document.getElementById("boot-diagnosis");
    if (!panel || panel.dataset.hosted) return;
    if (!/Waiting for the server/.test(panel.textContent || "")) return;
    panel.dataset.hosted = "1";
    const title = panel.querySelector("h2");
    if (title) title.textContent = "Waiting for the notebook";
    for (const p of panel.querySelectorAll("p")) p.textContent = HOSTED_HINT;
    for (const li of panel.querySelectorAll("li")) {
      if (/server not reachable/.test(li.textContent || "")) {
        li.textContent = "notebook not connected yet";
      }
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
