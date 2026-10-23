//! Windows command guard: checks a PowerShell command before it runs.

/// What the guard decided.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    /// Run the command as given.
    Allow,
    /// Run `Verdict::command` instead: a fixed-up copy of the input.
    Rewrite,
    /// Do not run it; `Verdict::notes` says why and what to use instead.
    Block,
}

/// The guard's answer for one command.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Verdict {
    /// Allow, Rewrite or Block.
    pub action: Action,
    /// The rewritten command for Rewrite; otherwise the input, unchanged.
    pub command: String,
    /// One line per finding, in the order found; empty for Allow.
    pub notes: Vec<String>,
}

const SUGGESTIONS: [(&str, &str); 24] = [
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

const FLAG_REWRITES: [(&str, &str, &str); 8] = [
    ("ls", "-la", "Get-ChildItem -Force"),
    ("ls", "-al", "Get-ChildItem -Force"),
    ("ls", "-a", "Get-ChildItem -Force"),
    ("ls", "-l", "Get-ChildItem"),
    ("rm", "-rf", "Remove-Item -Recurse -Force"),
    ("rm", "-fr", "Remove-Item -Recurse -Force"),
    ("rm", "-r", "Remove-Item -Recurse"),
    ("mkdir", "-p", "New-Item -ItemType Directory -Force"),
];

const REDIRECTS: [(&str, &str); 4] = [
    ("2>/dev/null", "2>$null"),
    ("&>/dev/null", "*>$null"),
    ("> /dev/null", "> $null"),
    (">/dev/null", ">$null"),
];

const FIND_NOTE: &str =
    "find: this is Windows find.exe (text search) - use Get-ChildItem -Recurse -Filter <pattern>";

#[derive(Clone, Copy, PartialEq, Eq)]
enum Quote {
    Outside,
    Single,
    Double,
    HereSingle,
    HereDouble,
}

/// The PowerShell way to do what a Unix-only command does, or None.
pub fn suggestion(head: &str) -> Option<&'static str> {
    SUGGESTIONS.iter().find(|(h, _)| *h == head).map(|(_, s)| *s)
}

/// Cut a command into pieces: segment, separator, segment, ... (always an odd count).
pub fn split(command: &str) -> Vec<String> {
    let chars: Vec<char> = command.chars().collect();
    let mut pieces = Vec::new();
    let mut current = String::new();
    let mut state = Quote::Outside;
    // split rule 3b (2026-10-23): a `;` inside @{...}, {...} or $(...) is not a separator
    let mut depth: usize = 0;
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        let next = chars.get(i + 1).copied();
        match state {
            Quote::Outside => {
                if c == '`' {
                    // split rule 1: the escaped character is never a separator
                    current.push(c);
                    if let Some(n) = next {
                        current.push(n);
                        i += 1;
                    }
                } else if c == '@' && (next == Some('\'') || next == Some('"')) {
                    current.push(c);
                    current.push(next.unwrap_or(c));
                    state = if next == Some('\'') { Quote::HereSingle } else { Quote::HereDouble };
                    i += 1;
                } else if c == '\'' {
                    current.push(c);
                    state = Quote::Single;
                } else if c == '"' {
                    current.push(c);
                    state = Quote::Double;
                } else if c == '{' || c == '(' {
                    current.push(c);
                    depth += 1;
                } else if c == '}' || c == ')' {
                    current.push(c);
                    depth = depth.saturating_sub(1);
                } else if depth > 0 {
                    current.push(c);
                } else if (c == '&' || c == '|') && next == Some(c) {
                    pieces.push(std::mem::take(&mut current));
                    pieces.push(format!("{c}{c}"));
                    i += 1;
                } else if c == '|' || c == ';' || c == '\n' {
                    pieces.push(std::mem::take(&mut current));
                    pieces.push(c.to_string());
                } else {
                    current.push(c);
                }
            }
            Quote::Single => {
                current.push(c);
                if c == '\'' {
                    state = Quote::Outside;
                }
            }
            Quote::Double => {
                current.push(c);
                if c == '`' {
                    if let Some(n) = next {
                        current.push(n);
                        i += 1;
                    }
                } else if c == '"' {
                    state = Quote::Outside;
                }
            }
            Quote::HereSingle | Quote::HereDouble => {
                current.push(c);
                let q = if state == Quote::HereSingle { '\'' } else { '"' };
                if c == '\n' && next == Some(q) && chars.get(i + 2) == Some(&'@') {
                    current.push(q);
                    current.push('@');
                    i += 2;
                    state = Quote::Outside;
                }
            }
        }
        i += 1;
    }
    pieces.push(current);
    pieces
}

