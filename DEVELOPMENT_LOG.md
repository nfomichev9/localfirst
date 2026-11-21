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

## 2026-11-15 — Evaluation Lab v1: local trials and context preparation

### Delivered scope

User pushed the prior checkpoint and authorized starting the agreed Evaluation Lab.
Recorded implementation boundaries first in `EVALUATION_LAB.md`. Added `/lab` and
navigation from Chat/Usage, using the existing FastAPI, SQLite, vanilla JavaScript,
Markdown/sanitizer, and frame-buffered streaming. No dependencies added.

- Define/save experiments with original prompt, source context, explicit success
  criteria, and optional exact-answer / literal-contains reference checks. Sample
  buttons fill drafts only; no automatic records, inference, or fabricated results.
- Task edits increment a revision. Every context check and trial stores an immutable
  task snapshot, exact submitted input, model, prompt variant, and results. Original
  prompt/context whitespace is preserved. Reference answers never enter generation
  or preparation requests. String checks are labeled as limited evidence.
- Local context preparation returns a validated structured suggestion: sufficiency,
  missing essentials, clarifying questions, assumptions, and proposed prompt. Treat
  task text as material, not procedural instructions; give the model no tools or
  access to other chats/files. Invalid JSON is an operation error with inspectable raw
  output. Users can retry or manually draft a prompt.
- Prepared trials require a reviewed/edited nonempty prompt and explicit acceptance.
  Draft provenance must match the task/revision. New user context is saved separately
  and marked in comparison cards; original trials reject hidden added inputs. Shared
  source context and criteria remain visible. No automatic claim that rewriting alone
  caused improvement when information changed.
- Trial history displays outputs, original/prepared variants, revisions, raw submitted
  inputs, provenance, measurements, mechanical checks, and independent human verdicts.
  Assess each criterion plus overall pass/fail/insufficient-context/uncertain, with
  evidence/rationale. A human pass requires all criteria to pass. Completed inference
  is not a task-success verdict. Human assessment can be corrected later.
- Per-experiment summaries show human passes/assessed trials, summed measured inference
  time (including preparation; excluding user review time), and actual external cost.
  All operations use the same single-generation guard as chat. Stop closes the stream,
  saves partial output and cancellation, and waits briefly for server finalization
  before refreshing history. Restart recovery marks interrupted work cancelled.
- Frontier comparison is explicitly not configured. No cloud credentials, paid calls,
  external judging, code execution, autonomous retrieval, or intelligent routing.

### Persistence and telemetry

`app/lab.py` owns routes, prompt preparation, validation, reference checks and local
inference lifecycle. `app/lab_storage.py` owns content-bearing tasks, operation snapshots
and human reviews. Prompts, references, outputs and notes stay in Lab tables; none go
into the content-free inference ledger.

Telemetry migration 2 transactionally recreates the ledger to make conversation ID
nullable and add a purpose field, preserving all existing columns and records. Lab
calls use `lab_prepare` / `lab_run`, task IDs and operation IDs; chat rows default to
`chat`. Migration 3 adds Lab tables and indexes. No fake conversations are created.
Global Usage includes Lab calls and now says so. Existing chat persistence, model
selection, bounded context, Markdown streaming and feedback remain intact.

### Verification actually executed

- Existing Python suite after backend/migration foundation: **47 passed**.
- Added Lab tests and completed its page: **57 passed**. The first intermediate run
  included a page-route test before lab.html existed; resolved by finishing the UI.
- Final `.venv/bin/python -m pytest -q`: **60 passed**. Covers task/review validation,
  reference non-disclosure, added-context provenance, task revisions and immutable
  snapshots, explicit draft acceptance, exact/contains checks, malformed preparation,
  offline/model failure, persistence/restart, timeouts, direct ASGI disconnect, shared
  chat/Lab locking, whitespace integrity, and telemetry linkage. Includes the actual
  committed v1 schema fixture, field-for-field migration preservation, foreign-key
  checks and a deliberately failed migration proving rollback. One existing non-failing
  Starlette/httpx deprecation warning remains.
