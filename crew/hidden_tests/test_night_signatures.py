"""Hidden tests for night_signatures.py - the author never sees these."""

import night_signatures as m


def job(task_id="j1", task_type="code_task", member="Hoss", status="failed", **result):
    return {"task_id": task_id, "task_type": task_type, "assigned_to": member,
            "status": status, "result": result}


def step(rung, detail="", ok=False):
    return {"rung": rung, "ok": ok, "detail": detail}


# ---- head -------------------------------------------------------------------

def test_head_table_rows():
    rows = [
        ("cited but never opened this job: backend/main.rs", "cited but never opened this job"),
        ("claims not found in what you read: '12' in: - x", "claims not found in what you read"),
        ("tests_failed: 3 failed\nThe hidden tests fail.", "tests_failed: N failed"),
        ("compile_failed: error[E0308]: mismatched types", "compile_failed: error[EN]"),
        ("bad output paths: python (not a declared output)", "bad output paths: python"),
        ("no YAML frontmatter (--- ... ---) at top", "no YAML frontmatter (--- ... ---) at top"),
        ("non-ASCII characters: 3", "non-ASCII characters"),
        ("4 item line(s) without a citation, e.g. - **Missing", "N item line(s) without a citation"),
        ("PermissionError: [Errno 13] Permission denied: 'C:\\x'",
         "PermissionError: [Errno N] Permission denied"),
        ("", ""),
    ]
    for text, want in rows:
        assert m.head(text) == want, text


def test_head_ignores_markers_before_index_20():
    assert m.head("short: abc (x) and more: tail") == "short: abc (x) and more"


def test_head_caps_at_60_and_strips_trailing_space():
    text = "a" * 59 + " " + "b" * 30
    assert m.head(text) == "a" * 59
    assert len(m.head("z" * 200)) == 60


def test_head_replaces_every_digit_run_with_one_n():
    assert m.head("2026-10-23 at 12:41") == "N-N-N at N:N"


def test_head_of_non_string():
    assert m.head(504) == "N"


# ---- classify ---------------------------------------------------------------

def test_not_failed_gives_nothing():
    assert m.classify(job(status="completed", error="boom")) == []
    assert m.classify(job(status="review")) == []
    assert m.classify({"status": "failed"}) == [("unknown", "?|unknown")]


def test_stopped_by_the_pa():
    j = job(error="stopped by the PA on 2026-10-20: harness fault", stop_reason="x")
    assert m.classify(j) == [("stopped", "code_task|stopped")]


def test_provider_errors_are_per_member():
    for err in ["HTTPStatusError: Server error '504 Gateway Timeout' for url 'https://a'",
                "ReadTimeout: The read operation timed out",
                "ConnectError: [Errno 11001]",
                "something 429 Too Many Requests"]:
        assert m.classify(job(member="Larry", error=err)) == [("provider", "provider|Larry")], err


def test_other_errors_are_harness():
    j = job(task_type="ahk_code_task",
            error="CrewError: no playbook for task type 'ahk_code_task'")
    assert m.classify(j) == [
        ("harness", "ahk_code_task|error|CrewError: no playbook for task type 'ahk_code_task'")]


def test_error_wins_over_steps_and_stop():
    j = job(error="ValueError: bad", stop_reason="budget_tokens", steps=[step("api", "x")])
    assert m.classify(j) == [("harness", "code_task|error|ValueError: bad")]


def test_ceiling_stops_name_the_member():
    for stop in ["budget_requests", "budget_tokens", "output_truncated", "empty_replies",
                 "thinking_cut_off"]:
        j = job(member="Qwen", stop_reason=stop, steps=[step("hidden tests", "1 failed")])
        assert m.classify(j) == [("ceiling", f"code_task|ceiling|{stop}|Qwen")], stop


def test_failed_steps_one_finding_each_in_order():
    j = job(task_type="research_digest", stop_reason="no_progress",
            steps=[step("output path", ok=True),
                   step("citations", "cited but never opened this job: a.md"),
                   step("grounding", "claims not found in what you read: '3' in: x")])
    assert m.classify(j) == [
        ("gate", "research_digest|citations|cited but never opened this job"),
        ("gate", "research_digest|grounding|claims not found in what you read"),
    ]


def test_mechanical_rungs():
    j = job(task_type="research_digest",
            steps=[step("frontmatter", "no YAML frontmatter (--- ... ---) at top"),
                   step("ascii", "non-ASCII characters: 3"),
                   step("quirks", "assert False inside try at lines 4, 9")])
    assert m.classify(j) == [
        ("mechanical", "research_digest|frontmatter|no YAML frontmatter (--- ... ---) at top"),
        ("mechanical", "research_digest|ascii|non-ASCII characters"),
        ("mechanical", "research_digest|quirks|assert False inside try at lines N, N"),
    ]


