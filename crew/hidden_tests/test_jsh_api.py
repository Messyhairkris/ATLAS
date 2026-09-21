"""Hidden tests for js_api.py. Every table row, plus a realistic module."""

import pytest

import js_api as ja


@pytest.mark.parametrize("source,expected", [
    ("export default 1", ["default"]),
    ("export function go() {}", ["go"]),
    ("export async function load() {}", ["load"]),
    ("export function* gen() {}", ["gen"]),
    ("export class Viewer {}", ["Viewer"]),
    ("export const A = 1, B = 2", ["A"]),
    ("export let x; export var y", ["x", "y"]),
    ("export const { a } = o", []),
    ("export { a, b as c, d as default }", ["a", "c", "default"]),
    ("export { a, }", ["a"]),
    ("export{a}", ["a"]),
    ('export * as ns from "m"', ["ns"]),
    ('export * from "m"', []),
    ("// export const hidden = 1", []),
    ('const s = "export const fake = 1"', []),
    ("export function a(){} export { a }", ["a"]),
    ("reexport const q = 1", []),
    ("obj.export const q = 1", []),
    ("export const $el = 1; export const _x = 2", ["$el", "_x"]),
    ("", []),
])
def test_exported_names_table(source, expected):
    assert ja.exported_names(source) == expected


def test_missing_api_keeps_required_order():
    assert ja.missing_api("export const A = 1", ["B", "A", "C"]) == ["B", "C"]


def test_missing_api_empty_when_all_present():
    assert ja.missing_api("export { A, B }", ["A", "B"]) == []


def test_missing_api_ignores_commented_exports():
    assert ja.missing_api("// export function go() {}", ["go"]) == ["go"]


@pytest.mark.parametrize("source,expected", [
    ("function a() {}", ["a"]),
    ("export async function b() { /* later */ }", ["b"]),
    ('function c() { throw new Error("not implemented"); }', ["c"]),
    ("function d() { throw new Error() }", ["d"]),
    ("function e(x = {}) { return x; }", []),
    ("function f(a = {}) {}", ["f"]),
    ('function g() { if (x) { throw new Error("bad"); } }', []),
    ('function h() { throw new Error("a" + b); }', []),
    ("const i = () => {}", []),
    ("function j() { return 1 } function k() {}", ["k"]),
    ("function l({ a, b } = {}, [c] = []) {\n  // nothing yet\n}", ["l"]),
    ("function m(f = (x) => x) { return f(1) }", []),
    ("function* n() {}", ["n"]),
    ('function o() { return "}"; }', []),
    ('function p() {\n  throw   new   Error ( "todo" ) ;\n}', ["p"]),
    ("", []),
])
def test_stub_functions_table(source, expected):
    assert ja.stub_functions(source) == expected


REAL = '''
import * as THREE from "./three.module.js";
// export function notReal() {}
export const DEFAULT_FOV = 50;
export function makeCamera(fov = DEFAULT_FOV) {
  const cam = new THREE.PerspectiveCamera(fov, 1, 0.01, 100);
  return cam;
}
export async function loadModel(url, { onProgress } = {}) {
  throw new Error("loadModel: not written yet");
}
function helper() { return "{"; }
export { helper as tidy };
'''


def test_a_realistic_module():
    assert ja.exported_names(REAL) == ["DEFAULT_FOV", "makeCamera", "loadModel",
                                       "tidy"]
    assert ja.stub_functions(REAL) == ["loadModel"]
    assert ja.missing_api(REAL, ["makeCamera", "notReal"]) == ["notReal"]
