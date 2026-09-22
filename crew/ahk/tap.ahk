; tap.ahk - the test library for crew-written AutoHotkey v1 tests.
;
; Results go to the file named by the first command-line parameter, one TAP line
; per check, never to the screen. A runtime error becomes a "not ok" line instead
; of a dialog (OnError, v1.1.29+). Done() writes the plan and "# done" and exits;
; a test file that never reaches Done() is reported as broken by the runner.
;
;   #Include tap.ahk
;   #Include module.ahk
;   Is(Add(2, 3), 5, "adds")
;   Ok(IsObject(Split("a,b")), "returns an array")
;   Done()

global TapFile := A_Args[1]
global TapCount := 0
global TapFailed := 0
OnError("TapUncaught")

Ok(condition, name) {
    TapCount += 1
    if (!condition)
        TapFailed += 1
    TapWrite((condition ? "ok " : "not ok ") TapCount " - " name)
    return condition
}

Is(got, want, name) {
    same := (got == want)
    return Ok(same, same ? name : name " (got: " TapShow(got) ", want: " TapShow(want) ")")
}

Done() {
    TapWrite("1.." TapCount)
    TapWrite("# done")
    ExitApp, % TapFailed ? 1 : 0
}

TapShow(value) {
    if IsObject(value)
        return "[object]"
    return """" value """"
}

TapWrite(line) {
    FileAppend, % line "`n", %TapFile%, UTF-8
}

TapUncaught(exception) {
    message := IsObject(exception) ? exception.Message : exception
    TapWrite("not ok " (TapCount + 1) " - uncaught error: " message)
    TapFailed += 1
    TapCount += 1
    Done()
    return 1
}