- `npm test`: **passed**, including prior Chat/Usage/streaming tests and new Lab browser
  flows for create/save/original run, context check, explicit draft acceptance, edited
  prepared run with added information, human review, reopen/reload, revisions, Stop,
  desktop/mobile layout and no external requests. The browser run caught a history
  refresh race: the HTTP abort completed before SQLite cancellation finalization,
  leaving a stale running card. Fixed with bounded status settling. Also corrected
  the test to use the visible desktop task list instead of the hidden mobile picker.
  Reviewed desktop/mobile screenshots under ignored `test-results/`.
- `.venv/bin/python tests/smoke_lab.py`: **passed against real Gemma 4 E2B**, with an
  isolated temporary database/server. Correct original/prepared arithmetic outputs,
  valid missing-context JSON that identified the absent email body and asked a question,
  real metrics/$0 API cost, identical snapshots after restart, HTTP cancellation and
  no chat pollution. Final warm observations: original 0.11s total/0.05s first content;
  prepared 0.12s/0.06s; context check 1.11s/0.08s. These small observations do not
  establish model quality or a preparation speedup. An earlier real disconnect assertion
  failed; the smoke check now distinguishes a saved cancellation from a response that
  completed before socket closure. The final real disconnect recorded `cancelled`;
  deterministic ASGI/browser tests also verify cancellation during active generation.
- `node --check app/static/lab.js`, `node --check tests/lab-browser.cjs`, Python
  compileall, pip check, and `git diff --check`: **passed**.

### Live activation and remaining limits

Confirmed no active chat/inference attempt. Made an online SQLite backup at
`data/before-evaluation-lab-20261115-155352.sqlite3`, gracefully stopped the known old
server, and started current code on the same loopback port (PID 36846). Verified every
original field in all 13 conversations, 54 messages and 24 inference records against
the pre-migration snapshot; all preserved exactly. Foreign-key check clean; schema
versions now 1/2/3; no sample Lab artifacts inserted into the user's database. Chat,
Usage, Lab and their API routes return HTTP 200. Live Chrome loaded the Lab with Gemma
selected, unsaved trials disabled, and no automatic inference.

Still single-user/single-worker. Context is capped at 4,096 tokens; character limits
bound input size but do not prove token fit. Very long tasks may be truncated by Ollama.
A small model's context check can miss essentials, over-ask, or produce invalid JSON.
Human review and reference checks are the first evaluation tools; there is no frontier
judge, isolated executable-code testing, statistical benchmark runner, audit history
of review edits, or measured cost per independently verified successful task. Selected
history is loaded in process without pagination. Future cloud trials need explicit
opt-in, credentials, spending controls, authoritative billing, and comparable answer
runs; a judge's approval alone is not proof of provider capability.

## 2026-11-15 — Make real chats the Evaluation Lab's default test set

User clarified that everyday conversations should supply evaluations rather than
requiring prewritten example prompts. Shifted the Lab's entry point to a paginated
**Start with a real chat** inbox of completed answers. Added **Evaluate in Lab** under
completed assistant replies, including historical replies without a ledger record.
Manual examples remain available in a collapsed optional section.

### Behavior and provenance

- Selecting an answer previews the original prompt, earlier context and saved answer.
  Review/edit suggested criteria and explicitly create the experiment. Import the
  saved answer as a baseline, reusing its existing measurements. No inference call,
  duplicate ledger entry, automatic grade or fabricated timing is created by import.
  Import is idempotent per assistant message. Source links reopen the conversation.
- Record new chat role/content message inputs in a separate local `chat_inputs` table
  before inference. Telemetry stays content-free. This captures the messages sent to
  Ollama, not its internal context truncation or the full wire/runtime configuration.
- For older turns, reconstruct the last 12 completed messages before that turn's actual
  user prompt; exclude failed/incomplete answers and all future turns. Label these
  inputs **reconstructed**, not recorded. Historical replies without telemetry reuse
  known legacy message counts/latency; unavailable TTFT/generation speed stay null.
