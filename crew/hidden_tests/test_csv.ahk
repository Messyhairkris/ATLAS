#Include tap.ahk
#Include csv.ahk

; rule 1 - basic parse
rows := CsvParse("a,b`nc,d")
Ok(IsObject(rows), "rule 1/7: CsvParse always returns an object")
Is(rows.Length(), 2, "rule 1: two rows")
Is(rows[1].Length(), 2, "rule 1: row 1 has two fields")
Is(rows[1][1], "a", "rule 1: row 1 field 1")
Is(rows[1][2], "b", "rule 1: row 1 field 2")
Is(rows[2][1], "c", "rule 1: row 2 field 1")
Is(rows[2][2], "d", "rule 1: row 2 field 2")

; rule 2 - verbatim fields
r := CsvParse("a b, c x")
Is(r[1][1], "a b", "rule 2: spaces inside a field are kept")
Is(r[1][2], " c x", "rule 2: leading space is data, never trimmed")
Is(CsvParse("007")[1][1], "007", "rule 2: digits stay a string")

; rule 3 - quoted fields
r := CsvParse("""a,b"",c")
Is(r[1].Length(), 2, "rule 3: quoted field is one field")
Is(r[1][1], "a,b", "rule 3: delimiter inside quotes is data")
Is(r[1][2], "c", "rule 3: field after the quoted one")
r := CsvParse("""a""""b""")
Is(r[1].Length(), 1, "rule 3: doubled quote stays inside one field")
Is(r[1][1], "a""b", "rule 3: doubled encapsulator is one literal quote")
Is(CsvParse(""" a """)[1][1], " a ", "rule 3: quoted spaces kept")

