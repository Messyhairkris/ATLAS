# Contract: ahk_scan.py — what a crew AutoHotkey module may not do

One Python module, `ahk_scan.py`, the safety check in the gate that judges crew-written
**AutoHotkey v1** scripts. AutoHotkey can press keys and click in whatever window has
focus, launch programs, and delete files - on Kris's real desktop. A crew module is a
file of **pure functions**: text in, value out. This module refuses everything else,
before anything is run.

It builds on `ahk_lex.py`, already accepted. **Import it and use it** - never look
at a comment or a string's contents yourself:

```python
from ahk_lex import code_lines, unterminated
```

## Public API (all of these names must exist)

```python
BANNED = frozenset({...})     # lowercase words, see below
def banned_words(source: str) -> list: ...
def problems(source: str, allow_includes=()) -> list: ...
```

Allowed imports: `re`, plus `ahk_lex` as shown. Nothing else.

## BANNED

A `frozenset` of **lowercase** words. It must contain at least every word below,
grouped by why:

- **launching and controlling programs:** `run runwait runas process shutdown dllcall
  comobjcreate comobjget comobjactive comobject urldownloadtofile reload`
- **sending input:** `send sendinput sendraw sendevent sendplay sendmode sendlevel
  controlsend controlsendraw controlclick click mouseclick mouseclickdrag mousemove
  blockinput hotkey hotstring`
- **windows:** `winactivate winclose winkill winmove winhide winshow winminimize
  winmaximize winrestore winset postmessage sendmessage onmessage`
- **files, registry, environment:** `fileappend filedelete filemove filecopy filerecycle
  filerecycleempty fileremovedir filecreatedir filemovedir filecopydir filesetattrib
  filesettime fileread filereadline fileopen filecreateshortcut fileinstall iniwrite
  iniread inidelete regwrite regread regdelete envset envupdate clipboard clipboardall
  onclipboardchange`
- **waiting for a person, or drawing on screen:** `msgbox inputbox input tooltip traytip
  gui menu progress splashimage splashtexton soundplay soundbeep sleep settimer onexit
  exitapp pause suspend`
- **calling by a name known only at run time:** `func objbindmethod isfunc gosub goto`

## banned_words(source)

For each line from `code_lines(source)`, in order:

- a line whose code starts with `#` (after leading whitespace) is skipped - directives
  are judged whole by `problems`;
- every **word** - a letter or `_` followed by letters, digits or `_` - whose lowercase
  form is in `BANNED` is reported, **unless** the character just before it is a
  backtick (`` ` ``) or a `.` (a method on an object, like `obj.Send`, is not the
  command).

Matching is by whole word, case-insensitive: `SendInput`, `sendinput` and `SENDINPUT`
are all caught; `Sender` and `run_count` are not.

Each report is exactly: `line N: 'Word' is not allowed in a crew module`, with the word
**as written** in the source, inside single quotes.

## problems(source, allow_includes=())

Every reason to refuse the file, in this order of checks, each report beginning
`line N: `:

1. every line from `unterminated(source)`:
   `line N: a string is opened and never closed`
2. then, for each line from `code_lines(source)`:
   - **a directive** - code starting with `#`: allowed only when it is
     `#Include <name>` or `#IncludeAgain <name>` (any case) and `<name>`, trimmed, is in
     `allow_includes` (compared without case). Otherwise:
     `line N: directives such as '#Persistent' are not allowed` - the quoted word is
     the first whitespace-separated word of the stripped line. A directive line gets no
     other report.
   - **a `%` anywhere** in the code:
     `line N: '%' reaches a variable or function by a name known only at run time`
   - **`::` anywhere** in the code (a hotkey or hotstring):
     `line N: a hotkey or hotstring would run whenever a key is pressed`
   - otherwise, **a label** - a line that is only a name and a colon, like `Start:`:
     `line N: a label is not allowed; write a function`
3. then every report from `banned_words(source)`.

The result is **sorted by line number**, and reports on the same line keep the order
above (a stable sort).

| source | problems |
|---|---|
| `Add(a, b) {\n    return a + b\n}` | `[]` |
| `x := "Run it" ; Send later` | `[]` - the words are in a string and a comment |
| `MsgBox, done` | `["line 1: 'MsgBox' is not allowed in a crew module"]` |
| `^j::Send, hi` | the hotkey report, then `'Send'`, both on line 1 |
| `x := %name%` | the `%` report |
| `#Include lib.ahk` with `allow_includes=["LIB.AHK"]` | `[]` |
| `#Persistent` | `["line 1: directives such as '#Persistent' are not allowed"]` |

## Style

See `HOUSE_STYLE.md`, which is part of this contract.
