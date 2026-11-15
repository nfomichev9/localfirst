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

## 2026-11-15 — Markdown, inference telemetry, and usage analytics

### Implementation and decisions

Extended the existing FastAPI/SQLite/vanilla-JavaScript application. No cloud calls,
routing, external analytics, new runtime Python dependencies, or frontend framework.
Existing user database files were not modified during development; tests use isolated databases.

- Markdown: local vendored Marked 18.2.0, DOMPurify 3.4.18, and Highlight.js 11.12.0, pinned with integrity hashes in package-lock.json and licenses under `app/static/vendor/`. Parse, sanitize with a narrow HTML allowlist, highlight known fenced-code languages, sanitize highlighted spans. Streamed partial responses and reopened history use the same renderer. SQLite retains raw Markdown; user text stays plain. Images/embedded media are excluded to prevent remote fetches. No runtime CDN dependencies.
- Ledger: `app/telemetry.py` owns a content-free, provider-independent inference record and aggregation service. The additive, idempotent schema migration leaves legacy conversations/messages intact and adds indexes plus a schema version record. Separate request IDs link to conversation and assistant message IDs. Record provider/model/location, timestamp, latency, TTFT, input/output counts, generation duration/speed, actual external API cost, running/success/error/cancelled status, optional feedback, and nullable task/benchmark IDs with routing mode for later evaluation.
- Measurement: Ollama count/nanosecond normalization stays at the adapter boundary. Generation speed uses actual eval duration. Missing/invalid measurements remain null. TTFT measures first nonempty response content arrival, not an assumed token boundary. Latency includes model discovery and context preparation. Interrupted running attempts become cancelled on startup without fabricated durations/counts. Finalization is idempotent. Local API cost is always zero; generic cloud ledger costs remain unknown unless supplied (tested with synthetic records only).
- Admitted attempts include discovery/model availability failures; input validation, missing conversations, and busy rejections are excluded. Empty generation is an error, not a successful task. No provider exception text or message content goes in the ledger. Success is inference completion, not task success.
- Chat tracker: compact expandable bar with model, location, response latency, total tokens when both counts exist, API cost, status; details show input/output, tok/s, TTFT, provider. Optional helpful/unhelpful feedback persists independently. Legacy responses show unavailable telemetry.
- Dashboard: `/usage`, linked from chat. Real persisted overview/performance cards, UTC daily request/local/cloud/token/cost charts with hover and keyboard inspection, rolling period/model filters, refresh, model breakdown, sample coverage, empty/error states, responsive layout. Empty days between observations remain visible. Percentages use successful requests; failure/cancellation rates use all admitted attempts. Latencies include finished errors/cancellations with known times. P95 uses nearest rank and requires 20 samples. No fabricated cloud-only baseline or savings.

### Staged verification actually executed

1. Existing Python suite after additive schema and Markdown changes: **24 passed**.
2. Telemetry/tracker tests before dashboard: **41 passed**, 1 dashboard test deselected until its page existed. The first full telemetry suite exposed the not-yet-created dashboard page; resolved by completing that stage.
3. Completed dashboard/API suite: **42 passed**. Browser tests found the empty `model=` query incorrectly filtered out all records. Fixed normalization and added a regression assertion.
4. Final Python suite after generic cost handling and daily gap tests: **44 passed**. Includes legacy-schema migration twice, raw Markdown preservation, restart recovery, idempotence, null/invalid metrics, exact averages/median/P95, sample threshold, time/model filters, costs, feedback, failure/offline cases, and ASGI disconnect telemetry. One existing non-failing Starlette/httpx deprecation warning remains.
5. `npm test`: **passed** in installed headless Chrome against a temporary fake-provider server/database. Covers Markdown headings/lists/emphasis/inline/fenced code/tables/links, highlighting, streaming and historical rendering, malicious HTML/URLs and every partial prefix of an attack fixture, compact/detailed metrics, persisted feedback, dashboard/chart interaction, empty dashboard, period/model changes, mobile width, and zero external browser requests. Desktop/mobile screenshots saved in ignored `test-results/` and visually inspected. Development-only Playwright 1.65.1; npm install audit reported **0 vulnerabilities** for the pinned packages.
6. `node --check` for app.js, markdown.js, usage.js; Python compileall; pip check: **passed**.
7. `.venv/bin/python tests/smoke_local.py`: **passed against real local Ollama**, including real provider generation-speed and TTFT fields, $0 actual cost, persisted follow-up context after server restart, HTTP disconnect/cancelled ledger record, and aggregate count/local share. Single observations: first reply 8 deltas, first content 2.22s, total 2.40s, 9 output tokens; follow-up 2 deltas, first 0.09s, total 0.14s, 3 output tokens. These are not benchmarks. Temporary servers/databases were cleaned up; existing conversations and Ollama were retained.

