# Registers the two Windows tasks for apple-music-discog on THIS PC (run it on one PC only):
#   1. "apple-music-discog weekly update"  - Fridays 12:00 (or at next logon if the PC was off)
#   2. "apple-music-discog website"        - starts http://localhost:8766 at logon, no window
# Run:    powershell -ExecutionPolicy Bypass -File setup-windows.ps1
# Remove: powershell -ExecutionPolicy Bypass -File setup-windows.ps1 -Remove
param([switch]$Remove)

$dir = $PSScriptRoot
$names = 'apple-music-discog weekly update', 'apple-music-discog website'

if ($Remove) {
    foreach ($n in $names) {
        Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue  # also ends the running website
        Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
    }
    "Removed both tasks."
    return
}

$python = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if ($python -like '*WindowsApps*' -or -not (Test-Path $pythonw)) {
    throw "Found only the Microsoft Store python stub ($python). Install Python from python.org (tick 'Add to PATH') and run again."
}

$weekly = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $names[0] -Force -Settings $weekly `
    -Description 'Adds new releases to the Apple Music discography playlists' `
    -Action (New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$dir\run-update.cmd`"") `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 12:00) | Out-Null

$always = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $names[1] -Force -Settings $always `
    -Description 'Local website for apple-music-discog (http://localhost:8766)' `
    -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "`"$dir\server.py`"" -WorkingDirectory $dir) `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) | Out-Null
Start-ScheduledTask -TaskName $names[1]

foreach ($n in $names) {
    $i = Get-ScheduledTask -TaskName $n | Get-ScheduledTaskInfo
    "{0}: next run {1}" -f $n, $(if ($n -like '*website') { 'at every logon (started now)' } else { $i.NextRunTime })
}
"Website: http://localhost:8766"
