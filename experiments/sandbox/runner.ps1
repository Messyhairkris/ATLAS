# ATLAS api-harness: in-sandbox job runner + status window.
#
# Launched by the .wsb LogonCommand. Shows a small always-on-top window so a
# human watching the sandbox sees what stage the run is in, trims Windows per
# debloat_profile.json, runs Godot, and writes the host protocol files:
#   <JobDir>\godot.log        Godot stdout+stderr, then EXIT_CODE=<n>
#   <JobDir>\runner_done.txt  PASS|FAIL + one-line reason (host waits on it)
#   <JobDir>\runner.log       ONLY on failure. On success the runner log lives
#                             in the sandbox's own TEMP and is destroyed with
#                             the sandbox, so passing runs leave nothing behind.
# The host still makes the final verdict; this window's verdict is a preview.
# Keep this file ASCII: Windows PowerShell 5.1 misreads BOM-less UTF-8.

param(
    [Parameter(Mandatory = $true)][string]$JobDir,
    [Parameter(Mandatory = $true)][string]$ToolsDir
)

$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$job = Get-Content -Raw -Path (Join-Path $JobDir 'job.json') | ConvertFrom-Json
$LocalLog = Join-Path $env:TEMP ("atlas-runner-" + $job.run_id + ".log")
$Started = Get-Date
$Stages = @('Sandbox booted', 'Trimming Windows', 'Running Godot',
            'Checking results', 'Done')
if ($job.stages) { $Stages = @($job.stages) }
$Verdict = 'FAIL'
$Reason = 'runner did not finish'

# ---- window ------------------------------------------------------------------
$bg = [System.Drawing.Color]::FromArgb(24, 26, 31)
$fg = [System.Drawing.Color]::Gainsboro
$form = New-Object System.Windows.Forms.Form
$form.Text = 'ATLAS sandbox run - ' + $job.run_id
$form.Size = New-Object System.Drawing.Size(700, 520)
$form.StartPosition = 'Manual'
$form.Location = New-Object System.Drawing.Point(24, 24)
$form.TopMost = $true
$form.BackColor = $bg
$form.ForeColor = $fg
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)

$title = New-Object System.Windows.Forms.Label
$title.Text = [string]$job.title
$title.Location = New-Object System.Drawing.Point(16, 10)
$title.Size = New-Object System.Drawing.Size(660, 22)
$title.ForeColor = [System.Drawing.Color]::DarkGray

$stageLabel = New-Object System.Windows.Forms.Label
$stageLabel.Font = New-Object System.Drawing.Font('Segoe UI', 18, [System.Drawing.FontStyle]::Bold)
$stageLabel.Location = New-Object System.Drawing.Point(14, 34)
$stageLabel.Size = New-Object System.Drawing.Size(660, 40)

$clock = New-Object System.Windows.Forms.Label
$clock.Location = New-Object System.Drawing.Point(16, 76)
$clock.Size = New-Object System.Drawing.Size(660, 22)
$clock.ForeColor = [System.Drawing.Color]::DarkGray

$checklist = New-Object System.Windows.Forms.Label
$checklist.Font = New-Object System.Drawing.Font('Consolas', 10)
$checklist.Location = New-Object System.Drawing.Point(16, 102)
$checklist.Size = New-Object System.Drawing.Size(660, 96)

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = 'Vertical'
$logBox.Font = New-Object System.Drawing.Font('Consolas', 9)
$logBox.BackColor = [System.Drawing.Color]::FromArgb(13, 17, 23)
$logBox.ForeColor = $fg
$logBox.Location = New-Object System.Drawing.Point(16, 202)
$logBox.Size = New-Object System.Drawing.Size(652, 264)

$form.Controls.AddRange(@($title, $stageLabel, $clock, $checklist, $logBox))
$form.Show()
[System.Windows.Forms.Application]::DoEvents()

function Pump {
    $clock.Text = ('elapsed {0:mm\:ss}   job {1}' -f ((Get-Date) - $Started), $job.run_id)
    [System.Windows.Forms.Application]::DoEvents()
}

function Log([string]$msg) {
    $line = ('{0:HH:mm:ss} {1}' -f (Get-Date), $msg)
    Add-Content -Path $LocalLog -Value $line -Encoding UTF8
    $logBox.AppendText($line + "`r`n")
    Pump
}

