//! A small Markdown reader for The Crew's report views: blocks and inline spans, no HTML.

/// A run of text inside a block.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Span {
    /// Plain text.
    Text(String),
    /// `**text**` or `__text__`.
    Bold(String),
    /// `*text*` or `_text_`.
    Italic(String),
    /// `` `text` ``.
    Code(String),
    /// `[text](target)`, `[[target|text]]`, or a bare `https://` address.
    Link { text: String, target: String },
}

/// One block of a document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Block {
    /// `# ` to `###### `.
    Heading { level: u8, spans: Vec<Span> },
    /// Lines of text, joined.
    Paragraph(Vec<Span>),
    /// `- `, `* ` or `+ ` item; depth = indent / 2.
    Bullet { depth: u8, spans: Vec<Span> },
    /// `1. ` or `1) ` item; depth = indent / 2.
    Numbered { depth: u8, number: u32, spans: Vec<Span> },
    /// `> ` lines, joined.
    Quote(Vec<Span>),
    /// A fenced block, or front matter (lang "yaml").
    Code { lang: String, text: String },
    /// A pipe table: header cells, then rows padded or cut to the header's width.
    Table { header: Vec<Vec<Span>>, rows: Vec<Vec<Vec<Span>>> },
    /// `---`, `***` or `___`.
    Rule,
}

fn flush(buf: &mut String, out: &mut Vec<Span>) {
    if !buf.is_empty() {
        out.push(Span::Text(std::mem::take(buf)));
    }
}

fn collect(chars: &[char]) -> String {
    chars.iter().collect()
}

fn find_pair(chars: &[char], from: usize, a: char, b: char) -> Option<usize> {
    let mut j = from;
    while j + 1 < chars.len() {
        if chars[j] == a && chars[j + 1] == b {
            return Some(j);
        }
        j += 1;
    }
    None
}

fn alnum_at(chars: &[char], i: usize) -> bool {
    chars.get(i).is_some_and(|c| c.is_alphanumeric())
}

