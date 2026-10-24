use the_crew::mdlite::{inline, parse, split_row, Block, Span};

fn t(s: &str) -> Span {
    Span::Text(s.to_string())
}
fn b(s: &str) -> Span {
    Span::Bold(s.to_string())
}
fn it(s: &str) -> Span {
    Span::Italic(s.to_string())
}
fn c(s: &str) -> Span {
    Span::Code(s.to_string())
}
fn link(text: &str, target: &str) -> Span {
    Span::Link { text: text.to_string(), target: target.to_string() }
}
fn p(spans: Vec<Span>) -> Block {
    Block::Paragraph(spans)
}
fn bullet(depth: u8, spans: Vec<Span>) -> Block {
    Block::Bullet { depth, spans }
}
fn cells(row: &[&str]) -> Vec<Vec<Span>> {
    row.iter().map(|x| if x.is_empty() { vec![] } else { vec![t(x)] }).collect()
}

// ---- inline -----------------------------------------------------------------

#[test]
fn inline_plain_and_empty() {
    assert_eq!(inline("just words"), vec![t("just words")]);
    assert_eq!(inline(""), Vec::<Span>::new());
}

#[test]
fn inline_code_bold_italic() {
    assert_eq!(
        inline("run `cargo test` **now**, *please*"),
        vec![t("run "), c("cargo test"), t(" "), b("now"), t(", "), it("please")]
    );
}

#[test]
fn inline_code_double_backticks_and_space_strip() {
    assert_eq!(inline("``a ` b``"), vec![c("a ` b")]);
    assert_eq!(inline("`` `x` ``"), vec![c("`x`")]);
    assert_eq!(inline("`  `"), vec![c("  ")], "all spaces: nothing stripped");
}

#[test]
fn inline_code_is_literal_inside() {
    assert_eq!(inline("`**not bold** \\* [x](y)`"), vec![c("**not bold** \\* [x](y)")]);
}

#[test]
fn inline_unclosed_backticks_are_text() {
    assert_eq!(inline("a `b and ``c` d"), vec![t("a "), c("b and ``c"), t(" d")]);
    assert_eq!(inline("one ` alone"), vec![t("one ` alone")]);
}

#[test]
fn inline_escapes() {
    assert_eq!(inline("\\*not italic\\* and \\`tick\\`"), vec![t("*not italic* and `tick`")]);
    assert_eq!(inline("C:\\Users\\Kris"), vec![t("C:\\Users\\Kris")], "a backslash before a letter stays");
}

#[test]
fn inline_snake_case_is_not_italic() {
    assert_eq!(inline("crew_status and NIGHT_REPORT.md"), vec![t("crew_status and NIGHT_REPORT.md")]);
}

#[test]
fn inline_underscore_emphasis_at_word_edges() {
    assert_eq!(inline("_quiet_ and __loud__"), vec![it("quiet"), t(" and "), b("loud")]);
    assert_eq!(inline("x__y__z"), vec![t("x__y__z")]);
    assert_eq!(inline("x__y__"), vec![t("x__y__")]);
    assert_eq!(inline("x_y_"), vec![t("x_y_")]);
    assert_eq!(inline("__a__b"), vec![t("__a__b")]);
}

#[test]
fn inline_star_bold_may_touch_a_word() {
    assert_eq!(inline("**a**b"), vec![b("a"), t("b")]);
    assert_eq!(inline("a*b*c"), vec![t("a"), it("b"), t("c")]);
}

#[test]
fn inline_star_needs_a_non_space_neighbour() {
    assert_eq!(inline("2 * 3 * 4"), vec![t("2 * 3 * 4")]);
    assert_eq!(inline("a *b * c*"), vec![t("a "), it("b * c")]);
}

#[test]
fn inline_bold_content_is_literal() {
    assert_eq!(inline("**`x` and *y***"), vec![b("`x` and *y"), t("*")]);
}

#[test]
fn inline_unclosed_bold_is_text() {
    assert_eq!(inline("a ** b"), vec![t("a ** b")]);
    assert_eq!(inline("****"), vec![t("****")]);
}

