# Stop the backend services (TTS :8880, whisper :2022): Windows Services
# (NSSM, register-services.ps1) if registered, else raw processes (Scheduled
# Task / manual run). Per-session voicemode stdio servers exit with their
# Claude session - not touched here. (The process-name match below used to be
# a bare 'voicemode-standup', which also matched a per-session shim's own
# command line and killed an unrelated Claude session's MCP connection; now
# scoped to the TTS venv's own uvicorn process.)
. "$PSScriptRoot\_paths.ps1"

$svc = Get-Service VoiceModeStandup* -ErrorAction SilentlyContinue
if ($svc) {
    $svc | Stop-Service -Force -ErrorAction SilentlyContinue
    Write-Host "stopped (services)"
    exit 0
}

foreach ($p in 8880,2022) {
    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}
Get-Process whisper-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "name='python.exe' OR name='python3.12.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'uvicorn main:app' -and $_.CommandLine -match [regex]::Escape($TtsDir) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "stopped"
