"""Tests for the Rust gate parts. The scan cases are written as bypass attempts:
each `BLOCKED` source is a way a member could reach the machine, and the scan must
say something about it; each `ALLOWED` source is ordinary code that must pass."""

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import cargo_out  # noqa: E402
import rs_api  # noqa: E402
import rs_lex  # noqa: E402
import rs_scan  # noqa: E402

PROFILE = {
    "crate_name": "photo_tools",
    "crates": {
        "image": {"banned_paths": ["image::open", "image::ImageReader", "image::io",
                                   "image::codecs", "image::save_buffer"],
                  "banned_methods": ["save", "save_with_format", "write_to"],
                  "banned_idents": ["ImageReader"]},
        "imageproc": {"banned_paths": ["imageproc::window", "imageproc::utils"],
                      "banned_idents": ["load_image_or_panic"]},
        "clap": {},
    },
}


# -- lexer -------------------------------------------------------------------------------

def kinds(src):
    return [(t.kind, t.text) for t in rs_lex.tokens(src)]


def test_nested_block_comment_is_one_comment():
    assert kinds("/* a /* b */ c */ x") == [("ident", "x")]


def test_raw_string_with_hashes_holds_quotes():
    toks = kinds('let s = r#"say "hi" "# ; y')
    assert ("str", 'r#"say "hi" "#') in toks and toks[-1] == ("ident", "y")


def test_char_versus_lifetime():
    assert kinds("'a' 'b '\\'' '\"'") == [("char", "'a'"), ("lifetime", "'b"),
                                          ("char", "'\\''"), ("char", "'\"'")]


def test_byte_and_c_strings():
    assert [k for k, _ in kinds('b"x" br"y" c"z" b\'q\'')] == ["str", "str", "str", "char"]


def test_numbers_do_not_eat_ranges_or_methods():
    assert kinds("1..2") == [("num", "1"), ("punct", ".."), ("num", "2")]
    assert kinds("1.5e-3 0xFF_u8")[0] == ("num", "1.5e-3")
    assert ("ident", "max") in kinds("1.max(2)")


def test_raw_identifier_and_not_equal():
    assert kinds("r#type != x") == [("ident", "type"), ("punct", "!="), ("ident", "x")]


def test_unterminated_string_is_an_error():
    assert rs_lex.errors('let s = "abc')


# -- scan: bypass attempts -----------------------------------------------------------------

BLOCKED = [
    "use std::fs;",
    "fn f() { std::fs::read(\"x\"); }",
    "fn f() { ::std::fs::read(\"x\"); }",
    "fn f() -> Vec<u8> { return ::std::fs::read(\"x\").unwrap(); }",
    "fn f(n: usize) -> bool { n > ::std::fs::read(\"x\").unwrap().len() }",
    "use std as s;",
    "use std::{fs, collections::HashMap};",
    "use std::io::{self, Write};",
    "use image::open;",
    "fn f() { let _ = image::open(\"a.png\"); }",
    "fn f(img: &image::GrayImage) { img.save(\"x.png\").unwrap(); }",
    "fn f() { let _ = image::ImageReader::open(\"a\"); }",
    "use image::*;",
    "fn f() { unsafe { } }",
    "extern crate std as s;",
    "extern \"C\" { fn abs(x: i32) -> i32; }",
    "const S: &str = include_str!(\"secret.txt\");",
    "const S: &str = std::include_str!(\"secret.txt\");",
    "const H: &str = env!(\"HOME\");",
    "macro_rules! m { () => {} }",
    "#[path = \"x.rs\"] mod m;",
    "mod other;",
    "#![allow(dead_code)]",
    "#[cfg_attr(test, path = \"x.rs\")] mod m {}",
    "type T = <std::fs::File as Default>::X;",
    "struct S { c: Vec<std::process::Child> }",
    "fn f() { std::thread::spawn(|| {}); }",
    "fn f() { let _ = std::env::var(\"X\"); }",
    "fn f() { let _ = core::ptr::null::<u8>(); }",
    "fn f() { let _ = crate::std::fs::read(\"x\"); }",
    "#[test] #[ignore] fn t() {}",
    "fn f() { let _ = std::path::Path::new(\"x\").exists(); }",
    "fn f() { let _ = '\"'; std::fs::remove_file(\"x\"); }",
    "fn f() { let _ = b'\\''; std::net::TcpStream::connect(\"x\"); }",
    "use std::process::Command as C;",
    "fn f() { std::process::exit(1) }",
    "fn f() { let _ = imageproc::image::open(\"a.png\"); }",
    "fn f() { let _ = imageproc::utils::load_image_or_panic(\"a.png\"); }",
    "use imageproc::utils::load_image_or_panic as l;",
]