- Chat-derived original trials replay the recorded/reconstructed role/content list
  unchanged. Prepared trials retain earlier messages and replace only the last user
  prompt, with new user context separately identified. References are always withheld.
  Criteria chosen after the saved answer are marked post-hoc and withheld from faithful
  original replays. Context preparation can see criteria, but never the current saved
  answer or reference. Source prompt/context edits create a custom variation.
- Imported answers can be assessed immediately. No need to rerun the original to
  obtain a baseline. Source artifacts and trial snapshots remain immutable; replays
  alone create new inference records. Per-experiment recorded-time summaries include
  the reused baseline; global Usage counts the original inference only once.
- Long imported inputs are preserved for assessment/replay. Oversized context checks
  fail with an explicit input-limit message rather than silently trimming source data.

### Persistence and verification

Migration 4 adds source provenance to tasks, role/content input snapshots to Lab
operations, and a separate saved-chat baseline table. It is transactional and preserves
existing tasks/preparations/trials/reviews. Original chat and ledger rows are unchanged.

Executed checks:
- `.venv/bin/python -m pytest -q`: **66 passed**. Added coverage for exact role-preserving
  capture/replay, future-message and failed-output exclusion, reconstruction bounds,
  post-hoc criterion/reference non-disclosure, no-inference/no-extra-usage imports,
  idempotence, added context, baseline reviews, pagination, restart, custom variations,
  migration 4 preserving linked preparations/reviews, and forced-failure rollback.
- `npm test`: **passed**, including existing Chat/Usage/streaming tests and a full chat
  deep-link → saved-answer preview → criterion review → baseline import flow. Confirms
  recorded source, readonly original inputs before import, reused output, unchanged
  global request count, and refreshed inbox links. Corrected the test to await the
  asynchronous inbox refresh before asserting the new Open evaluation button.
- `.venv/bin/python tests/smoke_lab.py`: **passed against real Gemma**, using a temporary
  DB/server. Extended it with a real chat response, import with zero added requests,
  reused output/metrics, and a replay of the recorded messages returning the expected
  arithmetic result. Existing prepared trials, missing-context JSON, metrics, restart
  and disconnect checks passed; disconnect saved `cancelled`. Isolated observations:
  original 6.47s including loading, prepared 0.18s, context check 1.27s, chat replay
  0.13s. These are not comparative benchmarks or evidence of rewriting effectiveness.
- Node syntax checks, Python compileall, and `git diff --check`: **passed**.

### Live activation

Confirmed the main server was idle; created
`data/before-chat-evaluation-20261115-161921.sqlite3`, then gracefully restarted current
code on port 8000 (PID 37388). Compared every preexisting field: all 13 conversations,
54 messages, 25 inference attempts, one Lab task and one Lab operation preserved
exactly. Foreign-key check clean; schema versions 1/2/3/4. The live inbox exposes 27
completed real chat answers. No existing answers were automatically imported or
rerun. Live Chrome confirmed the inbox loads without script errors or automatic
inference. Existing historical inputs remain honestly labeled reconstructed.

Every completed answer is now available as evaluation material. Actual quality labels
still require assessment; no frontier integration or automatic judge was introduced.

## 2026-11-16 — Focus reset and product vision board

User asked to reduce scope and return to focused VS Code work. Captured the current
vision in `VISION.md`, linked it near the top of README/PROJECT_PLAN, and marked older
roadmap expansions as subordinate to this direction. Created an in-conversation vision
board under `docs/vision/localfirst-vision.html` with selectable Chat, Lab, and future
Admin concepts. This is a planning aid, not a new application page or surface.

Core product: simple local chatbot, relevant frontier help for hard requests or
verification, essential context checks, and a compact Lab using real chat answers.
Later: uploads, desktop/folder access, organization, autonomous agents, and product
administration. Ordinary user Settings stay distinct from the future admin space.
Proposed next work is simplifying the existing chat/escalation/navigation rather than
adding more features. Preserve useful existing routing/adapter work and saved data.

Inspected current repository state, including newer routing, provider and Settings
files already present in the workspace. Did not overwrite or remove that work. No app
code, database, model, routing preference, account, or device pairing was changed. The
previous stop-server request remains in force; this task did not launch LocalFirst.
Documentation-only application changes; no runtime tests or paid/model calls needed.

