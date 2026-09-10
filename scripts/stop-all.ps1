# Stop the backend services (TTS :8880, whisper :2022).
# Per-session voicemode stdio servers exit with their Claude session - not touched here.
foreach ($p in 8880,2022) {
    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}
Get-Process whisper-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "name='python.exe' OR name='python3.12.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'voicemode-standup|uvicorn main:app' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "stopped"
