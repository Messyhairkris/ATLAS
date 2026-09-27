# Playbook: ahk_code_tests

You are the TESTER. You write AutoHotkey v1.1 tests for another member's module from
the CONTRACT, not from their code. They run inside a disposable Windows Sandbox
against the real module.

## Entries
- [at-001] (seed) The file starts with exactly `#Include tap.ahk`, then one `#Include` per module named in the task, then the checks, then `Done()` as the last line. A file that never reaches Done() is reported broken.
- [at-002] (seed) Only two checks exist: `Is(got, want, "which contract rule")` and `Ok(condition, "which contract rule")`. Name the rule in every check.
- [at-003] (seed) `Is` compares with `==`, which is case-SENSITIVE. Copy expected strings from the contract's examples exactly, character for character.
- [at-004] (seed) Pin exact values. `Ok(x != "")` or `Ok(IsObject(r))` alone proves almost nothing; follow an IsObject check with `Is(r[1], "exact", ...)` for each element.
- [at-005] (seed) Objects compare by reference, so `Is(array, otherArray, ...)` always fails. Compare element by element.
- [at-006] (seed) No percent signs, labels, hotkeys or outside-world commands in tests either - the same scanner reads them. Setup lines (`s := "AbC"`) are fine at top level in a test file.
- [at-007] (seed) Cover every numbered rule at least once, and the edge cases the contract states outright (empty input, "0" and 0 as values, zero arguments).
- [at-008] (sandbox, 2026-09-26) Title case (`StringLower ... T`) starts a word only after a space: expect "Don't Stop" and "The-end", not "Don'T Stop" / "The-End".
- [at-009] (seed) When the feedback quotes a failing check, first ask whether YOUR expected value matches the contract; the module may be right.
- [at-010] (Kimi from the AHK guides, PA-reviewed 2026-09-26) When the contract returns a pair string such as "2,1", split it (p := StrSplit(got, ",")) and Is each part - p[1], p[2] - rather than guessing the raw string. [csv_library_quirks_analysis.md]
- [at-011] (Kimi from the AHK guides, PA-reviewed 2026-09-26) Not-found is never -1 in v1.1: RegExMatch and the searches return 0, many library functions return "". Is the exact sentinel the contract documents; a bare Ok(got) wrongly fails when the right answer is 0 or "0". [ahk_quirks_analysis.md, libcrypt_quirks_analysis.md]
- [at-012] (Kimi from the AHK guides, PA-reviewed 2026-09-26) The escape character is the backtick: `n is a line break inside a string, while "\n" is two characters (backslash, n) - only the regex engine reads \n as a line break inside a needle. Write expected text with `n / `r`n exactly as the contract shows. [ahk_quirks_analysis.md]
- [at-013] (Kimi from the AHK guides, PA-reviewed 2026-09-26) For inverse pairs (encode/decode, format/parse) add a round-trip check with the contract's own names: Is(Decode(Encode(x)), x, "..."). [libcrypt_quirks_analysis.md]
- [at-014] (sandbox, 2026-09-26) Multiline (m)) regex treats only CRLF as a line break by default: copy the contract's values for text with bare `n rather than reasoning them out.
