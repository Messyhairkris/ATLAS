# Crew-built: Gordon, campaign ns-signatures, 2026-10-23, written from the contract alone
# (crew/contracts/ns_signatures.md) and accepted against the real module. Vendored as-is
# apart from the import line.
"""Tests for night_signatures.py, written from the contract in ns_signatures.md."""

from crew import night_signatures  # vendored: crew/night_signatures.py


def _job(task_id="j", task_type="code_task", member="Hoss", status="failed",
         error=None, stop_reason=None, steps=None):
    """Build a job dict; only the keys the test needs are present."""
    result = {}
    if error is not None:
        result["error"] = error
    if stop_reason is not None:
        result["stop_reason"] = stop_reason
    if steps is not None:
        result["steps"] = steps
    return {"task_id": task_id, "task_type": task_type, "assigned_to": member,
            "status": status, "result": result}


def test_categories_tuple_matches_contract():
    """The public CATEGORIES tuple is exactly the contract's order."""
    assert night_signatures.CATEGORIES == (
        "provider", "stopped", "harness", "ceiling", "mechanical", "gate",
        "stuck", "unknown",
    )


def test_head_cuts_at_first_marker_after_index_20():
    """Rule H3: cut at the smallest marker index at or after 20."""
    assert night_signatures.head(
        "cited but never opened this job: backend/main.rs"
    ) == "cited but never opened this job"


def test_head_replaces_digit_runs_with_single_N():
    """Rule H2: every run of digits becomes one N."""
    assert night_signatures.head("2026-10-23 at 12:41") == "N-N-N at N:N"


def test_head_ignores_marker_starting_before_index_20():
    """Rule H3: ': ' at index 12 does not count, so the line is not cut there."""
    assert night_signatures.head(
        "tests_failed: 3 failed\nThe hidden tests fail."
    ) == "tests_failed: N failed"


def test_head_ignores_open_paren_at_index_19():
    """Rule H3: ' (' at index 19 is before 20, so the line is unchanged."""
    assert night_signatures.head(
        "no YAML frontmatter (--- ... ---) at top"
    ) == "no YAML frontmatter (--- ... ---) at top"


def test_head_cuts_at_comma_eg_marker():
    """Rule H3: ', e.g.' is one of the three cut markers."""
    assert night_signatures.head(
        "4 item line(s) without a citation, e.g. - **Missing"
    ) == "N item line(s) without a citation"


def test_head_keeps_only_first_line():
    """Rule H1: everything after the first newline is dropped."""
    assert night_signatures.head("first line\nsecond line") == "first line"


def test_head_truncates_to_60_characters():
    """Rule H4: at most the first 60 characters are kept."""
    assert night_signatures.head("a" * 70) == "a" * 60


def test_head_strips_whitespace_left_by_truncation():
    """Rule H4: trailing whitespace is stripped again after truncation."""
    assert night_signatures.head("b" * 59 + " " + "c" * 10) == "b" * 59


def test_head_of_empty_string_is_empty():
    """Rule H: the empty string has no markers and stays empty."""
    assert night_signatures.head("") == ""


def test_head_cuts_at_smallest_of_several_markers():
    """Rule H3: with ': ' at 14 and 25, the cut is at 25 (14 is before 20)."""
    assert night_signatures.head(
        "compile_failed: error[E0308]: mismatched types"
    ) == "compile_failed: error[EN]"


def test_head_cuts_at_space_paren_marker():
    """Rule H3: ' (' at index 23 cuts, even though ': ' at 16 is too early."""
    assert night_signatures.head(
        "bad output paths: python (not a declared output)"
    ) == "bad output paths: python"


def test_head_converts_non_string_with_str():
    """Rule H1: the text is converted with str() before anything else."""
    assert night_signatures.head(12345) == "N"


def test_classify_non_failed_status_returns_empty():
    """Rule C1: a status other than exactly 'failed' gives no findings."""
    job = _job(status="completed", error="ValueError: bad")
    assert night_signatures.classify(job) == []


def test_classify_missing_status_returns_empty():
    """Rule C1: a missing status is not 'failed', so there are no findings."""
    assert night_signatures.classify({"task_type": "code_task"}) == []