Validation for the vision board: checked fragment structure and JavaScript syntax,
concept selection, saved selection state, and state restoration with a local Node
harness. `git diff --check` passed. No browser-rendering verification is claimed.

## 2026-11-16 — Customer landscape and business-model discovery

User requested a broad list of possible customers and how they use AI, while keeping
LocalFirst's delivery form open. Created `docs/research/customer-landscape-2026-11-16.md`
and `customer-segments.csv`: 30 overlapping segments with likely buyer, workflows,
current surface, bill to verify, candidate local/frontier tasks, placement hypothesis,
interview priority, adoption blockers, evidence status and source references.

Researched primary survey/research sources from the Federal Reserve Banks, Census,
Anthropic, Intuit, SHRM, ABA-hosted industry reporting and Thomson Reuters. Clearly
separated observed broad/sector workflows from inferred buyers, spend and product fit.
Recorded report dates, response periods, vendor/platform bias and sampling limits.
Salesforce's sales-use summary was available in search, but repeated page retrieval
failed; its contribution is explicitly marked search-result-level adjacent evidence.
No interviews, verified invoices, customer savings or willingness-to-pay were claimed.

Proposed interviewing automation agencies, marketing/content agencies with actual
variable spend, and small development agencies before choosing a winner. Include
MSPs as possible channels and fixed-subscription users as contrasts. Compare actual
API/overage costs against fixed plans, bundled software and included credits. Keep
an appropriately optimized cloud baseline and local/setup/support costs in the pilot
criteria. Do not add overlapping segments or incompatible adoption surveys into a TAM.

Added a customer/delivery-discovery section in VISION.md and a research milestone in
PROJECT_PLAN.md. Current chat is a prototype/test vehicle; desktop chat, a supported
companion, an API layer, and shared local deployment remain alternatives to validate,
not four parallel products to build. No app code/settings/database changed, no outreach
sent, no paid/model calls made, and LocalFirst was not started.

Validation: CSV parsed successfully with 30 unique, fully populated 12-column records;
all segments and evidence references appear in the report. `git diff --check` passed.
Application tests were not rerun for this documentation-only research task.

## 2026-11-16 — Product architecture and simple desktop onboarding

User requested a comprehensive architecture with an executive summary, tables and
diagrams, emphasizing no-terminal setup and a one-minute adoption ambition. Created
`ARCHITECTURE.md` and linked `docs/architecture/engineering-notes.md` for technical
requirements. Linked the proposal from README/VISION/PROJECT_PLAN and recorded the
clean-machine packaging proof as the recommended next technical step.

Proposal: one desktop app around the existing UI/FastAPI/SQLite engine, a pinned managed
Ollama runtime, one recommended Gemma, optional local hardware recommendation/manual
entry, consented verified resumable downloads, and local chat without mandatory login.
Keep context/handoff, deterministic permissions/budgets, provider adapters, telemetry
and real-chat Lab in the shared engine. Stage accounts/managed cloud billing, portals,
staff operations, files, organization and workers behind demonstrated needs.

Compared delivery/packaging options and checked primary Tauri, PyInstaller, Electron,
Ollama, Google and Apple documentation. Covered ownership, runtime-origin limitations,
secrets, crash recovery, model/artifact updates, migration/import/export, offline use,
diagnostics and release gates. Separated full cold-install timing from setup effort and
cached-model speed; calculated illustrative 4.6/7.5 GB transfer lower bounds. No new
hardware benchmark, quality result, customer savings or production readiness claimed.

Validation: local link/anchor checks, table-column checks, Markdown parsing with the
existing Marked dependency, diagram fences and transfer arithmetic passed; final
`git diff --check` passed. Mermaid rendering was not tested. Application tests were
not rerun for documentation-only work. No application code, settings, models or data
changed; no paid/model calls, downloads, installations or outreach. No app processes
started or stopped. Read-only inspection found an existing port-8000 listener (PID
44798); this task left it untouched.

## 2026-11-17 — Five-click onboarding and a week of personal use

