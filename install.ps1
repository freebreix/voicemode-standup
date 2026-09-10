<#
  voicemode-standup installer (Windows).

  Idempotent: re-run any time to repair. Fetches pinned upstreams (see
  manifest.psd1), wires ~/.voicemode/voicemode.env, registers the per-session
  MCP server and the two backend Scheduled Tasks, and starts the services.

  Usage:  pwsh -File install.ps1  [-SkipModels] [-SkipServices] [-CpuOnly]
#>
[CmdletBinding()]
param(
    [switch]$SkipModels,
    [switch]$SkipServices,
    [switch]$CpuOnly
)
$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
. "$RepoRoot\scripts\_paths.ps1"
$m = Import-PowerShellDataFile (Join-Path $RepoRoot 'manifest.psd1')
$dl = Join-Path $env:TEMP 'vms-dl'
New-Item -ItemType Directory -Force -Path $dl,$WhisperDir,(Join-Path $WhisperDir 'models'),(Join-Path $WhisperDir 'tmp'),$LogsDir | Out-Null

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "missing '$cmd' - $hint" }
}
function Get-File($url, $out) {
    if (Test-Path $out) { Write-Host "  have $(Split-Path $out -Leaf)"; return }
    Write-Host "  downloading $(Split-Path $out -Leaf) ..."
    curl.exe -sL --fail -o $out $url
}

Write-Host "== prereqs =="
Need uv    "install from https://astral.sh/uv"
Need git   "install Git for Windows"
Need curl.exe "ships with Windows 10+"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "ffmpeg not on PATH - whisper --convert needs it (winget install Gyan.FFmpeg)"
}
$gpu = -not $CpuOnly -and (Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' })
Write-Host ("  GPU (CUDA) build: {0}" -f $(if ($gpu) {'yes'} else {'no - CPU only'}))

Write-Host "`n== TTS fork ($($m.TtsTag)) =="
if (-not (Test-Path (Join-Path $TtsDir 'main.py'))) {
    git clone --branch $m.TtsTag --depth 1 $m.TtsRepo $TtsDir
    git -C $TtsDir remote add upstream https://github.com/ginto-sakata/local-openai-tts-server.git 2>$null
} else { Write-Host "  present" }
Copy-Item (Join-Path $ConfigDir 'tts.config.env.template') (Join-Path $TtsDir 'config.env') -Force
if (-not (Test-Path (Join-Path $TtsDir '.venv\Scripts\python.exe'))) {
    Write-Host "  creating venv + installing deps ..."
    Push-Location $TtsDir
    uv venv --python $m.PythonVersion .venv
    uv pip install --python .venv\Scripts\python.exe -r requirements-windows.txt
    Pop-Location
} else { Write-Host "  venv present" }

Write-Host "`n== whisper.cpp ($($m.WhisperCppTag)) =="
$base = "https://github.com/ggml-org/whisper.cpp/releases/download/$($m.WhisperCppTag)"
function Fetch-WhisperBuild($asset, $destName) {
    $zip = Join-Path $dl $asset
    Get-File "$base/$asset" $zip
    $ex = Join-Path $dl ($destName + '-x')
    Expand-Archive -Force $zip $ex
    $rel = Join-Path $ex 'Release'
    $from = if (Test-Path $rel) { $rel } else { $ex }
    $to = Join-Path $WhisperDir $destName
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    Get-ChildItem $from -File | Copy-Item -Destination $to -Force
}
if ($gpu) { Fetch-WhisperBuild $m.WhisperCublasAsset 'bin-cuda' }
Fetch-WhisperBuild $m.WhisperCpuAsset 'bin'

if (-not $SkipModels) {
    Write-Host "`n== whisper models =="
    foreach ($name in $m.WhisperModels) {
        Get-File "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$name.bin" `
                 (Join-Path $WhisperDir "models\ggml-$name.bin")
    }
}

Write-Host "`n== ~/.voicemode/voicemode.env =="
$envFile = Join-Path $HOME '.voicemode\voicemode.env'
New-Item -ItemType Directory -Force -Path (Split-Path $envFile) | Out-Null
$block = Get-Content (Join-Path $ConfigDir 'voicemode.env.block') -Raw
$existing = if (Test-Path $envFile) { Get-Content $envFile -Raw } else { '' }
$pattern = '(?s)# ===== voicemode-standup.*?# <<< voicemode-standup <<<\r?\n?'
if ($existing -match $pattern) {
    $existing = [regex]::Replace($existing, $pattern, '')
    Write-Host "  replacing existing managed block"
}
if (Test-Path $envFile) { Copy-Item $envFile "$envFile.bak.$(Get-Date -Format yyyyMMddHHmmss)" }
Set-Content -Path $envFile -Value ($existing.TrimEnd() + "`n`n" + $block.TrimEnd() + "`n") -NoNewline

Write-Host "`n== shim venv =="
# Dedicated venv with the shim installed editable. Used as the per-session MCP
# command - more predictable than `uvx --from <path>` (no build-cache surprises)
# and picks up shim edits immediately.
$shimPy = Join-Path $ShimDir '.venv\Scripts\python.exe'
if (-not (Test-Path $shimPy)) { uv venv --python $m.PythonVersion (Join-Path $ShimDir '.venv') }
uv pip install --python $shimPy -e $ShimDir
Write-Host "  $shimPy -m voicemode_standup"

Write-Host "`n== MCP server (per-session stdio, user scope) =="
if (Get-Command claude -ErrorAction SilentlyContinue) {
    claude mcp remove voicemode -s user 2>$null
    claude mcp remove voicemode -s local 2>$null
    claude mcp add voicemode --scope user -- "$shimPy" -m voicemode_standup
    Write-Host "  registered (user scope)"
} else {
    Write-Warning "claude CLI not found - add MCP manually:"
    Write-Host "  claude mcp add voicemode --scope user -- `"$shimPy`" -m voicemode_standup"
}

Write-Host "`n== Scheduled Tasks =="
& "$ScriptsDir\register-tasks.ps1"

if (-not $SkipServices) {
    Write-Host "`n== start services =="
    & "$ScriptsDir\stop-all.ps1"
    Start-Sleep 1
    & "$ScriptsDir\start-all.ps1"
}

Write-Host "`nDone. Open a fresh Claude session and have it call the converse tool."
