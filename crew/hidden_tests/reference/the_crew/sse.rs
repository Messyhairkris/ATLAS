//! Server-sent events: bytes from an HTTP event stream in, complete events out.

/// One dispatched event.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Event {
    /// The `event:` field, or "message" when there was none.
    pub event: String,
    /// The `data:` lines, joined with "\n".
    pub data: String,
    /// The last `id:` seen on the stream so far (it carries over between events).
    pub id: Option<String>,
}

/// Feeds on chunks of any size, split anywhere (even inside a UTF-8 character).
#[derive(Debug, Default)]
pub struct Parser {
    pending: Vec<u8>,
    started: bool,
    data: Vec<String>,
    event: String,
    id: Option<String>,
    retry: Option<u64>,
}

impl Parser {
    /// A parser at the start of a stream.
    pub fn new() -> Self {
        Self::default()
    }

    /// The last valid `retry:` value, in milliseconds.
    pub fn retry(&self) -> Option<u64> {
        self.retry
    }

    /// Take the next chunk; return every event it completed, in order.
    pub fn feed(&mut self, chunk: &[u8]) -> Vec<Event> {
        self.pending.extend_from_slice(chunk);
        let mut out = Vec::new();
        while let Some(nl) = self.pending.iter().position(|b| *b == b'\n') {
            let mut raw: Vec<u8> = self.pending.drain(..=nl).collect();
            raw.pop();
            if raw.last() == Some(&b'\r') {
                raw.pop();
            }
            let mut line = String::from_utf8_lossy(&raw).into_owned();
            if !self.started {
                self.started = true;
                if let Some(rest) = line.strip_prefix('\u{feff}') {
                    line = rest.to_string();
                }
            }
            if let Some(event) = self.line(&line) {
                out.push(event);
            }
        }
        out
    }

    fn line(&mut self, line: &str) -> Option<Event> {
        if line.is_empty() {
            let event = std::mem::take(&mut self.event);
            if self.data.is_empty() {
                return None;
            }
            let data = std::mem::take(&mut self.data).join("\n");
            let event = if event.is_empty() { "message".to_string() } else { event };
            return Some(Event { event, data, id: self.id.clone() });
        }
        if line.starts_with(':') {
            return None;
        }
        let (field, value) = match line.find(':') {
            Some(at) => {
                let value = &line[at + 1..];
                (&line[..at], value.strip_prefix(' ').unwrap_or(value))
            }
            None => (line, ""),
        };
        match field {
            "data" => self.data.push(value.to_string()),
            "event" => self.event = value.to_string(),
            "id" => {
                if !value.contains('\0') {
                    self.id = Some(value.to_string());
                }
            }
            "retry" => {
                if !value.is_empty() && value.bytes().all(|b| b.is_ascii_digit()) {
                    if let Ok(ms) = value.parse::<u64>() {
                        self.retry = Some(ms);
                    }
                }
            }
            _ => {}
        }
        None
    }
}
