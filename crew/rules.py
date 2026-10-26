"""Rules with triggers (Kris 2026-10-24): one folder of rules for every PA runtime,
each rule a small .md with a frontmatter trigger that says when it applies.

Rendered ONCE - into a PA's brief when its session starts (for_brief) and into a
crew job's system prompt when the job starts (for_job) - never added to every reply
(hooks that added text to every call wasted the weekly limits).

Triggers:
  always_on      - in every brief and every job prompt
  glob           - in a job's prompt when one of the rule's globs matches one of the
                   job's files (a brief knows no files yet, so it never appears there)
  model_decision - never inlined: listed with its description, so the model reads the
                   file (crew/rules/<name>.md) when it applies
  manual         - inlined only when its name is passed in

  parse_rule(text, name)     frontmatter + body, or None
  load_rules(folder)         every *.md in the folder, sorted, unparseable skipped
  glob_match(pattern, path)  case-insensitive, \\ = /, gitignore-like
  select(rules, files, manual) -> (full, listed)
  render(full, listed, budget_chars) -> str
  for_brief(folder, budget_chars)     the section for a PA brief
  for_job(spec, folder, budget_chars) the section for a crew job's system prompt
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

TRIGGERS = ("always_on", "model_decision", "glob", "manual")
RULES_DIR = Path(__file__).resolve().parent / "rules"


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _parse_globs(value: str) -> List[str]:
    """A quoted or plain comma-separated string, or a YAML-style list [a, b]; entries
    are stripped and empty ones dropped."""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    else:
        value = _unquote(value)
    return [_unquote(entry) for entry in value.split(",") if entry.strip()]


def parse_rule(text: str, name: str) -> Optional[dict]:
    """The rule in a `---` frontmatter block (name, trigger, description, globs) plus
    a stripped markdown body. None when there is no frontmatter, the trigger is not
    one of TRIGGERS, a model_decision rule has no description, or a glob rule has no
    globs. name defaults to the file's stem."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    meta: Dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        if key.strip():
            meta[key.strip()] = value.strip()
    body = "\n".join(lines[end + 1 :]).strip()
    trigger = meta.get("trigger", "").strip()
    if trigger not in TRIGGERS:
        return None
    description = _unquote(meta.get("description", ""))
    globs = _parse_globs(meta["globs"]) if "globs" in meta else []
    if trigger == "model_decision" and not description:
        return None
    if trigger == "glob" and not globs:
        return None
    return {
        "name": _unquote(meta.get("name", "")) or name,
        "trigger": trigger,
        "description": description,
        "globs": globs,
        "body": body,
    }


