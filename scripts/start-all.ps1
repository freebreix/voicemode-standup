# Launch the two backend services (TTS :8880, whisper :2022) as hidden
# background pwsh processes. The VoiceMode MCP itself is NOT a service here -
# each Claude session spawns its own stdio server via the shim (see README).
. "$PSScriptRoot\_paths.ps1"
foreach ($name in "tts","whisper") {
    Start-Process pwsh -WindowStyle Hidden -ArgumentList `
        '-NoProfile','-WindowStyle','Hidden','-File',"$ScriptsDir\start-$name.ps1"
    Write-Host "started $name"
    Start-Sleep 2
}
Write-Host "`nHealth (give whisper ~30-60s on a cold CUDA kernel cache):"
Start-Sleep 8
foreach ($p in 8880,2022) {
    $ok = Test-NetConnection 127.0.0.1 -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue
    Write-Host ("  {0}: {1}" -f $p, $(if ($ok) {"listening"} else {"not up yet"}))
}
