'use strict';
window.createStreamBuffer = function (render, interval = 0) {
  let pending = null, frame = null, timer = null, closed = false;
  function flush() {
    if (frame !== null) cancelAnimationFrame(frame);
    if (timer !== null) clearTimeout(timer);
    frame = null;
    timer = null;
    if (pending !== null) {
      const text = pending;
      pending = null;
      render(text);
    }
  }
  return {
    set(text) {
      if (closed) return;
      pending = text;
      if (frame !== null || timer !== null) return;
      if (interval) timer = setTimeout(flush, interval);
      else frame = requestAnimationFrame(flush);
    },
    close() {
      // Includes the last received batch even in a background tab or on Stop.
      closed = true;
      flush();
    }
  };
};

window.createReplyReveal = function (element) {
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const name = 'reply-reveal';
  let animation = null;
  function clear() {
    if (animation) {
      animation.onfinish = null;
      animation.cancel();
      CSS.highlights.delete(name);
      animation = null;
    }
  }
  function fadeAppended(before) {
    clear();
    if (motion.matches || !CSS.highlights || !window.Highlight || !CSS.registerProperty) return;
    const after = element.textContent;
    if (after.length <= before.length) return;
    let prefix = 0;
    while (prefix < before.length && before[prefix] === after[prefix]) prefix++;
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode()) && prefix >= node.length) prefix -= node.length;
    if (!node) return;
    const range = document.createRange();
    range.selectNodeContents(element);
    range.setStart(node, prefix);
    CSS.highlights.set(name, new Highlight(range));
    animation = element.animate([{'--reply-ink':'25%'}, {'--reply-ink':'100%'}], {
      duration: 145, easing: 'ease-out',
    });
    animation.onfinish = clear;
  }
  return {fadeAppended, clear};
};
