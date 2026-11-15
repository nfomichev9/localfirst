# Development log

## 2026-11-15 — MVP 1

### Context and decisions

Read `PROJECT_PLAN.md` and `LocalFirst_Project_Instructions.md`. `LocalFirst_Project_Brief.md` was absent. Followed the user's narrower MVP 1 scope. Verified Python 3.13.2, Ollama connectivity, and installed `llama3.2:3b` (Q4_K_M); did not download models. Checked the official Ollama chat/model-list and FastAPI response documentation.

Implemented these slices in one local-only application:

- Connection: FastAPI health/model discovery, explicit offline/no-model UI, refreshed installed-model selector with `llama3.2:3b` preference.
- Streaming: async httpx Ollama adapter, newline-delimited `start`/`delta`/`done`/`error` events, fetch streaming, AbortController stop, upstream closure, one response at a time. Added inactivity and total timeouts, explicit malformed/truncated/empty-stream handling, and friendly HTTP/provider errors.
- Persistence: sqlite3 conversations/messages, chronological message IDs, title from first prompt, completion/error/stopped status and metrics. Interrupted streaming records are marked stopped on startup. Latest 12 completed messages plus prompt form context; no summarization. Partial failed/stopped assistant responses are excluded from context.
- Interface: dark two-column responsive workspace, saved conversation navigation, new conversation, loading/streaming states, automatic scroll, keyboard input, locally generated response metadata, truthful $0 external API spend label, and local compute cost note. All model/user content uses textContent, not HTML injection.

SQLite uses short-lived connections and foreign keys with WAL. Runtime data stays under the ignored `data/` directory. No cloud adapter, routing, authentication, agent/tool execution, telemetry, or scheduled work was added. The Sites skill was used only for its local-only workflow; no Site was registered or published. Temporary test servers are terminated by the smoke script.

### Executed verification

- `.venv/bin/python -m pytest -q`: **24 passed** (0.30 seconds in final run). Tests mock Ollama, including disconnect/cancellation, concurrency rejection, actual bounded follow-up payloads, persistence after recreation, empty replies, offline/timeouts, invalid/truncated data, validation, and local origin/host restrictions.
- `node --check app/static/app.js`: **passed**.
- `.venv/bin/python -m compileall -q app tests`: **passed**.
- `.venv/bin/python -m pip check`: **passed**, no broken requirements.
- `.venv/bin/python tests/smoke_local.py`: **passed against real local Ollama**. A temporary localhost FastAPI server served HTML/CSS and discovered the installed model. The first response arrived in 5 deltas (first delta 0.69 seconds, completion 0.80 seconds, 6 output tokens). The follow-up recalled “juniper” in 2 deltas (first delta 0.08 seconds, completion 0.13 seconds, 3 output tokens). These are single observations, not benchmarks. Conversations were identical after terminating/restarting the server. Closing an active HTTP stream persisted a stopped partial reply. Server and temporary database were cleaned up.

The sandbox initially blocked localhost access, dependency network access, and socket binding. Approved escalated commands enabled those checks; failures were not treated as successful verification. Dependencies are installed in this workspace's `.venv`; no global Python packages were changed.

### Known issues and next check

No browser automation or visual inspection was performed. Open the page manually to verify the desktop/mobile layout, input, stop button, model selector, scrolling, and restored sidebar history. HTTP behavior and real stream cancellation are verified.

One non-failing Starlette TestClient deprecation warning advises switching its test client integration from httpx to httpx2. Keep the existing lightweight client for this MVP; revisit with a future dependency update. No test failures remain.

This is a single-user, single-worker development app. History is plaintext, partial output is only saved on orderly termination of a request, and context is message-bounded rather than token-budgeted. Very large prompts may be truncated by Ollama's 4,096-token context. Model output remains plain text. No further milestones have been started.

Next: run the browser acceptance check and try ordinary conversations on the M4. Record model quality and latency observations before choosing any later milestone.
