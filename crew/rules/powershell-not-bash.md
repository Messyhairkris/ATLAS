---
name: powershell-not-bash
trigger: always_on
description: Windows 10 - PowerShell is the shell; Unix habits break commands
globs: "*.ps1, crew/**/*.py"
---
This machine is Windows 10 and PowerShell is the default shell: no Unix commands
(ls -la, rm -rf, head, grep, which, touch) - use the PowerShell equivalents.
Full Windows paths in everything you write for the PM.