User clarified that the under-one-minute setup target excludes actual downloads and
should require at most five clicks, with guided onboarding. Updated ARCHITECTURE,
VISION, PROJECT_PLAN, README and the engineering notes to reflect that target. Count
mandatory install/launch/permission actions on the normal recommended path; keep
download wait separate and manual hardware entry as an optional guided branch.

Reordered the immediate milestone around making the existing product comfortable for
about a week of real daily use. Fix observed friction and reuse saved chats/the small
Lab selectively; production packaging is not required to begin. Review everyday
usefulness, context, handoff, history and recovery before considering business work.
Marketing, billing and customer/staff admin surfaces remain deferred. Existing future
architecture boundaries are retained without becoming current implementation tasks.

Documentation-only update. Markdown parsing, local links/anchors, table structure and
`git diff --check` verified; application tests were not rerun. No app code, settings,
data, models or process state changed; no inference, paid calls or installations.

## 2026-11-20 — Local PDF uploads in everyday chat

User chose PDF uploads first and stopped the proposed PowerPoint start. Added **＋ PDF**
and drag/drop to the existing composer, remove-before-send, local reading progress and
Stop, attachment-only summary, page coverage and follow-up questions. The selected PDF
remains available when reopening the conversation. Kept the mobile controls on one row.

Added the pinned, pure-Python `pypdf==7.1.1` dependency and `app/documents.py`. Extraction
runs in a disposable subprocess with timeout/cancellation, CPU and decompression/work
limits. Invalid, encrypted and entirely unreadable/scanned PDFs get clear errors.
Limits: 10 MiB, 150 pages, 300,000 extracted characters. Original file bytes are
discarded; filename and page text are stored in a small local SQLite table. No document
library, original-file archive, OCR, visual chart reading or other formats introduced.

PDF context includes page-labelled text and explicit coverage; long documents select
matching or distributed excerpts. Inputs/history are conservatively bounded in UTF-8
bytes, with a 16K local context window for PDF requests only. Ordinary chat keeps its
existing settings. Raw user questions remain readable, while exact submitted contexts
and coverage are saved for retries and Lab provenance. PDF turns/follow-ups/retries
stay local in every routing mode; automatic/manual cloud handoff is blocked for these
conversations without changing the saved routing preference.

Added `docs/implementation/pdf-chat.md`, updated README/vision/architecture/roadmap,
and added real synthetic-PDF fixtures, API/context/parser tests, browser coverage and
an optional real-Gemma smoke script. Marketing, billing/admin and web work remain
deferred. No actual user document was used for development or testing.

Validation:
- Python suite: **93 passed**. Includes scoped IDs, upload limits, errors, bounded
  retrieval of late pages/Unicode, follow-ups, exact retry/restart context, unchanged
  telemetry on upload, all routing modes remaining local, parser timeout/reaping,
  HTTP upload disconnect releasing the lock, and ordinary/PDF model context settings.
- `npm test`: **passed**, including existing chat/usage/Lab/streaming checks and new
  picker/drop/remove, summary/follow-up, reopening, errors, Stop/retry and mobile checks.
  No browser requests left localhost. Inspected desktop/mobile screenshots; corrected
  mobile wrapping and waited for viewport repaint before screenshots.
- Real `gemma4:e2b` smoke: answered the synthetic PDF's budget as USD 18400 [p. 1]
  and follow-up lead as Riley [p. 2]; restart preservation and $0 external API cost
  passed. This demonstrates the integration, not general PDF-answer accuracy.
- JavaScript syntax, Python compilation and `git diff --check`: passed. The existing
  Starlette TestClient/httpx deprecation warning remains unrelated to this feature.

Live activation: confirmed port 8000 was free and no saved inference/Lab operation was
active. Saved a consistent backup at `data/before-pdf-20261120-212ee98f.sqlite3`, then
started updated Uvicorn on `127.0.0.1:8000` (PID 84841). Verified every preexisting
column/value in all 11 tables: 18 conversations, 74 messages and 35 inference attempts
preserved; foreign keys clean. No synthetic chats/documents were added to the live DB.
Read-only live checks confirmed the PDF controls/routes and installed Gemma. Ollama's
existing process was left running. No paid calls or model downloads were made.