/// The spans of one block's text.
pub fn inline(text: &str) -> Vec<Span> {
    let chars: Vec<char> = text.chars().collect();
    let n = chars.len();
    let mut out = Vec::new();
    let mut buf = String::new();
    let mut i = 0;
    while i < n {
        let c = chars[i];
        let next = chars.get(i + 1).copied();
        // a. escape
        if c == '\\' && next.is_some_and(|d| d.is_ascii_punctuation()) {
            buf.push(chars[i + 1]);
            i += 2;
            continue;
        }
        // b. code span
        if c == '`' {
            let mut r = 0;
            while i + r < n && chars[i + r] == '`' {
                r += 1;
            }
            let mut k = i + r;
            let mut found = None;
            while k < n {
                if chars[k] == '`' {
                    let mut m = 0;
                    while k + m < n && chars[k + m] == '`' {
                        m += 1;
                    }
                    if m == r {
                        found = Some(k);
                        break;
                    }
                    k += m;
                } else {
                    k += 1;
                }
            }
            match found {
                Some(k) => {
                    let mut content = &chars[i + r..k];
                    if content.len() >= 2
                        && content[0] == ' '
                        && content[content.len() - 1] == ' '
                        && content.iter().any(|ch| *ch != ' ')
                    {
                        content = &content[1..content.len() - 1];
                    }
                    flush(&mut buf, &mut out);
                    out.push(Span::Code(collect(content)));
                    i = k + r;
                }
                None => {
                    for _ in 0..r {
                        buf.push('`');
                    }
                    i += r;
                }
            }
            continue;
        }
        // c. wiki link
        if c == '[' && next == Some('[') {
            if let Some(j) = find_pair(&chars, i + 2, ']', ']') {
                let content = collect(&chars[i + 2..j]);
                if !content.contains('[') {
                    let (target, label) = match content.split_once('|') {
                        Some((t, l)) => (t.trim().to_string(), l.trim().to_string()),
                        None => (content.trim().to_string(), content.trim().to_string()),
                    };
                    if !target.is_empty() {
                        let label = if label.is_empty() { target.clone() } else { label };
                        flush(&mut buf, &mut out);
                        out.push(Span::Link { text: label, target });
                        i = j + 2;
                        continue;
                    }
                }
            }
            buf.push('[');
            i += 1;
            continue;
        }
        // d. link
        if c == '[' {
            let close = (i + 1..n).find(|&j| chars[j] == ']');
            if let Some(j) = close {
                let label = &chars[i + 1..j];
                if !label.contains(&'[') && chars.get(j + 1) == Some(&'(') {
                    if let Some(k) = (j + 2..n).find(|&k| chars[k] == ')') {
                        let target = collect(&chars[j + 2..k]).trim().to_string();
                        if !target.is_empty() {
                            let mut text = collect(label);
                            let tc: Vec<char> = text.chars().collect();
                            if tc.len() >= 2 && tc[0] == '`' && tc[tc.len() - 1] == '`' {
                                text = collect(&tc[1..tc.len() - 1]);
                            }
                            if text.is_empty() {
                                text = target.clone();
                            }
                            flush(&mut buf, &mut out);
                            out.push(Span::Link { text, target });
                            i = k + 1;
                            continue;
                        }
                    }
                }
            }
            buf.push('[');
            i += 1;
            continue;
        }
        // e. bold
        if (c == '*' || c == '_') && next == Some(c) {
            let left_ok = c == '*' || !(i > 0 && alnum_at(&chars, i - 1));
            if left_ok {
                if let Some(j) = find_pair(&chars, i + 2, c, c) {
                    let content = collect(&chars[i + 2..j]);
                    let right_ok = c == '*' || !alnum_at(&chars, j + 2);
                    if !content.trim().is_empty() && right_ok {
                        flush(&mut buf, &mut out);
                        out.push(Span::Bold(content));
                        i = j + 2;
                        continue;
                    }
                }
            }
            buf.push(c);
            buf.push(c);
            i += 2;
            continue;
        }
        // f. italic
        if c == '*' || c == '_' {
            let left_ok = next.is_some_and(|d| !d.is_whitespace())
                && (c == '*' || !(i > 0 && alnum_at(&chars, i - 1)));
            if left_ok {
                let close = (i + 2..n).find(|&j| {
                    chars[j] == c
                        && !chars[j - 1].is_whitespace()
                        && (c == '*' || !alnum_at(&chars, j + 1))
                });
                if let Some(j) = close {
                    flush(&mut buf, &mut out);
                    out.push(Span::Italic(collect(&chars[i + 1..j])));
                    i = j + 1;
                    continue;
                }
            }
            buf.push(c);
            i += 1;
            continue;
        }
        // g. bare address
        if c == 'h' && (i == 0 || chars[i - 1].is_whitespace() || "(<\"'".contains(chars[i - 1])) {
            let rest = collect(&chars[i..]);
            let prefix = if rest.starts_with("https://") {
                8
            } else if rest.starts_with("http://") {
                7
            } else {
                0
            };
            if prefix > 0 {
                let mut end = i;
                while end < n && !chars[end].is_whitespace() && !"<>\"'`".contains(chars[end]) {
                    end += 1;
                }
                while end > i && ".,;:!?)".contains(chars[end - 1]) {
                    end -= 1;
                }
                if end - i > prefix {
                    let url = collect(&chars[i..end]);
                    flush(&mut buf, &mut out);
                    out.push(Span::Link { text: url.clone(), target: url });
                    i = end;
                    continue;
                }
            }
        }
        buf.push(c);
        i += 1;
    }
    flush(&mut buf, &mut out);
    out
}

/// The cells of one table row, trimmed, with `\|` read as a literal `|`.
pub fn split_row(line: &str) -> Vec<String> {
    let t = line.trim();
    let t = t.strip_prefix('|').unwrap_or(t);
    let t = if t.ends_with('|') && !t.ends_with("\\|") { &t[..t.len() - 1] } else { t };
    let mut cells = Vec::new();
    let mut cell = String::new();
    let mut chars = t.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\\' && chars.peek() == Some(&'|') {
            cell.push('|');
            chars.next();
        } else if c == '|' {
            cells.push(cell.trim().to_string());
            cell.clear();
        } else {
            cell.push(c);
        }
    }
    cells.push(cell.trim().to_string());
    cells
}

enum Open {
    None,
    Para(String),
    Bullet(u8, String),
    Numbered(u8, u32, String),
    Quote(String),
}

fn join(a: &mut String, b: &str) {
    if b.is_empty() {
        return;
    }
    if !a.is_empty() {
        a.push(' ');
    }
    a.push_str(b);
}

fn close(open: &mut Open, out: &mut Vec<Block>) {
    match std::mem::replace(open, Open::None) {
        Open::None => {}
        Open::Para(t) => out.push(Block::Paragraph(inline(&t))),
        Open::Bullet(d, t) => out.push(Block::Bullet { depth: d, spans: inline(&t) }),
        Open::Numbered(d, n, t) => out.push(Block::Numbered { depth: d, number: n, spans: inline(&t) }),
        Open::Quote(t) => out.push(Block::Quote(inline(&t))),
    }
}

fn indent(line: &str) -> (u8, &str) {
    let mut width = 0usize;
    let mut cut = line.len();
    for (at, c) in line.char_indices() {
        match c {
            ' ' => width += 1,
            '\t' => width += 4,
            _ => {
                cut = at;
                break;
            }
        }
    }
    ((width / 2).min(255) as u8, &line[cut..])
}