ALLOWED = [
    "use std::collections::HashMap;\nfn f() -> HashMap<u8, u8> { HashMap::new() }",
    "fn f(a: &mut u8, b: &mut u8) { std::mem::swap(a, b) }",
    "use std::fmt::Write as _;",
    "use std::fmt;\nimpl fmt::Display for E { fn fmt(&self, f: &mut fmt::Formatter<'_>) "
    "-> fmt::Result { write!(f, \"e\") } }",
    "use image::{GrayImage, Luma};",
    "fn f(g: &image::GrayImage) -> image::GrayImage { imageproc::edges::canny(g, 1.0, 2.0) }",
    "fn f() { let s = \"std::fs::read unsafe\"; let _ = s; }",
    "// unsafe std::fs here is a comment\nfn f() {}",
    "/* outer /* std::fs */ still comment */ fn f() {}",
    "fn f() -> u32 { \"7\".parse::<u32>().unwrap() + u32::MAX }",
    "const P: f64 = std::f64::consts::PI;",
    "use photo_tools::sobel::sobel_mask;",
    "#[cfg(test)]\nmod tests {\n    use super::*;\n    #[test]\n    fn t() {}\n}",
    "#[derive(Debug, Clone, Copy, PartialEq)] pub enum E { A }",
    "#[test] #[should_panic(expected = \"x\")] fn t() { panic!(\"x\") }",
    "fn f() -> String { let r = r#\"std::fs \"#; r.to_string() }",
    "fn f<'a>(x: &'a str) -> &'a str { x }",
    "fn f() -> Vec<u8> { Vec::<u8>::with_capacity(3) }",
    "use clap::{Parser, ValueEnum};",
    "fn f(v: &[u8]) -> usize { v.iter().filter(|&&b| b != 0).count() }",
    "fn f() { let o = imageproc::morphology::open; let _ = o; }",
]


@pytest.mark.parametrize("src", BLOCKED)
def test_scan_blocks(src):
    assert rs_scan.scan(src, PROFILE), src


@pytest.mark.parametrize("src", ALLOWED)
def test_scan_allows(src):
    assert rs_scan.scan(src, PROFILE) == [], src


def test_scan_message_names_line_and_item():
    probs = rs_scan.scan("fn a() {}\nfn b() { std::fs::read(\"x\"); }", PROFILE)
    assert probs and probs[0].startswith("line 2:") and "std::fs" in probs[0]


# -- API and stubs ------------------------------------------------------------------------

API_SRC = """
pub const RAMP: &str = " .:-=+*#%@";
pub struct Options { pub cell: u32 }
pub enum Mode { A, B }
pub fn render(x: u8) -> u8 { x }
pub(crate) fn hidden() {}
impl Default for Options { fn default() -> Self { Options { cell: 4 } } }
impl Options { pub fn validate(&self) -> bool { self.cell > 0 } }
pub const fn twice(x: u8) -> u8 { x * 2 }
"""


def test_api_finds_items_and_methods():
    assert rs_api.missing_api(API_SRC, ["RAMP", "Options", "Mode", "render", "twice",
                                        "Options::default", "Options::validate"]) == []


def test_api_reports_missing():
    assert rs_api.missing_api(API_SRC, ["render_all", "Options::new"]) == \
        ["render_all", "Options::new"]


def test_stubs():
    src = ("pub fn a() -> u8 { todo!() }\npub fn b() {}\n"
           "pub fn c() -> u8 { unimplemented!(\"later\"); }\n"
           "pub fn d() -> u8 { 1 }\nfn e(x: u8) -> u8 { if x > 1 { todo!() } else { x } }\n"
           "struct S { f: fn(u8) -> u8 }\n")
    found = rs_api.stubs(src)
    assert "a" in found and "b" in found and "c" in found and "d" not in found
    assert any(s.startswith("todo!") for s in found)


def test_count_tests_ignores_comments():
    src = "// #[test]\n#[test]\nfn a() {}\n#[test]\nfn b() {}\nconst S: &str = \"#[test]\";"
    assert rs_api.count_tests(src) == 2


# -- cargo output -----------------------------------------------------------------------

LIBTEST = """
running 3 tests
test a ... ok
test b ... FAILED
test c ... ignored

failures:

---- b stdout ----

thread 'b' panicked at tests/hidden_x.rs:5:5:
assertion `left == right` failed
  left: 1
 right: 2
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace


failures:
    b

test result: FAILED. 1 passed; 1 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.00s

running 2 tests
test d ... ok
test e ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
"""


def test_parse_libtest_counts_and_failures():
    r = cargo_out.parse_libtest(LIBTEST)
    assert r["counts"] == {"passed": 3, "failed": 1, "ignored": 1, "binaries": 2}
    assert "left: 1" in r["failures"]["b"] and "RUST_BACKTRACE" not in r["failures"]["b"]
    assert cargo_out.summary_line(r) == "1 failed, 3 passed, 1 skipped"


RUSTC = """   Compiling photo_tools v0.0.0 (C:\\slot0)
error[E0425]: cannot find value `x` in this scope
 --> src/sobel.rs:3:5
  |
3 |     x
  |     ^ not found in this scope

error[E0061]: this function takes 3 arguments but 2 arguments were supplied
 --> tests/hidden_sobel.rs:9:13
  |
9 |     let m = sobel_mask(&px, 3);
  |             ^^^^^^^^^^------- argument #3 of type `u16` is missing
  |
note: function defined here
 --> src/sobel.rs:1:8

warning: unused variable: `y`

error: aborting due to 2 previous errors
error: could not compile `photo_tools` (test "hidden_sobel") due to 2 previous errors
"""


def test_compile_errors_hide_hidden_test_source():
    errs = cargo_out.compile_errors(RUSTC)
    assert len(errs) == 2
    assert "src/sobel.rs:3:5" in errs[0] and "not found in this scope" in errs[0]
    assert "sobel_mask(&px" not in errs[1] and "hidden tests (line 9)" in errs[1]
    assert errs[1].startswith("error[E0061]: this function takes 3 arguments")
