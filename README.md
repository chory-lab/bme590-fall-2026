# BME 590 – Laboratory Automation (Fall 2026)

Professor: Emma Chory, Ph.D. · TA: Stefan Golas

## Install

Install [VS Code](https://code.visualstudio.com/), then run the command for your OS. It installs Python, `pylabrobot`, and all class materials.

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/chory-lab/bme590-fall-2026/main/install.ps1 | iex
```

**macOS / Linux** (Terminal):

```bash
curl -LsSf https://raw.githubusercontent.com/chory-lab/bme590-fall-2026/main/install.sh | sh
```

Takes 1–3 minutes. Re-run it any time to update.

## Get started

The installer puts the class materials in your **home folder**, which is where a new terminal starts:

- Windows: `C:\Users\<YourName>\bme590-fall-2026`
- macOS: `/Users/<YourName>/bme590-fall-2026`

The installer's "Next steps" message prints the exact path — use that one if you chose a different folder. From a new terminal, go there and open a workshop:

**Windows** (PowerShell):

```powershell
cd $HOME\bme590-fall-2026
uv run bme590 start 01
```

**Windows** (Command Prompt):

```bat
cd %USERPROFILE%\bme590-fall-2026
uv run bme590 start 01
```

**macOS / Linux** (Terminal — Git Bash on Windows is identical):

```bash
cd ~/bme590-fall-2026
uv run bme590 start 01
```

This copies workshop 01 into `assignments/`, opens it in VS Code, and selects the kernel. Run `uv run bme590` alone for the full command list.

You should not have to choose a kernel: the workshops name the class kernel and the installer registered it, so the notebook's top right reads **BME 590 (lab automation)** as soon as it opens. If it reads **Select Kernel** instead, click that, choose **Jupyter Kernel…**, then **BME 590 (lab automation)** — the kernels are one level down, under that heading, not in the first list you see. (VS Code also opens this picker by itself the first time you run a cell without a kernel.)

> Work in `assignments/` and keep it **inside the class folder** — the notebooks load figures by relative path.

## Guidelines on the use of AI
AI coding agents are very effective at the solving the types of problems contained in these workbooks, so much so that one could easily solve all of the exercises provided. We insist that you reason through the solutions and write them yourself without directly prompting an LLM for the solution. You are expected to be able to defend the reasoning for your solutions

## Help

If something's broken: run `uv run bme590 check` and paste the **entire** output into `#ed-discuss` on Slack, or email Stefan (stefan dot golas at duke dot edu).

If a new terminal says `command not found: uv` (macOS / Linux) or `uv is not recognized` (Windows), just re-run the install command above — it puts uv on the PATH that new terminals use, on every platform, and tells you which file it changed.
