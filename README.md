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

Takes 1–3 minutes.

> **When it finishes, close that terminal window and open a new one.** The installer puts `uv` on your PATH, but only a *new* terminal reads that — in the window you installed from, `uv run …` still answers `uv: command not found`.

## Get started

The installer puts the class materials in your **home folder**, which is where a new terminal starts:

- Windows: `C:\Users\<YourName>\bme590-fall-2026`
- macOS: `/Users/<YourName>/bme590-fall-2026`

The installer's "Next steps" message prints the exact path — use that one if you chose a different folder. From a **new** terminal window (see above), go there and open the first workshop:

**Windows** (PowerShell):

```powershell
cd $HOME\bme590-fall-2026
uv run bme590 start 00
```

**Windows** (Command Prompt):

```bat
cd %USERPROFILE%\bme590-fall-2026
uv run bme590 start 00
```

**macOS / Linux** (Terminal — Git Bash on Windows is identical):

```bash
cd ~/bme590-fall-2026
uv run bme590 start 00
```

This copies workshop 00 into `assignments/`, opens it in VS Code, and selects the kernel. Later workshops are `start 01`, `start 02`, and so on. Run `uv run bme590` alone for the full command list.

Every `uv run bme590` command pulls the latest course materials before it does anything else, so you pick up fixes and new workshops just by working — no reinstall, and nothing in `assignments/` is touched. (`uv run bme590 update` does only that, and reports what happened.)

You should not have to choose a kernel: the workshops name the class kernel and the installer registered it, so the notebook's top right reads **BME 590 (lab automation)** as soon as it opens. If it reads **Select Kernel** instead, click that, choose **Select Another Kernel…** → **Python Environments…**, then pick **BME 590 (lab automation)**. Do *not* choose **Existing Jupyter Server…** — that one asks for a URL like `127.0.0.1` and is not what you want. (VS Code also opens this picker by itself the first time you run a cell without a kernel.)

> Work in `assignments/` and keep it **inside the class folder** — the notebooks load figures by relative path.

## Guidelines on the use of AI
AI coding agents are very effective at the solving the types of problems contained in these workbooks, so much so that one could easily solve all of the exercises provided. We insist that you reason through the solutions and write them yourself without directly prompting an LLM for the solution. You are expected to be able to defend the reasoning for your solutions.

## Help

If something's broken: run `uv run bme590 check` and paste the **entire** output into `#ed-discuss` on Slack, or email Stefan (stefan dot golas at duke dot edu).

If a new terminal says `command not found: uv` (macOS / Linux) or `uv is not recognized` (Windows), just re-run the install command above — it puts uv on the PATH that new terminals use, on every platform, and tells you which file it changed.

## For maintainers: the answer key and autograder

The solution notebooks are an answer key and never live in this (public) repo. They live in the private repo `chory-lab/bme590-fall-2026-solutions` (branch `main`), generated from `sources/*.py` by `scripts/make_solutions.py`.

- To grade locally, clone it into `solutions/` (gitignored here):

  ```bash
  git clone https://github.com/chory-lab/bme590-fall-2026-solutions solutions
  uv run --group notebook python scripts/grade.py solutions/    # must be 24/24 checks, 350/350 points
  ```

- In CI, the `grade` job in `.github/workflows/workshops.yml` checks out the private repo into `solutions/` using the `SOLUTIONS_TOKEN` repo secret, rebuilds the solution notebooks from `sources/` and asserts they are unchanged (`git diff --exit-code`), grades them (positive control), then grades the untouched workshop stubs (negative control, must score 0). If the secret is absent the job self-skips with a warning rather than failing.
- `SOLUTIONS_TOKEN` is a fine-grained PAT with read-only `Contents` access to `chory-lab/bme590-fall-2026-solutions`, stored as a repo secret on `chory-lab/bme590-fall-2026`. The workflow's built-in `GITHUB_TOKEN` can only read the repo it runs in, which is why a dedicated token is needed to fetch the private answer key.
- The old `stefangolas` fork and `stefangolas/bme590-fall-2026-solutions` are no longer used.
