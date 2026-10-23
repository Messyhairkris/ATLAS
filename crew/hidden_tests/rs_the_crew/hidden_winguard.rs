use the_crew::winguard::{check, replace_words, split, suggestion, Action, Verdict};

fn v(action: Action, command: &str, notes: &[&str]) -> Verdict {
    Verdict {
        action,
        command: command.to_string(),
        notes: notes.iter().map(|n| n.to_string()).collect(),
    }
}

fn s(parts: &[&str]) -> Vec<String> {
    parts.iter().map(|p| p.to_string()).collect()
}

const HEAD: &str =
    "head: not a PowerShell command - use Select-Object -First N (or Get-Content file -TotalCount N)";
const FIND: &str =
    "find: this is Windows find.exe (text search) - use Get-ChildItem -Recurse -Filter <pattern>";

// ---- suggestion -------------------------------------------------------------

#[test]
fn suggestion_every_row() {
    let rows: [(&str, &str); 24] = [
        ("head", "Select-Object -First N (or Get-Content file -TotalCount N)"),
        ("tail", "Select-Object -Last N (or Get-Content file -Tail N)"),
        ("grep", "Select-String -Pattern 'text'"),
        ("which", "(Get-Command name).Source"),
        ("touch", "New-Item -ItemType File (only if the file is missing)"),
        ("wc", "Measure-Object -Line"),
        ("sed", "the -replace operator"),
        ("awk", "ForEach-Object with -split"),
        ("cut", "the -split operator"),
        ("tr", "the -replace operator"),
        ("xargs", "ForEach-Object"),
        ("export", "$env:NAME = 'value'"),
        ("unset", "Remove-Item Env:NAME"),
        ("env", "Get-ChildItem Env:"),
        ("source", ". .\\script.ps1 (dot-sourcing)"),
        ("uname", "[Environment]::OSVersion"),
        ("chmod", "icacls"),
        ("chown", "icacls"),
        ("ln", "New-Item -ItemType SymbolicLink"),
        ("du", "Get-ChildItem -Recurse | Measure-Object -Property Length -Sum"),
        ("df", "Get-PSDrive -PSProvider FileSystem"),
        ("less", "Get-Content file | Out-Host -Paging"),
        ("stat", "Get-Item path | Format-List *"),
        ("wget", "Invoke-WebRequest (or curl.exe)"),
    ];
    for (head, want) in rows {
        assert_eq!(suggestion(head), Some(want), "suggestion({head:?})");
    }
}

#[test]
fn suggestion_none_for_powershell_names_and_other_case() {
    for head in ["ls", "rm", "cat", "find", "where", "git", "Grep", "HEAD", "", "heads"] {
        assert_eq!(suggestion(head), None, "suggestion({head:?})");
    }
}

// ---- split ------------------------------------------------------------------

#[test]
fn split_table_rows() {
    let rows: [(&str, &[&str]); 9] = [
        ("a | b", &["a ", "|", " b"]),
        ("a || b && c", &["a ", "||", " b ", "&&", " c"]),
        ("a;", &["a", ";", ""]),
        ("", &[""]),
        ("x 'a|b' \"c;d\" e", &["x 'a|b' \"c;d\" e"]),
        ("a`|b", &["a`|b"]),
        ("one\ntwo", &["one", "\n", "two"]),
        ("say \"a`\"|b\" | c", &["say \"a`\"|b\" ", "|", " c"]),
        ("'open | x", &["'open | x"]),
    ];
    for (input, want) in rows {
        assert_eq!(split(input), s(want), "split({input:?})");
    }
}

#[test]
fn split_single_ampersand_is_not_a_separator() {
    assert_eq!(split("& \"C:\\t.exe\" a & b"), s(&["& \"C:\\t.exe\" a & b"]));
}

#[test]
fn split_here_string_single() {
    let cmd = "git commit -m @'\nexport the data; done | x\n'@; git log";
    assert_eq!(
        split(cmd),
        s(&["git commit -m @'\nexport the data; done | x\n'@", ";", " git log"])
    );
}

#[test]
fn split_here_string_double_and_apostrophe_inside() {
    let cmd = "Write-Output @\"\ndon't | stop\n\"@ | Out-Null";
    assert_eq!(split(cmd), s(&["Write-Output @\"\ndon't | stop\n\"@ ", "|", " Out-Null"]));
}

#[test]
fn split_unterminated_here_string_keeps_the_rest() {
    assert_eq!(split("x @'\na; b"), s(&["x @'\na; b"]));
}