Network downloads, socket binding, local Ollama access, and Chrome launch required
sandbox escalation. Initial blocked commands were not counted as passing checks.

### Known limits and first-cloud prerequisites

Still a single-user, single-worker development app; SQLite history is plaintext.
Abrupt termination loses in-flight partial content/measurements; restart records
cancellation with unknown metrics. No legacy telemetry backfill. Analytics aggregates
selected records in process; a much larger ledger will need SQL aggregation/pagination.
No task-success evaluator, benchmark runner, pricing baseline, token-budgeted history,
or meaningful cost-per-successful-task metric yet. Feedback is a lightweight quality
signal only. Browser coverage is Chrome; other browsers and broader accessibility
review remain future checks.

Before a first cloud model: explicit opt-in and private-content disclosure, credential
handling, hard spending limits, a cloud adapter with normalized usage and authoritative
USD costs, cancellation/retry/billing reconciliation, provider contract tests, and a
versioned defensible cloud-only baseline. Before routing decisions: comparable task IDs,
repeatable local/cloud/hybrid trials, task success/quality criteria, and evaluation of
cost, latency, reliability, and quality together. No such integration was implemented.

## 2026-11-15 — Resolve live server/frontend version mismatch

User reported correctly rendered Markdown alongside missing response telemetry and
`/usage` returning `{"detail":"Not Found"}`. Inspected the actual loopback server:
PID 31385 had started at 11:07:41, before the telemetry implementation. Both `/usage`
and `/api/usage` returned HTTP 404, and the active database had only the original
conversations/messages tables. The running Python process retained the old routes
while StaticFiles served the updated JavaScript. This was an outdated running server,
not a failed telemetry migration or inference-performance change.

Confirmed zero active streaming messages, made a SQLite online backup in ignored
`data/before-telemetry-restart-20261115-135953.sqlite3`, and gracefully restarted the
identified server on the same loopback port with current code. The replacement runs
in the background with logs in ignored `data/server.log`. Health, `/usage`, and
`/api/usage` now all return HTTP 200; the new ledger correctly starts with zero
attempts. Historical replies were retained and were not assigned invented telemetry.
README now explicitly explains restart requirements after backend updates.

## 2026-11-15 — Start the lightweight Gemma trial

User chose Google Gemma and explicitly asked to start with the lightweight model.
Installed `gemma4:e2b` through Ollama (current tag downloaded approximately 7.5 GB).
No larger Gemma, cloud model, or paid API was installed. Llama remains installed.
Reviewed the official Ollama Gemma tag and thinking-controls documentation first.

Added `app/models.py` with an explicit installed-model preference: Gemma E2B,
then Llama, then the first available model. `/api/models` returns the actual
installed default and a display label, **Lightweight · Gemma 4 E2B**. API requests
without a model use that preference; explicit selections are preserved, and a
missing explicit model remains an error rather than silently switching inference.
The selector retains raw model IDs for requests and telemetry. Refreshing the
model list preserves a deliberate selection; reloading the page chooses the default.

Gemma 4 requests use `think: false` for this initial responsiveness trial, via the
Ollama adapter only. Kept the 4,096-token context and 2,048-token generation limit.
No context/routing/quality claims changed. Updated the opt-in real smoke script
with `--model` so it can verify any installed model, including this trial.

Verification executed:
- Python suite: **47 passed**, including Gemma preference, explicit Llama selection,
  missing-model rejection, persisted Gemma model identity, and adapter thinking policy.
- `npm test`: **passed**, with isolated fake-provider Chrome regression coverage.
- `node --check app/static/app.js`, Python compileall, and `git diff --check`: **passed**.
- `.venv/bin/python tests/smoke_local.py --model gemma4:e2b`: **passed against real
  Ollama**, using a temporary database/server. Streaming, actual generation metrics,
  $0 API cost, follow-up recall, restart persistence, and disconnect/cancellation
  telemetry all passed. First short reply: 3 deltas, first content 6.68s, completion
  6.72s, 3 output tokens. Follow-up: 3 deltas, first content 0.31s, completion 0.37s,
  3 output tokens. Initial latency includes model loading; these are observations,
  not benchmarks or evidence of general answer quality.
- Confirmed the main app had no active streaming message, made another SQLite backup
  under ignored `data/`, and gracefully restarted it with current code on port 8000
  (PID 34645). Verified Gemma default, Llama still available, usage page/API HTTP 200,
  and the real Chrome selector default/label. Existing conversations were retained.