; rule 4 - line breaks
r := CsvParse("a`r`nb`nc")
Is(r.Length(), 3, "rule 4: CRLF and LF both end rows")
Is(r[2][1], "b", "rule 4: row after a CRLF")
Is(r[3][1], "c", "rule 4: row after a bare LF")
r := CsvParse("""x`r`ny"",z")
Is(r.Length(), 1, "rule 4: quoted CRLF does not end the row")
Is(r[1][1], "x`r`ny", "rule 4: quoted CRLF kept exactly")
Is(r[1][2], "z", "rule 4: field after embedded CRLF")
Is(CsvParse("""x`ny""")[1][1], "x`ny", "rule 4: quoted bare LF kept as bare LF")

; rule 5 - delimiter inside quotes
r := CsvParse("""1,2""")
Is(r[1].Length(), 1, "rule 5: one quoted field holding a comma")
Is(r[1][1], "1,2", "rule 5: delimiter inside quotes is data")

; rule 6 - blank lines and trailing breaks
r := CsvParse("a,b`n")
Is(r.Length(), 1, "rule 6: trailing LF adds no row")
Is(r[1][1], "a", "rule 6: the real row survives")
r := CsvParse("a`n`n`n")
Is(r.Length(), 1, "rule 6: trailing blank lines swallowed")
r := CsvParse("a`n`nb")
Is(r.Length(), 2, "rule 6: blank middle line vanishes")
Is(r[2][1], "b", "rule 6: row after the blank line")

; rule 7 - empty text
r := CsvParse("")
Ok(IsObject(r), "rule 7: empty text still returns an object")
Is(r.Length(), 0, "rule 7: empty text is an empty array")
Is(CsvParse("`n`r`n").Length(), 0, "rule 7: only line breaks is empty too")

; rule 8 - empty fields
r := CsvParse("a,")
Is(r[1].Length(), 2, "rule 8: trailing delimiter means a trailing field")
Is(r[1][2], "", "rule 8: trailing field is empty")
r := CsvParse("a,,b")
Is(r[1].Length(), 3, "rule 8: three fields with an empty middle")
Is(r[1][2], "", "rule 8: empty middle field")
Is(r[1][3], "b", "rule 8: field after the empty one")
r := CsvParse(",")
Is(r[1].Length(), 2, "rule 8: a lone delimiter is two empty fields")
Is(r[1][1], "", "rule 8: first empty field")

; rule 9 - lenient quotes
r := CsvParse("ab""c,d")
Is(r[1][1], "ab""c", "rule 9: stray quote mid-field is literal")
Is(r[1][2], "d", "rule 9: field after the literal quote")
r := CsvParse("""ab""cd,e")
Is(r[1][1], "abcd", "rule 9: text after a closing quote is appended")

; rule 10 - unterminated quoted field
r := CsvParse("a,""b`nc")
Is(r.Length(), 1, "rule 10: unterminated quote swallows the line break")
Is(r[1].Length(), 2, "rule 10: still two fields in the row")
Is(r[1][2], "b`nc", "rule 10: rest of text is the field's data")

; rule 11 - bare CR is data
r := CsvParse("a`rb,c")
Is(r.Length(), 1, "rule 11: bare `r does not end a row")
Is(r[1][1], "a`rb", "rule 11: bare `r kept as data")

; rule 12 - custom delimiter and encapsulator
r := CsvParse("a;b;c", ";")
Is(r[1].Length(), 3, "rule 12: custom delimiter splits")
Is(r[1][2], "b", "rule 12: custom delimiter field value")
r := CsvParse("'a;b';c", ";", "'")
Is(r[1][1], "a;b", "rule 12: custom encapsulator protects the delimiter")
Is(r[1][2], "c", "rule 12: field after custom-quoted field")
Is(CsvParse("'a''b'", ";", "'")[1][1], "a'b", "rule 12: doubled custom encapsulator unescapes")
r := CsvParse("a;b,c", ";")
Is(r[1].Length(), 2, "rule 12: comma is data when the delimiter is semicolon")
Is(r[1][2], "b,c", "rule 12: comma kept inside the field")

; rule 13 - CsvEscape
Is(CsvEscape("plain"), "plain", "rule 13: no trigger, unchanged")
Is(CsvEscape("a,b"), """a,b""", "rule 13: delimiter wraps")
Is(CsvEscape("a""b"), """a""""b""", "rule 13: double the quote, then wrap")
Is(CsvEscape("a`nb"), """a`nb""", "rule 13: line break wraps")
Is(CsvEscape("x`ry"), """x`ry""", "rule 13: bare `r wraps")
Is(CsvEscape(""), "", "rule 13: empty cell stays empty")
Is(CsvEscape("a,b", ";"), "a,b", "rule 13: not the delimiter, unchanged")
Is(CsvEscape("a;b", ";"), """a;b""", "rule 13: the delimiter there wraps")
Is(CsvEscape(" a "), " a ", "rule 13: spaces never trigger wrapping")

; rule 14 - CsvRow
Is(CsvRow(["a", "b"]), "a,b", "rule 14: simple join")
Is(CsvRow(["a b", "c,d"]), "a b,""c,d""", "rule 14: only the comma field is quoted")
Is(CsvRow([]), "", "rule 14: empty field list is an empty string")
Is(CsvRow([1, 2]), "1,2", "rule 14: numbers become text")
Is(CsvRow(["a"]), "a", "rule 14: one field, no delimiter")

; rule 15 - round trips
fields := ["alpha", "be ta", "g,amma"]
line := CsvRow(fields)
Is(line, "alpha,be ta,""g,amma""", "rule 14/15: serialized line")
rt := CsvParse(line)
Is(rt.Length(), 1, "rule 15: round trip is one row")
Is(rt[1].Length(), 3, "rule 15: round trip field count")
Is(rt[1][1], "alpha", "rule 15: round trip field 1")
Is(rt[1][2], "be ta", "rule 15: round trip field with a space")
Is(rt[1][3], "g,amma", "rule 15: round trip field with a comma")

fields2 := ["a""b", "c`r`nd", "e`nf"]
rt := CsvParse(CsvRow(fields2))
Is(rt[1].Length(), 3, "rule 15: round trip count with quotes and breaks")
Is(rt[1][1], "a""b", "rule 15: quote survives the round trip")
Is(rt[1][2], "c`r`nd", "rule 15: CRLF survives the round trip")
Is(rt[1][3], "e`nf", "rule 15: bare LF survives the round trip")

Is(CsvRow(["", "x"]), ",x", "rule 15: empty first field serializes bare")
rt := CsvParse(",x")
Is(rt[1][1], "", "rule 15: empty first field round trips")
Is(rt[1][2], "x", "rule 15: field after the empty one round trips")
Is(CsvRow([""]), "", "rule 15: lone empty field serializes to empty (exception)")

; rule 16 - purity and fresh arrays
a1 := CsvParse("a,b")
a1[1][1] := "Z"
a2 := CsvParse("a,b")
Is(a2[1][1], "a", "rule 16: each parse returns fresh arrays")

Done()