#[test]
fn split_consecutive_separators_give_empty_segments() {
    assert_eq!(split("a;;b"), s(&["a", ";", "", ";", "b"]));
    assert_eq!(split("|"), s(&["", "|", ""]));
}

#[test]
fn split_round_trips_and_has_odd_count() {
    let inputs = [
        "a | b || c && d; e\nf",
        "x 'q;q' \"w|w\" `;",
        "@'\n'@;z",
        "trailing `",
        "\"unterminated ; |",
        "ünïcödé | 文字; ok",
    ];
    for input in inputs {
        let parts = split(input);
        assert_eq!(parts.len() % 2, 1, "odd count for {input:?}");
        assert_eq!(parts.concat(), input, "round trip for {input:?}");
    }
}

#[test]
fn split_separators_are_exact_strings() {
    let parts = split("a&&b||c|d;e\nf");
    let seps: Vec<&str> = parts.iter().skip(1).step_by(2).map(|p| p.as_str()).collect();
    assert_eq!(seps, vec!["&&", "||", "|", ";", "\n"]);
}

// ---- split: nesting (rule 3b, added 2026-10-23 after a live false positive) --

#[test]
fn split_semicolon_inside_a_hashtable_is_not_a_separator() {
    assert_eq!(
        split("Select-Object @{n='f';e={$_.Name}} | Sort-Object"),
        s(&["Select-Object @{n='f';e={$_.Name}} ", "|", " Sort-Object"])
    );
}

#[test]
fn split_subexpression_and_script_block_hold_their_separators() {
    assert_eq!(split("$(a; b); c"), s(&["$(a; b)", ";", " c"]));
    assert_eq!(
        split("if ($x) { a | b; c }\nd"),
        s(&["if ($x) { a | b; c }", "\n", "d"])
    );
    assert_eq!(split("x { a && b || c } && y"), s(&["x { a && b || c } ", "&&", " y"]));
}

#[test]
fn split_unbalanced_closers_never_go_below_zero() {
    assert_eq!(split("a } ; b"), s(&["a } ", ";", " b"]));
    assert_eq!(split("a ) ) ; b"), s(&["a ) ) ", ";", " b"]));
}

#[test]
fn split_unclosed_brace_keeps_the_rest() {
    assert_eq!(split("x { y; z"), s(&["x { y; z"]));
}

#[test]
fn split_braces_inside_quotes_do_not_count() {
    assert_eq!(split("'{' ; b"), s(&["'{' ", ";", " b"]));
    assert_eq!(split("\"(\" | b"), s(&["\"(\" ", "|", " b"]));
    assert_eq!(split("`{ ; b"), s(&["`{ ", ";", " b"]));
}

#[test]
fn check_hashtable_with_semicolon_is_allowed() {
    // the live false positive of 2026-10-23
    let cmd = "Get-ChildItem | Select-Object @{n='file';e={$_.FullName}}, Length";
    assert_eq!(check(cmd), v(Action::Allow, cmd, &[]));
}

#[test]
fn check_inside_a_script_block_is_not_checked_but_after_it_is() {
    let cmd = "if ($x) { ls -la }";
    assert_eq!(check(cmd), v(Action::Allow, cmd, &[]));
    assert_eq!(
        check("foreach ($n in 'a','b') { $n }; ls -la"),
        v(
            Action::Rewrite,
            "foreach ($n in 'a','b') { $n }; Get-ChildItem -Force",
            &["ls -la -> Get-ChildItem -Force"]
        )
    );
}

// ---- replace_words ----------------------------------------------------------

#[test]
fn replace_words_table_rows() {
    assert_eq!(
        replace_words("  rm -rf build", 2, "Remove-Item -Recurse -Force"),
        "  Remove-Item -Recurse -Force build"
    );
    assert_eq!(replace_words(" ls -la ", 2, "Get-ChildItem -Force"), " Get-ChildItem -Force ");
    assert_eq!(replace_words("where  python", 1, "where.exe"), "where.exe  python");
    assert_eq!(replace_words("ls", 2, "x"), "ls");
}

#[test]
fn replace_words_zero_and_tabs() {
    assert_eq!(replace_words("ls -la", 0, "x"), "ls -la");
    assert_eq!(replace_words("\tls\t-la\tsrc\r", 2, "G"), "\tG\tsrc\r");
    assert_eq!(replace_words("", 1, "x"), "");
}

// ---- check: allow -----------------------------------------------------------