## 2026-11-20 — Simple attachment button

Changed the attachment button's visible label to `+`, with “Attach file” for its
tooltip and accessible name. Updated README instructions. PDF upload behavior is
unchanged. Verified markup and whitespace; no backend restart or new tests needed.

## 2026-11-20 — Settings interface polish

Rebuilt Settings as a compact dark dialog with a side navigation, divided rows,
consistent typography/spacing and a persistent action footer. Kept two sections:
Chat (existing response modes and read-only cloud configuration) and Spending
(existing daily limit, used/reserved usage and analytics link). No account, appearance,
notification, billing or placeholder controls added. Specification:
`docs/implementation/settings-polish.md`.

Used native controls and keyboard-accessible tabs, responsive horizontal navigation on
mobile, Escape/close back to chat, unsaved-change tracking, Reset, and clear loading/
error/retry states. Save still uses the existing API and explicit consent for automatic/
cloud-only policy changes; unchanged saved policies do not show an unchecked permission
prompt. Disabled unavailable cloud choices while preserving previously saved modes.
Usage failures display unavailable rather than guessed zero. Provider readiness says
configured, not connected, and the main page no longer exposes environment-variable
setup instructions. PDF conversations' existing local-only behavior is explained.

Validation: **15 routing API tests passed**; the full `npm test` browser suite passed,
including new Settings save/reset/reload, consent, currency limits, keyboard tabs,
Escape, unavailable provider/usage, JSON/HTML failure recovery and mobile checks.
Existing Chat/Usage/Lab/PDF/streaming tests passed with zero external browser requests.
Updated the mobile navigation assertion to include the collapsed sidebar; corrected a
PDF test timing race by waiting for upload completion before asserting routing text.
Inspected desktop/mobile screenshots for both sections and read-only live Settings.
JavaScript syntax and `git diff --check` passed.

Only frontend, tests and documentation changed in this task. Existing backend/schema,
saved preferences and chat data were not altered. All test writes used isolated test
data; live inspection was read-only. No inference, paid requests, dependencies or
server restart needed. Updated README usage instructions; changes appear on refresh.

## 2026-11-20 — Repair manual OpenAI handoff and connection setup

Reproduced the reported button failure on an eligible saved text-chat reply: HTTP 503.
The live routing preference was manual handoff with a $0.10 daily cap, but the server
had neither an API key nor a cloud model. The shell and launch environment contained
no configuration to restore. User confirmed they have an OpenAI API key; did not ask
them to put it in chat or access Codex/browser credentials.

Added a real Settings connection editor and scoped `/api/provider/connection` endpoints.
Verify key/model access through OpenAI model metadata, without a completion. Persist
keys only in native macOS Keychain using pinned `keyring==25.7.0`; SQLite stores the
model and opaque credential reference. Existing environment setup remains supported.
Secure-storage/verification errors preserve previous configuration; connection edits
are blocked during generation. Validation errors are sanitized so malformed requests
cannot echo keys. No key is returned by an API or saved with messages. The editor
clears the field on save/error/cancel/navigation. Native in-app storage is Mac-only;
there is no plaintext fallback.

Missing provider/limit errors now include typed action headers, inline feedback beside
the clicked answer, and a working Settings link. Connection setup returns to the same
conversation. Kept explicit preview/edit/confirm and spending guards; PDFs stay local.
Manual preparation now has a bounded, clearly labelled source-based fallback when
local JSON/availability fails. Original request text is preserved; oversized briefs
still require editing before send. Automatic preparation remains fail-closed.

Verification:
- **102 Python tests passed**, including secure-reference restart behavior, no secret
  in SQLite/responses, validation/auth/storage errors, metadata-only checks, actionable
  handoff failures, source fallback, plus existing routing/PDF/Lab/telemetry coverage.
- Full `npm test` passed. Added real local API browser coverage for connect/error,
  exact conversation return, prepare/edit/cancel/confirm, streaming, duplicate prevention,
  stopping preparation, malformed local output and cloud failure preserving the draft.
  Test server explicitly uses synthetic keys, in-memory secrets and fake cloud functions;
  no real provider credentials can be inherited or sent by that harness.
