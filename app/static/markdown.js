/* Raw Markdown is stored separately. Sanitize after parsing and highlighting. */
'use strict';
// Keep unchanged blocks and text nodes alive for selection, code scrolling, and copy.
function patchMarkdown(target, source) {
  let index = 0;
  for (const next of [...source.childNodes]) {
    const current = target.childNodes[index++];
    if (!current) { target.append(next); continue; }
    if (current.isEqualNode(next)) continue;
    if (current.nodeType !== next.nodeType || current.nodeName !== next.nodeName) {
      current.replaceWith(next);
    } else if (current.nodeType === Node.TEXT_NODE) {
      // Appending leaves existing selection offsets intact.
      let prefix = 0;
      while (prefix < current.length && prefix < next.length && current.data[prefix] === next.data[prefix]) prefix++;
      current.replaceData(prefix, current.length - prefix, next.data.slice(prefix));
    } else {
      for (const attr of [...current.attributes]) if (!next.hasAttribute(attr.name)) current.removeAttribute(attr.name);
      for (const attr of [...next.attributes]) if (current.getAttribute(attr.name) !== attr.value) current.setAttribute(attr.name, attr.value);
      patchMarkdown(current, next);
    }
  }
  while (target.childNodes.length > index) target.lastChild.remove();
}
const markdownHighlights = new WeakMap();
window.renderMarkdown = function (element, raw) {
  const fragment = document.createElement('div');
  fragment.innerHTML = DOMPurify.sanitize(marked.parse(raw, {gfm: true, breaks: false}), {
    ALLOWED_TAGS: ['p','br','hr','h1','h2','h3','h4','h5','h6','ul','ol','li','strong','em','del','blockquote','pre','code','table','thead','tbody','tr','th','td','a','span'],
    ALLOWED_ATTR: ['href','title','class','start'],
    ALLOW_DATA_ATTR: false
  });
  const previousHighlights = markdownHighlights.get(element) || new Map();
  const highlights = new Map();
  fragment.querySelectorAll('pre code').forEach(code => {
    const language = [...code.classList].find(c => c.startsWith('language-'))?.slice(9);
    if (language && hljs.getLanguage(language)) {
      const key = `${language}\0${code.textContent}`;
      const html = previousHighlights.get(key) ?? DOMPurify.sanitize(hljs.highlight(code.textContent, {language}).value, {ALLOWED_TAGS:['span'], ALLOWED_ATTR:['class']});
      highlights.set(key, html);
      code.innerHTML = html;
      code.classList.add('hljs');
    }
  });
  fragment.querySelectorAll('a').forEach(a => { a.rel = 'noreferrer noopener'; });
  markdownHighlights.set(element, highlights);
  patchMarkdown(element, fragment);
};
