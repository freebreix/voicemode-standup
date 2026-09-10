# whisper.cpp STT (OpenAI-compatible) on 127.0.0.1:2022
# GPU build (CUDA 12.4 cuBLAS) + large-v3-turbo => ~0.5s per utterance on RTX 2060.
# First launch after a driver/build change JIT-compiles CUDA kernels (~1 min, cached
# in %APPDATA%\NVIDIA\ComputeCache). CPU fallback: bin-cuda absent -> bin is used.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_paths.ps1"
. "$PSScriptRoot\_guard.ps1"
Assert-PortFree 2022 "whisper STT"

$log = Join-Path $LogsDir 'whisper.log'

$model = $env:VOICEMODE_WHISPER_MODEL; if (-not $model) { $model = "large-v3-turbo" }
$modelPath = Join-Path $WhisperDir "models\ggml-$model.bin"
if (-not (Test-Path $modelPath)) { throw "whisper model not found: $modelPath - run install.ps1" }

$bin = Join-Path $WhisperDir "bin-cuda\whisper-server.exe"
if (-not (Test-Path $bin)) { $bin = Join-Path $WhisperDir "bin\whisper-server.exe" }
if (-not (Test-Path $bin)) { throw "whisper-server.exe not found - run install.ps1" }

# whisper-server writes ffmpeg scratch files (from --convert) into --tmp-dir.
# Two Windows bugs make the default (".") fail:
#   1. Scheduled Task launches with CWD = C:\WINDOWS\system32 (not writable by a
#      Limited user) so the temp .wav never gets created and ffmpeg 500s with
#      "Error opening input file ...".
#   2. generate_temp_filename() streams std::filesystem::path::preferred_separator
#      (a wchar_t, value 92) into a narrow stream, so the separator prints as the
#      literal text "92". Passing a tmp-dir that already ends in "/" keeps the
#      mangled name ("<tmpdir>/92whisper-server-*.wav") inside our folder.
$tmp = Join-Path $WhisperDir "tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Set-Location $tmp

& $bin `
    --host 127.0.0.1 --port 2022 `
    --model $modelPath `
    --language auto `
    --flash-attn `
    --convert `
    --tmp-dir "$($tmp -replace '\\','/')/" `
    --inference-path /v1/audio/transcriptions *> $log