#[test]
fn inline_links() {
    assert_eq!(
        inline("see [the report](runs/crew/night/NIGHT_REPORT.md) now"),
        vec![t("see "), link("the report", "runs/crew/night/NIGHT_REPORT.md"), t(" now")]
    );
}

#[test]
fn inline_link_text_backticks_removed_and_empty_text() {
    assert_eq!(inline("[`campaign.py`](crew/campaign.py)"), vec![link("campaign.py", "crew/campaign.py")]);
    assert_eq!(inline("[](a.md)"), vec![link("a.md", "a.md")]);
}

#[test]
fn inline_link_target_is_trimmed_and_may_hold_spaces() {
    assert_eq!(inline("[x]( C:\\My Files\\a.md )"), vec![link("x", "C:\\My Files\\a.md")]);
}

#[test]
fn inline_not_links() {
    assert_eq!(inline("[a] (b)"), vec![t("[a] (b)")]);
    assert_eq!(inline("[a]()"), vec![t("[a]()")]);
    assert_eq!(inline("[open"), vec![t("[open")]);
}

#[test]
fn inline_nested_bracket_finds_the_inner_link() {
    assert_eq!(inline("[a [b](c)"), vec![t("[a "), link("b", "c")]);
}

#[test]
fn inline_wiki_links() {
    assert_eq!(
        inline("see [[crew-roles]] and [[hoss-direction|Hoss]]"),
        vec![t("see "), link("crew-roles", "crew-roles"), t(" and "), link("Hoss", "hoss-direction")]
    );
}

#[test]
fn inline_wiki_link_edge_cases() {
    assert_eq!(inline("[[ ]]"), vec![t("[[ ]]")]);
    assert_eq!(inline("[[a|]]"), vec![link("a", "a")]);
    assert_eq!(inline("[[unclosed"), vec![t("[[unclosed")]);
}

#[test]
fn inline_bare_addresses() {
    assert_eq!(
        inline("docs: https://docs.rs/egui/0.37.0, or (http://localhost:8080)."),
        vec![
            t("docs: "),
            link("https://docs.rs/egui/0.37.0", "https://docs.rs/egui/0.37.0"),
            t(", or ("),
            link("http://localhost:8080", "http://localhost:8080"),
            t(")."),
        ]
    );
}

#[test]
fn inline_bare_address_rules() {
    assert_eq!(inline("xhttps://a.b"), vec![t("xhttps://a.b")], "must start a word");
    assert_eq!(inline("https://"), vec![t("https://")], "nothing after the scheme");
    assert_eq!(inline("\"https://a.b/c\""), vec![t("\""), link("https://a.b/c", "https://a.b/c"), t("\"")]);
}

#[test]
fn inline_unicode() {
    assert_eq!(inline("caf\u{e9} **\u{2192} ok**"), vec![t("caf\u{e9} "), b("\u{2192} ok")]);
}

// ---- split_row --------------------------------------------------------------

#[test]
fn split_row_basics() {
    assert_eq!(split_row("| a | b |"), vec!["a".to_string(), "b".to_string()]);
    assert_eq!(split_row("  |a|b  "), vec!["a".to_string(), "b".to_string()]);
    assert_eq!(split_row("| one |"), vec!["one".to_string()]);
    assert_eq!(split_row("|"), vec!["".to_string()]);
}

#[test]
fn split_row_escaped_pipes() {
    assert_eq!(split_row("| `a \\| b` | c |"), vec!["`a | b`".to_string(), "c".to_string()]);
    assert_eq!(split_row("| x \\|"), vec!["x |".to_string()]);
}

#[test]
fn split_row_empty_cells() {
    assert_eq!(split_row("| a || c |"), vec!["a".to_string(), "".to_string(), "c".to_string()]);
}

// ---- parse: blocks ----------------------------------------------------------

#[test]
fn parse_empty() {
    assert_eq!(parse(""), Vec::<Block>::new());
    assert_eq!(parse("\n\n   \n"), Vec::<Block>::new());
}

