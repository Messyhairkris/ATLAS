use the_crew::sse::{Event, Parser};

fn ev(event: &str, data: &str, id: Option<&str>) -> Event {
    Event { event: event.to_string(), data: data.to_string(), id: id.map(str::to_string) }
}

fn all(input: &str) -> Vec<Event> {
    Parser::new().feed(input.as_bytes())
}

#[test]
fn one_data_line() {
    assert_eq!(all("data: {\"type\":\"session.idle\"}\n\n"), vec![ev("message", "{\"type\":\"session.idle\"}", None)]);
}

#[test]
fn nothing_until_the_blank_line() {
    let mut p = Parser::new();
    assert_eq!(p.feed(b"data: a\n"), vec![]);
    assert_eq!(p.feed(b"\n"), vec![ev("message", "a", None)]);
}

#[test]
fn several_data_lines_join_with_newlines() {
    assert_eq!(all("data: one\ndata: two\ndata:\ndata: four\n\n"), vec![ev("message", "one\ntwo\n\nfour", None)]);
}

#[test]
fn event_field_names_the_event_then_resets() {
    assert_eq!(
        all("event: ping\ndata: x\n\ndata: y\n\n"),
        vec![ev("ping", "x", None), ev("message", "y", None)]
    );
}

#[test]
fn id_carries_over_to_later_events() {
    assert_eq!(
        all("id: 7\ndata: a\n\ndata: b\n\nid: 9\ndata: c\n\n"),
        vec![ev("message", "a", Some("7")), ev("message", "b", Some("7")), ev("message", "c", Some("9"))]
    );
}

#[test]
fn id_with_nul_is_ignored_and_empty_id_is_kept() {
    assert_eq!(
        all("id: 1\ndata: a\n\nid: bad\0id\ndata: b\n\nid\ndata: c\n\n"),
        vec![ev("message", "a", Some("1")), ev("message", "b", Some("1")), ev("message", "c", Some(""))]
    );
}

#[test]
fn comments_are_ignored() {
    assert_eq!(all(": keepalive\n:\ndata: a\n: between\n\n"), vec![ev("message", "a", None)]);
}

#[test]
fn only_one_space_after_the_colon_is_removed() {
    assert_eq!(all("data:  two spaces\n\ndata:none\n\n"), vec![ev("message", " two spaces", None), ev("message", "none", None)]);
}

#[test]
fn a_field_with_no_colon_has_an_empty_value() {
    assert_eq!(all("data\ndata\n\n"), vec![ev("message", "\n", None)]);
}

#[test]
fn colon_inside_the_value_is_kept() {
    assert_eq!(all("data: {\"a\":\"b: c\"}\n\n"), vec![ev("message", "{\"a\":\"b: c\"}", None)]);
}

#[test]
fn blank_line_without_data_dispatches_nothing_but_resets_the_event_name() {
    assert_eq!(all("event: lonely\n\ndata: x\n\n"), vec![ev("message", "x", None)]);
}

#[test]
fn unknown_fields_are_ignored() {
    assert_eq!(all("foo: bar\nData: no\ndata: yes\n\n"), vec![ev("message", "yes", None)]);
}

#[test]
fn crlf_line_endings() {
    assert_eq!(all("event: e\r\ndata: a\r\n\r\n"), vec![ev("e", "a", None)]);
}

#[test]
fn chunks_split_anywhere() {
    let stream = "event: message.part.delta\ndata: {\"delta\":\"h\u{e9}llo\"}\n\n";
    let bytes = stream.as_bytes();
    for size in 1..=7 {
        let mut p = Parser::new();
        let mut got = Vec::new();
        for chunk in bytes.chunks(size) {
            got.extend(p.feed(chunk));
        }
        assert_eq!(got, vec![ev("message.part.delta", "{\"delta\":\"h\u{e9}llo\"}", None)], "chunk size {size}");
    }
}

#[test]
fn crlf_split_between_chunks() {
    let mut p = Parser::new();
    assert_eq!(p.feed(b"data: a\r"), vec![]);
    assert_eq!(p.feed(b"\n\r"), vec![]);
    assert_eq!(p.feed(b"\n"), vec![ev("message", "a", None)]);
}

#[test]
fn many_events_in_one_chunk() {
    let got = all("data: 1\n\ndata: 2\n\ndata: 3\n\n");
    assert_eq!(got.iter().map(|e| e.data.as_str()).collect::<Vec<_>>(), vec!["1", "2", "3"]);
}

#[test]
fn an_unfinished_event_is_not_dispatched() {
    let mut p = Parser::new();
    assert_eq!(p.feed(b"data: a\n\ndata: half"), vec![ev("message", "a", None)]);
    assert_eq!(p.feed(b" more\n"), vec![]);
    assert_eq!(p.feed(b"\n"), vec![ev("message", "half more", None)]);
}

#[test]
fn byte_order_mark_only_at_the_start() {
    assert_eq!(all("\u{feff}data: a\n\n"), vec![ev("message", "a", None)]);
    assert_eq!(all("data: a\n\n\u{feff}data: b\n\n"), vec![ev("message", "a", None)]);
}

#[test]
fn byte_order_mark_split_across_chunks() {
    let mut p = Parser::new();
    assert_eq!(p.feed(&[0xEF, 0xBB]), vec![]);
    assert_eq!(p.feed(&[0xBF]), vec![]);
    assert_eq!(p.feed(b"data: a\n\n"), vec![ev("message", "a", None)]);
}

#[test]
fn invalid_utf8_is_replaced_not_fatal() {
    let mut p = Parser::new();
    assert_eq!(p.feed(b"data: a\xffb\n\n"), vec![ev("message", "a\u{fffd}b", None)]);
}

#[test]
fn retry_is_recorded_when_all_digits() {
    let mut p = Parser::new();
    assert_eq!(p.retry(), None);
    p.feed(b"retry: 3000\n");
    assert_eq!(p.retry(), Some(3000));
    p.feed(b"retry: 12a\nretry:\nretry: -5\n");
    assert_eq!(p.retry(), Some(3000), "invalid retry values change nothing");
    p.feed(b"retry: 99999999999999999999999\n");
    assert_eq!(p.retry(), Some(3000), "an overflowing value changes nothing");
}

#[test]
fn retry_and_id_alone_dispatch_nothing() {
    assert_eq!(all("retry: 10\n\nid: 4\n\n"), vec![]);
}

#[test]
fn default_parser_is_new() {
    let mut p = Parser::default();
    assert_eq!(p.feed(b"data: a\n\n"), vec![ev("message", "a", None)]);
}
