/* Coalesce received text into one paint per frame; never pace model output. */
'use strict';
window.createStreamBuffer = function (render) {
  let pending = null, frame = null, closed = false;
  function flush() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
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
      if (frame === null) frame = requestAnimationFrame(flush);
    },
    close() {
      // Includes the last received batch even in a background tab or on Stop.
      closed = true;
      flush();
    }
  };
};