- Native Keychain roundtrip passed using one synthetic entry in a separate test
  namespace, then deleted; no existing credentials accessed. Real Gemma answer/preview
  passed with a temporary DB and synthetic question; the source fallback was needed.
  No cloud completion was dispatched. This is not validation of the user's API key.
- Inspected blank-key live connection editor on desktop/mobile. JS syntax, Python
  compilation and `git diff --check` passed. Primary OpenAI model/metadata API and
  Keyring documentation checked; existing price catalog was not expanded.

Saved `data/before-handoff-fix-20261120-4e5c2a86.sqlite3`, verified the idle owned server,
and restarted it to load backend changes (PID 85916 on localhost:8000). All preexisting
values across 12 tables preserved: 20 conversations, 86 messages, 41 inference attempts;
foreign keys clean. Saved manual mode/$0.10 cap unchanged. Live connection endpoints
and editor verified read-only; no credential configured automatically. User's remaining
step is entering their API key in Settings. No paid calls, real chat transmissions,
model downloads or business/admin expansion were performed.

## 2026-11-20 — API key in a local configuration file

User prefers editing a file over shell commands or Keychain setup. Created the root
`.env` with a blank `OPENAI_API_KEY=` and `OPENAI_MODEL=gpt-6-luna`, and explicitly
ignored it in Git. Added pinned `python-dotenv==1.2.1`; the default app reads this
file on startup without variable interpolation or changing the process environment.
Shell values take precedence over file values; a configured key takes precedence
over a saved Keychain connection. Blank keys retain the Keychain fallback. Custom
databases do not inherit the project file unless explicitly supplied, keeping test
and smoke environments isolated. The Settings connection editor remains available.

Updated README with the file workflow. All 26 connection/routing tests passed,
including file loading, literal credential text, no credential in API responses or
SQLite, configuration precedence, blank fallback, and test-database isolation.
`git check-ignore .env` and `git diff --check` passed. No real key read or configured,
no paid requests, no routing/budget changes, and no live server restart. Save the key
in `.env` and restart LocalFirst to load it.

User then entered the key. Verified authentication and access to the selected model
through OpenAI's metadata endpoint; no completion requested or chat content sent.
Backed up the idle live database to `data/before-env-restart-20261120-215257.sqlite3`
and restarted the owned LocalFirst server (PID 86321, localhost:8000). Live health
and settings checks passed: provider ready, manual handoff and $0.10 daily cap retained.
All 20 conversations, 86 messages and 41 inference attempts preserved. Key contents
were not printed or included in API responses or documentation.

## 2026-11-20 — Make the current Settings page reachable from home

User reported that Settings still looked old when opened from the home page. Traced
the live home link to `/settings`; the returned document, CSS and JS already matched
the current redesigned files. Could not inspect the user's browser directly, so a
stale browser cache remains a possible explanation rather than a confirmed cause.

Versioned the home Settings link and its CSS/JS URLs to bypass previous cached copies.
Added `Cache-Control: no-cache` to home and Settings documents/assets so future
navigation revalidates them. No visual redesign or preference changes in this fix.
Extended the browser coverage to click Settings from home and verify the styled
dialog, rather than only visiting the Settings URL directly. A focused API check
also follows the actual link and checks the document, asset responses and caching.

Focused API test and full `npm test` passed, including Settings behavior/mobile,
handoff, chat streaming, PDFs and Lab; inspected the generated Settings screenshot.
Backed up the idle DB to `data/before-settings-cache-20261120-215653.sqlite3` and
restarted LocalFirst (PID 86610). Live home navigation/asset responses verified;
OpenAI readiness, manual handoff/$0.10 cap, 20 conversations, 86 messages and 41
inference attempts preserved. No paid requests or chat content sent externally.

## 2026-11-20 — Opt-in web search for local chat

