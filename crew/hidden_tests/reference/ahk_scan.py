"""Reference implementation of contracts/ahk_scan.md (never given to the crew)."""

import re

from ahk_lex import code_lines, unterminated

BANNED = frozenset({
    # launching and controlling other programs
    "run", "runwait", "runas", "process", "shutdown", "dllcall", "comobjcreate",
    "comobjget", "comobjactive", "comobject", "urldownloadtofile", "reload",
    # sending input to whatever window has focus
    "send", "sendinput", "sendraw", "sendevent", "sendplay", "sendmode", "sendlevel",
    "controlsend", "controlsendraw", "controlclick", "click", "mouseclick",
    "mouseclickdrag", "mousemove", "blockinput", "hotkey", "hotstring",
    # windows
    "winactivate", "winclose", "winkill", "winmove", "winhide", "winshow",
    "winminimize", "winmaximize", "winrestore", "winset", "postmessage",
    "sendmessage", "onmessage",
    # files, the registry and the environment
    "fileappend", "filedelete", "filemove", "filecopy", "filerecycle",
    "filerecycleempty", "fileremovedir", "filecreatedir", "filemovedir",
    "filecopydir", "filesetattrib", "filesettime", "fileread", "filereadline",
    "fileopen", "filecreateshortcut", "fileinstall", "iniwrite", "iniread",
    "inidelete", "regwrite", "regread", "regdelete", "envset", "envupdate",
    "clipboard", "clipboardall", "onclipboardchange",
    # anything that waits for a person or puts something on screen
    "msgbox", "inputbox", "input", "tooltip", "traytip", "gui", "menu",
    "progress", "splashimage", "splashtexton", "soundplay", "soundbeep",
    "sleep", "settimer", "onexit", "exitapp", "pause", "suspend",
    # calling something by a name that is only known at run time
    "func", "objbindmethod", "isfunc", "gosub", "goto",
})

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LABEL = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*:\s*$")
_INCLUDE = re.compile(r"^\s*#include(?:again)?\s+(.+?)\s*$", re.IGNORECASE)


def banned_words(source: str) -> list:
    """Every banned word used as code, one sentence each, in line order."""
    found = []
    for number, text in code_lines(source):
        if text.strip().startswith("#"):
            continue                # a directive is judged whole, in problems()
        for match in _WORD.finditer(text):
            start = match.start()
            if start > 0 and text[start - 1] == "`":
                continue
            if start > 0 and text[start - 1] == ".":
                continue            # a method or property on an object, obj.Send
            if match.group(0).lower() in BANNED:
                found.append(f"line {number}: {match.group(0)!r} is not allowed "
                             f"in a crew module")
    return found


def problems(source: str, allow_includes=()) -> list:
    """Everything that keeps this file out of the test runner, in line order."""
    allowed = {name.lower() for name in allow_includes}
    out = []
    for number in unterminated(source):
        out.append(f"line {number}: a string is opened and never closed")
    for number, text in code_lines(source):
        stripped = text.strip()
        if stripped.startswith("#"):
            include = _INCLUDE.match(text)
            if include and include.group(1).strip().lower() in allowed:
                continue
            out.append(f"line {number}: directives such as {stripped.split()[0]!r} "
                       f"are not allowed")
            continue
        if "%" in text:
            out.append(f"line {number}: '%' reaches a variable or function by a "
                       f"name known only at run time")
        if "::" in text:
            out.append(f"line {number}: a hotkey or hotstring would run whenever a "
                       f"key is pressed")
        elif _LABEL.match(text):
            out.append(f"line {number}: a label is not allowed; write a function")
    out.extend(banned_words(source))
    return sorted(out, key=lambda p: int(p.split(":")[0].split()[1]))
