# One-line setup for the viz3d demo on Windows: installs uv if it is missing, then lets
# `viz3d setup` build the environment from uv.lock and register the Jupyter kernel.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv run viz3d setup @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run viz3d doctor