Added a globe/Search toggle beside **+**, off initially and reset when opening or
starting a chat. The current message alone becomes the query (600-character maximum).
DuckDuckGo's public HTML search returns up to four bounded excerpts; its public Lite
view is a single fallback under the same 15-second deadline. No new dependency, API
key, paid search/model call, arbitrary page fetch, or website operation was added.
Result URLs are unwrapped and validated; response size is capped at 256 KiB. Provider
errors/empty results stay visible instead of generating an ungrounded answer.

The selected local model receives dated, bounded source context with explicit
untrusted-data and citation instructions, using a 16K context window and 12KB input
budget. Web turns always use local inference without changing the saved routing
preference; automatic/manual cloud handoff does not dispatch them. PDF chats keep
Search disabled and reject search requests at the backend. Ordinary chat stays as
before when Search is off. Added loading protection while switching model catalogs.

Search occurs within the cancellable response stream. Stop closes in-flight search
HTTP work; errors/cancelled replies remain retryable. SQLite saves source/query/time
metadata and actual model input. Retries reuse a completed source snapshot and only
repeat retrieval if the first search never completed. Added a nullable `web_context`
column to `chat_inputs`; old records stay intact. Existing telemetry includes search
time in response latency/first-token time; generation speed stays provider-measured.

Answers show a persisted Sources disclosure independent of model-generated claims.
Numeric citations such as [1, 2] link to those retrieved sources during rendering,
including streaming, while raw answer text and code blocks remain unchanged. This
uses the existing stable Markdown DOM patcher and no new animation/framework.
Versioned the changed assets and enabled revalidation to avoid the recent Chrome
cache problem. README and `docs/implementation/web-search.md` describe the scope.

Verification:
- Full Python suite passed; focused coverage includes both result formats, wrapped/
  unsafe links, fixed search endpoints/query scope, size/time limits, cancellation,
  errors, context bounds, local-only routing in all four modes, PDF isolation,
  source restart/retry behavior, and Ollama context options.
- Full `npm test` passed, including new Search selection, grounded reply, linked
  numeric citations, Sources persistence, mobile, Stop during retrieval, retry,
  provider error and ordinary-chat recovery. Final targeted web/PDF browser runs
  also passed after grouping the composer controls; inspected desktop/mobile renders.
  Browser tests use fake search/cloud adapters and temporary databases only.
- `tests/smoke_web.py` passed with an actual public GTA VI search and installed
  Gemma 4 E2B, including a Rockstar result, source references, local telemetry and
  source persistence across restart in a temporary DB. Initial live retrieval hit
  rate limiting; added/tested the bounded Lite fallback. Gemma sometimes produced
  numeric citations without Markdown links, motivating deterministic link rendering.
  The check proves retrieval/integration, not that every generated claim is correct.
- JS syntax, Python compilation and `git diff --check` passed. No real user chat,
  PDF content or API key was sent to a search provider; only synthetic smoke queries.

Backed up the idle live DB to `data/before-web-search-20261120-222130.sqlite3` and
restarted LocalFirst (PID 87558, localhost:8000). Live control/API/assets and saved
OpenAI readiness/manual mode/$0.10 cap verified. Compared hashes of every preexisting
column/row across 13 tables: all preserved, including 21 conversations and 91 messages;
foreign keys clean. The app is running with Search available on refresh.

Limitations: excerpts are not full-page reading; indexed information can lag or
conflict, and local-model synthesis can still be wrong. The public provider can
rate-limit requests or change markup. A dedicated search API can later replace the
small search adapter without changing the chat UI or local inference pipeline.

## 2026-11-20 — Next session priorities

User set two priorities for tomorrow, November 21:
1. Pull the repo onto their older MacBook and try local models there. Inspect actual
   chip/RAM and measure setup friction, memory use, first-token time, generation
   speed and answer quality before selecting models or making performance claims.
2. Clean up the product UI into a coherent, clean, sleek, easy-to-use and powerful
   workspace with the polish of frontier chat products. Long-term positioning is
   corporate-focused; product usability remains the immediate priority.

Saved this agenda at the top of PROJECT_PLAN.md. No implementation, downloads,
remote-machine setup, scheduling or business/admin expansion performed in this turn.
