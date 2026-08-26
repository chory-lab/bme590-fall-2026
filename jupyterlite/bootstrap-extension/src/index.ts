/**
 * plr-workshops:bootstrap
 *
 * Prepares every Pyodide kernel for the workshops, so the notebooks contain
 * coursework and nothing else.
 *
 * This replaces a code cell that used to be prepended to all six workshops.
 * That cell had two failure modes worth remembering, because they are the
 * reason this extension exists:
 *
 *   - Visible, it is boilerplate above the title of every notebook.
 *   - Hidden (`source_hidden`), it becomes a one-line grey strip that students
 *     scroll past, and skipping it makes every later cell fail with
 *     "No module named pylabrobot" -- which reads as a broken site.
 *
 * Neither survives Restart Kernel, which wipes the install and re-runs
 * nothing. Keying on kernel id here covers restarts as well as new notebooks.
 *
 * The execution is `silent`, so nothing lands in the notebook -- which means
 * the failure path is not optional. A bootstrap that throws must reach the
 * parent page, or the student meets the consequences several cells later with
 * no error to point at.
 */
import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';

/** Kernel-side bootstrap. Deliberately thin: the logic lives in the package,
 *  where it is readable, testable and versioned with the wheel. */
/** Split in two so the cold-start cost can be attributed: resolving and
 *  installing the wheel is a different problem from importing it. */
const INSTALL = `
import piplite
await piplite.install("bme590-workshops==0.1.0")
`;

const INITIALIZE = `
from plr_workshops.jupyterlite_bootstrap import initialize
await initialize()
`;

/** Kernel ids already prepared. A kernel restart issues a new id, so this both
 *  prevents duplicate work and re-bootstraps automatically after a restart. */
const prepared = new Set<string>();

function announce(type: string, detail: Record<string, unknown> = {}): void {
  const message = { type, ...detail };
  // The deck lives on the parent page; postMessage is how the rest of this
  // site already talks to it (see outer.html's relay).
  try {
    window.parent.postMessage(message, '*');
  } catch {
    /* standalone (no parent) is fine -- the console line below still lands */
  }
  console.log('[plr]', type, JSON.stringify(detail));
}

async function bootstrap(panel: NotebookPanel): Promise<void> {
  await panel.sessionContext.ready;

  const kernel = panel.sessionContext.session?.kernel;
  if (!kernel) {
    announce('PLR_BOOTSTRAP_FAILED', { error: 'no kernel for this notebook' });
    return;
  }
  if (prepared.has(kernel.id)) {
    return;
  }
  prepared.add(kernel.id);

  announce('PLR_BOOTSTRAP_STARTED', { kernelId: kernel.id });

  try {
    // `future.done` resolves even when the code raised, so the reply status is
    // what actually says whether a step worked.
    const run = async (code: string, label: string): Promise<number> => {
      const started = performance.now();
      const reply = await kernel.requestExecute({
        code,
        silent: true,
        store_history: false,
        stop_on_error: true
      }).done;
      if (reply.content.status !== 'ok') {
        const content = reply.content as any;
        const error = content.ename
          ? `${content.ename}: ${content.evalue}`
          : `execution ${reply.content.status}`;
        throw new Error(`${label}: ${error}`);
      }
      return Math.round(performance.now() - started);
    };

    // A no-op first, to separate "the kernel is not actually ready yet" from
    // "installing takes a while". sessionContext.ready resolves before Pyodide
    // has finished coming up, so the first execute absorbs the remaining
    // warm-up -- and attributing that to the install is how you end up
    // optimising the wrong thing.
    const firstExecMs = await run('pass', 'warmup');
    const installMs = await run(INSTALL, 'install');
    const initMs = await run(INITIALIZE, 'initialize');

    announce('PLR_BOOTSTRAP_READY', {
      kernelId: kernel.id,
      firstExecMs,
      installMs,
      initMs
    });
  } catch (err) {
    // Let a later open (or a restart) try again rather than latching failure.
    prepared.delete(kernel.id);
    announce('PLR_BOOTSTRAP_FAILED', {
      kernelId: kernel.id,
      error: err instanceof Error ? err.message : String(err)
    });
  }
}

