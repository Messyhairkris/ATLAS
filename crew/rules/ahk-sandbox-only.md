---
name: ahk-sandbox-only
trigger: glob
description: AutoHotkey never runs on Kris's desktop - Windows Sandbox only
globs: "*.ahk, **/*.ahk"
---
Never run AutoHotkey on Kris's desktop; only in Windows Sandbox.
For a syntax check, load the script with `/iLib` (it compiles without executing).