#[test]
fn parse_headings() {
    assert_eq!(
        parse("# Night report\n### Step **3**\n####### seven\n#tag\n#"),
        vec![
            Block::Heading { level: 1, spans: vec![t("Night report")] },
            Block::Heading { level: 3, spans: vec![t("Step "), b("3")] },
            p(vec![t("####### seven #tag")]),
            Block::Heading { level: 1, spans: vec![] },
        ]
    );
}

#[test]
fn parse_paragraph_lines_join_with_one_space() {
    assert_eq!(
        parse("first line\n   second `line`  \nthird\n\nnew paragraph"),
        vec![p(vec![t("first line second "), c("line"), t(" third")]), p(vec![t("new paragraph")])]
    );
}

#[test]
fn parse_code_fence() {
    assert_eq!(
        parse("before\n```powershell\n  Get-ChildItem\n\n# not a heading\n```\nafter"),
        vec![
            p(vec![t("before")]),
            Block::Code { lang: "powershell".to_string(), text: "  Get-ChildItem\n\n# not a heading".to_string() },
            p(vec![t("after")]),
        ]
    );
}

#[test]
fn parse_code_fence_unclosed_and_long_closer() {
    assert_eq!(parse("```\na\nb"), vec![Block::Code { lang: String::new(), text: "a\nb".to_string() }]);
    assert_eq!(
        parse("  ``` rust \nx\n  ````  \ny"),
        vec![Block::Code { lang: "rust".to_string(), text: "x".to_string() }, p(vec![t("y")])]
    );
    assert_eq!(parse("```\n```"), vec![Block::Code { lang: String::new(), text: String::new() }]);
}

#[test]
fn parse_front_matter() {
    assert_eq!(
        parse("---\nname: x\ntype: project\n---\n# Title"),
        vec![
            Block::Code { lang: "yaml".to_string(), text: "name: x\ntype: project".to_string() },
            Block::Heading { level: 1, spans: vec![t("Title")] },
        ]
    );
}

#[test]
fn parse_front_matter_needs_a_closing_line() {
    assert_eq!(parse("---\nname: x"), vec![Block::Rule, p(vec![t("name: x")])]);
    assert_eq!(parse("text\n---\nmore\n---"), vec![p(vec![t("text")]), Block::Rule, p(vec![t("more")]), Block::Rule]);
}

#[test]
fn parse_rules() {
    assert_eq!(
        parse("***\n___\n  -----  \n--\n-*-"),
        vec![Block::Rule, Block::Rule, Block::Rule, p(vec![t("-- -*-")])]
    );
}

#[test]
fn parse_bullets_and_depth() {
    assert_eq!(
        parse("- one\n* two\n  + nested\n    - deeper\n\t- tab\n-not a bullet"),
        vec![
            bullet(0, vec![t("one")]),
            bullet(0, vec![t("two")]),
            bullet(1, vec![t("nested")]),
            bullet(2, vec![t("deeper")]),
            bullet(2, vec![t("tab -not a bullet")]),
        ]
    );
}

#[test]
fn parse_bullet_wrapped_lines_continue_it() {
    assert_eq!(
        parse("- The crew MCP goes through the keeper (`--worker`\n  opts in).\n- next"),
        vec![
            bullet(0, vec![t("The crew MCP goes through the keeper ("), c("--worker"), t(" opts in).")]),
            bullet(0, vec![t("next")]),
        ]
    );
}

#[test]
fn parse_empty_bullet() {
    assert_eq!(parse("- "), vec![bullet(0, vec![])]);
}

#[test]
fn parse_numbered() {
    assert_eq!(
        parse("1. first\n2) second\n   10. sub\n1234567890. too long"),
        vec![
            Block::Numbered { depth: 0, number: 1, spans: vec![t("first")] },
            Block::Numbered { depth: 0, number: 2, spans: vec![t("second")] },
            Block::Numbered { depth: 1, number: 10, spans: vec![t("sub 1234567890. too long")] },
        ]
    );
}

