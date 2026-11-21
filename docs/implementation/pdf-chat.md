# PDF chat — focused implementation

November 20, 2026. Add one PDF attachment to the existing composer. Extract text
locally with pypdf; no original-file archive, OCR, web browsing or file-manager UI.
Save page text and filename in local SQLite so questions/retries/reopening work.

- Upload raw PDF bytes to a conversation-scoped endpoint, limited to 10 MiB/150 pages.
  Parse in a disposable subprocess with a timeout and cancellation; never execute PDF
  actions or resolve external resources. Reject invalid/encrypted/unreadable files.
- Attaching a PDF binds it to the next user message. Later questions reuse the latest
  attached document; removing an unsent attachment restores the previous document.
- PDF turns stay local regardless of the ordinary routing preference. Protect retry,
  automatic and manual handoff paths too; leave saved routing settings unchanged.
- Assemble bounded page excerpts and recent history, with page labels and an explicit
  coverage report. Record the exact submitted messages for retries/Lab. Use a 16K
  local context window only for PDF requests; leave ordinary chat unchanged.
- File picker and drag/drop, filename/page status, remove-before-send, progress/error
  states, Stop and keyboard access. Attachment-only Send requests a summary.
- Test real PDF extraction, malformed/encrypted/scanned/large files, upload limits,
  scoped IDs, follow-ups/retries/restart, coverage, cloud isolation, cancelled parsing
  and generation, browser flow, and a synthetic document with installed Gemma.

Limits are implementation bounds, not supported-document quality claims. Text
extraction does not reproduce charts, images, complex tables or page layout. Report
unreadable pages and selected excerpts instead of implying a full visual review.
