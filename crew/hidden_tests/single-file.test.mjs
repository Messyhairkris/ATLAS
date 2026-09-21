// Hidden tests for single-file.js. Every contract table row, plus running the page.
import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import * as sf from "./single-file.js";

// The contract's page template, verbatim.
const TEMPLATE = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escaped title}</title>
<style>{css}</style>
<script>
(function () {
  var MODULES = {S(modules)};
  var ASSETS = {S(B64)};
  var map = {};
  for (var name in MODULES) {
    map[name] = URL.createObjectURL(new Blob([MODULES[name]], { type: "text/javascript" }));
  }
  window.SPLAT_PACKED = {
    portfolio: {S(portfolio)},
    asset: function (file) {
      if (!(file in ASSETS)) return null;
      var s = atob(ASSETS[file]), a = new Uint8Array(s.length);
      for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);
      return { fileBytes: a, fileName: file };
    }
  };
  var im = document.createElement("script");
  im.type = "importmap";
  im.textContent = JSON.stringify({ imports: map });
  document.head.appendChild(im);
  var go = document.createElement("script");
  go.type = "module";
  go.textContent = "import " + JSON.stringify({S(entry)}) + ";";
  document.head.appendChild(go);
})();
</script>
</head>
<body>{body}</body>
</html>
`;

test("PACKED_GLOBAL", () => assert.equal(sf.PACKED_GLOBAL, "SPLAT_PACKED"));

const REWRITES = [
  ['import a from "./a.js";', { "./a.js": "x:a" }, 'import a from "x:a";', []],
  ["import './b.js'", { "./b.js": "x:b" }, "import 'x:b'", []],
  ['export { c } from "../c.js"', { "../c.js": "x:c" }, 'export { c } from "x:c"', []],
  ['const m = await import( "./d.js" )', { "./d.js": "x:d" },
    'const m = await import( "x:d" )', []],
  ['import t from "three"', {}, 'import t from "three"', []],
  ['import e from "./e.js"; import f from "./e.js"', {},
    'import e from "./e.js"; import f from "./e.js"', ["./e.js"]],
  ['const s = "./not-an-import.js"', {}, 'const s = "./not-an-import.js"', []],
  ['import {\n  a,\n} from "./m.js";\nimport "./n.js";', { "./m.js": "x:m" },
    'import {\n  a,\n} from "x:m";\nimport "./n.js";', ["./n.js"]],
];
for (const [src, rename, code, unmapped] of REWRITES) {
  test(`rewriteSpecifiers ${JSON.stringify(src)}`, () => {
    assert.deepEqual(sf.rewriteSpecifiers(src, rename), { code, unmapped });
  });
}

test("rewriteSpecifiers keeps the quote style", () => {
  assert.equal(sf.rewriteSpecifiers("import x from './q.js'", { "./q.js": "x:q" }).code,
    "import x from 'x:q'");
});

for (const [bytes, out] of [[[], ""], [[102], "Zg=="], [[102, 111], "Zm8="],
  [[102, 111, 111], "Zm9v"], [[0, 255, 128], "AP+A"]]) {
  test(`bytesToBase64 ${JSON.stringify(bytes)}`, () => {
    assert.equal(sf.bytesToBase64(new Uint8Array(bytes)), out);
  });
}

test("bytesToBase64 handles a large array", () => {
  const big = new Uint8Array(3_000_001);
  for (let i = 0; i < big.length; i++) big[i] = (i * 7) & 255;
  assert.equal(sf.bytesToBase64(big), Buffer.from(big).toString("base64"));
});

test("scriptSafe table", () => {
  assert.equal(sf.scriptSafe({ a: 1 }), '{"a":1}');
  assert.equal(sf.scriptSafe("</script>"), '"\\u003c/script>"');
  assert.equal(sf.scriptSafe("<!--"), '"\\u003c!--"');
});

test("scriptSafe escapes line separators and still parses back", () => {
  const value = { s: "a\u2028b\u2029c</script><x>" };
  const out = sf.scriptSafe(value);
  assert.ok(!out.includes("<") && !out.includes("\u2028") && !out.includes("\u2029"));
  assert.deepEqual(JSON.parse(out), value);
});

const SITE = () => ({
  title: 'Bones & "Skulls" <1>',
  css: "body{margin:0}",
  body: '<canvas id="stage"></canvas>',
  modules: { three: "export const T = 1;", "x:viewer": 'import "three"; // </script>' },
  entry: "x:viewer",
  portfolio: '{"title":"Bones","note":"</script>"}',
  assets: { "Jackalope.spz": new Uint8Array([0, 1, 2, 250, 255]), "b.spz": new Uint8Array(0) },
});

test("packedPage matches the contract template exactly", () => {
  const site = SITE();
  const b64 = { "Jackalope.spz": "AAEC+v8=", "b.spz": "" };
  const fill = {
    "{escaped title}": "Bones &amp; &quot;Skulls&quot; &lt;1&gt;",
    "{css}": site.css, "{body}": site.body,
    "{S(modules)}": sf.scriptSafe(site.modules), "{S(B64)}": sf.scriptSafe(b64),
    "{S(portfolio)}": sf.scriptSafe(site.portfolio), "{S(entry)}": sf.scriptSafe(site.entry),
  };
  let expected = TEMPLATE;
  for (const [k, v] of Object.entries(fill)) expected = expected.split(k).join(v);
  assert.equal(sf.packedPage(site), expected);
});

test("packed page has exactly one closing script tag", () => {
  const page = sf.packedPage(SITE());
  assert.equal(page.split("</script>").length - 1, 1);
});

function runPage(page) {
  const script = page.slice(page.indexOf("<script>") + 8, page.indexOf("</script>"));
  const head = [];
  const blobs = new Map();
  const ctx = {
    window: {}, atob, Uint8Array, JSON,
    Blob: class { constructor(parts, opts) { this.text = parts.join(""); this.type = opts.type; } },
    URL: { createObjectURL(b) { const u = "blob:" + blobs.size; blobs.set(u, b); return u; } },
    document: { head: { appendChild: (el) => head.push(el) }, createElement: () => ({}) },
  };
  vm.runInNewContext(script, ctx);
  return { packed: ctx.window.SPLAT_PACKED, head, blobs };
}

test("running the page exposes the portfolio and the original bytes", () => {
  const { packed } = runPage(sf.packedPage(SITE()));
  assert.equal(packed.portfolio, SITE().portfolio);
  const got = packed.asset("Jackalope.spz");
  assert.equal(got.fileName, "Jackalope.spz");
  assert.deepEqual(Array.from(got.fileBytes), [0, 1, 2, 250, 255]);
  assert.equal(packed.asset("b.spz").fileBytes.length, 0);
  assert.equal(packed.asset("missing.spz"), null);
});

test("running the page maps every module and imports the entry", () => {
  const { head, blobs } = runPage(sf.packedPage(SITE()));
  assert.deepEqual(head.map((el) => el.type), ["importmap", "module"]);
  const map = JSON.parse(head[0].textContent).imports;
  assert.deepEqual(Object.keys(map).sort(), ["three", "x:viewer"]);
  assert.equal(blobs.get(map["x:viewer"]).text, SITE().modules["x:viewer"]);
  assert.equal(blobs.get(map.three).type, "text/javascript");
  assert.equal(head[1].textContent, 'import "x:viewer";');
});

test("an entry that is not a module throws, naming it", () => {
  assert.throws(() => sf.packedPage({ ...SITE(), entry: "x:nope" }), /x:nope/);
});

test("an asset that is not a Uint8Array throws, naming it", () => {
  assert.throws(() => sf.packedPage({ ...SITE(), assets: { "bad.spz": [1, 2] } }), /bad\.spz/);
});