fn is_separator(line: &str) -> bool {
    let t = line.trim();
    t.starts_with('|') && t.contains('-') && t.chars().all(|c| matches!(c, '|' | '-' | ':' | ' '))
}

fn is_rule(line: &str) -> bool {
    let t = line.trim();
    t.chars().count() >= 3 && ['-', '*', '_'].iter().any(|m| t.chars().all(|c| c == *m))
}

fn heading(line: &str) -> Option<(u8, &str)> {
    let n = line.chars().take_while(|c| *c == '#').count();
    if !(1..=6).contains(&n) {
        return None;
    }
    let rest = &line[n..];
    if rest.is_empty() || rest.starts_with(' ') {
        Some((n as u8, rest.trim()))
    } else {
        None
    }
}

fn numbered(rest: &str) -> Option<(u32, &str)> {
    let digits = rest.chars().take_while(|c| c.is_ascii_digit()).count();
    if !(1..=9).contains(&digits) {
        return None;
    }
    let after = &rest[digits..];
    if after.starts_with(". ") || after.starts_with(") ") {
        Some((rest[..digits].parse().ok()?, after[2..].trim()))
    } else {
        None
    }
}

/// The blocks of a Markdown document, in order.
pub fn parse(markdown: &str) -> Vec<Block> {
    let lines: Vec<&str> = markdown.lines().collect();
    let mut out = Vec::new();
    let mut open = Open::None;
    let mut i = 0;
    if lines.first() == Some(&"---") {
        if let Some(j) = (1..lines.len()).find(|&j| lines[j] == "---") {
            out.push(Block::Code { lang: "yaml".to_string(), text: lines[1..j].join("\n") });
            i = j + 1;
        }
    }
    while i < lines.len() {
        let line = lines[i];
        let trimmed = line.trim();
        if let Some(after) = line.trim_start().strip_prefix("```") {
            close(&mut open, &mut out);
            let lang = after.trim().to_string();
            let mut body = Vec::new();
            i += 1;
            while i < lines.len() {
                let t = lines[i].trim();
                if t.len() >= 3 && t.chars().all(|c| c == '`') {
                    break;
                }
                body.push(lines[i]);
                i += 1;
            }
            out.push(Block::Code { lang, text: body.join("\n") });
            i += 1;
            continue;
        }
        if trimmed.is_empty() {
            close(&mut open, &mut out);
            i += 1;
            continue;
        }
        if let Some((level, text)) = heading(line) {
            close(&mut open, &mut out);
            out.push(Block::Heading { level, spans: inline(text) });
            i += 1;
            continue;
        }
        if is_rule(line) {
            close(&mut open, &mut out);
            out.push(Block::Rule);
            i += 1;
            continue;
        }
        if trimmed.starts_with('|') && i + 1 < lines.len() && is_separator(lines[i + 1]) {
            close(&mut open, &mut out);
            let header: Vec<Vec<Span>> = split_row(line).iter().map(|c| inline(c)).collect();
            let width = header.len();
            let mut rows = Vec::new();
            i += 2;
            while i < lines.len() && lines[i].trim().starts_with('|') {
                let mut row: Vec<Vec<Span>> = split_row(lines[i]).iter().map(|c| inline(c)).collect();
                row.resize(width, Vec::new());
                rows.push(row);
                i += 1;
            }
            out.push(Block::Table { header, rows });
            continue;
        }
        let (depth, rest) = indent(line);
        if rest.starts_with("- ") || rest.starts_with("* ") || rest.starts_with("+ ") {
            close(&mut open, &mut out);
            open = Open::Bullet(depth, rest[2..].trim().to_string());
            i += 1;
            continue;
        }
        if let Some((number, text)) = numbered(rest) {
            if number == 1 || !matches!(open, Open::Para(_)) {
                close(&mut open, &mut out);
                open = Open::Numbered(depth, number, text.to_string());
                i += 1;
                continue;
            }
        }
        if let Some(q) = rest.strip_prefix('>') {
            let q = q.strip_prefix(' ').unwrap_or(q).trim();
            if let Open::Quote(t) = &mut open {
                join(t, q);
            } else {
                close(&mut open, &mut out);
                open = Open::Quote(q.to_string());
            }
            i += 1;
            continue;
        }
        match &mut open {
            Open::Para(t) | Open::Bullet(_, t) | Open::Numbered(_, _, t) | Open::Quote(t) => join(t, trimmed),
            Open::None => open = Open::Para(trimmed.to_string()),
        }
        i += 1;
    }
    close(&mut open, &mut out);
    out
}
