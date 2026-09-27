#Include tap.ahk
#Include regex.ahk

; rule 1: MatchAll shape - [1] is the whole match, groups follow
r1 := MatchAll("a1 b2", "([a-z])(\d)")
Ok(IsObject(r1), "rule 1: MatchAll returns an array object")
Is(r1.Length(), 2, "rule 1: two matches")
Is(r1[1][1], "a1", "rule 1: element 1 whole match")
Is(r1[1][2], "a", "rule 1: element 1 group 1")
Is(r1[1][3], "1", "rule 1: element 1 group 2")
Is(r1[2][1], "b2", "rule 1: element 2 whole match")
Is(r1[2][2], "b", "rule 1: element 2 group 1")
Is(r1[2][3], "2", "rule 1: element 2 group 2")

; rule 2: needle with no groups gives length-1 capture arrays
r2 := MatchAll("a1 b2", "\d")
Is(r2.Length(), 2, "rule 2: two digit matches")
Is(r2[1].Length(), 1, "rule 2: capture array holds only the whole match")
Is(r2[1][1], "1", "rule 2: first digit")
Is(r2[2][1], "2", "rule 2: second digit")

; rule 3: no match is an empty array object, not an error, not ""
r3 := MatchAll("xyz", "\d+")
Ok(IsObject(r3), "rule 3: no-match result is still an object")
Is(r3.Length(), 0, "rule 3: no matches means Length() 0")
r3b := MatchAll("", "\d+")
Ok(IsObject(r3b), "rule 3: empty text result is still an object")
Is(r3b.Length(), 0, "rule 3: empty text means Length() 0")

; rule 4: MatchFirst - capture array of the first match, or ""
f1 := MatchFirst("Price: $99.50", "\$(\d+)\.(\d+)")
Ok(IsObject(f1), "rule 4: MatchFirst returns a capture array")
Is(f1[1], "$99.50", "rule 4: whole match includes the dollar sign")
Is(f1[2], "99", "rule 4: group 1 is the dollars")
Is(f1[3], "50", "rule 4: group 2 is the cents")
Is(MatchFirst("xyz", "\d+"), "", "rule 4: no match returns empty string")
Is(MatchFirst("", "\d+"), "", "rule 4: empty text returns empty string")
f4 := MatchFirst("a1 b2", "([a-z])")
Is(f4[1], "a", "rule 4: MatchFirst returns the FIRST match only")

; rule 5: Count - integer, 0 on no match, consistent with MatchAll
Is(Count("a1 b2 c3", "\d"), 3, "rule 5: counts every match")
Is(Count("xyz", "\d"), 0, "rule 5: zero on no match")
Is(Count("", "\d+"), 0, "rule 5: empty text counts zero")
Is(Count("a1 b2", "([a-z])(\d)"), MatchAll("a1 b2", "([a-z])(\d)").Length(), "rule 5: Count equals MatchAll length")

; rule 6: unmatched optional group is "" and still occupies its slot
f6 := MatchFirst("ab", "(a)(c)?(b)")
Is(f6.Length(), 4, "rule 6: array holds whole match plus all three groups")
Is(f6[1], "ab", "rule 6: whole match")
Is(f6[2], "a", "rule 6: group 1")
Is(f6[3], "", "rule 6: unmatched optional group is empty string")
Is(f6[4], "b", "rule 6: group 3 still numbered after the empty slot")

; rule 7: non-overlapping, left to right
Is(Count("aaa", "aa"), 1, "rule 7: matches do not overlap")
Is(Count("aaaa", "aa"), 2, "rule 7: greedy left-to-right consumption")

; rule 8: zero-length matches count, scan moves one char
r8 := MatchAll("bc", "a*")
Is(r8.Length(), 3, "rule 8: empty match at 1, 2 and one past the end")
Is(r8[1][1], "", "rule 8: first empty match")
Is(r8[2][1], "", "rule 8: second empty match")
Is(r8[3][1], "", "rule 8: empty match one past the last character")
Is(Count("bc", "a*"), 3, "rule 8: Count agrees with MatchAll")
Is(Count("banana", "a*"), 7, "rule 8: empty matches between the a's")
Is(Count("", "a*"), 1, "rule 8: empty needle-pattern matches on empty text")

; rule 9: case-sensitive default, anchors behave
Is(Count("aAa", "a"), 2, "rule 9: regex is case-sensitive by default")
Is(Count("abc", "^abc$"), 1, "rule 9: anchors work")

; rule 10: caller option letters at the start stay in effect
Is(Count("aAa", "i)a"), 3, "rule 10: caller i) option is honored")
Is(Count("one`r`ntwo", "m)^(\w+)$"), 2, "rule 10: caller m) option is honored (CRLF text)")
Is(Count("one`ntwo", "m)^(\w+)$"), 0, "rule 10: m) alone does not break lines at a bare LF")

; rule 11: doubled quotes inside a needle string
f11 := MatchFirst("say ""hi"" now", """(.*?)""")
Is(f11[1], """hi""", "rule 11: whole match includes the quote marks")
Is(f11[2], "hi", "rule 11: group 1 is the text inside the quotes")

; rule 12: group numbers follow opening parens, nesting included
f12 := MatchFirst("Jason James", "((\w+) (\w+))")
Is(f12[1], "Jason James", "rule 12: whole match")
Is(f12[2], "Jason James", "rule 12: outer group is group 1")
Is(f12[3], "Jason", "rule 12: first inner group is group 2")
Is(f12[4], "James", "rule 12: second inner group is group 3")

; rule 13: pure - caller's variables are never modified
src := "a1 b2"
res := MatchAll(src, "\d")
Is(src, "a1 b2", "rule 13: caller's text variable is unchanged")
stk := "i)a"
Is(Count("aAa", stk), 3, "rule 10: caller's needle in a variable still works")
Is(stk, "i)a", "rule 13: caller's needle variable is unchanged")

Done()
