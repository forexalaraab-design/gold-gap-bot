# Optional LOCAL watchdog (run on your own PC when it's on).
# Guarantees the cloud chain never dies: if the latest GitHub run is older
# than 15 minutes and not running, it re-dispatches the workflow once.
#
#   powershell -File .\watchdog.ps1
#
# Tune $CheckSec (how often this checks) and $MaxAgeMin as you like.
# It does nothing special when the chain is healthy.
$gh  = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "forexalaraab-design/gold-gap-bot"
$MaxAgeMin = 15
$CheckSec  = 300

while ($true) {
    try {
        $r = (& $gh run list -R $repo --limit 1 --json databaseId,createdAt,status 2>$null | ConvertFrom-Json)
        if ($null -eq $r) { throw "no runs" }
        $last = [datetime]::Parse($r.createdAt)
        $age = ((Get-Date).ToUniversalTime() - $last).TotalMinutes
        if ($age -gt $MaxAgeMin -and $r.status -ne 'in_progress') {
            Write-Output ("[{0}] chain stale ({1:N1} min) -> re-dispatch" -f (Get-Date -Format HH:mm:ss), $age)
            & $gh workflow run goldgap.yml -R $repo --ref main
        } else {
            Write-Output ("[{0}] chain ok  age={1:N1} min  status={2}" -f (Get-Date -Format HH:mm:ss), $age, $r.status)
        }
    } catch {
        Write-Output ("[{0}] watchdog error: {1}" -f (Get-Date -Format HH:mm:ss), $_.Exception.Message)
    }
    Start-Sleep -Seconds $CheckSec
}