# 🚀 BME 590 - Laboratory Automation Class Repository

Welcome to the official class repository for Fall 2026 BME 590: Laboratory Automation!

**Professor**: Emma Chory, Ph.D.

**Teaching Assistant:** Benjamin (Ben) Perry

---

This README will provide all the necessary steps to set up your computer for class assignments, tutorials, and projects. We will install all necessary tools, including Python and the `pylabrobot` library, which is the core module we will use to control laboratory equipment. 

Please follow these steps in order and if you run into any issues, please send an issue to the \#pylabrobot channel in slack! Additionally, you can contact Ben or Professor Chory.

---

## Step 1: Install everything, with one command

You need **one** thing installed by hand: [**VS Code**](https://code.visualstudio.com/), the editor we use in this class. Install it, then run the command below for your operating system.

Everything else — Python, the `pylabrobot` library, the class materials, the VS Code settings — is installed by the command. It needs no administrator rights, does not touch any Python you already have, and is safe to run more than once.

**Windows** — open **PowerShell** (search "PowerShell" in the Start menu) and paste:

```powershell
irm https://raw.githubusercontent.com/chory-lab/bme590-fall-2026/main/install.ps1 | iex
```

**macOS / Linux** — open **Terminal** and paste:

```bash
curl -LsSf https://raw.githubusercontent.com/chory-lab/bme590-fall-2026/main/install.sh | sh
```

Expect it to take **1–3 minutes**, most of which is downloading. When it finishes it prints the folder it installed into (`bme590-fall-2026` in your home folder) and the next steps.

> **Windows users:** you do **not** need WSL, and you do **not** need Conda. Earlier versions of this class asked for both. Nothing in these workshops requires them, and every extra tool is another thing that can break.

If you already have a copy of the repository, you can instead double-click **`Install-Windows.cmd`** (Windows) or **`Install-macOS.command`** (Mac) inside it. On a Mac, if it says the file is "from an unidentified developer", right-click it and choose **Open** — or just use the Terminal command above, which is not subject to that check.

### If the network is the problem

The install downloads about 130 MB. On a conference-grade Wi-Fi network, or one that inspects TLS traffic, that can crawl or fail outright. For those cases we publish an **offline bundle** per platform on the [Releases page](https://github.com/chory-lab/bme590-fall-2026/releases) — one file containing every package *and* the Python interpreter:

```powershell
# Windows: with the bundle in your Downloads folder
powershell -ExecutionPolicy Bypass -File install.ps1 -Wheelhouse "$HOME\Downloads\wheelhouse-windows-x86_64-py311.zip"
```

```bash
# macOS / Linux
sh install.sh --wheelhouse ~/Downloads/wheelhouse-macos-arm64-py311.zip
```

Download the bundle matching your machine (`windows-x86_64`, `macos-arm64` for Apple silicon, `macos-x86_64` for Intel Macs, `linux-x86_64`). The install then needs **no network at all** and takes about a minute. A bundle that also happens to be sitting next to the installer is picked up automatically, so a TA can hand out a USB stick with both files on it.

### What the installer actually does

Worth reading once, so that nothing here is magic. The command you paste is a
short bootstrap whose only job is to obtain a Python; it then hands off to
[`scripts/install.py`](./scripts/install.py), which does the rest:

1. Installs [**uv**](https://docs.astral.sh/uv/), a single small program that manages Python versions and packages. It lives in your user folder and needs no admin rights. (uv is fetched by `curl` / PowerShell, which your OS already has; uv then fetches Python 3.11. That's the whole chain.)
2. Downloads the class materials (using Git if you have it, a `.zip` if you don't).
3. Creates a `.venv` folder inside the class folder, holding **Python 3.11** and every package the workshops need. It installs the exact versions pinned in `uv.lock`, so the whole class runs identical software — which is what makes problems debuggable.
4. Writes `.vscode/settings.json` so VS Code already points at that Python. (This is the step people most often got wrong by hand.)
5. Installs the **Python** and **Jupyter** VS Code extensions, if VS Code's `code` command is available.
6. Registers a Jupyter kernel named **BME 590 (lab automation)**.
7. Runs a self-test: it checks every `pylabrobot` import the workshops use, then runs a small pipetting protocol end to end.

---

## Step 2: Open the class folder and run a workshop

Every working session is **one command**, run from the class folder:

```bash
uv run bme590 start 01
```

It makes your own copy of workshop 01 in `assignments/`, brings the environment up to date, opens the copy in VS Code with the kernel already selected, and prints a short reminder of how the visualizer and GIF recording work. Run `uv run bme590` on its own for the workshop list and the other commands:

| Command | What it does |
|---|---|
| `uv run bme590 start 01` | copy workshop 01 and open it, ready to run |
| `uv run bme590 check` | verify the install; prints a report you can paste into Slack |
| `uv run bme590 update` | pull the latest materials and match the environment to them |
| `uv run bme590 lab` | work in JupyterLab instead of VS Code |

> Work in `assignments/`, and **keep it inside the class folder**. The notebooks load figures and data files by relative path (`../figs/`, `../data/`), so a copy on your Desktop will show no images and fail to read `cloning.csv` — which looks exactly like a broken install, but isn't one. `bme590 start` puts the copy in the right place for you.

<details>
<summary>The same thing by hand, if you would rather see the steps</summary>

1. Open VS Code → **File → Open Folder…** → choose the `bme590-fall-2026` folder the installer reported. Open the *folder*, not just a file: the folder is what carries the settings that point at the right Python.
2. If VS Code offers to install the **Python** and **Jupyter** extensions, accept.
3. Copy the workshop you're starting into `assignments/`:

    ```bash
    uv run python scripts/start_workshop.py 01
    ```

4. Open your copy from the VS Code file tree and press **Run** on the first cell. The notebooks name the kernel the installer registered, so you should not be asked to choose one; if you are, pick **BME 590 (lab automation)**.

</details>

### While you are working in a notebook

- **The visualizer** opens in a browser tab at `http://127.0.0.1:1337`, and the top right should read **Connected**. If it doesn't, reload that page.
- **Re-running a visualizer cell** leaves the old visualizer running, and your browser tab stays attached to *it* — so the deck looks frozen. Either restart the kernel, or use the helper that closes the old one first:

    ```python
    from plr_workshops.workshop import visualizer, wait_for_recording

    lh, vis = await visualizer(deck)   # safe to re-run as often as you like
    ```

- **Recording a GIF** requires clicking **Start Recording** *before* the protocol cell runs. The workshops leave a five second window for it; `await wait_for_recording()` waits for you instead, which is easier to hit and still works when you have set `SLEEP = 0`.
- **`SLEEP`** at the top of each notebook scales every pause. Set it to `0` to run at full speed once you have watched the protocol.

---

## Step 3: Check your install, any time

If anything looks wrong — an import fails, a notebook can't find `pylabrobot`, a cell errors in a way that seems unrelated to your code — run:

```bash
uv run python scripts/doctor.py
```

It prints your Python version and location, checks every package and workshop import, and runs a pipetting smoke test. **Paste its entire output into the `#pylabrobot` Slack channel** when you ask for help; it contains nearly everything we need to diagnose a broken environment, and a screenshot of a single red line usually does not.

Running commands in a terminal that don't start with `uv run`? Activate the environment first, so that plain `python` means the class's Python:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
```

Or simply prefix any command with `uv run`, which needs no activation at all.

---

## Step 4: Updating to the latest version

We fix bugs and improve the workshops during the semester. To get the latest materials **and** any new packages they need, re-run the installer command from Step 1. It updates in place: it pulls the new materials, installs anything new, and re-runs the self-test.

If you prefer to do it by hand from inside the class folder:

```bash
git pull
uv sync --frozen
```

Your work in `assignments/` is never touched by either route. This is the reason for the copy step — if you edit the files in `workshops/` directly, an update can collide with your changes.

---

## Advanced: installing with Conda instead

The `uv` path above is the supported one, and the one we can help you debug. If you have a specific reason to use Conda — you already manage everything else that way, for example — `environment.yaml` builds the same environment:

```bash
conda env create -f environment.yaml
conda activate lab-automation
python scripts/doctor.py
```

This is slower (Conda's solver, rather than a pre-resolved lock file) and its package versions are pinned less tightly, so if you hit something the rest of the class doesn't, try the `uv` path before asking for help.

---

## Help Resources & Troubleshooting

If you are having issues with installing or running PyLabRobot locally, please reach out to the TA for help.

**Before you ask, do these two things** — between them they fix or diagnose most problems:

1. Re-run the installer command from Step 1. It is safe to run repeatedly and repairs a half-finished install.
2. Run `uv run python scripts/doctor.py` and copy its **entire** output into your message.

If at any point in this process you run into troubles installing the requisite software, please follow the order of steps below:

1. Post an issue in the \#ed-discuss channel on slack. For anonymous question asking, use the `/anonymous` prefix before your message.
2. Email Ben (benjamin [dot] perry [at] duke [dot] edu) with the subject line **BME 590 Code Issues**
3. Come to office hours for Ben or Professor Chory, if scheduled.
4. Email Professor Chory (emma [dot] chory [at] duke [dot] edu).
