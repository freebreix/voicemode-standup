# Dot-sourced by each start-*.ps1. Exits the caller if $Port is already served,
# so a second launch (scheduled task + manual, or overlapping start-all) is a no-op.
function Assert-PortFree([int]$Port, [string]$Name) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "$Name already listening on $Port - nothing to do."
        exit 0
    }
}
