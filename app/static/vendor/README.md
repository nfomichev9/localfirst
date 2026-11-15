# Offline browser libraries

Pinned and checked into the repository; the running app makes no CDN requests.
The exact upstream packages and integrity hashes are in package-lock.json.

- marked 18.2.0: node_modules/marked/lib/marked.umd.js → marked.min.js (UMD distribution; filename retained for existing script reference), MIT.
- DOMPurify 3.4.18: node_modules/dompurify/dist/purify.min.js → purify.min.js, MPL-2.0 OR Apache-2.0.
- Highlight.js 11.12.0: node_modules/@highlightjs/cdn-assets/highlight.min.js → highlight.min.js, BSD-3-Clause. Common languages bundled. Unknown languages remain escaped plain code.

Corresponding licenses are included here. npm is only needed for development,
not to launch LocalFirst. To update, pin versions in package.json, run npm install,
copy these three distribution files and licenses, then run Python and browser tests.
The rendering allowlist intentionally omits images, raw HTML controls, SVG, and
embedded media. Marked parses Markdown; DOMPurify sanitizes the resulting HTML.
