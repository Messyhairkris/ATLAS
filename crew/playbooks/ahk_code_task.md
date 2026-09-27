# Playbook: ahk_code_task

You are writing one complete AutoHotkey v1.1 file of PURE functions against a
contract. A static scanner reads it first; then hidden tests you never see run it
inside a disposable Windows Sandbox. You cannot argue with them; you can only
satisfy the contract.

## Entries
- [ah-001] (seed) Write the WHOLE file every time, from the first line to the last. Not a diff, not a fragment. A partial file is a failed task.
- [ah-002] (seed) Every line of code lives inside a function. Code outside a function runs the moment the file is included and is refused ("no loose code"); only comments and blank lines may sit outside.
- [ah-003] (seed) No percent signs anywhere - not `%var%`, not `% expr`. Use expression syntax: `x := a . b`, `return out`. The scanner refuses every '%'.
- [ah-004] (seed) Nothing that touches the outside world: no Send, Click, Run, WinActivate, Clipboard, FileRead/FileAppend, RegRead, DllCall, Sleep, SetTimer, Gui, MsgBox, hotkeys (::) or labels. Text and numbers in, a value out.
- [ah-005] (seed) Legacy COMMANDS return nothing. `StringLower, out, text` writes into `out`; `return StringLower(text)` silently returns "". Run the command into a local, then return the local.
- [ah-006] (seed) In AutoHotkey v1.1 the string "0" is FALSE. To test for "empty", compare `value == ""` explicitly; `if (value)` wrongly treats "0" and 0 as empty.
- [ah-007] (seed) `=` compares case-INsensitively, `==` case-sensitively. The hidden tests use `==`, so return exactly the case the contract shows.
- [ah-008] (seed) Arrays are 1-based. RegExMatch returns 0 (not -1) when nothing matches. Objects are passed by reference - build a new array to return, never edit the caller's.
- [ah-009] (sandbox, 2026-09-26) `StringLower, out, text, T` (title case) starts a new word only after a SPACE: "don't stop" -> "Don't Stop", "the-end" -> "The-end". Hyphens and apostrophes do not start words.
- [ah-010] (seed) The contract's API block is exact: every function it names exists with that spelling and those parameters. No stubs - an empty body or a lone `return` is a failure.
- [ah-011] (seed) Read the worked examples as tests; walk your code through every row before you submit.
- [ah-012] (seed) If the contract is wrong or contradicts itself, write a NOTE comment at the end AND implement it as written.
- [ah-013] (Kimi from the AHK guides, PA-reviewed 2026-09-26) To walk lines or fields, `Loop, Parse, text, `n, `r` splits on `n and strips `r (so CRLF and LF both work); the field is A_LoopField and the 1-based counter A_Index. Write the arguments bare - never %text%. [csv_library_quirks_analysis.md]
- [ah-014] (Kimi from the AHK guides, PA-reviewed 2026-09-26) Read regex captures from an O) match object: RegExMatch(text, "O)" . needle, m, pos), then m.Value(0) is the whole match, m.Value(n) group n, m.Count() the number of groups, m.Pos(n)/m.Len(n) where it is. Do not collect the m1, m2 pseudo-variables - reading them generically needs the refused '%'. [ahk_quirks_analysis.md]
- [ah-015] (Kimi from the AHK guides, PA-reviewed 2026-09-26) CSV-style output: double every quote first (" becomes ""), THEN wrap the cell in quotes if it contains the delimiter, a quote or a line break. Wrapping first quotes it twice. [csv_library_quirks_analysis.md]
- [ah-016] (PA, from tap.ahk) Never name a variable TapFile, TapCount or TapFailed: tap.ahk declares them super-global, so a module that uses those names reads and changes the test harness itself. Declare scratch variables with `local` at the top of the function. [crew/ahk/tap.ahk]
- [ah-017] (Kimi from the AHK guides, PA-reviewed 2026-09-26) A long string or needle can continue on the next line when that line starts with `.` (concatenation); it needs no '%' and no continuation section. [ahk_v1_comprehensive_prompt.md]
- [ah-018] (Kimi from the AHK guides, PA-reviewed 2026-09-26) Numbers with more digits than a 64-bit integer holds are silently trimmed as bare literals; keep them as quoted strings and work digit by digit. [Maths_Quirks.md]
- [ah-019] (Kimi from the AHK guides, PA-reviewed 2026-09-26) There is no switch/case in v1.1: write if / else if chains or a ternary (x := a ? b : c), and return early instead of nesting. [ahk_quirks_analysis.md]
- [ah-020] (sandbox, 2026-09-26) In multiline mode (m)) AutoHotkey's default line break is CRLF (`r`n): on text with bare `n, ^ and $ do NOT match at each line unless the `n option is added too ("m`n)").
