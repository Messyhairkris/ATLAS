# Contract: project_search.py - finding a thing inside a project folder

One self-contained Python module, `project_search.py`. It is what a PA uses when it needs something
from another conversation, an artifact or a linked file **without loading the whole folder** (Kris,
2026-10-30: "delegate a crew member to find it"). It is the **pure** matching half: a runner walks
the folder and hands it the texts, this module decides what matches, how well, and what to show.

**Allowed imports: `re`, `typing`, `__future__`.** No `open()`, no clock, no screen (the crew's
airlock bans `open()`; crew/codetask.py).

## Public API

```python
STOPWORDS = (<a tuple of str>)

def terms(query) -> list
def score(text, ts) -> int
def snippet(text, ts, width=160) -> str
def rank(docs, ts, limit=20) -> list
```

A **doc** is `{"id": str, "kind": str, "text": str}`; `kind` names where it came from
(`"chat"`, `"artifact"`, `"file"`). A **hit** is `{"id", "kind", "score", "snippet"}`.

## The rules

**`terms(query)`** - the query's words to look for: lowercase; split on anything that is not a letter,
a digit or an underscore (`re.findall(r"[A-Za-z0-9_]+")`); drop words in `STOPWORDS`; drop empty
strings; drop repeats keeping the **first**; the original order is kept. A query that is not a `str`,
or is empty, gives `[]`.

`STOPWORDS` is a tuple of lowercase English filler words; it must contain at least
`the a an of in on at to for and or is are was were be been that this it its with from as`.

**`score(text, ts)`** - how many **distinct** terms appear in `text`, compared case-insensitively
(`t in text.lower()`). Each term counts at most once, so `score` can never exceed `len(ts)`. An
empty `ts` gives `0`. A term that is a substring of a word counts - this is a cheap finder, not a
stemmer.

**`snippet(text, ts, width=160)`** - a one-line window around the **earliest** match, for showing
in a result list.

1. Collapse the text to one line first: `" ".join(text.split())`.
2. `""` when `ts` is empty or no term is in it.
3. When the whole line is at most `width` characters, return it **unchanged** - no ellipsis.
4. Otherwise `start = max(0, earliest_index - width // 3)`, `end = min(len(line), start + width)`,
   then `start = max(0, end - width)` so the window is always exactly `width` characters.
5. Prepend `"..."` when `start > 0`, append `"..."` when `end < len(line)`.

**`rank(docs, ts, limit=20)`** - the results, best first:
- only docs whose `score` is above zero;
- each is `{"id", "kind", "score", "snippet"}` (`kind` is `""` when the doc has none);
- sorted by `score` **descending**, then by `id` **ascending** so ties are stable and reproducible;
- at most `limit` of them; a `limit` of zero or less gives `[]`.

## Worked examples

```python
terms("Find the CHAT about the engine!")     # ["find", "chat", "about", "engine"]
terms("the a of")                            # []
terms(None)                                  # []

score("The engine log and the chat", ["engine", "chat"])   # 2
score("The engine log", ["engine", "engine"])              # 1  (distinct terms only)
score("nothing here", ["engine"])                          # 0

snippet("short line", ["line"])                            # "short line"
snippet("a\n b\tc", ["b"])                                 # "a b c"
snippet("x" * 500, [], 10)                                 # ""

rank([{"id": "b", "kind": "chat", "text": "engine chat"},
      {"id": "a", "kind": "chat", "text": "engine"},
      {"id": "c", "kind": "file", "text": "nothing"}],
     ["engine", "chat"])
# [ {"id": "b", "kind": "chat", "score": 2, "snippet": "engine chat"},
#   {"id": "a", "kind": "chat", "score": 1, "snippet": "engine"} ]
```

## Style

Type hints. A one-line docstring per public function naming the rule it implements. No `print()`, no
module-level code beyond the constants. Follow HOUSE_STYLE.md, pasted below this contract when the
task is submitted.
