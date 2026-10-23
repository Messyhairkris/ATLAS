"""Who may be the PA, and promoting a crew member to it (Kris only).

Kris, 2026-10-23: "I would like to choose between Claude, Kimi, Qwen, and Gordon for
now, with the ability to upgrade a Crew Member to PA status." The approved list and each
PA's scope live in personnel.json under "pa"; crew/pa_brief.py turns them into the PA's
first prompt.

Only the PM promotes or demotes. As with Autonomy Stages, no MCP tool can do it - and
because a PA may have a shell, these commands also need a real console and the member's
name typed back. A PA's shell (Claude Code, OpenCode) is non-interactive, so it is refused.

  python -m crew pa list
  python -m crew pa promote Larry --by Kris [--runtime opencode] [--steps 40]
  python -m crew pa demote Qwen --by Kris
  python -m crew pa brief Gordon
"""

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Callable, List, Optional

from .config import CrewError

PERSONNEL = Path(__file__).resolve().parent / "personnel.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def approved(path: Path = PERSONNEL) -> List[str]:
    return list((_load(path).get("pa") or {}).get("approved") or [])


def listing(path: Path = PERSONNEL) -> dict:
    cfg = _load(path).get("pa") or {}
    return {"default": cfg.get("default"), "approved": cfg.get("approved") or [],
            "scopes": {name: {k: v for k, v in scope.items() if k != "notes"}
                       for name, scope in (cfg.get("scopes") or {}).items()}}


def real_console() -> bool:
    """True only when stdin is an actual console a person types into.

    isatty() is not enough on Windows: the NUL device a tool shell gives its children
    counts as a character device (measured 2026-10-23 from Claude Code's PowerShell tool:
    isatty() True, then input() hit EOF). GetConsoleMode succeeds only on a console."""
    if sys.platform != "win32":
        return sys.stdin.isatty()
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)                     # STD_INPUT_HANDLE
    mode = ctypes.c_uint32()
    return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode)))


def _confirm(member: str, verb: str, ask: Callable[[str], str], interactive: bool) -> None:
    if not interactive:
        raise CrewError(f"pa {verb} needs the PM at a real console (stdin is not a "
                        f"console); a PA cannot {verb} anyone")
    try:
        typed = ask(f"Type {member} to {verb} {member} as a PA: ").strip()
    except EOFError:
        typed = ""
    if typed != member:
        raise CrewError(f"not confirmed (typed {typed!r}); nothing changed")


def _write_checked(path: Path, text: str) -> None:
    json.loads(text)                     # never leave personnel.json unparseable
    path.write_text(text, encoding="utf-8")


def _set_approved(text: str, names: List[str]) -> str:
    line = '"approved": [' + ", ".join(f'"{n}"' for n in names) + "]"
    new, count = re.subn(r'"approved":\s*\[[^\]]*\]', line, text, count=1)
    if count != 1:
        raise CrewError('personnel.json has no "pa": {"approved": [...]} to edit')
    return new


def promote(member: str, by: str, runtime: str = "opencode", steps: int = 40,
            path: Path = PERSONNEL, ask: Callable[[str], str] = input,
            interactive: Optional[bool] = None, today: Optional[str] = None) -> dict:
    if by != "Kris":
        raise CrewError("only the PM (--by Kris) promotes a PA")
    data = _load(path)
    staff = data.get("members") or {}
    if member not in staff and member != "Claude":
        raise CrewError(f"{member} is not a crew member (personnel.json members: "
                        f"{', '.join(staff)})")
    names = list((data.get("pa") or {}).get("approved") or [])
    if member in names:
        raise CrewError(f"{member} is already an approved PA")
    _confirm(member, "promote", ask, real_console() if interactive is None else interactive)
    text = _set_approved(path.read_text(encoding="utf-8"), names + [member])
    if member not in ((data.get("pa") or {}).get("scopes") or {}):
        day = today or dt.date.today().isoformat()
        scope = json.dumps({"runtime": runtime, "model": staff.get(member, {}).get("model", ""),
                            "steps": steps,
                            "notes": f"Promoted to PA by Kris on {day}; no record as PA yet - "
                                     f"keep plans small and check in often."})
        text, count = re.subn(r'("scopes":\s*\{\s*\n)', lambda m: m.group(1)
                              + f'      "{member}": {scope},\n', text, count=1)
        if count != 1:
            raise CrewError('personnel.json has no "pa": {"scopes": {...}} to add to')
    _write_checked(path, text)
    return {"promoted": member, "approved": names + [member]}


def demote(member: str, by: str, path: Path = PERSONNEL, ask: Callable[[str], str] = input,
           interactive: Optional[bool] = None) -> dict:
    if by != "Kris":
        raise CrewError("only the PM (--by Kris) demotes a PA")
    names = approved(path)
    if member not in names:
        raise CrewError(f"{member} is not an approved PA")
    if len(names) == 1:
        raise CrewError("refusing to demote the last approved PA")
    _confirm(member, "demote", ask, real_console() if interactive is None else interactive)
    keep = [n for n in names if n != member]
    text = _set_approved(path.read_text(encoding="utf-8"), keep)
    data = json.loads(text)
    if (data.get("pa") or {}).get("default") == member:
        text = re.sub(r'("default":\s*)"[^"]*"', lambda m: f'{m.group(1)}"{keep[0]}"',
                      text, count=1)
    _write_checked(path, text)       # the scope entry stays, as the record of the post
    return {"demoted": member, "approved": keep}
