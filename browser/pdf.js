import {getDocument, GlobalWorkerOptions} from './pdf.min.mjs';

GlobalWorkerOptions.workerSrc = new URL('./pdf.worker.min.mjs', import.meta.url).href;

export async function readPDF(file, signal) {
  if (file.size > 10 * 1024 * 1024) throw new Error('Choose a PDF smaller than 10 MB.');
  const data = new Uint8Array(await file.arrayBuffer());
  signal?.throwIfAborted();
  const loading = getDocument({data, isEvalSupported: false, useWasm: false, disableFontFace: true});
  const abort = () => { loading.destroy().catch(() => {}); };
  signal?.addEventListener('abort', abort, {once: true});
  try {
    const pdf = await loading.promise;
    if (pdf.numPages > 80) throw new Error('Choose a PDF with 80 pages or fewer for browser chat.');
    const unreadable_pages = [], pages = [];
    for (let number = 1; number <= pdf.numPages; number++) {
      signal?.throwIfAborted();
      const page = await pdf.getPage(number);
      const {items} = await page.getTextContent();
      const text = items.map(item => item.str || '').join(' ').replace(/\s+/g, ' ').trim();
      if (text) pages.push({number, text: text.slice(0, 4000), truncated: text.length > 4000});
      else unreadable_pages.push(number);
      page.cleanup();
    }
    if (!pages.length) throw new Error('This PDF has no readable text. Scanned pages need OCR before upload.');
    return {pages, unreadable_pages, page_count: pdf.numPages};
  } catch (error) {
    signal?.throwIfAborted();
    const detail = error?.name === 'PasswordException' ? 'Choose a PDF without a password.'
      : error?.name === 'InvalidPDFException' ? 'This file is not a readable PDF.' : error.message;
    throw new Error(detail);
  } finally {
    signal?.removeEventListener('abort', abort);
    await loading.destroy().catch(() => {});
  }
}
