# Piper TTS (OpenAI-compatible) on 127.0.0.1:8880
# Outputs 24kHz PCM (response_format=pcm, resampled from Piper's 22.05kHz via soxr)
# for VoiceMode's streaming path; also serves wav. Synthetic "auto" voice routes
# hu/en by request text. Voices per tts/config.env.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_paths.ps1"
. "$PSScriptRoot\_guard.ps1"
Assert-PortFree 8880 "Piper TTS"

$py  = Join-Path $TtsDir '.venv\Scripts\python.exe'
$log = Join-Path $LogsDir 'tts.log'
if (-not (Test-Path $py))     { throw "tts venv missing - run install.ps1 ($py)" }
if (-not (Test-Path (Join-Path $TtsDir 'main.py'))) { throw "tts checkout missing - run install.ps1" }

Set-Location $TtsDir
& $py -m uvicorn main:app --host 127.0.0.1 --port 8880 *> $log