#[test]
fn check_allow_rows() {
    for cmd in [
        "Get-ChildItem -Force",
        "   ",
        "",
        "find /i \"error\" log.txt",
        "Get-Process | where { $_.CPU -gt 1 }",
        "where {$_}",
        "python -c \"import a; print(1)\"",
        "git commit -m @'\nexport the data\n'@",
        "echo a`|b",
        "where.exe python",
        "1X=2 cmd",
        "=x cmd",
        "ls",
        "rm file.txt",
        "where",
        "where -h",
        "$x=1",
    ] {
        assert_eq!(check(cmd), v(Action::Allow, cmd, &[]), "check({cmd:?})");
    }
}

// ---- check: block -----------------------------------------------------------

#[test]
fn check_block_unix_only_after_a_pipe() {
    let cmd = "git log --oneline | head -5";
    assert_eq!(check(cmd), v(Action::Block, cmd, &[HEAD]));
}

#[test]
fn check_block_two_segments_two_notes_in_order() {
    let cmd = "grep -r TODO src; which python";
    assert_eq!(
        check(cmd),
        v(
            Action::Block,
            cmd,
            &[
                "grep: not a PowerShell command - use Select-String -Pattern 'text'",
                "which: not a PowerShell command - use (Get-Command name).Source",
            ]
        )
    );
}

#[test]
fn check_block_assignment_prefix() {
    let cmd = "FOO=1 python run.py";
    assert_eq!(
        check(cmd),
        v(
            Action::Block,
            cmd,
            &["FOO=1 prefix: not PowerShell - use $env:FOO = '1'; then the command"]
        )
    );
    let cmd = "X_1=a=b tool";
    assert_eq!(
        check(cmd),
        v(
            Action::Block,
            cmd,
            &["X_1=a=b prefix: not PowerShell - use $env:X_1 = 'a=b'; then the command"]
        )
    );
}

#[test]
fn check_block_assignment_comes_before_suggestion() {
    let cmd = "_V= grep x";
    assert_eq!(
        check(cmd),
        v(Action::Block, cmd, &["_V= prefix: not PowerShell - use $env:_V = ''; then the command"])
    );
}

#[test]
fn check_block_find_unix_style() {
    for cmd in ["find . -name '*.rs'", "find .. -type f", "find -name x", "find ~/src"] {
        assert_eq!(check(cmd), v(Action::Block, cmd, &[FIND]), "check({cmd:?})");
    }
}

#[test]
fn check_block_several_paths() {
    let cmd = "rm -rf build dist";
    assert_eq!(
        check(cmd),
        v(
            Action::Block,
            cmd,
            &["rm -rf with several paths - use Remove-Item -Recurse -Force -Path <a>, <b>"]
        )
    );
    let cmd = "mkdir -p a b";
    assert_eq!(
        check(cmd),
        v(
            Action::Block,
            cmd,
            &["mkdir -p with several paths - use New-Item -ItemType Directory -Force -Path <a>, <b>"]
        )
    );
    let cmd = "ls -l a b c";
    assert_eq!(
        check(cmd),
        v(Action::Block, cmd, &["ls -l with several paths - use Get-ChildItem -Path <a>, <b>"])
    );
}

#[test]
fn check_block_head_is_lowercased_in_the_note() {
    let cmd = "TAIL -n 20 log.txt";
    assert_eq!(
        check(cmd),
        v(
            Action::Block,
            cmd,
            &["tail: not a PowerShell command - use Select-Object -Last N (or Get-Content file -Tail N)"]
        )
    );
}

#[test]
fn check_block_wins_over_rewrite_and_keeps_command() {
    let cmd = "ls -la | grep x";
    assert_eq!(
        check(cmd),
        v(
            Action::Block,
            cmd,
            &["grep: not a PowerShell command - use Select-String -Pattern 'text'"]
        )
    );
}

#[test]
fn check_block_quoted_separator_does_not_hide_a_real_one() {
    let cmd = "echo \"a | b\" | wc -l";
    assert_eq!(
        check(cmd),
        v(Action::Block, cmd, &["wc: not a PowerShell command - use Measure-Object -Line"])
    );
}

// ---- check: rewrite ---------------------------------------------------------

