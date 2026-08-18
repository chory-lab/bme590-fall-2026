# BME 590 – Laboratory Automation (Fall 2026)

Professor: Emma Chory, Ph.D. · TA: Benjamin (Ben) Perry

## Install

Install [VS Code](https://code.visualstudio.com/), then run the command for your OS. It installs Python, `pylabrobot`, and all class materials — no admin rights, no Conda, no WSL.

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

From the class folder, open a workshop:

```bash
uv run bme590 start 01
```

This copies workshop 01 into `assignments/`, opens it in VS Code, and selects the kernel. Run `uv run bme590` alone for the full command list.

> Work in `assignments/` and keep it **inside the class folder** — the notebooks load figures by relative path.

## Help

If something's broken: run `uv run python scripts/doctor.py` and paste the **entire** output into `#ed-discuss` on Slack, or email Ben (benjamin dot perry at duke dot edu).
