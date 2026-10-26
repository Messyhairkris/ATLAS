# Contract: history_docs.py - what search over past work indexes, and how a query is built

Part of the crew harness. Kris wants to search past crew jobs, the PA chats' artifacts,
research digests, night reports and playbooks from The Crew window and from a PA. The harness
keeps an SQLite full-text index (FTS5); this module is the pure part: it turns a crew job and
a document into the records that get indexed, and turns what a person typed into a safe FTS5
query. Pure text in, dicts and text out. No I/O.

## Public API

```python
MAX_BODY_CHARS = 20000

def job_record(job: dict, outputs: dict[str, str], path: str) -> dict: ...
def doc_record(path: str, text: str, kind: str = "doc", when: str = "") -> dict: ...
def fts_query(text: str, max_terms: int = 12) -> str: ...
```

Allowed imports: `re`. Nothing else. Spell every name exactly as above.

Every record has exactly these keys, all strings: `key`, `kind`, `title`, `body`, `path`,
`when`, `who`, `tags`.

## job_record(job, outputs, path)

`job` is a crew job (a dict as stored in job.json); `outputs` maps an output file name to its
text; `path` is where the job lives. Any key of `job` may be missing.

1. `key` = `"job:" + job["task_id"]` (`task_id` is always present).
2. `kind` = `"job"`.
3. `title` = `job["title"]` when it is a non-empty string, else the task id.
4. `who` = `job["assigned_to"]` or `""`.
5. `when` = the first non-empty of `job["finished_at"]`, `job["updated_at"]`,
   `job["created_at"]`, else `""`.
6. `tags`: these values, in this order, each only when it is a non-empty string, each only
   once, joined with one space: `job["task_type"]`, `job["status"]`,
   `job["result"]["stop_reason"]` (`result` may be missing or `None`), and the word
   `"question"` when `job["question"]` is truthy.
7. `body`: these parts, each only when non-empty, joined with `"\n\n"`:
   - `job["description"]`;
   - for every name in `outputs` in sorted order: `"## " + name + "\n" + outputs[name]`;
   - when `job["result"]["findings"]` is a non-empty list: `"## notes\n"` followed by one line
     `"- " + finding` per finding, joined with `"\n"`.
   Then cut to the first `MAX_BODY_CHARS` characters (no ellipsis).
8. `path` = `path` with every `\` replaced by `/`.

## doc_record(path, text, kind="doc", when="")

1. `p` = `path` with every `\` replaced by `/`. `key` = `kind + ":" + p`; `path` = `p`;
   `kind` = `kind`; `when` = `when`; `who` = `""`.
2. Frontmatter is present when the text's first line is exactly `---` and a later line is
   exactly `---`; it is the lines between them. (Lines are split on `"\n"`; a trailing `"\r"`
   on a line is ignored for these comparisons.)
3. `title`: the frontmatter's `title:` value (text after the first `:`, stripped, with one pair
   of surrounding `"` or `'` quotes removed) when there is one and it is non-empty; else the
   text of the first body line that starts with `"# "` (after `"# "`, stripped); else the last
   segment of `p`.
4. `tags`: from the frontmatter's `tags:` value - with surrounding `[` `]` removed, split on
   commas, each stripped of spaces and quotes, empty ones dropped, joined with one space - else
   `""`.
5. `body`: the text after the frontmatter (the whole text when there is none), stripped, cut to
   the first `MAX_BODY_CHARS` characters.

## fts_query(text, max_terms=12)

What a person typed becomes an FTS5 query in which nothing they type can be read as an FTS5
operator, column filter or syntax error.

1. Walk `text` left to right with the regex `"([^"]*)"|(\w+)(\*?)` (a double-quoted phrase, or
   a word optionally followed by `*`). Everything else in the text is ignored (so an unmatched
   `"` is ignored and the words after it are read as words).
2. A phrase becomes `"w1 w2 ..."` - its `\w+` words, lower-cased, joined with one space. A
   phrase with no words is dropped.
3. A word becomes `"word"` lower-cased; with a `*` straight after it, `"word"*` (a prefix query).
4. Drop a term that is the same as an earlier term (compare the whole term text, `*` included).
5. Keep the first `max_terms` terms; join them with one space. No terms -> `""`.

## Worked examples (the hidden tests walk every row)

| call | result |
|---|---|
| `fts_query("budget line")` | `'"budget" "line"'` |
| `fts_query('"token budget" Qwen')` | `'"token budget" "qwen"'` |
| `fts_query("compact*")` | `'"compact"*'` |
| `fts_query('NOT a OR b')` | `'"not" "a" "or" "b"'` |
| `fts_query('title:x -y (z)')` | `'"title" "x" "y" "z"'` |
| `fts_query('"" ok')` | `'"ok"'` |
| `fts_query('"unclosed phrase')` | `'"unclosed" "phrase"'` |
| `fts_query("a a A")` | `'"a"'` |
| `fts_query("a a*")` | `'"a" "a"*'` |
| `fts_query("x " * 20, 3)` | `'"x"'` |
| `fts_query("one two three four", 3)` | `'"one" "two" "three"'` |
| `fts_query("café ünïcode")` | `'"café" "ünïcode"'` |
| `fts_query("  ;; ")` | `''` |
| `doc_record("a\\b\\c.md", "---\ntitle: \"Hi\"\ntags: [x, 'y']\n---\n\nBody\n")` | key `doc:a/b/c.md`, title `Hi`, tags `x y`, body `Body`, path `a/b/c.md` |
| `doc_record("r/n.md", "# Night report\ntext", "night", "2026-10-26T03:00")` | key `night:r/n.md`, kind `night`, title `Night report`, when `2026-10-26T03:00`, body `# Night report\ntext` |
| `doc_record("r/plain.md", "no heading")` | title `plain.md`, tags `""` |
| `doc_record("r/t.md", "---\ntitle:\ntags: a, b\n---\n# H\nx")` | title `H`, tags `a b`, body `# H\nx` |
| `doc_record("r/f.md", "---\nonly one fence\n# T")` | no frontmatter: title `T`, body is the whole text stripped |
| `job_record({"task_id": "j1"}, {}, "C:\\runs\\j1")` | title `j1`, tags `""`, body `""`, when `""`, who `""`, path `C:/runs/j1` |
| `job_record({"task_id": "j2", "title": "T", "task_type": "scout", "status": "review", "result": {"stop_reason": "passed", "findings": ["f1", "f2"]}, "question": {"question": "q"}, "description": "D", "assigned_to": "Hoss", "created_at": "c", "finished_at": "f"}, {"b.md": "B", "a.md": "A"}, "p")` | tags `scout review passed question`, who `Hoss`, when `f`, body `D\n\n## a.md\nA\n\n## b.md\nB\n\n## notes\n- f1\n- f2` |
| `job_record({"task_id": "j3", "title": "", "status": "failed", "task_type": "failed", "result": None}, {}, "p")` | title `j3`, tags `failed` |
