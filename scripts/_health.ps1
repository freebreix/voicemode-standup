# Dot-sourced by start-all.ps1 and register-services.ps1. Prints port/health
# status for the two backend services (give whisper ~30-60s on a cold CUDA
# kernel cache before its port comes up).
function Show-Health {
    Start-Sleep 5
    foreach ($p in 8880,2022) {
        $ok = Test-NetConnection 127.0.0.1 -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue
        Write-Host ("  {0}: {1}" -f $p, $(if ($ok) {"listening"} else {"not up yet"}))
    }
    try {
        $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8880/v1/health' -TimeoutSec 5
        if ($h.status -ne 'ok') {
            Write-Host "`nTTS CONFIG ERRORS:" -ForegroundColor Red
            $h.errors | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
        } else {
            Write-Host ("  TTS languages: {0} (primary {1}, quality {2})" -f ($h.languages -join ','), $h.primary_language, $h.preferred_quality)
        }
    } catch { }
}
