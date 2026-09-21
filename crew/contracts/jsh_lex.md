# Contract: js_lex.py - telling JavaScript code apart from its comments and strings

Part of the **JS harness**: the gates that will judge crew-written JavaScript the way
the AST scan judges Python. Every later gate asks "is this word in CODE, or inside a
comment or a string?" - `// import x from "fs"` is not an import. This module answers
that one question and nothing else. Pure text in, pure data out.

## Public API

```python
KINDS = ("code", "comment", "string", "template", "regex")

def segments(source: str) -> list[tuple[str, str]]: ...
def code_only(source: str) -> str: ...
```

Allowed imports: none are needed. You may use `re` if you want it.

## segments(source)

Walk the source left to right. At each position, while in code, the FIRST matching
rule wins:

1. `//` starts a **comment** that runs up to, but NOT including, the next `\n`
   (or to the end of the source).
2. `/*` starts a **comment** that runs through the next `*/`, inclusive. If there is
   no `*/`, it runs to the end.
3. `'` or `"` starts a **string** that runs through the next matching quote of the
   SAME kind, inclusive. A backslash skips the character after it (so `\"` does not
   end a `"` string, and `\\` is one escaped backslash). Unterminated: to the end.
4. A backtick starts a **template** that runs through the next unescaped backtick,
   inclusive, with the same backslash rule. `${...}` is NOT special: everything up to
   the closing backtick is template. Unterminated: to the end.
5. A `/` (not followed by `/` or `*`, which rules 1-2 took) starts a **regex**
   literal when BOTH hold:
   - **position**: the code before it, ignoring comments and trailing whitespace, is
     empty, OR ends with one of the characters `( , = : [ ! & | ? { } ; + - * % < > ~ ^`,
     OR ends with one of the words `return typeof instanceof in of new delete void
     throw case do else yield await` (a whole word: the character before it is not a
     letter, digit, `_` or `$`). A string, template or regex just before counts as a
     value, so `"a" / 2` is division.
   - **it closes on the same line**: scanning from the next character, a backslash
     skips the character after it; `[` opens a class and `]` closes it; an
     unescaped `/` outside a class ends the literal. Any letters directly after the
     closing `/` are flags and belong to the segment. If a newline comes before the
     closing `/`, this rule does not apply and the `/` is code.
6. Anything else is **code**, one character at a time.

Output rules:

- Consecutive code characters are merged into ONE `("code", text)` segment.
- There are never empty segments. `segments("")` is `[]`.
- **Joining the texts gives back the source exactly**:
  `"".join(t for _, t in segments(s)) == s` for every input.
- Every comment, string, template and regex is its own segment, even when adjacent.

## code_only(source)

The source with every comment replaced by ONE space, every string by `""` (two
double-quote characters), every template by two backticks and every regex by `/_/`.
Code is unchanged.

## Worked examples (the tests walk every row)

Written as Python literals.

| source | segments(source) |
|---|---|
| `"a = 1"` | `[("code", "a = 1")]` |
| `"x // hi\ny"` | `[("code", "x "), ("comment", "// hi"), ("code", "\ny")]` |
| `"a /* b */ c"` | `[("code", "a "), ("comment", "/* b */"), ("code", " c")]` |
| `"/* open"` | `[("comment", "/* open")]` |
| `"'it\\'s'"` | `[("string", "'it\\'s'")]` - the backslash-quote does not end it |
| `"\"a\" + 'b'"` | `[("string", '"a"'), ("code", " + "), ("string", "'b'")]` |
| `'"a""b"'` | `[("string", '"a"'), ("string", '"b"')]` |
| `'`x ${"y"} z`'` | `[("template", '`x ${"y"} z`')]` |
| `'"// not a comment"'` | `[("string", '"// not a comment"')]` |
| `'// "not a string"'` | `[("comment", '// "not a string"')]` |
| `"a / b"` | `[("code", "a / b")]` - division |
| `'"open'` | `[("string", '"open')]` |
| `'"a\\\\" b'` (a string ending in an escaped backslash) | `[("string", '"a\\\\"'), ("code", " b")]` |
| `'x.replace(/"/g, "&q;")'` | `[("code", "x.replace("), ("regex", '/"/g'), ("code", ", "), ("string", '"&q;"'), ("code", ")")]` |
| `"a = b / c / d"` | `[("code", "a = b / c / d")]` - division: each `/` follows a name |
| `"return /a[/]b/gi.test(s)"` | `[("code", "return "), ("regex", "/a[/]b/gi"), ("code", ".test(s)")]` |
| `"(a+b)/2"` | `[("code", "(a+b)/2")]` - after `)` it is division |
| `"f(/\//)"` | `[("code", "f("), ("regex", "/\//"), ("code", ")")]` - an escaped slash |
| `"/^x$/.test(s)"` | `[("regex", "/^x$/"), ("code", ".test(s)")]` - at the very start |
| `"const r = /ab\nc/"` | `[("code", "const r = /ab\nc/")]` - a newline first, so code |
| `'"a" / 2'` | `[("string", '"a"'), ("code", " / 2")]` - a string is a value |
| `"x = a /* c */ / b"` | `[("code", "x = a "), ("comment", "/* c */"), ("code", " / b")]` |
| `""` | `[]` |

| source | code_only(source) |
|---|---|
| `'import x from "fs" // note'` | `'import x from "" '` + `' '` = `'import x from ""  '` |
| `"f(`t`, 'u')"` | `'f(``, "")'` |
| `"a /* b */ c"` | `"a   c"` - the comment became one space between two spaces |
| `'s.split(/"/)'` | `"s.split(/_/)"` |
