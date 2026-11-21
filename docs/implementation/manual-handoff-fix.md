# Manual handoff reliability

November 20, 2026. Reproduced the live button returning HTTP 503 because the saved
mode is manual handoff but the server has no OpenAI key or model. Neither the launch
environment nor a project configuration supplies them. No cloud request was made.

- Give Settings a real OpenAI connection editor, using the existing supported model
  catalog. Verify credentials/model with a model-metadata request, not a completion.
- Store keys only in native macOS Keychain; store model/credential reference in SQLite.
  Preserve environment-based setup. Never return, log or put keys in command arguments.
  Load the app-owned credential after restart; keep local chat usable if storage fails.
- Make the handoff click surface missing connection/budget with an actionable Settings
  link near the clicked answer. Keep Stop and errors visible; no silent fallback/send.
- Test the complete browser path: local reply, prepare, edit, cancel, confirm, streamed
  frontier reply, duplicate prevention and failure recovery. Use fake cloud responses;
  preserve explicit confirmation and spending checks. PDFs stay local.
- Verify real Gemma brief preparation with a synthetic conversation. If local JSON is
  unusable, offer a clearly labelled reviewable source-based brief rather than a dead end.
- Do not use Codex credentials or browser sessions. This existing connection uses the
  OpenAI API; ChatGPT sign-in is a separate integration, not silently interchangeable.