def load_rules(folder: Path = RULES_DIR) -> List[dict]:
    """Every *.md in `folder` (sorted by file name) that parses; a missing folder is []."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    rules: List[dict] = []
    for path in sorted(folder.glob("*.md"), key=lambda p: p.name):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rule = parse_rule(text, path.stem)
        if rule is not None:
            rules.append(rule)
    return rules


def _segment_regex(segment: str) -> str:
    """One path segment: * = any run of characters except /, ? = one character
    except /, everything else literal."""
    out = []
    for ch in segment:
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


_STARSTAR = object()


def _full_path_regex(pattern: str) -> str:
    """A pattern with at least one /: the whole path must match. **/ matches zero or
    more whole folders; a trailing ** matches anything."""
    atoms: List[object] = []
    for segment in pattern.split("/"):
        if segment == "**":
            if not atoms or atoms[-1] is not _STARSTAR:
                atoms.append(_STARSTAR)
        else:
            atoms.append(_segment_regex(segment))
    regex = ""
    prev_was_starstar = False
    for i, atom in enumerate(atoms):
        if atom is _STARSTAR:
            if i == len(atoms) - 1:
                regex += ".*" if not regex else "/.*"
            else:
                # **/ : the join into the next segment is inside the repetition, so
                # the next atom attaches without its own slash
                regex += "(?:[^/]+/)*" if not regex else "/(?:[^/]+/)*"
            prev_was_starstar = True
            continue
        if atom == "":
            continue
        if not regex:
            regex = atom
        elif prev_was_starstar:
            regex += atom
        else:
            regex += "/" + atom
        prev_was_starstar = False
    return regex


def glob_match(pattern: str, path: str) -> bool:
    """Case-insensitive; \\ in either argument counts as /.

    * matches any run of characters except /, ? exactly one character except /,
    **/ zero or more whole folders, and a trailing ** anything. A pattern with no /
    is matched against the last path segment only (like .gitignore): *.ps1 matches
    a/b/run.ps1. Otherwise the whole path must match: crew/**/*.py matches crew/x.py
    and crew/a/b/x.py, not tests/crew/x.py."""
    pattern = pattern.replace("\\", "/").lower()
    path = path.replace("\\", "/").lower()
    if not pattern or not path:
        return False
    if "/" not in pattern:
        return (
            re.fullmatch(_segment_regex(pattern), path.rsplit("/", 1)[-1]) is not None
        )
    return re.fullmatch(_full_path_regex(pattern), path) is not None


def select(
    rules: Sequence[dict], files: Sequence[str] = (), manual: Sequence[str] = ()
) -> Tuple[List[dict], List[dict]]:
    """(full, listed). full: every always_on rule, every glob rule with at least one
    glob matching at least one of files, every manual rule whose name is in manual -
    in that trigger order, by name within each. listed: every model_decision rule.
    Unmatched glob and manual rules are left out."""
    manual = set(manual)
    picked: Dict[str, List[dict]] = {"always_on": [], "glob": [], "manual": []}
    listed: List[dict] = []
    for rule in rules:
        trigger = rule.get("trigger")
        if trigger == "always_on":
            picked["always_on"].append(rule)
        elif trigger == "model_decision":
            listed.append(rule)
        elif trigger == "glob":
            if any(
                glob_match(glob, path)
                for glob in rule.get("globs") or ()
                for path in files
            ):
                picked["glob"].append(rule)
        elif trigger == "manual" and rule.get("name") in manual:
            picked["manual"].append(rule)
    full: List[dict] = []
    for trigger in ("always_on", "glob", "manual"):
        full.extend(sorted(picked[trigger], key=lambda r: r["name"]))
    listed.sort(key=lambda r: r["name"])
    return full, listed


def render(
    full: Sequence[dict], listed: Sequence[dict], budget_chars: int = 3000
) -> str:
    """'' when both are empty. Otherwise '## Rules', then each full rule as
    '### {name}' + newline + body, in order, while the whole text so far stays at
    most budget_chars; a full rule that would go over is not shown and is added to
    the listed part instead, with the description '(over the rules budget)' when it
    has none. Then, when anything is listed: the 'Read one of these when it applies'
    line and one '- {name}: {description}' line per rule. Lines joined with \\n."""
    if not full and not listed:
        return ""
    listed = list(listed)
    blocks = ["## Rules"]
    for rule in full:
        block = f"### {rule['name']}\n{rule['body']}"
        if len("\n".join(blocks + [block])) <= budget_chars:
            blocks.append(block)
        else:
            listed.append(
                {
                    "name": rule["name"],
                    "description": rule.get("description") or "(over the rules budget)",
                }
            )
    lines = [line for block in blocks for line in block.split("\n")]
    if listed:
        lines.append("Read one of these when it applies (crew/rules/<name>.md):")
        lines.extend(f"- {rule['name']}: {rule['description']}" for rule in listed)
    return "\n".join(lines)


def for_brief(folder: Path = RULES_DIR, budget_chars: int = 3000) -> str:
    """The rules section for a PA brief: it knows no files yet, so glob rules do not
    appear there."""
    return render(*select(load_rules(folder)), budget_chars=budget_chars)


def for_job(spec: dict, folder: Path = RULES_DIR, budget_chars: int = 2000) -> str:
    """The rules section for a crew job's system prompt, from the job's files:
    spec['output']['files'], spec['module'] and the names in spec['context_files']
    (all that are present; any of them may be missing)."""
    files: List[str] = []
    output = spec.get("output") or {}
    if isinstance(output, dict):
        files.extend(output.get("files") or [])
    module = spec.get("module")
    if module:
        files.append(module)
    files.extend(spec.get("context_files") or [])
    files = [f for f in files if f]
    return render(*select(load_rules(folder), files), budget_chars=budget_chars)