def test_classify_error_starting_with_stopped_by_the_pa():
    """Rule C2a: an error starting 'stopped by the PA' is a stopped finding."""
    job = _job(error="stopped by the PA on 2026-10-20: x")
    assert night_signatures.classify(job) == [("stopped", "code_task|stopped")]


def test_classify_provider_marker_in_error():
    """Rule C2b: a provider marker in the error gives a provider finding."""
    job = _job(member="Larry", error="ReadTimeout: The read operation timed out")
    assert night_signatures.classify(job) == [("provider", "provider|Larry")]


def test_classify_provider_marker_504_gateway():
    """Rule C2b: '504 Gateway' is one of the provider markers."""
    job = _job(error="504 Gateway Time-out")
    assert night_signatures.classify(job) == [("provider", "provider|Hoss")]


def test_classify_harness_error_uses_head_of_error():
    """Rule C2c: any other error is a harness finding labelled by head(error)."""
    job = _job(error="ValueError: bad")
    assert night_signatures.classify(job) == [
        ("harness", "code_task|error|ValueError: bad")
    ]


def test_classify_error_decides_over_stop_reason_and_failed_steps():
    """Rule C2: a non-empty error decides alone, before ceiling and steps."""
    job = _job(error="ValueError: bad", stop_reason="budget_tokens",
               steps=[{"rung": "frontmatter", "ok": False, "detail": "x"}])
    assert night_signatures.classify(job) == [
        ("harness", "code_task|error|ValueError: bad")
    ]


def test_classify_ceiling_stop_wins_over_failed_steps():
    """Rule C3: a ceiling stop is reported before any failed step."""
    job = _job(member="Qwen", stop_reason="budget_tokens",
               steps=[{"rung": "frontmatter", "ok": False, "detail": "x"}])
    assert night_signatures.classify(job) == [
        ("ceiling", "code_task|ceiling|budget_tokens|Qwen")
    ]


def test_classify_ceiling_stop_output_truncated():
    """Rule C3: 'output_truncated' is one of the ceiling stops."""
    job = _job(member="Qwen", stop_reason="output_truncated")
    assert night_signatures.classify(job) == [
        ("ceiling", "code_task|ceiling|output_truncated|Qwen")
    ]


def test_classify_mechanical_rung_frontmatter():
    """Rule C4: a failed frontmatter step is mechanical."""
    job = _job(steps=[{"rung": "frontmatter", "ok": False,
                       "detail": "no YAML frontmatter (--- ... ---) at top"}])
    assert night_signatures.classify(job) == [
        ("mechanical",
         "code_task|frontmatter|no YAML frontmatter (--- ... ---) at top")
    ]


def test_classify_mechanical_rung_ascii():
    """Rule C4: a failed ascii step is mechanical."""
    job = _job(steps=[{"rung": "ascii", "ok": False, "detail": "non-ascii char"}])
    assert night_signatures.classify(job) == [
        ("mechanical", "code_task|ascii|non-ascii char")
    ]


def test_classify_output_rung_bad_output_paths_is_mechanical():
    """Rule C4: an output step whose label starts 'bad output paths' is mechanical."""
    job = _job(steps=[{"rung": "output", "ok": False,
                       "detail": "bad output paths: python (not a declared output)"}])
    assert night_signatures.classify(job) == [
        ("mechanical", "code_task|output|bad output paths: python")
    ]


def test_classify_output_rung_other_detail_is_gate():
    """Rule C4: an output step with any other label is a gate finding."""
    job = _job(steps=[{"rung": "output", "ok": False,
                       "detail": "missing output: a.py"}])
    assert night_signatures.classify(job) == [
        ("gate", "code_task|output|missing output: a.py")
    ]


def test_classify_one_finding_per_failed_step_in_order():
    """Rule C4: every failed step gives one finding, in the order of steps."""
    job = _job(steps=[
        {"rung": "frontmatter", "ok": False,
         "detail": "no YAML frontmatter (--- ... ---) at top"},
        {"rung": "hidden tests", "ok": False, "detail": "3 failed, 30 passed"},
    ])
    assert night_signatures.classify(job) == [
        ("mechanical",
         "code_task|frontmatter|no YAML frontmatter (--- ... ---) at top"),
        ("gate", "code_task|hidden tests|N failed, N passed"),
    ]


