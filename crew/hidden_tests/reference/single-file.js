// Reference implementation for the single-file.js contract.
export const PACKED_GLOBAL = "SPLAT_PACKED";

const SPEC = /((?:\bfrom|\bimport)\s*\(?\s*)(["'])(\.{1,2}\/[^"']*)\2/g;

export function rewriteSpecifiers(source, rename) {
  const unmapped = [];
  const code = source.replace(SPEC, (all, lead, quote, spec) => {
    if (Object.prototype.hasOwnProperty.call(rename, spec)) {
      return lead + quote + rename[spec] + quote;
    }
    if (!unmapped.includes(spec)) unmapped.push(spec);
    return all;
  });
  return { code, unmapped };
}

export function bytesToBase64(bytes) {
  const parts = [];
  for (let i = 0; i < bytes.length; i += 32768) {
    parts.push(String.fromCharCode.apply(null, bytes.subarray(i, i + 32768)));
  }
  return btoa(parts.join(""));
}

export function scriptSafe(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function packedPage(site) {
  if (!Object.prototype.hasOwnProperty.call(site.modules, site.entry)) {
    throw new Error(`entry module ${site.entry} is not in modules`);
  }
  const b64 = {};
  for (const [name, bytes] of Object.entries(site.assets)) {
    if (!(bytes instanceof Uint8Array)) throw new Error(`asset ${name} is not a Uint8Array`);
    b64[name] = bytesToBase64(bytes);
  }
  return [
    "<!doctype html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    `<title>${escapeHtml(site.title)}</title>`, `<style>${site.css}</style>`, "<script>",
    "(function () {",
    `  var MODULES = ${scriptSafe(site.modules)};`,
    `  var ASSETS = ${scriptSafe(b64)};`,
    "  var map = {};",
    "  for (var name in MODULES) {",
    '    map[name] = URL.createObjectURL(new Blob([MODULES[name]], { type: "text/javascript" }));',
    "  }",
    "  window.SPLAT_PACKED = {",
    `    portfolio: ${scriptSafe(site.portfolio)},`,
    "    asset: function (file) {",
    "      if (!(file in ASSETS)) return null;",
    "      var s = atob(ASSETS[file]), a = new Uint8Array(s.length);",
    "      for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);",
    "      return { fileBytes: a, fileName: file };",
    "    }",
    "  };",
    '  var im = document.createElement("script");',
    '  im.type = "importmap";',
    "  im.textContent = JSON.stringify({ imports: map });",
    "  document.head.appendChild(im);",
    '  var go = document.createElement("script");',
    '  go.type = "module";',
    `  go.textContent = "import " + JSON.stringify(${scriptSafe(site.entry)}) + ";";`,
    "  document.head.appendChild(go);",
    "})();", "</script>", "</head>", `<body>${site.body}</body>`, "</html>", "",
  ].join("\n");
}
