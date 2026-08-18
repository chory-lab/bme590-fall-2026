# BME 590 - install bootstrap (Windows PowerShell)
#
#   irm https://raw.githubusercontent.com/chory-lab/bme590-fall-2026/main/install.ps1 | iex
#
#
# This script does one thing: get a Python. Everything else -- fetching the
# course files, building the environment, configuring VS Code, verifying it --
# lives in scripts/install.py, which this hands off to. Keeping the shell layer
# this thin is deliberate: the logic exists once, in Python, instead of twice in
# two shell dialects that drift apart.
#
# Arguments are passed straight through, so this works:
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Wheelhouse D:\wheelhouse-windows-x86_64-py311.zip

param(
  [string]$Wheelhouse,
  [string]$Root
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Piped through `irm ... | iex`, this script runs in the caller's session, so
# `exit` would close the caller's whole PowerShell window -- including any error
# message still on screen. `$PSScriptRoot` is empty only in that case, which is
# how we tell the two apart: when run as a file we exit with a code (CI depends
# on it), when piped we leave the session alone.
$InvokedViaIex = -not $PSScriptRoot

$Raw = 'https://raw.githubusercontent.com/chory-lab/bme590-fall-2026/main'

function Die ($m) {
  Write-Host "`nINSTALL FAILED: $m" -ForegroundColor Red
  if ($InvokedViaIex) { throw 'Install aborted -- see the message above.' }
  exit 1
}

Write-Host '==> Checking for uv' -ForegroundColor Cyan

# uv is the package manager: one static ~35 MB executable, installed per-user
# with no administrator rights, which also supplies the Python 3.11 the class
# runs on.
function Find-Uv {
  $cmd = Get-Command uv -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  foreach ($p in @("$env:USERPROFILE\.local\bin\uv.exe", "$env:LOCALAPPDATA\uv\bin\uv.exe")) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

# Find-Uv accepts a uv that is not on PATH (the two known per-user locations), so
# the install can succeed while every future `uv run` in a new terminal reports
# "uv is not recognized" -- and re-running this, which the README offers as the
# fix, would never help. Guarantee the PATH entry ourselves.
#
# The registry, not [Environment]::SetEnvironmentVariable: reading the user PATH
# through that API expands any %USERPROFILE% style entries it contains, and
# writing the expanded result back would bake them in permanently. Read raw,
# write back as ExpandString.
function Add-ToUserPath ($dir) {
  $onPath = ($env:Path -split ';' | Where-Object { $_ } |
             ForEach-Object { $_.TrimEnd('\') }) -icontains $dir.TrimEnd('\')
  if ($onPath) { return }
  try {
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
    $raw = $key.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
    $already = ($raw -split ';' | Where-Object { $_ } |
                ForEach-Object { $_.TrimEnd('\') }) -icontains $dir.TrimEnd('\')
    if (-not $already) {
      $new = if ($raw) { "$dir;$raw" } else { $dir }
      $key.SetValue('Path', $new, [Microsoft.Win32.RegistryValueKind]::ExpandString)
      Write-Host "  added $dir to your PATH (new terminals will find uv)"
    }
    $key.Close()
  } catch {
    # A managed machine can forbid this. Not fatal -- the install still works in
    # this window; say what to do so a new one is not a mystery.
    Write-Host "  could not update your PATH ($($_.Exception.Message))."
    Write-Host "  If a new terminal says 'uv is not recognized', add $dir to PATH by hand."
    return
  }
  $env:Path = "$dir;$env:Path"
}

$uv = Find-Uv
if (-not $uv) {
  Write-Host '  not found - installing it (per-user, no administrator rights needed)'
  try {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  } catch {
    Die @"
could not install uv: $($_.Exception.Message)
Behind a proxy or campus firewall? Download it from
https://github.com/astral-sh/uv/releases, put it on your PATH, and run this again.
"@
  }
  # uv's installer edits PATH for future shells; make it visible to this one.
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
  $uv = Find-Uv
  if (-not $uv) { Die 'uv installed but is not on PATH. Close this window, open a new PowerShell, and run the command again.' }
}
Write-Host "  OK  uv at $uv" -ForegroundColor Green
Add-ToUserPath (Split-Path -Parent $uv)
$env:UV_BIN = $uv

# The installer proper: use the copy beside this script when there is one (a real
# checkout), otherwise fetch the single file it needs.
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'scripts\install.py'))) {
  $installer = Join-Path $PSScriptRoot 'scripts\install.py'
} else {
  $installer = Join-Path ([System.IO.Path]::GetTempPath()) "bme590-install-$(Get-Random).py"
  try {
    Invoke-WebRequest -Uri "$Raw/scripts/install.py" -OutFile $installer -UseBasicParsing
  } catch {
    Die "could not download the installer: $($_.Exception.Message)"
  }
}

$passthrough = @()
if ($Wheelhouse) { $passthrough += @('--wheelhouse', $Wheelhouse) }
if ($Root)       { $passthrough += @('--root', $Root) }

# --no-project: run against a bare interpreter, not the class environment, which
# does not exist yet. uv downloads that interpreter if the machine has none.
& $uv run --no-project --python 3.11 $installer @passthrough

if ($InvokedViaIex) {
  # Running in the caller's session: do not exit (that would close their
  # window). Report the result instead; install.py has already printed the
  # details above.
  if ($LASTEXITCODE -ne 0) {
    Write-Host "`nINSTALL FAILED (exit code $LASTEXITCODE). See the message above, or re-run to start over." -ForegroundColor Red
  }
} else {
  exit $LASTEXITCODE
}