def test_classify_skips_steps_that_are_ok():
    """Rule C4: only steps with a falsy ok are reported."""
    job = _job(steps=[
        {"rung": "frontmatter", "ok": True, "detail": "fine"},
        {"rung": "ascii", "ok": False, "detail": "non-ascii char"},
    ])
    assert night_signatures.classify(job) == [
        ("mechanical", "code_task|ascii|non-ascii char")
    ]


def test_classify_stuck_stop_with_no_failed_step():
    """Rule C5: a stuck stop with no failed step is a stuck finding."""
    job = _job(stop_reason="no_change")
    assert night_signatures.classify(job) == [
        ("stuck", "code_task|stuck|no_change|Hoss")
    ]


def test_classify_stuck_stop_loop_repeat():
    """Rule C5: 'loop_repeat' is one of the stuck stops."""
    job = _job(stop_reason="loop_repeat")
    assert night_signatures.classify(job) == [
        ("stuck", "code_task|stuck|loop_repeat|Hoss")
    ]


def test_classify_unknown_when_nothing_recorded():
    """Rule C6: no error, no ceiling, no failed step, no stuck stop -> unknown."""
    job = _job(stop_reason="submitted")
    assert night_signatures.classify(job) == [("unknown", "code_task|unknown")]


def test_classify_defaults_missing_fields():
    """Job dict defaults: missing task_type and assigned_to are '?'."""
    assert night_signatures.classify({"status": "failed"}) == [
        ("unknown", "?|unknown")
    ]


def test_classify_missing_rung_and_detail_default():
    """Job dict defaults: missing rung is '?' and missing detail is ''."""
    job = _job(steps=[{"ok": False}])
    assert night_signatures.classify(job) == [("gate", "code_task|?|")]


def test_group_worked_example_two_providers_and_one_ceiling():
    """Rule G worked example: provider entry then ceiling entry."""
    jobs = [
        _job("a", member="Larry", error="ReadTimeout: The read operation timed out"),
        _job("b", member="Larry", error="ReadTimeout: The read operation timed out"),
        _job("c", member="Qwen", stop_reason="budget_tokens"),
    ]
    assert night_signatures.group(jobs) == [
        {"category": "provider", "signature": "provider|Larry", "count": 2,
         "members": ["Larry"], "job_ids": ["a", "b"], "candidate": False},
        {"category": "ceiling", "signature": "code_task|ceiling|budget_tokens|Qwen",
         "count": 1, "members": ["Qwen"], "job_ids": ["c"], "candidate": False},
    ]


def test_group_candidate_true_at_exactly_threshold():
    """Rule G3: a mechanical entry with count == threshold is a candidate."""
    jobs = [
        _job(str(i), steps=[{"rung": "frontmatter", "ok": False,
                             "detail": "no YAML frontmatter (--- ... ---) at top"}])
        for i in range(3)
    ]
    result = night_signatures.group(jobs)
    assert len(result) == 1
    assert result[0]["count"] == 3
    assert result[0]["candidate"] is True


def test_group_candidate_false_one_below_threshold():
    """Rule G3: count 3 is below threshold 4, so it is not a candidate."""
    jobs = [
        _job(str(i), steps=[{"rung": "frontmatter", "ok": False,
                             "detail": "no YAML frontmatter (--- ... ---) at top"}])
        for i in range(3)
    ]
    result = night_signatures.group(jobs, threshold=4)
    assert result[0]["count"] == 3
    assert result[0]["candidate"] is False


def test_group_entry_has_exactly_the_contract_keys():
    """Rule G1: an entry has exactly these six keys."""
    entry = night_signatures.group([_job("a", error="ReadTimeout: x")])[0]
    assert set(entry) == {"category", "signature", "count", "members", "job_ids",
                          "candidate"}


def test_group_members_sorted_alphabetically():
    """Rule G2: members are sorted alphabetically, not first-seen."""
    jobs = [
        _job("1", member="Zoe", steps=[{"rung": "ascii", "ok": False,
                                        "detail": "non-ascii char"}]),
        _job("2", member="Alice", steps=[{"rung": "ascii", "ok": False,
                                          "detail": "non-ascii char"}]),
    ]
    result = night_signatures.group(jobs)
    assert len(result) == 1
    assert result[0]["members"] == ["Alice", "Zoe"]