/// Replace the first `k` words of `segment`, keeping what surrounds them.
pub fn replace_words(segment: &str, k: usize, with: &str) -> String {
    let mut words: Vec<(usize, usize)> = Vec::new();
    let mut start: Option<usize> = None;
    for (i, c) in segment.char_indices() {
        if c.is_whitespace() {
            if let Some(s) = start.take() {
                words.push((s, i));
            }
        } else if start.is_none() {
            start = Some(i);
        }
    }
    if let Some(s) = start {
        words.push((s, segment.len()));
    }
    if k == 0 || words.len() < k {
        return segment.to_string();
    }
    format!("{}{}{}", &segment[..words[0].0], with, &segment[words[k - 1].1..])
}

/// The guard's verdict on one PowerShell command.
pub fn check(command: &str) -> Verdict {
    let unchanged = |action: Action, notes: Vec<String>| Verdict {
        action,
        command: command.to_string(),
        notes,
    };
    if command.split_whitespace().next().is_none() {
        return unchanged(Action::Allow, Vec::new());
    }
    let pieces = split(command);
    let blocks: Vec<String> = pieces.iter().step_by(2).filter_map(|s| block_note(s)).collect();
    if !blocks.is_empty() {
        return unchanged(Action::Block, blocks);
    }
    let mut notes = Vec::new();
    let mut out = String::new();
    for (i, piece) in pieces.iter().enumerate() {
        if i % 2 == 1 {
            out.push_str(piece);
        } else {
            let piped = i > 0 && pieces[i - 1] == "|";
            out.push_str(&rewrite_segment(piece, piped, &mut notes));
        }
    }
    if notes.is_empty() {
        unchanged(Action::Allow, Vec::new())
    } else {
        Verdict { action: Action::Rewrite, command: out, notes }
    }
}

fn assignment(word: &str) -> Option<(&str, &str)> {
    let (name, value) = word.split_once('=')?;
    let first = name.chars().next()?;
    let valid = (first.is_ascii_alphabetic() || first == '_')
        && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_');
    if valid {
        Some((name, value))
    } else {
        None
    }
}

fn flag_rewrite(head: &str, flag: &str) -> Option<&'static str> {
    FLAG_REWRITES.iter().find(|(h, f, _)| *h == head && *f == flag).map(|(_, _, r)| *r)
}

fn block_note(segment: &str) -> Option<String> {
    let words: Vec<&str> = segment.split_whitespace().collect();
    let first = *words.first()?;
    let head = first.to_ascii_lowercase();
    // check rule 2a, then 2b, 2c, 2d: the first match is the segment's one note
    if let Some((name, value)) = assignment(first) {
        return Some(format!(
            "{name}={value} prefix: not PowerShell - use $env:{name} = '{value}'; then the command"
        ));
    }
    if let Some(s) = suggestion(&head) {
        return Some(format!("{head}: not a PowerShell command - use {s}"));
    }
    let second = words.get(1).copied()?;
    if head == "find"
        && (second == "." || second == ".." || second.starts_with('-') || second.starts_with('~'))
    {
        return Some(FIND_NOTE.to_string());
    }
    let replacement = flag_rewrite(&head, second)?;
    let arguments = words.iter().skip(2).filter(|w| !w.contains('>')).count();
    if arguments > 1 {
        return Some(format!(
            "{head} {second} with several paths - use {replacement} -Path <a>, <b>"
        ));
    }
    None
}

fn rewrite_segment(segment: &str, piped: bool, notes: &mut Vec<String>) -> String {
    let words: Vec<&str> = segment.split_whitespace().collect();
    let mut text = segment.to_string();
    if let (Some(first), Some(second)) = (words.first(), words.get(1)) {
        let head = first.to_ascii_lowercase();
        if let Some(replacement) = flag_rewrite(&head, second) {
            notes.push(format!("{first} {second} -> {replacement}"));
            text = replace_words(segment, 2, replacement);
        } else if head == "where" && !piped && !second.starts_with('{') && !second.starts_with('-')
        {
            notes.push(format!("{first} -> where.exe"));
            text = replace_words(segment, 1, "where.exe");
        }
    }
    for (from, to) in REDIRECTS {
        if text.contains(from) {
            text = text.replace(from, to);
            notes.push(format!("{from} -> {to}"));
        }
    }
    text
}
