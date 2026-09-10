# Piper TTS (OpenAI-compatible) on 127.0.0.1:8880
# Outputs 24kHz PCM (response_format=pcm, resampled from Piper's 22.05kHz via soxr)
# for VoiceMode's streaming path; also serves wav. The "auto" voice detects the
# utterance language and assigns a stable per-session speaker. Config in tts/config.env.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_paths.ps1"
. "$PSScriptRoot\_guard.ps1"
Assert-PortFree 8880 "Piper TTS"

$py  = Join-Path $TtsDir '.venv\Scripts\python.exe'
$log = Join-Path $LogsDir 'tts.log'
if (-not (Test-Path $py)) { throw "tts venv missing - run install.ps1 ($py)" }

Set-Location $TtsDir
& $py -m uvicorn main:app --host 127.0.0.1 --port 8880 *> $log