#[test]
fn parse_numbered_interrupts_a_paragraph_only_at_one() {
    assert_eq!(
        parse("It happened in\n2026. Then more.\n1. a list"),
        vec![
            p(vec![t("It happened in 2026. Then more.")]),
            Block::Numbered { depth: 0, number: 1, spans: vec![t("a list")] },
        ]
    );
    assert_eq!(
        parse("- item\n3. three"),
        vec![bullet(0, vec![t("item")]), Block::Numbered { depth: 0, number: 3, spans: vec![t("three")] }]
    );
}

#[test]
fn parse_quotes() {
    assert_eq!(
        parse("> Kris: \"approve\n>needs no words\"\n>\n> - still quoted\nlazy\n\nafter"),
        vec![
            Block::Quote(vec![t("Kris: \"approve needs no words\" - still quoted lazy")]),
            p(vec![t("after")]),
        ]
    );
}

#[test]
fn parse_quote_after_a_paragraph_starts_a_new_block() {
    assert_eq!(parse("text\n> quote"), vec![p(vec![t("text")]), Block::Quote(vec![t("quote")])]);
}

#[test]
fn parse_table() {
    let md = "| member | posts |\n|---|:---:|\n| Hoss | tester |\n| Gordon |\n| Larry | clerk | extra |\nafter";
    assert_eq!(
        parse(md),
        vec![
            Block::Table {
                header: cells(&["member", "posts"]),
                rows: vec![cells(&["Hoss", "tester"]), cells(&["Gordon", ""]), cells(&["Larry", "clerk"])],
            },
            p(vec![t("after")]),
        ]
    );
}

#[test]
fn parse_table_cells_are_inline() {
    let md = "| a | b |\n| - | - |\n| `x \\| y` | **z** |";
    assert_eq!(
        parse(md),
        vec![Block::Table { header: cells(&["a", "b"]), rows: vec![vec![vec![c("x | y")], vec![b("z")]]] }]
    );
}

#[test]
fn parse_pipe_line_without_separator_is_a_paragraph() {
    assert_eq!(parse("| not | a table |\nplain"), vec![p(vec![t("| not | a table | plain")])]);
    assert_eq!(parse("| a |\n|   |"), vec![p(vec![t("| a | |   |")])], "a separator needs a dash");
}

#[test]
fn parse_table_header_only_and_ends_at_blank() {
    assert_eq!(
        parse("| a |\n|--|\n\n| b |"),
        vec![Block::Table { header: cells(&["a"]), rows: vec![] }, p(vec![t("| b |")])]
    );
}

#[test]
fn parse_blocks_interrupt_paragraphs() {
    assert_eq!(
        parse("para\n# head\npara2\n- item\npara3 continues item\n```\ncode\n```"),
        vec![
            p(vec![t("para")]),
            Block::Heading { level: 1, spans: vec![t("head")] },
            p(vec![t("para2")]),
            bullet(0, vec![t("item para3 continues item")]),
            Block::Code { lang: String::new(), text: "code".to_string() },
        ]
    );
}

#[test]
fn parse_crlf() {
    assert_eq!(
        parse("# A\r\n\r\n- b\r\n"),
        vec![Block::Heading { level: 1, spans: vec![t("A")] }, bullet(0, vec![t("b")])]
    );
}

#[test]
fn parse_night_report_shape() {
    let md = "# Night report - 2026-10-23\n\n0 failed job(s) in 0 group(s).\n\n## Guard\n\n| action | count |\n|---|---|\n| rewrite | 2 |\n\n- report: `runs\\crew\\night\\NIGHT_REPORT.md`\n";
    assert_eq!(
        parse(md),
        vec![
            Block::Heading { level: 1, spans: vec![t("Night report - 2026-10-23")] },
            p(vec![t("0 failed job(s) in 0 group(s).")]),
            Block::Heading { level: 2, spans: vec![t("Guard")] },
            Block::Table { header: cells(&["action", "count"]), rows: vec![cells(&["rewrite", "2"])] },
            bullet(0, vec![t("report: "), c("runs\\crew\\night\\NIGHT_REPORT.md")]),
        ]
    );
}
