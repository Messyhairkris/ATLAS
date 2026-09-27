; csv.ahk - parse and serialize CSV/DSV strings (AutoHotkey v1.1)
; Contract: crew/contracts/ahk_csv.md
; Self-contained: a plain character loop, no includes, no regex module needed.

CsvParse(text, delim := ",", encap := """") {
    local rows := []
    local row := []
    local field := ""
    local inQuotes := false
    local afterQuote := false
    local rowStarted := false
    local len := StrLen(text)
    local i := 1
    local ch := ""
    local nx := ""
    local br := 0
    while (i <= len) {
        ch := SubStr(text, i, 1)
        nx := SubStr(text, i + 1, 1)
        if (inQuotes) {
            if (ch == encap) {
                if (nx == encap) {
                    field .= encap
                    rowStarted := true
                    i += 2
                    continue
                }
                inQuotes := false
                afterQuote := true
                i += 1
                continue
            }
            field .= ch
            rowStarted := true
            i += 1
            continue
        }
        br := 0
        if (ch == "`n")
            br := 1
        else if (ch == "`r" && nx == "`n")
            br := 2
        if (afterQuote) {
            if (ch == delim) {
                row.Push(field)
                field := ""
                afterQuote := false
                i += 1
                continue
            }
            if (br) {
                row.Push(field)
                rows.Push(row)
                row := []
                field := ""
                afterQuote := false
                rowStarted := false
                i += br
                continue
            }
            field .= ch
            i += 1
            continue
        }
        if (ch == delim) {
            row.Push(field)
            field := ""
            rowStarted := true
            i += 1
            continue
        }
        if (br) {
            if (rowStarted) {
                row.Push(field)
                rows.Push(row)
                row := []
                field := ""
                rowStarted := false
            }
            i += br
            continue
        }
        if (ch == encap && field == "") {
            inQuotes := true
            rowStarted := true
            i += 1
            continue
        }
        field .= ch
        rowStarted := true
        i += 1
    }
    if (rowStarted) {
        row.Push(field)
        rows.Push(row)
    }
    return rows
}

CsvEscape(cell, delim := ",", encap := """") {
    local out := cell
    local need := false
    if (InStr(cell, encap)) {
        out := StrReplace(cell, encap, encap . encap)
        need := true
    }
    if (InStr(cell, delim) || InStr(cell, "`n") || InStr(cell, "`r"))
        need := true
    if (need)
        out := encap . out . encap
    return out
}

CsvRow(fields, delim := ",", encap := """") {
    local out := ""
    local i := 1
    local n := fields.Length()
    while (i <= n) {
        if (i > 1)
            out .= delim
        out .= CsvEscape(fields[i], delim, encap)
        i += 1
    }
    return out
}