#[test]
fn check_rewrite_rows() {
    let rows: [(&str, &str, &[&str]); 9] = [
        ("ls -la", "Get-ChildItem -Force", &["ls -la -> Get-ChildItem -Force"]),
        (
            "rm -rf build 2>/dev/null",
            "Remove-Item -Recurse -Force build 2>$null",
            &["rm -rf -> Remove-Item -Recurse -Force", "2>/dev/null -> 2>$null"],
        ),
        (
            "mkdir -p out\\logs",
            "New-Item -ItemType Directory -Force out\\logs",
            &["mkdir -p -> New-Item -ItemType Directory -Force"],
        ),
        ("cd crew && ls -l", "cd crew && Get-ChildItem", &["ls -l -> Get-ChildItem"]),
        ("where python", "where.exe python", &["where -> where.exe"]),
        ("echo hi > /dev/null", "echo hi > $null", &["> /dev/null -> > $null"]),
        ("LS -la", "Get-ChildItem -Force", &["LS -la -> Get-ChildItem -Force"]),
        (
            "ls -la; rm -r tmp",
            "Get-ChildItem -Force; Remove-Item -Recurse tmp",
            &["ls -la -> Get-ChildItem -Force", "rm -r -> Remove-Item -Recurse"],
        ),
        ("cat x &>/dev/null", "cat x *>$null", &["&>/dev/null -> *>$null"]),
    ];
    for (input, want, notes) in rows {
        assert_eq!(check(input), v(Action::Rewrite, want, notes), "check({input:?})");
    }
}

#[test]
fn check_rewrite_other_flag_spellings() {
    assert_eq!(
        check("rm -fr x"),
        v(Action::Rewrite, "Remove-Item -Recurse -Force x", &["rm -fr -> Remove-Item -Recurse -Force"])
    );
    assert_eq!(
        check("ls -al src"),
        v(Action::Rewrite, "Get-ChildItem -Force src", &["ls -al -> Get-ChildItem -Force"])
    );
    assert_eq!(
        check("ls -a"),
        v(Action::Rewrite, "Get-ChildItem -Force", &["ls -a -> Get-ChildItem -Force"])
    );
}

#[test]
fn check_rewrite_flags_are_case_sensitive() {
    assert_eq!(check("rm -RF x"), v(Action::Allow, "rm -RF x", &[]));
    assert_eq!(check("ls -LA"), v(Action::Allow, "ls -LA", &[]));
}

#[test]
fn check_rewrite_where_keeps_its_case_in_the_note() {
    assert_eq!(
        check("WHERE git"),
        v(Action::Rewrite, "where.exe git", &["WHERE -> where.exe"])
    );
}

#[test]
fn check_rewrite_where_only_at_the_start_of_a_pipeline() {
    assert_eq!(
        check("cd x; where python"),
        v(Action::Rewrite, "cd x; where.exe python", &["where -> where.exe"])
    );
    assert_eq!(check("Get-Item x | where Name"), v(Action::Allow, "Get-Item x | where Name", &[]));
}

#[test]
fn check_rewrite_redirect_counts_once_per_segment_and_kind() {
    assert_eq!(
        check("a 2>/dev/null b 2>/dev/null"),
        v(Action::Rewrite, "a 2>$null b 2>$null", &["2>/dev/null -> 2>$null"])
    );
    assert_eq!(
        check("a >/dev/null; b >/dev/null"),
        v(Action::Rewrite, "a >$null; b >$null", &[">/dev/null -> >$null", ">/dev/null -> >$null"])
    );
}

#[test]
fn check_rewrite_redirect_with_space_after_two() {
    assert_eq!(
        check("Remove-Item x 2> /dev/null"),
        v(Action::Rewrite, "Remove-Item x 2> $null", &["> /dev/null -> > $null"])
    );
}

#[test]
fn check_rewrite_word_note_then_redirect_notes_in_listed_order() {
    assert_eq!(
        check("rm -r t >/dev/null 2>/dev/null"),
        v(
            Action::Rewrite,
            "Remove-Item -Recurse t >$null 2>$null",
            &["rm -r -> Remove-Item -Recurse", "2>/dev/null -> 2>$null", ">/dev/null -> >$null"]
        )
    );
}

#[test]
fn check_rewrite_keeps_separators_and_spacing() {
    assert_eq!(
        check("  ls -la  &&  echo ok\nrm -rf  out "),
        v(
            Action::Rewrite,
            "  Get-ChildItem -Force  &&  echo ok\nRemove-Item -Recurse -Force  out ",
            &["ls -la -> Get-ChildItem -Force", "rm -rf -> Remove-Item -Recurse -Force"]
        )
    );
}

#[test]
fn check_rewrite_redirect_inside_quotes_is_still_rewritten() {
    assert_eq!(
        check("echo '>/dev/null'"),
        v(Action::Rewrite, "echo '>$null'", &[">/dev/null -> >$null"])
    );
}

#[test]
fn check_argument_count_ignores_redirect_words() {
    assert_eq!(
        check("mkdir -p out 2>/dev/null"),
        v(
            Action::Rewrite,
            "New-Item -ItemType Directory -Force out 2>$null",
            &["mkdir -p -> New-Item -ItemType Directory -Force", "2>/dev/null -> 2>$null"]
        )
    );
}
