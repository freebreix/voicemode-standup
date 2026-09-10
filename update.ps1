<#
  Re-pull pinned upstreams after a manifest.psd1 bump, then restart services.
  For a first-time setup use install.ps1.
#>
[CmdletBinding()]
param([switch]$CpuOnly)
$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
. "$RepoRoot\scripts\_paths.ps1"
$m = Import-PowerShellDataFile (Join-Path $RepoRoot 'manifest.psd1')

Write-Host "== TTS server deps =="
Copy-Item (Join-Path $ConfigDir 'tts.config.env.template') (Join-Path $TtsDir 'config.env') -Force
if (Test-Path (Join-Path $TtsDir '.venv\Scripts\python.exe')) {
    Push-Location $TtsDir
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
    Pop-Location
} else {
    Write-Warning "tts/.venv missing - run install.ps1"
}

Write-Host "`n== shim deps ($($m.VoiceModePin)) =="
# uvx re-resolves from shim/pyproject.toml on next launch; force a rebuild:
uv cache prune 2>$null | Out-Null
Write-Host "  shim will rebuild on next Claude session"

Write-Host "`n== re-merge voicemode.env block =="
$iargs = @{ SkipModels = $true; SkipServices = $true }
if ($CpuOnly) { $iargs.CpuOnly = $true }
& "$RepoRoot\install.ps1" @iargs

Write-Host "`n== restart services =="
& "$ScriptsDir\stop-all.ps1"; Start-Sleep 1; & "$ScriptsDir\start-all.ps1"
