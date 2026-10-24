# Contract: sse.rs - server-sent events

Module `src/sse.rs` of the crate `the_crew`. The Crew's chat window follows a PA's work
through an HTTP event stream (`text/event-stream`): text arrives in chunks of any size, and
the window needs whole events. `Parser::feed` takes each chunk as bytes and returns the
events it completed. Pure code: no I/O, no threads.

## API (exact)

```rust
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
pub struct Parser { /* your private fields */ }

impl Parser {
    /// A parser at the start of a stream.
    pub fn new() -> Self
    /// The last valid `retry:` value, in milliseconds.
    pub fn retry(&self) -> Option<u64>
    /// Take the next chunk; return every event it completed, in order.
    pub fn feed(&mut self, chunk: &[u8]) -> Vec<Event>
}
```

Imports allowed: none needed. `std::mem::take` is allowed. `Parser::new()` must behave
exactly like `Parser::default()`.

## Rule L - lines

1. Keep a byte buffer. `feed` appends the chunk to it, then takes out every complete line:
   the bytes up to a `\n` (the `\n` is removed, and one `\r` just before it too). Bytes after
   the last `\n` stay in the buffer for the next `feed`. Work in BYTES until a line is
   complete, so a chunk that ends inside a UTF-8 character or between `\r` and `\n` is fine.
2. Turn each complete line into a String with `String::from_utf8_lossy` (bad bytes become
   U+FFFD; never panic).
3. The very first line of the stream only: if it starts with U+FEFF (the byte-order mark,
   bytes EF BB BF), remove it. A U+FEFF anywhere later is ordinary text.
4. A line with no `\n` yet is never processed, so an unfinished event is never dispatched.

## Rule F - each line, in order

- **Empty line:** DISPATCH (below).
- **Starts with `:`** - a comment: ignore it.
- **Otherwise:** FIELD and VALUE. If the line contains `:`, FIELD is what comes before the
  FIRST `:` and VALUE is what comes after it, with ONE leading space removed if there is one
  (`data:  x` gives value ` x`). With no `:`, FIELD is the whole line and VALUE is `""`.
  Field names are case-sensitive.
  - `data`: add VALUE to the event's data lines (an empty VALUE is still a line).
  - `event`: the event's name becomes VALUE.
  - `id`: if VALUE contains no NUL (`\0`) character, the stream's last id becomes
    `Some(VALUE)` (an empty VALUE gives `Some("")`); with a NUL, ignore the line.
  - `retry`: if VALUE is one or more ASCII digits and nothing else, and fits a u64, the
    parser's retry becomes that number; anything else is ignored.
  - any other field: ignore.

**DISPATCH:** if there are no data lines, dispatch nothing, but still clear the event name.
Otherwise produce `Event { event, data, id }` where `event` is the name (or `"message"` if
it is empty), `data` is the data lines joined with `"\n"`, and `id` is a clone of the last id
(which is NOT cleared - it carries over). Then clear the data lines and the event name.

## Worked examples (`\n` = newline)

| fed | events |
|---|---|
| `data: a\n\n` | `{message, "a", None}` |
| `data: a\n` then `\n` | nothing, then `{message, "a", None}` |
| `data: one\ndata: two\ndata:\ndata: four\n\n` | `{message, "one\ntwo\n\nfour", None}` |
| `event: ping\ndata: x\n\ndata: y\n\n` | `{ping, "x", None}`, `{message, "y", None}` |
| `id: 7\ndata: a\n\ndata: b\n\n` | `{message, "a", Some("7")}`, `{message, "b", Some("7")}` |
| `data\ndata\n\n` | `{message, "\n", None}` (two empty data lines) |
| `event: lonely\n\ndata: x\n\n` | `{message, "x", None}` |
| `: keepalive\ndata: a\n\n` | `{message, "a", None}` |
| `Data: no\ndata: yes\n\n` | `{message, "yes", None}` |
| `event: e\r\ndata: a\r\n\r\n` | `{e, "a", None}` |
| `data: a\r` then `\n\r` then `\n` | nothing, nothing, then `{message, "a", None}` |
| `data: a\n\ndata: half` then ` more\n` then `\n` | `{message, "a", None}`, nothing, then `{message, "half more", None}` |
| `retry: 3000\n` then `retry: 12a\n` | nothing; `retry()` is `Some(3000)` both times |
| `retry: 10\n\nid: 4\n\n` | nothing (no data lines) |
