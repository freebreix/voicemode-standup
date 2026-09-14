# Register (or refresh) the two backend processes as real Windows Services via
# NSSM (nssm.cc). The SCM launches services in Session 0, so no console window
# is ever created - unlike the Scheduled Task fallback (register-tasks.ps1),
# whose hidden pwsh window can still flash visible under Task Scheduler.
# Registering a service needs admin; that's the whole reason register-tasks.ps1
# stays around as what install.ps1 falls back to when it can't elevate.
#
# Run once, elevated:  pwsh -File scripts\register-services.ps1     Remove: ... -Remove
param([switch]$Remove)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_paths.ps1"
. "$PSScriptRoot\_health.ps1"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "register-services.ps1 must run elevated (Windows Services require admin) - re-run pwsh as Administrator."
}

$nssm = Get-ChildItem (Join-Path $RepoRoot 'tools\nssm') -Recurse -Filter nssm.exe -ErrorAction SilentlyContinue |
    Sort-Object { $_.FullName -match '\\win64\\' } -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $nssm) { throw "nssm.exe not found under tools\nssm - run install.ps1 first" }

$pwsh = (Get-Command pwsh).Source
$services = [ordered]@{
    VoiceModeStandupTTS     = 'start-tts.ps1'
    VoiceModeStandupWhisper = 'start-whisper.ps1'
}

foreach ($name in $services.Keys) {
    & $nssm stop $name 2>$null | Out-Null
    & $nssm remove $name confirm 2>$null | Out-Null
    if ($Remove) { Write-Host "removed $name"; continue }

    $script = Join-Path $ScriptsDir $services[$name]
    & $nssm install $name $pwsh "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
    & $nssm set $name AppDirectory $RepoRoot        | Out-Null
    & $nssm set $name AppStdout (Join-Path $LogsDir "$name.svc.log") | Out-Null
    & $nssm set $name AppStderr (Join-Path $LogsDir "$name.svc.log") | Out-Null
    & $nssm set $name AppRotateFiles 1              | Out-Null
    & $nssm set $name AppRotateBytes 5242880        | Out-Null
    & $nssm set $name Start SERVICE_AUTO_START      | Out-Null
    & $nssm set $name AppExit Default Restart       | Out-Null
    & $nssm set $name AppThrottle 1500              | Out-Null
    & $nssm start $name | Out-Null
    Write-Host "registered + started $name"
}
if (-not $Remove) {
    Write-Host "`nHealth (give whisper ~30-60s on a cold CUDA kernel cache):"
    Show-Health
    Write-Host "`nManage:  Get-Service VoiceModeStandup* | Format-Table Name,Status"
}
