"""Hidden tests for ahk_scan.py - the author never sees these.

This module is what stands between a crew script and Kris's real keyboard, so the
tests care most about what gets through: a banned word must never be missed
because it sat next to a comment or a string.
"""

import ahk_scan as S

REQUIRED = """run runwait runas process shutdown dllcall comobjcreate comobjget
comobjactive comobject urldownloadtofile reload send sendinput sendraw sendevent
sendplay sendmode sendlevel controlsend controlsendraw controlclick click mouseclick
mouseclickdrag mousemove blockinput hotkey hotstring winactivate winclose winkill
winmove winhide winshow winminimize winmaximize winrestore winset postmessage
sendmessage onmessage fileappend filedelete filemove filecopy filerecycle
filerecycleempty fileremovedir filecreatedir filemovedir filecopydir filesetattrib
filesettime fileread filereadline fileopen filecreateshortcut fileinstall iniwrite
iniread inidelete regwrite regread regdelete envset envupdate clipboard clipboardall
onclipboardchange msgbox inputbox input tooltip traytip gui menu progress splashimage
splashtexton soundplay soundbeep sleep settimer onexit exitapp pause suspend func
objbindmethod isfunc gosub goto""".split()


def test_every_required_word_is_banned_and_lowercase():
    assert isinstance(S.BANNED, frozenset)
    assert set(REQUIRED) <= S.BANNED
    assert all(w == w.lower() for w in S.BANNED)


def test_a_clean_module_has_no_problems():
    src = "Add(a, b) {\n    return a + b\n}\n"
    assert S.problems(src) == []
    assert S.banned_words(src) == []


def test_words_in_strings_and_comments_are_not_code():
    assert S.problems('x := "Run it" ; Send later') == []
    assert S.problems("/*\nRun, notepad.exe\n*/\ny := 1") == []


def test_a_banned_word_after_a_string_is_still_caught():
    assert S.banned_words('x := "safe" Run("calc")') == [
        "line 1: 'Run' is not allowed in a crew module"]


def test_the_word_is_reported_as_written():
    assert S.banned_words("MsgBox, done") == [
        "line 1: 'MsgBox' is not allowed in a crew module"]
    assert S.banned_words("SENDINPUT {Enter}") == [
        "line 1: 'SENDINPUT' is not allowed in a crew module"]


def test_whole_words_only():
    assert S.banned_words("Sender := 1\nrun_count := 2\nrerun := 3") == []


def test_methods_and_escapes_are_not_commands():
    assert S.banned_words("obj.Send(x)") == []
    assert S.banned_words("x := a`Run") == []


def test_every_occurrence_is_reported_in_order():
    src = "Run(a)\nb := 1\nSleep 10\nClick"
    assert S.banned_words(src) == [
        "line 1: 'Run' is not allowed in a crew module",
        "line 3: 'Sleep' is not allowed in a crew module",
        "line 4: 'Click' is not allowed in a crew module"]


def test_two_on_one_line():
    assert S.banned_words("WinActivate, x ; then\nSend, a Sleep 5") == [
        "line 1: 'WinActivate' is not allowed in a crew module",
        "line 2: 'Send' is not allowed in a crew module",
        "line 2: 'Sleep' is not allowed in a crew module"]


def test_directives():
    assert S.problems("#Persistent") == [
        "line 1: directives such as '#Persistent' are not allowed"]
    assert S.problems("  #NoEnv  ; habit") == [
        "line 1: directives such as '#NoEnv' are not allowed"]
    assert S.problems("#Include lib.ahk") == [
        "line 1: directives such as '#Include' are not allowed"]


def test_an_allowed_include_passes_whatever_the_case():
    assert S.problems("#Include lib.ahk", allow_includes=["LIB.AHK"]) == []
    assert S.problems("#includeagain  tap.ahk ", allow_includes=["tap.ahk"]) == []
    assert S.problems("#Include other.ahk", allow_includes=["tap.ahk"]) != []


def test_a_directive_naming_a_banned_word_gets_one_report():
    assert S.problems("#Include run.ahk") == [
        "line 1: directives such as '#Include' are not allowed"]
    assert S.problems("#Include run.ahk", allow_includes=["run.ahk"]) == []


def test_percent_signs():
    assert S.problems("x := %name%") == [
        "line 1: '%' reaches a variable or function by a name known only at run time"]
    assert S.problems('x := "50%"') == []


def test_hotkeys_and_hotstrings():
    assert S.problems("^j::Send, hi") == [
        "line 1: a hotkey or hotstring would run whenever a key is pressed",
        "line 1: 'Send' is not allowed in a crew module"]
    assert S.problems("::btw::by the way") == [
        "line 1: a hotkey or hotstring would run whenever a key is pressed"]


def test_labels():
    assert S.problems("Start:") == ["line 1: a label is not allowed; write a function"]
    assert S.problems("  Next_1:  ") == ["line 1: a label is not allowed; write a function"]
    assert S.problems("x := a ? b : c") == []


def test_unterminated_strings_come_first_on_their_line():
    assert S.problems('Run("open') == [
        "line 1: a string is opened and never closed",
        "line 1: 'Run' is not allowed in a crew module"]


def test_problems_are_sorted_by_line():
    src = "Sleep 1\n#Persistent\nx := %y%\nStart:"
    lines = [int(p.split(":")[0].split()[1]) for p in S.problems(src)]
    assert lines == [1, 2, 3, 4]
