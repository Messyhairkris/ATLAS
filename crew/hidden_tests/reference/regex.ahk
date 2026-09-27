; regex.ahk - RegExMatch captures as real arrays (AutoHotkey v1.1)
; Pure functions only: text in, value out. Depends on nothing.
; Contract: crew/contracts/ahk_regex.md

MatchAll(text, needle) {
    pattern := RegexObjectNeedle(needle)
    all := []
    pos := 1
    limit := StrLen(text) + 1
    while (pos <= limit) {
        found := RegExMatch(text, pattern, m, pos)
        if (found = 0)
            break
        all.Push(RegexCapture(m))
        step := m.Len(0)
        if (step < 1)
            step := 1
        pos := found + step
    }
    return all
}

MatchFirst(text, needle) {
    pattern := RegexObjectNeedle(needle)
    found := RegExMatch(text, pattern, m, 1)
    if (found = 0)
        return ""
    return RegexCapture(m)
}

Count(text, needle) {
    pattern := RegexObjectNeedle(needle)
    n := 0
    pos := 1
    limit := StrLen(text) + 1
    while (pos <= limit) {
        found := RegExMatch(text, pattern, m, pos)
        if (found = 0)
            break
        n += 1
        step := m.Len(0)
        if (step < 1)
            step := 1
        pos := found + step
    }
    return n
}

RegexCapture(m) {
    cap := []
    cap.Push(m.Value(0))
    last := m.Count()
    i := 1
    while (i <= last) {
        cap.Push(m.Value(i))
        i += 1
    }
    return cap
}

RegexObjectNeedle(needle) {
    cut := InStr(needle, ")")
    if (cut > 1) {
        ok := 1
        i := 1
        while (i < cut) {
            ch := SubStr(needle, i, 1)
            if (!InStr("imsxADJUXPSCon", ch, 1)) {
                ok := 0
                break
            }
            i += 1
        }
        if (ok)
            return "O" . needle
    }
    return "O)" . needle
}