/**
 * Horizontal space.
 *
 * The notebook shares the window with the deck, so it typically gets ~45% of
 * the viewport -- and JupyterLab's default chrome spends roughly 380px of that
 * before any code is visible: the file browser (~250px, open on every cold
 * start), two activity bars (~33px each), and a 64px prompt gutter on both the
 * input and output of every cell.
 *
 * These are all JupyterLab CSS variables, so this narrows spacing rather than
 * fighting the layout, and nothing here hides functionality: the file browser
 * is one click away on the activity bar that remains.
 */
const SPACING = `
  /* :root:root, not :root.
     The theme extension's stylesheet loads *after* this one and defines the
     same variables at :root, so an equal-specificity rule here loses on source
     order no matter when it is injected. Doubling the selector raises
     specificity (0,2,0 vs 0,1,0) and wins regardless of load order -- verified
     by reading the computed value back, which is the only way to catch this:
     the rule is present in the DOM either way. */
  :root:root {
    /* 64px of gutter, twice per cell, to show "[12]:". 40 still fits three
       digits at this font size. */
    --jp-cell-prompt-width: 40px;
    --jp-cell-padding: 3px;
    --jp-notebook-padding: 4px;
    --jp-sidebar-min-width: 200px;
  }
  /* The prompt is right-aligned into its gutter; reclaim the inner padding too. */
  .jp-InputPrompt, .jp-OutputPrompt { padding-left: 0; }
  /* Toolbar buttons carry generous side padding that costs a full row of width
     in a narrow pane. */
  .jp-NotebookPanel-toolbar .jp-ToolbarButtonComponent { padding-left: 4px; padding-right: 4px; }

  /* The right activity bar: a full-height grey strip holding one gear icon
     (Property Inspector) and otherwise nothing. Neither it nor the debugger is
     used anywhere in the workshops, and it sits directly between the notebook
     and the deck, so it reads as a gap between the two panes.
     The panel itself (#jp-right-stack) is untouched, so View ▸ Right Sidebar
     still works for anyone who wants it. */
  .jp-SideBar.jp-mod-right { display: none; }
`;

function reclaimSpace(app: JupyterFrontEnd): void {
  const style = document.createElement('style');
  style.id = 'plr-spacing';
  style.textContent = SPACING;
  document.head.appendChild(style);

  // Collapse the file browser on a cold start only.
  //
  // JupyterLab persists panel layout, so a student who opens the file browser
  // and reloads should find it open. Forcing it shut on every load would keep
  // overriding a deliberate choice, which is worse than the crowding. The flag
  // records that we have had our one opinion about it.
  // `app.shell` is typed as the minimal IShell, which does not declare
  // collapseLeft; the concrete LabShell does. Feature-detect rather than cast
  // hard, so a shell without it stays merely crowded instead of throwing during
  // startup -- this plugin also owns the kernel bootstrap, and taking that down
  // over a layout tweak would be a bad trade.
  const shell = app.shell as {
    collapseLeft?: () => void;
    collapseRight?: () => void;
    collapseDown?: () => void;
  };
  const collapse = () => {
    try {
      shell.collapseLeft?.();
      shell.collapseRight?.();
      // The log console docks along the bottom and opens on the first warning
      // JupyterLab emits -- which happens on every boot ("Disabling terminals
      // plugin because they are not available on the server"). It costs
      // vertical space for a message no student can act on.
      shell.collapseDown?.();
    } catch {
      /* layout is cosmetic; never let it break activation */
    }
  };

  const KEY = 'plr.collapsedLeftOnce';
  try {
    if (!window.localStorage.getItem(KEY)) {
      collapse();
      window.localStorage.setItem(KEY, '1');
    }
  } catch {
    // Private mode with storage denied: crowded is survivable, throwing is not.
    collapse();
  }
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'plr-workshops:bootstrap',
  autoStart: true,
  requires: [INotebookTracker],

  activate: (app: JupyterFrontEnd, notebooks: INotebookTracker) => {
    console.log('[plr] bootstrap extension activated');

    void app.restored.then(() => reclaimSpace(app));

    notebooks.widgetAdded.connect((_sender, panel) => {
      void bootstrap(panel);

      // Restart Kernel and Change Kernel both arrive here with a fresh kernel
      // id. Without this, a restart leaves the kernel un-bootstrapped and the
      // next cell fails on an import -- the exact symptom this replaces.
      panel.sessionContext.kernelChanged.connect(() => {
        void bootstrap(panel);
      });
    });
  }
};

export default plugin;
