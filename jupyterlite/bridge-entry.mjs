// Host-side bridge to the JupyterLite iframe via jupyter-iframe-commands.
// Exposed as window.__liteBridge for the driver and for future page code.
import { createBridge } from "jupyter-iframe-commands-host";

window.__liteBridge = createBridge({ iframeId: "lite" });
