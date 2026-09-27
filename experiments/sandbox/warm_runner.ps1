# ATLAS api-harness: WARM sandbox runner for AutoHotkey tests.
#
# Kris, 2026-09-26: "I dont reset my computer after every reboot, only when I need
# to. Perhaps we can run the tests using one sandbox unless conditions warrant
# refreshing between tests cycles." Booting took ~5 minutes; running the tests ~30 s.
#
# One sandbox serves many runs. The host drops a job folder into <WarmDir>\inbox
# (files, job.json, and ready.txt written LAST); this runner picks jobs up in name
# order, runs each test file in its own AutoHotkey process with a timeout, writes
#   <job>\run.log, <job>\<test>.tap, <job>\runner_done.txt  (same protocol as runner.ps1)
# and between jobs kills every AutoHotkey process. If one survives, the box is
# not clean: it writes dirty.txt and shuts down, and the host boots a fresh one.
# It also shuts down after idle_s without work, after max_jobs, or on stop.txt.
# <WarmDir>\heartbeat.txt is rewritten every second so the host knows it is alive.
# Keep this file ASCII: Windows PowerShell 5.1 misreads BOM-less UTF-8.

param(
    [Parameter(Mandatory = $true)][string]$WarmDir,
    [Parameter(Mandatory = $true)][string]$ToolsDir
)

$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$cfg = Get-Content -Raw -Path (Join-Path $WarmDir 'warm.json') | ConvertFrom-Json
$Inbox = Join-Path $WarmDir 'inbox'
$exe = Join-Path $cfg.exe_dir $cfg.exe
$Started = Get-Date
$LastWork = Get-Date
$JobsDone = 0
$StopReason = ''

# ---- window (Kris asked to always see what a sandbox is doing) -----------------
$form = New-Object System.Windows.Forms.Form
$form.Text = 'ATLAS warm sandbox'
$form.Size = New-Object System.Drawing.Size(700, 420)
$form.StartPosition = 'Manual'
$form.Location = New-Object System.Drawing.Point(24, 24)
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 26, 31)
$form.ForeColor = [System.Drawing.Color]::Gainsboro
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$stateLabel = New-Object System.Windows.Forms.Label
$stateLabel.Font = New-Object System.Drawing.Font('Segoe UI', 16, [System.Drawing.FontStyle]::Bold)
$stateLabel.Location = New-Object System.Drawing.Point(14, 12)
$stateLabel.Size = New-Object System.Drawing.Size(660, 36)
$info = New-Object System.Windows.Forms.Label
$info.Location = New-Object System.Drawing.Point(16, 52)
$info.Size = New-Object System.Drawing.Size(660, 22)
$info.ForeColor = [System.Drawing.Color]::DarkGray
$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = 'Vertical'
$logBox.Font = New-Object System.Drawing.Font('Consolas', 9)
$logBox.BackColor = [System.Drawing.Color]::FromArgb(13, 17, 23)
$logBox.ForeColor = [System.Drawing.Color]::Gainsboro
$logBox.Location = New-Object System.Drawing.Point(16, 80)
$logBox.Size = New-Object System.Drawing.Size(652, 290)
$form.Controls.AddRange(@($stateLabel, $info, $logBox))
$form.Show()

function Pump([string]$state) {
    $idle = [int]((Get-Date) - $LastWork).TotalSeconds
    $stateLabel.Text = $state
    $info.Text = ('up {0:mm\:ss}   runs served {1}/{2}   idle {3}s of {4}s' -f `
        ((Get-Date) - $Started), $JobsDone, $cfg.max_jobs, $idle, $cfg.idle_s)
    Set-Content -Path (Join-Path $WarmDir 'heartbeat.txt') `
        -Value ('{0:o} jobs={1} state={2}' -f (Get-Date), $JobsDone, $state) -Encoding ASCII
    [System.Windows.Forms.Application]::DoEvents()
}

function Log([string]$msg) {
    $logBox.AppendText(('{0:HH:mm:ss} {1}' -f (Get-Date), $msg) + "`r`n")
    Add-Content -Path (Join-Path $WarmDir 'warm.log') -Value ('{0:HH:mm:ss} {1}' -f (Get-Date), $msg) -Encoding ASCII
}

function Stop-Ahk {
    Get-Process -Name 'AutoHotkey*' -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force } catch {}
    }
    Start-Sleep -Milliseconds 300
    return -not (Get-Process -Name 'AutoHotkey*' -ErrorAction SilentlyContinue)
}

