# Dot-sourced by every script. Resolves repo layout from this file's location,
# so the stack works from any checkout path (no hardcoded C:\ paths).
$RepoRoot   = Split-Path -Parent $PSScriptRoot
$ScriptsDir = $PSScriptRoot
$TtsDir     = Join-Path $RepoRoot 'tts'
$WhisperDir = Join-Path $RepoRoot 'whisper'
$ShimDir    = Join-Path $RepoRoot 'shim'
$ConfigDir  = Join-Path $RepoRoot 'config'
$LogsDir    = Join-Path $RepoRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
