use the_crew::diffview::{classify, files, parse_hunk_header, stats, Kind, Line};

fn l(kind: Kind, old: Option<u32>, new: Option<u32>, text: &str) -> Line {
    Line { kind, old, new, text: text.to_string() }
}

fn kinds(lines: &[Line]) -> Vec<Kind> {
    lines.iter().map(|x| x.kind).collect()
}

const GIT: &str = "diff --git a/src/a.rs b/src/a.rs
index 1111111..2222222 100644
--- a/src/a.rs
+++ b/src/a.rs
@@ -1,3 +1,4 @@ fn main() {
 one
-two
+TWO
+three
 four
";

// ---- parse_hunk_header ------------------------------------------------------

#[test]
fn hunk_header_full() {
    assert_eq!(parse_hunk_header("@@ -1,3 +1,4 @@"), Some((1, 3, 1, 4)));
}

#[test]
fn hunk_header_counts_default_to_one() {
    assert_eq!(parse_hunk_header("@@ -5 +5,2 @@ fn main() {"), Some((5, 1, 5, 2)));
    assert_eq!(parse_hunk_header("@@ -7 +9 @@"), Some((7, 1, 9, 1)));
}

#[test]
fn hunk_header_new_file() {
    assert_eq!(parse_hunk_header("@@ -0,0 +1,12 @@"), Some((0, 0, 1, 12)));
}

#[test]
fn hunk_header_text_after_is_ignored() {
    assert_eq!(parse_hunk_header("@@ -10,2 +10,3 @@    pub fn x() -> u32 {"), Some((10, 2, 10, 3)));
}

#[test]
fn hunk_header_rejects_malformed() {
    for bad in [
        "@@ -1,3 +1,4@@",
        "@@ -a +1 @@",
        "@@@ -1 +1 -1 @@@",
        "@@ -1, +1 @@",
        "@@ -1 +1",
        "@@ 1 +1 @@",
        "@@ -1 -1 @@",
        " @@ -1 +1 @@",
        "@@ -99999999999 +1 @@",
        "",
    ] {
        assert_eq!(parse_hunk_header(bad), None, "{bad:?}");
    }
}

// ---- classify ---------------------------------------------------------------

#[test]
fn git_diff_whole() {
    assert_eq!(
        classify(GIT),
        vec![
            l(Kind::FileHeader, None, None, "diff --git a/src/a.rs b/src/a.rs"),
            l(Kind::FileHeader, None, None, "index 1111111..2222222 100644"),
            l(Kind::FileHeader, None, None, "--- a/src/a.rs"),
            l(Kind::FileHeader, None, None, "+++ b/src/a.rs"),
            l(Kind::Hunk, None, None, "@@ -1,3 +1,4 @@ fn main() {"),
            l(Kind::Context, Some(1), Some(1), " one"),
            l(Kind::Removed, Some(2), None, "-two"),
            l(Kind::Added, None, Some(2), "+TWO"),
            l(Kind::Added, None, Some(3), "+three"),
            l(Kind::Context, Some(3), Some(4), " four"),
        ]
    );
}

#[test]
fn crlf_endings_are_dropped() {
    let got = classify("@@ -1 +1 @@\r\n-a\r\n+b\r\n");
    assert_eq!(
        got,
        vec![
            l(Kind::Hunk, None, None, "@@ -1 +1 @@"),
            l(Kind::Removed, Some(1), None, "-a"),
            l(Kind::Added, None, Some(1), "+b"),
        ]
    );
}

#[test]
fn empty_input_gives_nothing() {
    assert_eq!(classify(""), Vec::<Line>::new());
}

#[test]
fn text_before_the_diff_is_other() {
    let text = "PROPOSED COMMIT: add x\n\nApprove to let the PA commit exactly this;\n crew/x.py | 2 +-\n";
    assert_eq!(kinds(&classify(text)), vec![Kind::Other; 4]);
}

#[test]
fn empty_line_inside_a_hunk_is_context() {
    let got = classify("@@ -1,3 +1,3 @@\n a\n\n-b\n+c\n");
    assert_eq!(
        got,
        vec![
            l(Kind::Hunk, None, None, "@@ -1,3 +1,3 @@"),
            l(Kind::Context, Some(1), Some(1), " a"),
            l(Kind::Context, Some(2), Some(2), ""),
            l(Kind::Removed, Some(3), None, "-b"),
            l(Kind::Added, None, Some(3), "+c"),
        ]
    );
}

#[test]
fn no_newline_marker_inside_and_after_a_hunk() {
    let got = classify("@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+b\n\\ No newline at end of file\n");
    assert_eq!(
        got,
        vec![
            l(Kind::Hunk, None, None, "@@ -1 +1 @@"),
            l(Kind::Removed, Some(1), None, "-a"),
            l(Kind::NoNewline, None, None, "\\ No newline at end of file"),
            l(Kind::Added, None, Some(1), "+b"),
            l(Kind::NoNewline, None, None, "\\ No newline at end of file"),
        ]
    );
}

#[test]
fn lines_after_a_finished_hunk_are_other() {
    let got = classify("@@ -1 +1 @@\n-a\n+b\n+c\n-d\nplain\n");
    assert_eq!(
        kinds(&got),
        vec![Kind::Hunk, Kind::Removed, Kind::Added, Kind::Other, Kind::Other, Kind::Other]
    );
    assert_eq!(got[3], l(Kind::Other, None, None, "+c"));
}

#[test]
fn only_old_lines_left_keeps_the_body_open() {
    let got = classify("@@ -1,2 +1 @@\n a\n-b\n-c\n");
    assert_eq!(
        got,
        vec![
            l(Kind::Hunk, None, None, "@@ -1,2 +1 @@"),
            l(Kind::Context, Some(1), Some(1), " a"),
            l(Kind::Removed, Some(2), None, "-b"),
            l(Kind::Other, None, None, "-c"),
        ]
    );
}

#[test]
fn only_new_lines_left_keeps_the_body_open() {
    let got = classify("@@ -1 +1,3 @@\n a\n+b\n+c\n+d\n");
    assert_eq!(
        kinds(&got),
        vec![Kind::Hunk, Kind::Context, Kind::Added, Kind::Added, Kind::Other]
    );
}

#[test]
fn a_foreign_line_breaks_the_hunk() {
    let got = classify("@@ -1,3 +1,3 @@\n a\nWHAT\n b\n");
    assert_eq!(
        got,
        vec![
            l(Kind::Hunk, None, None, "@@ -1,3 +1,3 @@"),
            l(Kind::Context, Some(1), Some(1), " a"),
            l(Kind::Other, None, None, "WHAT"),
            l(Kind::Other, None, None, " b"),
        ]
    );
}

#[test]
fn body_lines_that_look_like_headers() {
    let got = classify("@@ -1,2 +1,2 @@\n--- not a header\n+++ not a header\n");
    assert_eq!(
        got,
        vec![
            l(Kind::Hunk, None, None, "@@ -1,2 +1,2 @@"),
            l(Kind::Removed, Some(1), None, "--- not a header"),
            l(Kind::Added, None, Some(1), "+++ not a header"),
        ]
    );
}

#[test]
fn two_hunks_restart_the_numbers() {
    let got = classify("@@ -1 +1 @@\n x\n@@ -40,2 +41,2 @@\n y\n-z\n+Z\n");
    assert_eq!(
        got,
        vec![
            l(Kind::Hunk, None, None, "@@ -1 +1 @@"),
            l(Kind::Context, Some(1), Some(1), " x"),
            l(Kind::Hunk, None, None, "@@ -40,2 +41,2 @@"),
            l(Kind::Context, Some(40), Some(41), " y"),
            l(Kind::Removed, Some(41), None, "-z"),
            l(Kind::Added, None, Some(42), "+Z"),
        ]
    );
}

#[test]
fn a_new_hunk_header_wins_even_with_lines_left() {
    let got = classify("@@ -1,5 +1,5 @@\n a\n@@ -9 +9 @@\n-b\n");
    assert_eq!(kinds(&got), vec![Kind::Hunk, Kind::Context, Kind::Hunk, Kind::Removed]);
    assert_eq!(got[3].old, Some(9));
}

#[test]
fn header_prefixes_only_count_in_a_header() {
    let text = "index this is prose\ndiff --git a/x b/x\nnew file mode 100644\nindex 0000000..1234567\nrename from q\nBinary files a/x and b/x differ\nsimilarity index 90%\nwhatever\nold mode 100644\nnew mode 100755\ncopy from p\ncopy to r\nrename to s\ndeleted file mode 100644\ndissimilarity index 10%\n";
    let got = classify(text);
    assert_eq!(got[0].kind, Kind::Other, "outside a header 'index ' is just text");
    assert_eq!(got[1].kind, Kind::FileHeader);
    for i in 2..7 {
        assert_eq!(got[i].kind, Kind::FileHeader, "{:?}", got[i].text);
    }
    assert_eq!(got[7].kind, Kind::Other, "a stray line in a header is Other");
    for i in 8..15 {
        assert_eq!(got[i].kind, Kind::FileHeader, "a header continues after Other: {:?}", got[i].text);
    }
}

#[test]
fn header_prefix_after_a_hunk_is_other() {
    let got = classify("diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\nindex 123\n");
    assert_eq!(got[4], l(Kind::Other, None, None, "index 123"));
}

#[test]
fn plain_diff_u_without_git_header() {
    let got = classify("--- old.txt\t2026-10-23 10:00:00\n+++ new.txt\t2026-10-23 10:05:00\n@@ -2 +2 @@\n-x\n+y\n");
    assert_eq!(
        kinds(&got),
        vec![Kind::FileHeader, Kind::FileHeader, Kind::Hunk, Kind::Removed, Kind::Added]
    );
    assert_eq!(got[3].old, Some(2));
    assert_eq!(got[4].new, Some(2));
}

#[test]
fn second_file_after_a_finished_hunk() {
    let text = "--- a/one\n+++ b/one\n@@ -1 +1 @@\n-a\n+b\n--- a/two\n+++ b/two\n@@ -3 +3 @@\n-c\n+d\n";
    let got = classify(text);
    assert_eq!(
        kinds(&got),
        vec![
            Kind::FileHeader, Kind::FileHeader, Kind::Hunk, Kind::Removed, Kind::Added,
            Kind::FileHeader, Kind::FileHeader, Kind::Hunk, Kind::Removed, Kind::Added,
        ]
    );
}

#[test]
fn saturating_numbers_never_panic() {
    let got = classify("@@ -4294967295 +4294967295,2 @@\n x\n+y\n");
    assert_eq!(got[1], l(Kind::Context, Some(4294967295), Some(4294967295), " x"));
    assert_eq!(got[2], l(Kind::Added, None, Some(4294967295), "+y"));
}

#[test]
fn text_is_kept_exactly() {
    let got = classify("@@ -1 +1 @@\n-  tabs\tand  spaces  \n+\u{e9}t\u{e9} \u{2192} ok\n");
    assert_eq!(got[1].text, "-  tabs\tand  spaces  ");
    assert_eq!(got[2].text, "+\u{e9}t\u{e9} \u{2192} ok");
}

// ---- stats and files --------------------------------------------------------

#[test]
fn stats_counts_added_and_removed() {
    assert_eq!(stats(&classify(GIT)), (2, 1));
    assert_eq!(stats(&[]), (0, 0));
}

#[test]
fn stats_ignore_plus_lines_outside_hunks() {
    let got = classify("+++ b/x\n@@ -1 +1 @@\n-a\n+b\n+stray\n");
    assert_eq!(stats(&got), (1, 1));
}

#[test]
fn files_from_git_headers() {
    let text = format!("{GIT}diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-x\n+y\n");
    assert_eq!(files(&classify(&text)), vec!["src/a.rs".to_string(), "README.md".to_string()]);
}

#[test]
fn files_new_and_deleted() {
    let text = "diff --git a/new.txt b/new.txt\nnew file mode 100644\n--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+hi\ndiff --git a/old.txt b/old.txt\ndeleted file mode 100644\n--- a/old.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-bye\n";
    assert_eq!(files(&classify(text)), vec!["new.txt".to_string(), "old.txt".to_string()]);
}

#[test]
fn files_strip_timestamps_and_keep_unprefixed_paths() {
    let got = classify("--- old.txt\t2026-10-23 10:00:00\n+++ new.txt\t2026-10-23 10:05:00\n@@ -2 +2 @@\n-x\n+y\n");
    assert_eq!(files(&got), vec!["new.txt".to_string()]);
}

#[test]
fn files_ignore_body_lines() {
    let got = classify("@@ -1,2 +1,2 @@\n--- a/fake\n+++ b/fake\n");
    assert_eq!(files(&got), Vec::<String>::new());
}

#[test]
fn files_dev_null_without_an_old_header_is_skipped() {
    let got = classify("+++ /dev/null\n");
    assert_eq!(files(&got), Vec::<String>::new());
}