function Run-Job([string]$JobDir) {
    $job = Get-Content -Raw -Path (Join-Path $JobDir 'job.json') | ConvertFrom-Json
    $report = ''
    $okCount = 0; $badCount = 0; $broken = @()
    foreach ($t in $job.tests) {
        $tap = Join-Path $JobDir ($t + '.tap')
        $err = Join-Path $JobDir ($t + '.stderr')
        Set-Content -Path (Join-Path $JobDir 'stage.txt') -Value ('2 running ' + $t) -Encoding ASCII
        Pump ('Running ' + $t)
        Log ('run: ' + $job.run_id + ' ' + $t)
        $proc = Start-Process -FilePath $exe `
            -ArgumentList @('/ErrorStdOut', ('"' + (Join-Path $JobDir $t) + '"'), ('"' + $tap + '"')) `
            -WorkingDirectory $JobDir -RedirectStandardError $err -NoNewWindow -PassThru
        $deadline = (Get-Date).AddSeconds([int]$job.per_test_timeout_s)
        while (-not $proc.HasExited -and (Get-Date) -lt $deadline) {
            Pump ('Running ' + $t); Start-Sleep -Milliseconds 200
        }
        if (-not $proc.HasExited) {
            try { Stop-Process -Id $proc.Id -Force } catch {}
            $broken += ($t + ': timed out after ' + $job.per_test_timeout_s + 's')
            Log ($t + ': TIMEOUT')
            continue
        }
        $text = if (Test-Path $tap) { Get-Content -Raw -Path $tap } else { '' }
        $errText = if (Test-Path $err) { Get-Content -Raw -Path $err } else { '' }
        $report += ('# file ' + $t + "`r`n" + $text + "`r`n")
        if ($errText) { $report += ('# stderr ' + $t + "`r`n" + $errText + "`r`n") }
        $ok = ([regex]::Matches($text, '(?m)^ok ')).Count
        $bad = ([regex]::Matches($text, '(?m)^not ok')).Count
        $okCount += $ok; $badCount += $bad
        if (-not $text.Contains('# done')) {
            $broken += ($t + ': never reached Done() (exit ' + $proc.ExitCode + ')' + $(if ($errText) { ' - ' + $errText.Trim() } else { '' }))
        }
        Log ('{0}: {1} ok, {2} not ok, exit {3}' -f $t, $ok, $bad, $proc.ExitCode)
    }
    $summary = '{0} failed, {1} passed' -f $badCount, $okCount
    Set-Content -Path (Join-Path $JobDir 'run.log') -Value ($report + "`r`n" + $summary + "`r`n" + ($broken -join "`r`n")) -Encoding UTF8
    if ($broken.Count) { $v = 'FAIL ' + $broken[0] }
    elseif ($badCount) { $v = 'FAIL ' + $summary }
    elseif ($okCount -eq 0) { $v = 'FAIL no test reported a result' }
    else { $v = 'PASS ' + $summary }
    Set-Content -Path (Join-Path $JobDir 'runner_done.txt') -Value $v -Encoding ASCII
    Log ($job.run_id + ': ' + $v)
}

# ---- boot: trim Windows once, then serve jobs --------------------------------
Pump 'Booted - trimming Windows'
Log ('sandbox up for {0:N0}s before the runner started' -f ((Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime).TotalSeconds)
$profilePath = Join-Path $ToolsDir 'debloat_profile.json'
if ($cfg.debloat -and (Test-Path $profilePath)) {
    try {
        . (Join-Path $ToolsDir 'debloat.ps1')
        $prof = Get-Content -Raw -Path $profilePath | ConvertFrom-Json
        Invoke-Debloat -Settings $prof -JobDir $WarmDir -GodotDir $cfg.exe_dir -Log ${function:Log}
    } catch { Log ('debloat failed: ' + $_) }
}
Set-Content -Path (Join-Path $WarmDir 'ready_for_jobs.txt') -Value 'ready' -Encoding ASCII
Log 'ready for jobs'

while ($true) {
    if (Test-Path (Join-Path $WarmDir 'stop.txt')) { $StopReason = 'asked to stop'; break }
    if ($JobsDone -ge [int]$cfg.max_jobs) { $StopReason = ('served ' + $JobsDone + ' runs'); break }
    if (((Get-Date) - $LastWork).TotalSeconds -gt [int]$cfg.idle_s) { $StopReason = 'idle'; break }
    $next = Get-ChildItem -Path $Inbox -Directory -ErrorAction SilentlyContinue |
        Where-Object { (Test-Path (Join-Path $_.FullName 'ready.txt')) -and -not (Test-Path (Join-Path $_.FullName 'runner_done.txt')) } |
        Sort-Object Name | Select-Object -First 1
    if (-not $next) { Pump 'Warm - waiting for tests'; Start-Sleep -Milliseconds 500; continue }
    try { Run-Job $next.FullName } catch {
        Set-Content -Path (Join-Path $next.FullName 'runner_done.txt') -Value ('FAIL runner error: ' + $_) -Encoding ASCII
        Log ('runner error: ' + $_)
    }
    $JobsDone++
    $LastWork = Get-Date
    if (-not (Stop-Ahk)) {
        Set-Content -Path (Join-Path $WarmDir 'dirty.txt') -Value 'an AutoHotkey process survived Stop-Process' -Encoding ASCII
        $StopReason = 'not clean after a run'
        break
    }
}

Log ('shutting down: ' + $StopReason)
Set-Content -Path (Join-Path $WarmDir 'stopped.txt') -Value $StopReason -Encoding ASCII
Pump ('Shutting down - ' + $StopReason)
Start-Sleep -Seconds 2
shutdown.exe /s /t 0
