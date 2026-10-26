"""Hidden tests for history_docs.py. Every contract row, plus queries a person types."""

import sqlite3

import pytest

import history_docs as hd

KEYS = {"key", "kind", "title", "body", "path", "when", "who", "tags"}


@pytest.mark.parametrize("text, want", [
    ("budget line", '"budget" "line"'),
    ('"token budget" Qwen', '"token budget" "qwen"'),
    ("compact*", '"compact"*'),
    ("NOT a OR b", '"not" "a" "or" "b"'),
    ("title:x -y (z)", '"title" "x" "y" "z"'),
    ('"" ok', '"ok"'),
    ('"unclosed phrase', '"unclosed" "phrase"'),
    ("a a A", '"a"'),
    ("a a*", '"a" "a"*'),
    ("one two three four", '"one" "two" "three" "four"'),
    ("caf\u00e9 \u00fcn\u00efcode", '"caf\u00e9" "\u00fcn\u00efcode"'),
    ("  ;; ", ""),
    ("", ""),
    ('"a, b!" c', '"a b" "c"'),
    ("x* x*", '"x"*'),
    ("NEAR(a b)", '"near" "a" "b"'),
    ("a*b", '"a"* "b"'),
])
def test_fts_query(text, want):
    assert hd.fts_query(text) == want


def test_fts_query_term_cap():
    assert hd.fts_query("x " * 20, 3) == '"x"'
    assert hd.fts_query("one two three four", 3) == '"one" "two" "three"'
    assert hd.fts_query(" ".join(f"w{i}" for i in range(20))) == " ".join(
        f'"w{i}"' for i in range(12))


@pytest.mark.parametrize("typed", ['NOT', 'a OR', '"', 'col:', '(', 'x AND (y', '^a',
                                   'NEAR', '*', 'a"b"c', "'", '-', 'ab*cd*'])
def test_fts_query_never_breaks_fts5(typed):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
    db.execute("INSERT INTO t VALUES ('not a or b near col ab cd x y')")
    q = hd.fts_query(typed)
    if q:
        db.execute("SELECT * FROM t WHERE t MATCH ?", (q,)).fetchall()


def test_doc_record_frontmatter():
    r = hd.doc_record("a\\b\\c.md", "---\ntitle: \"Hi\"\ntags: [x, 'y']\n---\n\nBody\n")
    assert set(r) == KEYS
    assert (r["key"], r["kind"], r["title"], r["tags"], r["body"], r["path"], r["who"],
            r["when"]) == ("doc:a/b/c.md", "doc", "Hi", "x y", "Body", "a/b/c.md", "", "")


def test_doc_record_heading_and_kind():
    r = hd.doc_record("r/n.md", "# Night report\ntext", "night", "2026-10-26T03:00")
    assert (r["key"], r["kind"], r["title"], r["when"], r["body"]) == (
        "night:r/n.md", "night", "Night report", "2026-10-26T03:00", "# Night report\ntext")


def test_doc_record_falls_back_to_the_file_name():
    r = hd.doc_record("r/plain.md", "no heading")
    assert (r["title"], r["tags"], r["body"]) == ("plain.md", "", "no heading")


def test_doc_record_empty_title_uses_the_heading():
    r = hd.doc_record("r/t.md", "---\ntitle:\ntags: a, b\n---\n# H\nx")
    assert (r["title"], r["tags"], r["body"]) == ("H", "a b", "# H\nx")


def test_doc_record_one_fence_is_not_frontmatter():
    text = "---\nonly one fence\n# T"
    r = hd.doc_record("r/f.md", text)
    assert (r["title"], r["body"], r["tags"]) == ("T", text.strip(), "")


def test_doc_record_horizontal_rules_are_not_frontmatter():
    # review 2026-10-26: digests use --- as rules; only a FIRST line --- opens frontmatter
    text = "# Title\n\ntext\n\n---\n\nmore\n\n---\nend"
    r = hd.doc_record("h.md", text)
    assert (r["title"], r["body"], r["tags"]) == ("Title", text, "")


def test_doc_record_crlf_and_single_quotes():
    r = hd.doc_record("w.md", "---\r\ntitle: 'Windows file'\r\n---\r\nbody\r\n")
    assert r["title"] == "Windows file"
    assert r["body"] == "body"


def test_doc_record_title_with_colon_and_heading_spacing():
    r = hd.doc_record("x.md", "---\ntitle: ATLAS: today\n---\n#NoSpace\n#  Two\n")
    assert r["title"] == "ATLAS: today"
    r = hd.doc_record("y.md", "#NoSpace\n#  Two  \n")
    assert r["title"] == "Two"


def test_doc_record_body_cap():
    r = hd.doc_record("big.md", "z" * (hd.MAX_BODY_CHARS + 50))
    assert r["body"] == "z" * hd.MAX_BODY_CHARS


def test_job_record_minimal():
    r = hd.job_record({"task_id": "j1"}, {}, "C:\\runs\\j1")
    assert set(r) == KEYS
    assert (r["key"], r["kind"], r["title"], r["tags"], r["body"], r["when"], r["who"],
            r["path"]) == ("job:j1", "job", "j1", "", "", "", "", "C:/runs/j1")


def test_job_record_full():
    job = {"task_id": "j2", "title": "T", "task_type": "scout", "status": "review",
           "result": {"stop_reason": "passed", "findings": ["f1", "f2"]},
           "question": {"question": "q"}, "description": "D", "assigned_to": "Hoss",
           "created_at": "c", "finished_at": "f"}
    r = hd.job_record(job, {"b.md": "B", "a.md": "A"}, "p")
    assert r["tags"] == "scout review passed question"
    assert (r["who"], r["when"], r["title"]) == ("Hoss", "f", "T")
    assert r["body"] == "D\n\n## a.md\nA\n\n## b.md\nB\n\n## notes\n- f1\n- f2"


def test_job_record_dedupes_tags_and_handles_none():
    r = hd.job_record({"task_id": "j3", "title": "", "status": "failed",
                       "task_type": "failed", "result": None}, {}, "p")
    assert (r["title"], r["tags"]) == ("j3", "failed")


def test_job_record_when_order_and_skips():
    assert hd.job_record({"task_id": "a", "updated_at": "u", "created_at": "c"}, {},
                         "p")["when"] == "u"
    assert hd.job_record({"task_id": "a", "finished_at": "", "created_at": "c"}, {},
                         "p")["when"] == "c"
    r = hd.job_record({"task_id": "a", "result": {"findings": []}, "question": None,
                       "status": ""}, {"o.md": "O"}, "p")
    assert (r["tags"], r["body"]) == ("", "## o.md\nO")


def test_job_record_body_cap():
    r = hd.job_record({"task_id": "a", "description": "d" * 30000}, {}, "p")
    assert r["body"] == "d" * hd.MAX_BODY_CHARS


def test_records_load_into_fts5_and_are_found():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE h USING fts5(key UNINDEXED, kind, title, body, path, "
               "when_ UNINDEXED, who, tags)")
    recs = [hd.job_record({"task_id": "j9", "title": "Compaction study",
                           "description": "token budget line"}, {}, "p"),
            hd.doc_record("d.md", "# Night\nnothing here")]
    for r in recs:
        db.execute("INSERT INTO h VALUES (?,?,?,?,?,?,?,?)",
                   (r["key"], r["kind"], r["title"], r["body"], r["path"], r["when"], r["who"],
                    r["tags"]))
    hits = db.execute("SELECT key FROM h WHERE h MATCH ?",
                      (hd.fts_query('"token budget" compact*'),)).fetchall()
    assert hits == [("job:j9",)]
