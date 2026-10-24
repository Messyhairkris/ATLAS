//! Unified diff lines, classified for display, with old and new line numbers.

/// What one line of a diff is.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    /// A file's header: `diff --git`, `index`, `---`, `+++`, mode, rename, copy, `Binary files`.
    FileHeader,
    /// A hunk header: `@@ -a,b +c,d @@`.
    Hunk,
    /// A `+` line inside a hunk.
    Added,
    /// A `-` line inside a hunk.
    Removed,
    /// A ` ` (or empty) line inside a hunk.
    Context,
    /// `\ No newline at end of file`.
    NoNewline,
    /// Anything else: commit message text, stats, a line that broke a hunk.
    Other,
}

/// One classified line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Line {
    /// What the line is.
    pub kind: Kind,
    /// Its number in the old file (Removed and Context only).
    pub old: Option<u32>,
    /// Its number in the new file (Added and Context only).
    pub new: Option<u32>,
    /// The line exactly as given, without its line ending.
    pub text: String,
}

const HEADER_PREFIXES: [&str; 12] = [
    "index ",
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "Binary files ",
];

#[derive(Clone, Copy, PartialEq, Eq)]
enum State {
    Outside,
    Header,
    Body,
}

fn number(s: &str) -> Option<(u32, &str)> {
    let end = s.find(|c: char| !c.is_ascii_digit()).unwrap_or(s.len());
    if end == 0 {
        return None;
    }
    let n = s[..end].parse::<u32>().ok()?;
    Some((n, &s[end..]))
}

fn range(s: &str) -> Option<(u32, u32, &str)> {
    let (start, rest) = number(s)?;
    if let Some(after) = rest.strip_prefix(',') {
        let (count, rest) = number(after)?;
        Some((start, count, rest))
    } else {
        Some((start, 1, rest))
    }
}

/// `(old_start, old_count, new_start, new_count)` of a hunk header, or None.
pub fn parse_hunk_header(line: &str) -> Option<(u32, u32, u32, u32)> {
    let rest = line.strip_prefix("@@ -")?;
    let (os, oc, rest) = range(rest)?;
    let rest = rest.strip_prefix(" +")?;
    let (ns, nc, rest) = range(rest)?;
    if !rest.starts_with(" @@") {
        return None;
    }
    Some((os, oc, ns, nc))
}

fn line(kind: Kind, old: Option<u32>, new: Option<u32>, text: &str) -> Line {
    Line { kind, old, new, text: text.to_string() }
}

/// Every line of `diff`, classified, in order.
pub fn classify(diff: &str) -> Vec<Line> {
    let mut out = Vec::new();
    let mut state = State::Outside;
    let (mut old_no, mut new_no) = (0u32, 0u32);
    let (mut old_left, mut new_left) = (0u32, 0u32);
    for text in diff.lines() {
        if text.starts_with("diff --git ") {
            state = State::Header;
            out.push(line(Kind::FileHeader, None, None, text));
        } else if let Some((os, oc, ns, nc)) = parse_hunk_header(text) {
            state = State::Body;
            old_no = os;
            new_no = ns;
            old_left = oc;
            new_left = nc;
            out.push(line(Kind::Hunk, None, None, text));
        } else if state == State::Body && (old_left > 0 || new_left > 0) {
            match text.chars().next() {
                Some('+') => {
                    out.push(line(Kind::Added, None, Some(new_no), text));
                    new_no = new_no.saturating_add(1);
                    new_left = new_left.saturating_sub(1);
                }
                Some('-') => {
                    out.push(line(Kind::Removed, Some(old_no), None, text));
                    old_no = old_no.saturating_add(1);
                    old_left = old_left.saturating_sub(1);
                }
                Some(' ') | None => {
                    out.push(line(Kind::Context, Some(old_no), Some(new_no), text));
                    old_no = old_no.saturating_add(1);
                    new_no = new_no.saturating_add(1);
                    old_left = old_left.saturating_sub(1);
                    new_left = new_left.saturating_sub(1);
                }
                Some('\\') => out.push(line(Kind::NoNewline, None, None, text)),
                Some(_) => {
                    state = State::Outside;
                    out.push(line(Kind::Other, None, None, text));
                }
            }
        } else if state == State::Body && text.starts_with('\\') {
            out.push(line(Kind::NoNewline, None, None, text));
        } else if text.starts_with("--- ") || text.starts_with("+++ ") {
            state = State::Header;
            out.push(line(Kind::FileHeader, None, None, text));
        } else if state == State::Header && HEADER_PREFIXES.iter().any(|p| text.starts_with(p)) {
            out.push(line(Kind::FileHeader, None, None, text));
        } else {
            if state == State::Body {
                state = State::Outside;
            }
            out.push(line(Kind::Other, None, None, text));
        }
    }
    out
}

/// `(added, removed)`: how many Added and Removed lines there are.
pub fn stats(lines: &[Line]) -> (usize, usize) {
    let added = lines.iter().filter(|l| l.kind == Kind::Added).count();
    let removed = lines.iter().filter(|l| l.kind == Kind::Removed).count();
    (added, removed)
}

fn header_path(text: &str, prefix: &str) -> String {
    let rest = &text[4..];
    let rest = rest.split('\t').next().unwrap_or("");
    rest.strip_prefix(prefix).unwrap_or(rest).to_string()
}

/// The path of each file the diff changes, in order, from its `+++` header line.
pub fn files(lines: &[Line]) -> Vec<String> {
    let mut out = Vec::new();
    let mut last_old: Option<String> = None;
    for l in lines {
        if l.kind != Kind::FileHeader {
            continue;
        }
        if l.text.starts_with("--- ") {
            last_old = Some(header_path(&l.text, "a/"));
        } else if l.text.starts_with("+++ ") {
            let raw = l.text[4..].split('\t').next().unwrap_or("");
            if raw == "/dev/null" {
                if let Some(old) = &last_old {
                    out.push(old.clone());
                }
            } else {
                out.push(header_path(&l.text, "b/"));
            }
        }
    }
    out
}
