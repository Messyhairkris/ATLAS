; str.ahk - composable, pure string helpers. Contract: ahk_str.md.
; Every function returns a NEW value; nothing is modified in place, nothing here
; touches windows, keys, clipboard, files, registry or time.
; Save as UTF-8 with BOM so non-ASCII letters (rule 8 of the contract) behave.

Lower(text) {
    local out := ""
    StringLower, out, text
    return out
}

Upper(text) {
    local out := ""
    StringUpper, out, text
    return out
}

Title(text) {
    local out := ""
    StringLower, out, text, T
    return out
}

Default(value, fallback := "") {
    if (value == "")
        return fallback
    return value
}

Coalesce(values*) {
    local index := 0
    for index, one in values {
        if !(one == "")
            return one
    }
    return ""
}
