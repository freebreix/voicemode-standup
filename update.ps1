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

Write-Host "== TTS fork -> $($m.TtsTag) =="
if (Test-Path (Join-Path $TtsDir '.git')) {
    git -C $TtsDir fetch --tags origin
    git -C $TtsDir checkout --force $m.TtsTag
    Copy-Item (Join-Path $ConfigDir 'tts.config.env.template') (Join-Path $TtsDir 'config.env') -Force
    Push-Location $TtsDir
    uv pip install --python .venv\Scripts\python.exe -r requirements-windows.txt
    Pop-Location
} else {
    Write-Warning "tts/ not a clone - run install.ps1"
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