def test_group_job_ids_keep_first_seen_order():
    """Rule G2: job_ids keep the order the jobs were first seen."""
    jobs = [
        _job("b", member="Larry", error="ReadTimeout: x"),
        _job("a", member="Larry", error="ReadTimeout: x"),
    ]
    result = night_signatures.group(jobs)
    assert result[0]["job_ids"] == ["b", "a"]


def test_group_orders_categories_by_CATEGORIES_position():
    """Rule G4: entries follow the order of CATEGORIES, not the input order."""
    jobs = [
        _job("u", stop_reason="submitted"),
        _job("s", stop_reason="no_change"),
        _job("g", steps=[{"rung": "output", "ok": False,
                          "detail": "missing output: a.py"}]),
        _job("m", steps=[{"rung": "frontmatter", "ok": False,
                          "detail": "no YAML frontmatter (--- ... ---) at top"}]),
        _job("c", member="Qwen", stop_reason="budget_tokens"),
        _job("p", member="Larry", error="ReadTimeout: x"),
    ]
    result = night_signatures.group(jobs)
    assert [e["category"] for e in result] == [
        "provider", "ceiling", "mechanical", "gate", "stuck", "unknown"
    ]


def test_group_orders_by_count_descending_within_category():
    """Rule G4: inside one category, higher count comes first."""
    jobs = [
        _job("1", steps=[{"rung": "frontmatter", "ok": False,
                          "detail": "no YAML frontmatter (--- ... ---) at top"}]),
        _job("2", steps=[{"rung": "frontmatter", "ok": False,
                          "detail": "no YAML frontmatter (--- ... ---) at top"}]),
        _job("3", steps=[{"rung": "ascii", "ok": False,
                          "detail": "non-ascii char"}]),
    ]
    result = night_signatures.group(jobs)
    assert [e["count"] for e in result] == [2, 1]


def test_group_orders_by_signature_alphabetically_when_count_ties():
    """Rule G4: with equal counts, signatures sort alphabetically."""
    jobs = [
        _job("1", steps=[{"rung": "frontmatter", "ok": False,
                          "detail": "no YAML frontmatter (--- ... ---) at top"}]),
        _job("2", steps=[{"rung": "ascii", "ok": False,
                          "detail": "non-ascii char"}]),
    ]
    result = night_signatures.group(jobs)
    assert [e["signature"] for e in result] == [
        "code_task|ascii|non-ascii char",
        "code_task|frontmatter|no YAML frontmatter (--- ... ---) at top",
    ]


def test_group_empty_input_returns_empty_list():
    """Rule G4: no jobs give an empty list."""
    assert night_signatures.group([]) == []


def test_advice_provider():
    """Rule A: the provider advice text is exact."""
    assert night_signatures.advice("provider") == (
        "the member's endpoint failed; relay or wait, nothing to fix in the work"
    )


def test_advice_stopped():
    """Rule A: the stopped advice text is exact."""
    assert night_signatures.advice("stopped") == (
        "stopped by a person; nothing to fix"
    )


def test_advice_harness():
    """Rule A: the harness advice text is exact."""
    assert night_signatures.advice("harness") == (
        "our harness raised an error; read the traceback in the job"
    )


def test_advice_ceiling():
    """Rule A: the ceiling advice text is exact."""
    assert night_signatures.advice("ceiling") == (
        "our budget ended the job; check the member's ceilings before blaming them"
    )


def test_advice_mechanical():
    """Rule A: the mechanical advice text is exact."""
    assert night_signatures.advice("mechanical") == (
        "a format miss a program can repair; candidate for a zero-token fixer"
    )


def test_advice_gate():
    """Rule A: the gate advice text is exact."""
    assert night_signatures.advice("gate") == (
        "a gate refused the content; needs a reader (model error or contract wording)"
    )


def test_advice_stuck():
    """Rule A: the stuck advice text is exact."""
    assert night_signatures.advice("stuck") == (
        "the member looped without progress; rescope the task or relay it sooner"
    )


def test_advice_unknown():
    """Rule A: the unknown advice text is exact."""
    assert night_signatures.advice("unknown") == (
        "failed with no recorded reason; read the job"
    )


def test_advice_unknown_for_any_other_value():
    """Rule A: a category outside the table gets the unknown text."""
    assert night_signatures.advice("banana") == (
        "failed with no recorded reason; read the job"
    )
