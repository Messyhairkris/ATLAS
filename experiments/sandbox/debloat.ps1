# ATLAS api-harness: trims a fresh Windows Sandbox before agent code runs.
# Dot-sourced by runner.ps1; every switch comes from debloat_profile.json.
# Every action is best-effort and logged: a setting Windows refuses (e.g.
# Defender tamper protection) is reported, never fatal. ASCII only.

function Set-Reg([string]$Path, [string]$Name, $Value, $Log) {
    try {
        if (-not (Test-Path $Path)) { New-Item -Path $Path -Force | Out-Null }
        Set-ItemProperty -Path $Path -Name $Name -Value $Value -Type DWord -Force
    } catch {
        & $Log ('  reg failed ' + $Path + '\' + $Name + ': ' + $_.Exception.Message)
    }
}

function Invoke-Debloat($Settings, [string]$JobDir, [string]$GodotDir, $Log) {
    if (-not $Settings.enabled) { & $Log 'profile disabled'; return }
    $adv = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'

    if ($Settings.hide_news_feed) {
        Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Feeds' 'ShellFeedsTaskbarViewMode' 2 $Log
        Set-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Feeds' 'EnableFeeds' 0 $Log
        & $Log 'news and interests feed: off'
    }
    if ($Settings.hide_search_box) {
        Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search' 'SearchboxTaskbarMode' 0 $Log
        & $Log 'taskbar search box: hidden'
    }
    if ($Settings.hide_task_view_button) { Set-Reg $adv 'ShowTaskViewButton' 0 $Log }
    if ($Settings.hide_cortana_button) { Set-Reg $adv 'ShowCortanaButton' 0 $Log }
    if ($Settings.disable_animations) {
        Set-Reg $adv 'TaskbarAnimations' 0 $Log
        Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects' 'VisualFXSetting' 2 $Log
        try {
            Set-ItemProperty -Path 'HKCU:\Control Panel\Desktop\WindowMetrics' -Name 'MinAnimate' -Value '0' -Force
        } catch {}
        & $Log 'animations: off (best-performance visual effects)'
    }

    if ($Settings.kill_shell) {
        # Winlogon restarts a killed shell by default; turn that off first.
        Set-Reg 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' 'AutoRestartShell' 0 $Log
        Get-Process -Name explorer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        & $Log 'shell (explorer.exe): stopped - taskbar, desktop, feed and tray apps gone'
    }

    foreach ($svc in @($Settings.stop_services)) {
        $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
        if ($s -and $s.Status -eq 'Running') {
            try { Stop-Service -Name $svc -Force -NoWait -ErrorAction Stop; & $Log ('service stopped: ' + $svc) }
            catch { & $Log ('service stop refused: ' + $svc) }
        }
    }

    $killed = @()
    foreach ($name in @($Settings.kill_processes)) {
        $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
        if ($procs) {
            $procs | Stop-Process -Force -ErrorAction SilentlyContinue
            $killed += $name
        }
    }
    if ($killed.Count) { & $Log ('processes ended: ' + ($killed -join ', ')) }

    if ($Settings.defender_exclude_job) {
        try {
            Add-MpPreference -ExclusionPath @($JobDir, $GodotDir) -ErrorAction Stop
            & $Log 'defender: job + Godot folders excluded from scanning'
        } catch { & $Log ('defender exclusion refused: ' + $_.Exception.Message) }
    }
    if ($Settings.defender_realtime_off) {
        try {
            Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction Stop
            & $Log 'defender: real-time monitoring off'
        } catch { & $Log ('defender real-time off refused: ' + $_.Exception.Message) }
    }
}