Next: user trials of ordinary requests and helpful/unhelpful feedback. The earlier
Gemma reliability issues are not considered resolved merely by these small smoke
checks. No larger Gemma download or tier system was added in this step.

## 2026-11-15 — Smooth chat streaming and reading polish

Focused frontend change only for this task: backend, Ollama requests, conversation
storage, telemetry schema/calculations, and model configuration were left intact.
No packages or frameworks added. Inspected existing frontend first: every delta
parsed/highlighted all Markdown, replaced every content child, rebuilt metrics, and
forced a smooth scroll to the bottom. Completion also focused the composer, clearing
text selected for copying.

Changes:
- Added a small `createStreamBuffer` helper using requestAnimationFrame. Each frame
  renders the latest complete received buffer once, coalescing bursts without a
  character/word timer or artificial pacing. Completion, errors, and Stop synchronously
  flush pending text, cancel the scheduled frame, and close the buffer. Late deltas
  cannot update a stopped response; post-stop metadata reload never replaces its text.
- Kept Marked/DOMPurify and the sanitization allowlist. Patch changed Markdown DOM
  nodes instead of replacing all children. Unchanged blocks, code scroll containers,
  and text nodes survive updates; growing text uses suffix edits to preserve earlier
  selection offsets. Cache highlighting for unchanged code blocks between renders.
  Markdown is still parsed per rendered batch to support incomplete delimiters,
  tables, and reference links resolving earlier text; this is not a new parser.
- Content and metadata update independently. Metrics are not rebuilt on each delta,
  identical raw content is not rendered again on final metadata updates, and completion
  does not focus the textarea when response text is selected.
- Follow output only while the user remains within 64px of the bottom and is not
  selecting response text. Scroll updates happen with frame paints, with no queued CSS
  smooth-scroll animations. Scrolling up pauses following; returning to the bottom
  resumes it. Sending a prompt and opening history still intentionally scroll to end.
- One subtle 160ms entrance on the first nonempty streamed content (94% to 100%
  opacity, 2px movement); no animation for subsequent batches or historical messages.
  Reduced-motion preference disables it. Adjusted assistant typography to 15px,
  1.75 line height, maximum 72ch, with measured paragraph/list/heading/code spacing.

Verification actually executed:
- `npm test`: **passed** in headless Chrome with isolated fake-provider databases.
  New `tests/streaming.cjs` covers deterministic burst/frame coalescing, pending text
  flush without a frame firing, closed-buffer rejection of late data, every partial
  prefix of Markdown/table/code/reference-link fixtures matching full final rendering,
  Unicode intact with each received batch exactly once, stable paragraph/code/metrics
  node identity, selection both in earlier blocks and a growing paragraph, no forced
  scrolling while reading above, following at bottom, Stop freezing partial content,
  final partial output on errors, reduced motion, and mobile chat width. Existing
  Markdown/XSS, historical rendering, highlighting, feedback, and dashboard checks
  also pass. The first run caught completion autofocus clearing selected text; fixed
  and reran the suite successfully. Reviewed the updated desktop chat screenshot.
- Python suite: **47 passed**; existing Starlette/httpx deprecation warning remains.
- `node --check` for app.js, markdown.js, streaming.js, and streaming.cjs; and
  `git diff --check`: **passed**.

Static files are served from disk by the running app, so a browser refresh applies
this change without restarting the backend. No extra real-model generation was
needed for this frontend change; deterministic burst/slow/error streams exercise
its lifecycle. Legitimate Markdown reinterpretation can still change layout when
unfinished syntax closes. Full Markdown parsing remains per batch (at most once
per animation frame during generation), rather than a specialized incremental parser.

## 2026-11-15 — Capture deferred local chat organization feature

Recorded the user's idea in `PROJECT_PLAN.md` as a final, deferred roadmap milestone:
a Settings entry during local-agent setup that organizes existing LocalFirst chats
into in-app folders and creates a searchable local index. Proposed an initial pass
with preview/edit/apply/undo, preserved source conversations and manual choices, and
user-triggered reruns. Scheduling/end-of-session automation remains undecided.
No organizer, settings UI, background agent, database changes, or actual chat moves
were implemented. Documentation-only change; checked with `git diff --check`.

## 2026-11-15 — Agree next product direction: Evaluation Lab

User confirmed the vision of a separate testing space with explicit task-success
criteria, local responses, optional frontier comparison/judging, and local checks
for missing context before escalation. Recorded this as the next milestone in
`PROJECT_PLAN.md`, including the first original-versus-prepared-prompt experiment.
Keep human judgments and objective checks distinct from model judgments, and measure
clarification overhead plus end-to-end cost/latency. No Lab, cloud integration,
paid inference, or automatic routing was implemented or activated. Documentation
only; `git diff --check` passed.
