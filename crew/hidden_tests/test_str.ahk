; test_str.ahk - hidden tests for str.ahk. Rule numbers name rules in ahk_str.md.
; Save as UTF-8 with BOM: rules 1, 2 and 8 use non-ASCII letters.
#Include tap.ahk
#Include str.ahk

; rule 1: Lower
Is(Lower("AbC"), "abc", "rule 1: Lower lowercases mixed case")
Is(Lower("HELLO"), "hello", "rule 1: Lower on all caps")
Is(Lower("N/M 3"), "n/m 3", "rule 1: Lower keeps digits and punctuation")
Is(Lower("already"), "already", "rule 1: Lower leaves lowercase alone")

; rule 2: Upper
Is(Upper("AbC"), "ABC", "rule 2: Upper uppercases mixed case")
Is(Upper("hello"), "HELLO", "rule 2: Upper on all lowercase")
Is(Upper("42nd"), "42ND", "rule 2: Upper keeps digits")

; rule 7: empty input
Is(Lower(""), "", "rule 7: Lower of empty is empty")
Is(Upper(""), "", "rule 7: Upper of empty is empty")
Is(Title(""), "", "rule 7: Title of empty is empty")

; rule 3: Title
Is(Title("hello world"), "Hello World", "rule 3: Title capitalizes each word")
Is(Title("hELLO wORLD"), "Hello World", "rule 3: Title on already-mixed case resets it")
Is(Title("the-end"), "The-end", "rule 3: a hyphen does not start a new word")
Is(Title("don't stop"), "Don't Stop", "rule 3: an apostrophe does not start a new word")
Is(Title("john's hat"), "John's Hat", "rule 3: Title on a possessive")

; rule 4: Default, empty string is the ONLY empty value
Is(Default("", "fb"), "fb", "rule 4: Default replaces the empty string")
Is(Default("x", "fb"), "x", "rule 4: Default keeps a non-empty value")
Is(Default("0", "fb"), "0", "rule 4: Default keeps ""0""")
Is(Default(0, "fb"), 0, "rule 4: Default keeps numeric 0")
Is(Default(" ", "fb"), " ", "rule 4: Default keeps a space; a space is a value")
Is(Default("FB", "fb"), "FB", "rule 4: Default never edits the value it keeps")

; rule 5: Default with no fallback
Is(Default(""), "", "rule 5: Default without fallback returns empty for empty")
Is(Default("y"), "y", "rule 5: Default without fallback keeps a value")
Is(Default(0), 0, "rule 5: Default without fallback keeps zero")

; rule 6: Coalesce
Is(Coalesce(), "", "rule 6: Coalesce with zero arguments is empty")
Is(Coalesce(""), "", "rule 6: Coalesce of one empty string is empty")
Is(Coalesce("", "", ""), "", "rule 6: Coalesce of only empty strings is empty")
Is(Coalesce("", "", "x"), "x", "rule 6: Coalesce returns the first non-empty")
Is(Coalesce("a", "b"), "a", "rule 6: Coalesce returns the first value")
Is(Coalesce("", 0, "x"), 0, "rule 6: zero is a value, never skipped")
Is(Coalesce("", "0", "x"), "0", "rule 6: ""0"" is a value, never skipped")

; rule 8: non-ASCII letters follow the commands
Is(Lower("ÀÉÎ"), "àéî", "rule 8: Lower maps non-ASCII letters like StringLower")
Is(Upper("àéî"), "ÀÉÎ", "rule 8: Upper maps non-ASCII letters like StringUpper")

; rule 9: numbers where text is expected
Is(Lower(42), "42", "rule 9: a number becomes its text form in Lower")
Is(Title(100), "100", "rule 9: Title of a number is that number's text")
Is(Default("", 7), 7, "rule 9: a fallback may be a number")

; rule 10: caller's variables left unchanged
s := "AbC"
Lower(s)
Is(s, "AbC", "rule 10: Lower leaves the caller's variable unchanged")
t := "don't stop"
Title(t)
Is(t, "don't stop", "rule 10: Title leaves the caller's variable unchanged")
u := ""
Default(u, "z")
Is(u, "", "rule 10: Default leaves the caller's variable unchanged")

; rule 11: pure and composable
Is(Upper(Lower("AbC")), "ABC", "rule 11: calls compose inside one expression")
Is(Default(Title(""), "empty"), "empty", "rule 11: Title and Default compose")

Done()
