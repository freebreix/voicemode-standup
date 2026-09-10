# Register (or refresh) the two backend services as per-user logon Scheduled Tasks.
# Run once:  pwsh -File scripts\register-tasks.ps1      Remove:  ... -Remove
param([switch]$Remove)
. "$PSScriptRoot\_paths.ps1"

$pwsh     = (Get-Command pwsh).Source
$user     = "$env:USERDOMAIN\$env:USERNAME"
$services = "tts","whisper"

foreach ($name in $services) {
    $taskName = "VoiceModeStandup\$name"
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    if ($Remove) { Write-Host "removed $taskName"; continue }

    $action  = New-ScheduledTaskAction -Execute $pwsh `
        -Argument "-NoProfile -WindowStyle Hidden -File `"$ScriptsDir\start-$name.ps1`""

    # AtLogOn + a 10-min repetition for a day. start-*.ps1 dot-sources _guard.ps1
    # and exits immediately if the port is already served, so the repetition is a
    # cheap self-heal for a missed logon event or a crashed service.
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $trigger.Delay = 'PT15S'
    $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes 10) `
        -RepetitionDuration (New-TimeSpan -Days 1)).Repetition

    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "registered $taskName"
}
if (-not $Remove) {
    Write-Host "`nStart now:  Get-ScheduledTask -TaskPath '\VoiceModeStandup\' | Start-ScheduledTask"
}