def test_bad_output_paths_is_mechanical_but_other_output_failures_are_not():
    j = job(steps=[step("output", "bad output paths: python (not a declared output)")])
    assert m.classify(j) == [("mechanical", "code_task|output|bad output paths: python")]
    j = job(steps=[step("output", "missing output: a.py")])
    assert m.classify(j) == [("gate", "code_task|output|missing output: a.py")]


def test_stuck_only_when_no_step_failed():
    for stop in ["no_progress", "no_change", "loop_repeat", "contract_abandoned"]:
        j = job(member="Nemotron", stop_reason=stop, steps=[step("api", ok=True)])
        assert m.classify(j) == [("stuck", f"code_task|stuck|{stop}|Nemotron")], stop


def test_unknown():
    assert m.classify(job(stop_reason="submitted")) == [("unknown", "code_task|unknown")]
    assert m.classify(job(stop_reason=None, steps=None)) == [("unknown", "code_task|unknown")]


def test_missing_fields_default_to_question_marks():
    j = {"status": "failed", "result": {"error": "504 Gateway Timeout"}}
    assert m.classify(j) == [("provider", "provider|?")]


# ---- group ------------------------------------------------------------------

def test_group_counts_members_and_job_ids():
    jobs = [job("a", member="Larry", error="504 Gateway Timeout"),
            job("b", member="Larry", error="ReadTimeout"),
            job("c", member="Qwen", stop_reason="budget_tokens")]
    assert m.group(jobs) == [
        {"category": "provider", "signature": "provider|Larry", "count": 2,
         "members": ["Larry"], "job_ids": ["a", "b"], "candidate": False},
        {"category": "ceiling", "signature": "code_task|ceiling|budget_tokens|Qwen",
         "count": 1, "members": ["Qwen"], "job_ids": ["c"], "candidate": False},
    ]


def test_group_order_category_then_count_then_signature():
    fm = step("frontmatter", "no YAML frontmatter at top")
    jobs = [job("1", stop_reason="no_change"),
            job("2", steps=[step("api", "missing: b")]),
            job("3", steps=[step("api", "missing: a")]),
            job("4", steps=[step("api", "missing: a")]),
            job("5", steps=[fm]),
            job("6", error="stopped by the PA: x")]
    order = [(e["category"], e["signature"]) for e in m.group(jobs)]
    assert order == [
        ("stopped", "code_task|stopped"),
        ("mechanical", "code_task|frontmatter|no YAML frontmatter at top"),
        ("gate", "code_task|api|missing: a"),
        ("gate", "code_task|api|missing: b"),
        ("stuck", "code_task|stuck|no_change|Hoss"),
    ]


def test_candidate_needs_mechanical_and_threshold():
    fm = step("frontmatter", "no YAML frontmatter at top")
    jobs = [job(str(i), member=name, steps=[fm]) for i, name in
            enumerate(["Hoss", "Barry", "Hoss"])]
    (entry,) = m.group(jobs)
    assert entry["count"] == 3 and entry["candidate"] is True
    assert entry["members"] == ["Barry", "Hoss"]
    assert entry["job_ids"] == ["0", "1", "2"]
    (entry,) = m.group(jobs, threshold=4)
    assert entry["candidate"] is False
    gate = [job(str(i), steps=[step("api", "x")]) for i in range(5)]
    assert m.group(gate)[0]["candidate"] is False


def test_one_job_counts_once_per_signature_but_job_id_listed_once():
    j = job("dup", steps=[step("api", "x"), step("api", "x")])
    (entry,) = m.group([j])
    assert entry["count"] == 2
    assert entry["job_ids"] == ["dup"]


def test_group_skips_jobs_that_did_not_fail():
    assert m.group([job(status="completed"), job(status="review")]) == []
    assert m.group([]) == []


# ---- advice -----------------------------------------------------------------

def test_advice_every_category_and_fallback():
    want = {
        "provider": "the member's endpoint failed; relay or wait, nothing to fix in the work",
        "stopped": "stopped by a person; nothing to fix",
        "harness": "our harness raised an error; read the traceback in the job",
        "ceiling": "our budget ended the job; check the member's ceilings before blaming them",
        "mechanical": "a format miss a program can repair; candidate for a zero-token fixer",
        "gate": "a gate refused the content; needs a reader (model error or contract wording)",
        "stuck": "the member looped without progress; rescope the task or relay it sooner",
        "unknown": "failed with no recorded reason; read the job",
    }
    for category, text in want.items():
        assert m.advice(category) == text
    assert m.advice("nonsense") == want["unknown"]


def test_categories_constant():
    assert m.CATEGORIES == ("provider", "stopped", "harness", "ceiling", "mechanical", "gate",
                            "stuck", "unknown")
