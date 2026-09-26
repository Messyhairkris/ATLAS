"""PA reference implementation of contracts/st_mission.md (never shown to the crew)."""

import json
import urllib.parse


def _parts(u):
    p = urllib.parse.urlsplit(u)
    return p.scheme.lower(), p.netloc.lower(), urllib.parse.unquote(p.path)


def url_allowed(url, prefixes):
    if not isinstance(url, str) or not url:
        return False
    try:
        scheme, netloc, path = _parts(url)
    except ValueError:
        return False
    if scheme not in ("http", "https", "file"):
        return False
    if ".." in path.split("/"):
        return False
    for pre in prefixes or []:
        try:
            ps, pn, pp = _parts(pre)
        except ValueError:
            continue
        if ps != scheme or pn != netloc:
            continue
        if scheme == "file":
            if path.lower().startswith(pp.lower()):
                return True
        elif path.startswith(pp):
            return True
    return False


class Mission:
    def __init__(self, allowed_tools, acting_tools, url_prefixes, max_steps, max_actions,
                 max_errors_in_a_row=3, max_repeats=2):
        self.allowed_tools = list(allowed_tools)
        self.acting_tools = list(acting_tools)
        self.url_prefixes = list(url_prefixes)
        self.max_steps = max_steps
        self.max_actions = max_actions
        self.max_errors_in_a_row = max_errors_in_a_row
        self.max_repeats = max_repeats
        self.steps = self.actions = self.errors_in_a_row = self.refused = 0
        self._refused_run = 0
        self._seen = {}
        self._by_tool = {}

    def _key(self, name, args):
        return name + "\x00" + json.dumps(args, sort_keys=True)

    def _refuse(self, text):
        self.refused += 1
        self._refused_run += 1
        return text

    def check(self, name, args):
        if self.steps >= self.max_steps:
            return self._refuse(f"step budget spent ({self.max_steps} steps)")
        if name not in self.allowed_tools:
            return self._refuse(f"tool '{name}' is not part of this mission")
        if name in self.acting_tools and self.actions >= self.max_actions:
            return self._refuse(f"action budget spent ({self.max_actions} actions)")
        if "url" in args and not url_allowed(args["url"], self.url_prefixes):
            return self._refuse(f"url '{args['url']}' is outside this mission's allowlist")
        n = self._seen.get(self._key(name, args), 0)
        if n >= self.max_repeats:
            return self._refuse(
                f"repeated call: '{name}' with the same arguments {n} times already")
        return None

    def record(self, name, args, ok):
        self.steps += 1
        self._refused_run = 0
        if name in self.acting_tools:
            self.actions += 1
        self.errors_in_a_row = 0 if ok else self.errors_in_a_row + 1
        k = self._key(name, args)
        self._seen[k] = self._seen.get(k, 0) + 1
        self._by_tool[name] = self._by_tool.get(name, 0) + 1

    def stop_reason(self):
        if self.steps >= self.max_steps:
            return "max_steps"
        if self.errors_in_a_row >= self.max_errors_in_a_row:
            return "errors_in_a_row"
        if self._refused_run >= 3:
            return "refused_in_a_row"
        return None

    def summary(self):
        return {"steps": self.steps, "actions": self.actions, "refused": self.refused,
                "errors_in_a_row": self.errors_in_a_row, "by_tool": dict(self._by_tool),
                "stop_reason": self.stop_reason()}
