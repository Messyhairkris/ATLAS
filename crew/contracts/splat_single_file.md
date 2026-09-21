# Contract: single-file.js - packing an exported portfolio site into ONE .html

Splat Studio exports a folder: `viewer/`, `js/`, `vendor/`, `data/portfolio.json`,
`assets/*.spz`. Kris opens exported pages by double-clicking them, and a browser will
not run module scripts or fetch files from `file://`, so the folder never plays. This
module folds the whole site into one page that runs from a double-click. It was
proven by hand first: the packed page renders the Jackalope with no console errors.

It runs **inside the studio, in the browser**, so it uses no Node APIs at all: no
`Buffer`, no `fs`, no `require`. Pure strings and `Uint8Array` in, a string out.

## Public API

```js
export const PACKED_GLOBAL = "SPLAT_PACKED";
export function rewriteSpecifiers(source, rename) { }   // -> { code, unmapped }
export function bytesToBase64(bytes) { }                // Uint8Array -> string
export function scriptSafe(value) { }                   // any JSON value -> string
export function packedPage(site) { }                    // -> string (the whole .html)
```

Allowed imports: **none**. You may use the globals `btoa`, `JSON`, `String`,
`Object`, `Array`, `Math`, `RegExp`. Nothing that touches the page, the network or
the disk.

## rewriteSpecifiers(source, rename)

`rename` is a plain object from a relative specifier to a bare module name, e.g.
`{"./three.core.js": "x:three-core"}`. Find every string literal (single or double
quotes) that is a module specifier - one that directly follows, with optional
whitespace between:

1. `from`
2. `import` (a side-effect import)
3. `import(` (a dynamic import)

Only specifiers that start with `./` or `../` are looked at. For each one:

- if it is a key of `rename`, replace the specifier text with the value, keeping the
  original quote character;
- otherwise leave it exactly as it is and add it to `unmapped`.

Bare specifiers (`"three"`) are never changed and never reported. Return
`{ code, unmapped }` where `unmapped` lists each unmapped specifier once, in order of
first appearance. Everything outside the replaced specifiers is unchanged.

| source | rename | code | unmapped |
|---|---|---|---|
| `import a from "./a.js";` | `{"./a.js": "x:a"}` | `import a from "x:a";` | `[]` |
| `import './b.js'` | `{"./b.js": "x:b"}` | `import 'x:b'` | `[]` |
| `export { c } from "../c.js"` | `{"../c.js": "x:c"}` | `export { c } from "x:c"` | `[]` |
| `const m = await import( "./d.js" )` | `{"./d.js": "x:d"}` | `const m = await import( "x:d" )` | `[]` |
| `import t from "three"` | `{}` | unchanged | `[]` |
| `import e from "./e.js"; import f from "./e.js"` | `{}` | unchanged | `["./e.js"]` |
| `const s = "./not-an-import.js"` | `{}` | unchanged | `[]` |

## bytesToBase64(bytes)

Standard base64 (RFC 4648, `+` and `/`, `=` padding) of a `Uint8Array`. It must work
for arrays of tens of megabytes: build the binary string in chunks of at most 32768
bytes (`String.fromCharCode.apply(null, chunk)` on a larger array throws "Maximum
call stack size exceeded"), then call `btoa` once on the joined string.

| bytes | result |
|---|---|
| `[]` | `""` |
| `[102]` | `"Zg=="` |
| `[102, 111]` | `"Zm8="` |
| `[102, 111, 111]` | `"Zm9v"` |
| `[0, 255, 128]` | `"AP+A"` |

## scriptSafe(value)

`JSON.stringify(value)`, then made safe to paste inside a `<script>` element:
replace every `<` with `\u003c`, every U+2028 with `\u2028` and every U+2029 with
`\u2029` (the six-character escape text). The result is still valid JSON that
parses back to `value`.

| value | result |
|---|---|
| `{"a": 1}` | `{"a":1}` |
| `"</script>"` | `"\u003c/script>"` |
| `"<!--"` | `"\u003c!--"` |

## packedPage(site)

`site` is:

```js
{
  title: "Test yooooo",            // page <title>, HTML-escaped (& < > ")
  css: "...",                      // viewer.css text
  body: "...",                     // the viewer's <body> inner HTML, WITHOUT scripts
  modules: { "three": "...", "x:viewer": "..." },   // bare name -> module source
  entry: "x:viewer",               // the module that starts the page
  portfolio: "{...}",              // data/portfolio.json as text
  assets: { "Jackalope.spz": Uint8Array }           // file name -> bytes
}
```

Return exactly this page, where `S(x)` means `scriptSafe(x)` and `B64` is an object
from each asset name to `bytesToBase64` of its bytes:

```html
<!doctype html>
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
```

Lines end with `\n`, including the last. Indentation is two spaces per level, exactly
as shown. The `{...}` placeholders are replaced with no extra spaces. `css` and
`body` are inserted as they are - they come from the studio's own files.

Rules, in order:

1. `site.entry` must be a key of `site.modules`, otherwise throw an `Error` whose
   message contains the entry name.
2. Every value in `site.assets` must be a `Uint8Array`, otherwise throw an `Error`
   whose message contains that asset's name.
3. Build and return the page.

The tests run the `<script>` block with fake `document`, `URL`, `Blob` and `window`
objects and check that `SPLAT_PACKED.asset(name)` returns the original bytes, that
`SPLAT_PACKED.portfolio` is the original text, and that the import map names every
module.
