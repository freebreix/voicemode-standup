# Launch the two backend services (TTS :8880, whisper :2022) as hidden
# background pwsh processes. Used when running without Windows Services
# (register-tasks.ps1 / no elevation) or for a manual one-off run - if
# register-services.ps1 registered NSSM services, use Start-Service instead.
# The VoiceMode MCP itself is NOT a service here - each Claude session spawns
# its own stdio server via the shim (see README).
. "$PSScriptRoot\_paths.ps1"
. "$PSScriptRoot\_health.ps1"
foreach ($name in "tts","whisper") {
    Start-Process pwsh -WindowStyle Hidden -ArgumentList `
        '-NoProfile','-WindowStyle','Hidden','-File',"$ScriptsDir\start-$name.ps1"
    Write-Host "started $name"
    Start-Sleep 2
}
Write-Host "`nHealth (give whisper ~30-60s on a cold CUDA kernel cache):"
Show-Health
