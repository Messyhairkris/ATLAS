"""${HOME} and ${REPO} in settings, so no tracked file has to carry an account name.

The harness kept absolute paths in `crew/config.json` and its siblings, which meant every publish
carried the Windows account name. A settings file now names the two places it may reach instead:

    "${HOME}/Documents"      the account's home directory
    "${REPO}/runs/crew"      this checkout's root

`expand()` is the only thing that turns them into real paths, and it is what a loader calls.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

HOME = "${HOME}"
REPO = "${REPO}"

REPO_ROOT = Path(__file__).resolve().parent.parent


def expand(text: Any, home: Optional[Any] = None, repo: Optional[Any] = None) -> Any:
    """`${HOME}`, `${REPO}` and a leading `~` replaced by real paths; anything else unchanged."""
    if not isinstance(text, str):
        return text
    out = text.replace(HOME, str(home if home is not None else Path.home()))
    out = out.replace(REPO, str(repo if repo is not None else REPO_ROOT))
    if out.startswith("~"):
        out = str(home if home is not None else Path.home()) + out[1:]
    return out


def expand_all(value: Any, home: Optional[Any] = None, repo: Optional[Any] = None) -> Any:
    """`expand()` through a string, a list or a dict, leaving the shape alone."""
    if isinstance(value, str):
        return expand(value, home, repo)
    if isinstance(value, list):
        return [expand_all(v, home, repo) for v in value]
    if isinstance(value, dict):
        return {k: expand_all(v, home, repo) for k, v in value.items()}
    return value


def is_portable(text: Any) -> bool:
    """True when a settings string carries no account: only ${HOME}, ${REPO} or a relative path."""
    if not isinstance(text, str):
        return True
    if HOME in text or REPO in text:
        return True
    drive = len(text) > 2 and text[1] == ":"
    return not drive and not text.startswith(("/", os.sep))