function Set-Stage([int]$i) {
    $stageLabel.Text = $Stages[$i]
    $rows = for ($k = 0; $k -lt $Stages.Count; $k++) {
        if ($k -lt $i) { '[x] ' + $Stages[$k] }
        elseif ($k -eq $i) { '[>] ' + $Stages[$k] }
        else { '[ ] ' + $Stages[$k] }
    }
    $checklist.Text = ($rows -join "`r`n")
    Log ('--- stage: ' + $Stages[$i])
    # The host watches this file: a runner that is still moving is never killed
    # as "never started" (Kris's box needs more than 4 minutes to boot one).
    Set-Content -Path (Join-Path $JobDir 'stage.txt') -Value ([string]$i + ' ' + $Stages[$i]) -Encoding ASCII
}

function Snapshot {
    $os = Get-CimInstance Win32_OperatingSystem
    [pscustomobject]@{
        Procs  = (Get-Process).Count
        FreeMB = [math]::Round($os.FreePhysicalMemory / 1024)
    }
}

function Finish([string]$verdict, [string]$reason) {
    $script:Verdict = $verdict
    $script:Reason = $reason
}

try {
    # ---- 1. boot -------------------------------------------------------------
    Set-Stage 0
    $os = Get-CimInstance Win32_OperatingSystem
    $boot = (Get-Date) - $os.LastBootUpTime
    Log ('sandbox up for {0:N0}s before the runner started' -f $boot.TotalSeconds)

    # ---- 2. debloat ----------------------------------------------------------
    Set-Stage 1
    $profilePath = Join-Path $ToolsDir 'debloat_profile.json'
    if ($job.debloat -and (Test-Path $profilePath)) {
        $before = Snapshot
        . (Join-Path $ToolsDir 'debloat.ps1')
        $prof = Get-Content -Raw -Path $profilePath | ConvertFrom-Json
        Invoke-Debloat -Settings $prof -JobDir $JobDir -GodotDir $job.godot_dir -Log ${function:Log}
        Start-Sleep -Milliseconds 800
        $after = Snapshot
        Log ('trim result: processes {0} -> {1}, free memory {2} MB -> {3} MB' -f `
             $before.Procs, $after.Procs, $before.FreeMB, $after.FreeMB)
    } else {
        Log 'debloat skipped (disabled in job or profile missing)'
    }

    if ($job.kind -eq 'ahk') {
        # ---- 3. run each AutoHotkey test file, one process each ------------------
        Set-Stage 2
        $exe = Join-Path $job.exe_dir $job.exe
        $report = ''
        $okCount = 0; $badCount = 0; $broken = @()
        foreach ($t in $job.tests) {
            $tap = Join-Path $JobDir ($t + '.tap')
            $err = Join-Path $JobDir ($t + '.stderr')
            $stageLabel.Text = 'Running ' + $t
            Set-Content -Path (Join-Path $JobDir 'stage.txt') -Value ('2 running ' + $t) -Encoding ASCII
            Pump
            Log ('run: ' + $t)
            $proc = Start-Process -FilePath $exe `
                -ArgumentList @('/ErrorStdOut', ('"' + (Join-Path $JobDir $t) + '"'), ('"' + $tap + '"')) `
                -WorkingDirectory $JobDir -RedirectStandardError $err -NoNewWindow -PassThru
            if (-not $proc.WaitForExit([int]$job.per_test_timeout_s * 1000)) {
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
        # ---- 4. check --------------------------------------------------------------
        Set-Stage 3
        $summary = '{0} failed, {1} passed' -f $badCount, $okCount
        Set-Content -Path (Join-Path $JobDir 'run.log') -Value ($report + "`r`n" + $summary + "`r`n" + ($broken -join "`r`n")) -Encoding UTF8
        if ($broken.Count) { Finish 'FAIL' ($broken[0]) }
        elseif ($badCount) { Finish 'FAIL' $summary }
        elseif ($okCount -eq 0) { Finish 'FAIL' 'no test reported a result' }
        else { Finish 'PASS' $summary }
    } else {
        # ---- 3. run Godot ----------------------------------------------------------
        Set-Stage 2
        $out = Join-Path $JobDir 'stdout.txt'
        $err = Join-Path $JobDir 'stderr.txt'
        $exe = Join-Path $job.godot_dir $job.godot_exe
        Log ('launch: ' + $job.godot_exe + ' ' + ($job.args -join ' '))
        $proc = Start-Process -FilePath $exe -ArgumentList $job.args `
            -WorkingDirectory $JobDir -RedirectStandardOutput $out `
            -RedirectStandardError $err -NoNewWindow -PassThru
        $deadline = (Get-Date).AddSeconds([int]$job.timeout_s)
        $pos = 0L
        $lines = 0
        $watch = @($job.markers) + @('HARNESS_PROBE', 'SCRIPT ERROR', 'Parse Error', 'ERROR')
        $timedOut = $false
        while (-not $proc.HasExited) {
            if ((Get-Date) -gt $deadline) {
                $timedOut = $true
                Log ('hard timeout {0}s: killing Godot' -f $job.timeout_s)
                try { Stop-Process -Id $proc.Id -Force } catch {}
                break
            }
            if (Test-Path $out) {
                try {
                    $fs = [System.IO.File]::Open($out, 'Open', 'Read', 'ReadWrite')
                    $null = $fs.Seek($pos, 'Begin')
                    $sr = New-Object System.IO.StreamReader($fs)
                    $chunk = $sr.ReadToEnd()
                    $pos = $fs.Position
                    $sr.Close()
                    foreach ($l in ($chunk -split "`r?`n")) {
                        if (-not $l) { continue }
                        $lines++
                        foreach ($w in $watch) {
                            if ($l.Contains($w)) { Log ('godot: ' + $l); break }
                        }
                    }
                } catch {}
            }
            $stageLabel.Text = ('Running Godot ({0} log lines)' -f $lines)
            Pump
            Start-Sleep -Milliseconds 300
        }
        $proc.WaitForExit(5000) | Out-Null
        $code = if ($timedOut) { 'TIMEOUT' } else { $proc.ExitCode }
        Log ('godot finished: exit ' + $code)

        # ---- 4. check --------------------------------------------------------------
        Set-Stage 3
        $text = ''
        if (Test-Path $out) { $text += (Get-Content -Raw -Path $out) }
        if (Test-Path $err) { $text += (Get-Content -Raw -Path $err) }
        Set-Content -Path (Join-Path $JobDir 'godot.log') -Value ($text + "`r`nEXIT_CODE=$code`r`n") -Encoding UTF8
        $found = @($job.markers | Where-Object { $text.Contains($_) })
        $probeOk = (-not $job.probe_nonce) -or $text.Contains('HARNESS_PROBE ' + $job.probe_nonce + ' SCENE_LOADED')
        $errors = $text.Contains('SCRIPT ERROR') -or $text.Contains('Parse Error')
        Log ('markers seen: ' + ($(if ($found.Count) { $found -join ', ' } else { 'none' })))
        Log ('probe scene-loaded: ' + $probeOk + '   script errors: ' + $errors)
        if ($timedOut) { Finish 'FAIL' 'Godot hit the hard timeout' }
        elseif ($errors) { Finish 'FAIL' 'script/parse errors in the Godot log' }
        elseif (-not $probeOk) { Finish 'FAIL' 'harness probe never saw the main scene load' }
        elseif ($found.Count -eq 0) { Finish 'FAIL' 'no success marker in the Godot log' }
        else { Finish 'PASS' ('markers: ' + ($found -join ', ')) }
    }
}
catch {
    Log ('RUNNER ERROR: ' + $_.Exception.Message)
    Finish 'FAIL' ('runner error: ' + $_.Exception.Message)
}

# ---- 5. done -------------------------------------------------------------------
Set-Stage 4
Log ('verdict (preview; host decides): ' + $Verdict + ' - ' + $Reason)
if ($Verdict -ne 'PASS') {
    Copy-Item -Path $LocalLog -Destination (Join-Path $JobDir 'runner.log') -Force
}
$stageLabel.Text = $Verdict + ': ' + $Reason
$stageLabel.ForeColor = $(if ($Verdict -eq 'PASS') { [System.Drawing.Color]::LightGreen } else { [System.Drawing.Color]::Salmon })
Pump
Set-Content -Path (Join-Path $JobDir 'runner_done.txt') -Value ($Verdict + ' ' + $Reason) -Encoding ASCII
$lingerUntil = (Get-Date).AddSeconds([int]$job.linger_s)
while ((Get-Date) -lt $lingerUntil -and $form.Visible) { Pump; Start-Sleep -Milliseconds 200 }
$form.Close()
