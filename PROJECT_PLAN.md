# LocalFirst — MVP 1 Implementation Plan

> Current scope and priorities are defined in [VISION.md](VISION.md), updated November 20, 2026. The milestones below retain implementation history; older expansion plans do not override the focused direction. Simple local PDF text uploads are now in scope for daily use.

> Next: make the existing product comfortable for a week of personal daily use, then review real friction before business work. [ARCHITECTURE.md](ARCHITECTURE.md) defines later packaging/onboarding: at most five clicks, under one minute excluding downloads. The browser/Python setup below remains the current implementation.

## Next session — November 21, 2026

| Priority | Work | What we want to learn or achieve |
| --- | --- | --- |
| 1. MacBook trial | Pull the repo onto the user's older MacBook, check its chip/RAM, get the app running and try suitable local models. | Validate setup on a second machine and find a useful balance of answer quality, memory use, first-token time and generation speed. Record actual measurements before choosing defaults. |
| 2. Product UI polish | Review the current chat, composer, navigation, sources and Settings as one workspace, then improve their visual consistency and interaction. | A clean, sleek, easy-to-use and powerful work environment with the polish expected from frontier chat products. Keep everyday controls obvious and secondary details accessible without clutter. |

Long-term product direction: a corporate-focused AI workspace built around local
inference and selective frontier help. The immediate work is the product experience;
marketing, billing and customer/internal admin remain deferred. Today’s implementation
already includes PDF text uploads, opt-in web search and optional OpenAI handoff.
The original MVP milestones below are implementation history, not the current task list.

**Status:** Ready to implement  
**Machine:** Apple M4 Mac mini, 16 GB unified memory  
**Priority:** Make local chat stable before introducing paid cloud inference or routing  
**Related document:** `LocalFirst_Project_Brief.md` (long-term vision; this plan governs the immediate milestone)

## 1. Objective

Build a small browser-based chatbot that uses **only the locally running Ollama service**. The first demonstration is:

> Open the app in a browser → select an installed Ollama model → send a message → see the response appear progressively → see elapsed time and token counts → reload/restart and find the conversation still saved.

This is a **single-user local development app**, not a deployed or distributable product yet.

## 2. Tech stack — favor simplicity

- **Backend:** Python 3 + FastAPI
- **Local model provider:** Ollama HTTP API, using `/api/tags` to enumerate installed models and streaming `/api/chat` for responses
- **Persistence:** SQLite (Python standard library `sqlite3` is sufficient)
- **Frontend:** Plain HTML, CSS, and JavaScript served by FastAPI; no React, Vite, Electron, or other frontend build step
- **HTTP client:** An established async Python HTTP client; close streams and propagate cancellation correctly
- **Tests:** pytest with a fake/mocked Ollama server or transport so automated tests do not require model downloads or inference

Choose documented, currently supported dependencies. Do not assume a model tag; discover installed models at runtime. Keep backend inference behind a small `OllamaAdapter` interface so a future cloud adapter can be added without rewriting the UI or persistence.

## 3. Required features

1. **Chat UI:** Attractive but restrained two-column layout (conversation list + message pane), a message composer, send/stop controls, loading/streaming states, and reasonable mobile sizing. Render model output safely as text; do not inject raw HTML.
2. **Model connection:** Detect whether Ollama at `http://127.0.0.1:11434` is reachable; list locally installed models; allow selecting one. Show a useful error if no service or models are available. Do not automatically pull/download a model.
3. **Streaming:** On send, POST the bounded message history to Ollama's `/api/chat` with streaming enabled. Relay content incrementally to the browser using a simple defined event protocol (e.g. newline-delimited JSON with `delta`, `done`, `error` event types). Do not wait for the entire completion before displaying text.
4. **Stored history:** SQLite tables for conversations and messages. Create, list, open, and continue conversations. Completed replies and their metadata survive app/browser restart. Avoid treating cancelled or errored output as a successfully completed answer.
5. **Metrics:** Display actual selected model, wall-clock end-to-end response duration, and prompt/output tokens when Ollama supplies counts. Show `—` if unavailable. Label local API charge as `$0` (not total compute/electricity cost). Do not invent measurements.
6. **Context limit:** Send only the most recent **12 messages**, plus the new user message, to the model. Earlier turns must remain saved, and the UI should clearly tell the user when older context was omitted. No automatic summarization in this milestone.
7. **Resilience and cancellation:** Clear errors for Ollama offline, model not found, timeout, and empty response. A Stop button cancels the browser request and closes the upstream Ollama stream; do not silently retry or use another provider. Restrict to one in-flight generation at a time for this prototype.
8. **Local privacy:** Bind the development server to loopback (`127.0.0.1`) by default. Use no cloud models, external analytics, login, email, browser-session integration, or access to personal files. Do not record raw chat content in diagnostic logs.

## 4. Suggested code boundaries

```text
localfirst/
├── app/
│   ├── main.py              # FastAPI endpoints + static app serving
│   ├── ollama_adapter.py    # Ollama connectivity, model list, stream
│   ├── storage.py           # SQLite conversations and messages
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── styles.css
├── tests/
│   ├── test_storage.py
│   └── test_chat_api.py
├── README.md
├── DEVLOG.md
├── .gitignore
├── pyproject.toml          # or requirements.txt; choose one
├── PROJECT_PLAN.md
└── LocalFirst_Project_Brief.md
```

Keep the codebase small. Exact filenames and routes may change if there is a clear simpler option; document differences in `DEVLOG.md`.

## 5. Implementation sequence

**Slice A — Connection:** Confirm local Python and Ollama prerequisites. Build FastAPI health and model-discovery endpoints, plus a page that shows online/offline state and installed models. Write one mocked test for model discovery/offline behavior.

**Slice B — Streaming:** Add chat submission and true incremental streaming from Ollama to the browser. Show a Stop button and surface errors. Test stream parsing and cancellation with a fake transport.

**Slice C — Persistence:** Save conversations/messages to SQLite and load them at startup. Test persistence and chronological ordering without invoking a real model.

**Slice D — Usability and instrumentation:** Add conversation navigation, small responsive styling, actual completion metadata, visible context-window truncation, and readable startup instructions. Run tests and do a real end-to-end local smoke test.

After each slice, keep the app runnable and record what changed, what was tested, and unresolved issues in `DEVLOG.md`. Do not move on if basic tests are failing.

## 6. Acceptance checks / definition of done

- [ ] `README.md` contains verified commands to create an environment, install dependencies, launch the app, and run tests on the Mac.
- [ ] Browser opens the local chat page without requiring the user to chat in Terminal.
- [ ] Available local Ollama models appear; model selection works.
- [ ] A short prompt produces visibly streamed text, not only a final block.
- [ ] Two follow-up turns in one conversation work.
- [ ] Close/restart the app; earlier messages are still present.
- [ ] Model identity, elapsed time, and available token counts are shown accurately.
- [ ] Ollama-offline and empty-output conditions produce useful, non-misleading errors.
- [ ] Stop actually ends ongoing generation, with partial results not marked complete.
- [ ] Tests pass with a mocked provider, without a working Ollama model.
- [ ] No cloud credential, paid API, autonomous agent, or unsolicited dependency/integration is introduced.

## 7. Not in this milestone

- Cloud APIs or model-provider credentials
- Local/cloud Auto routing, quality classifiers, fallback, or spending controls
- Prompt summarization, embeddings, RAG, tool use, web access, image uploads
- Agent orchestration, scheduling, autonomous coding, background jobs
- Authentication, multi-user support, Mac/Windows packaging, production deployment
- Performance or cost-savings claims without comparative measurements

## 8. Handoff to the VS Code coding agent

> Read `PROJECT_PLAN.md` and `LocalFirst_Project_Brief.md`. Implement **only MVP 1** according to the plan. Start by inspecting the current folder and checking whether the installed Ollama service is reachable and which model tags are present; do not assume a tag. Briefly state the files you will create, then implement Slice A through Slice D in order. Use simple established libraries, no cloud calls, and no broad filesystem access. Run automated tests, perform a local smoke test when possible, fix failures, and update `README.md` and `DEVLOG.md` with results and any blockers. Stop after the definition of done is satisfied, and summarize exactly what works and what does not. Do not begin routing/cloud integration without a separate request.

## 9. Official technical references

- Ollama chat endpoint: https://docs.ollama.com/api/chat
- Ollama model listing: https://docs.ollama.com/api/tags
- Ollama streaming format: https://docs.ollama.com/api/streaming
- FastAPI streaming responses: https://fastapi.tiangolo.com/advanced/custom-response/

## 10. Deferred final milestone — Local chat organization

User-requested future feature, intentionally scheduled at the very end of the current
roadmap. This does not authorize implementing an agent, scheduling jobs, or reorganizing
existing chats now.

During local-agent setup in Settings, offer **Organize my chats** for the existing
conversation library (for example, an initial collection of about 20 chats). Use the
selected local model to suggest a small, useful folder structure, assign chats by topic
or project, and build a local index so the user can find earlier discussions.

Proposed initial behavior:
- Scope to chats already stored in LocalFirst; folders are in-app organization, not
  moves of database files or arbitrary materials on the user's filesystem.
- Preview suggested folders, assignments, and short index descriptions before applying.
  Allow correcting names/assignments, leaving uncertain chats unsorted, and undoing a batch.
- Preserve conversation IDs, original messages, telemetry, and the ability to continue
  each chat. Generated index descriptions are derived data, not edits to source chats.
- Let users rename/move chats themselves and retain those choices on subsequent runs.
- Support an initial organization pass and a user-triggered rerun for new chats.
  Automatic end-of-session or scheduled organization is a separate future decision.
- Keep model processing and the index local. Handle long chats in bounded pieces;
  avoid inferring organization from titles alone when content is available. Treat chat
  contents as material to classify, not instructions for the organizer to execute.
- Prefer a small folder-management and search/index feature over a general-purpose
  autonomous agent. Measure processing time and usefulness before expanding scope.

Acceptance for that future milestone: preview/apply/undo work on an existing library;
folder membership and indexing survive restart; search opens the original chat;
manual choices survive reruns; cancellation does not leave half-applied organization;
no chats are deleted, source messages rewritten, or content sent to external services.

## 11. Paused — Evaluation Lab and context preparation

Agreed product direction: the local model should help prepare a complete request,
not merely attempt a cheaper answer. Validate that role in a separate Evaluation
Lab within LocalFirst before implementing automatic routing.

The Lab should let the user supply a task, relevant context, and explicit success
criteria before generation. Show the local answer, optional authorized frontier
answer, evaluator verdict with rationale/evidence, and cost/latency. Retain human
assessment separately from model assessment. A frontier judge's approval is evidence,
not ground truth; judging an answer does not establish that the judge can independently
solve the task. Establish frontier capability with an actual comparable run.

Use task-appropriate checks: verified reference results for deterministic tasks,
executable tests for code, factual coverage/unsupported-claim checks for summaries,
and explicit rubrics for writing/planning. Distinguish successful, failed,
insufficient-context, and uncertain evaluations; do not equate response completion
or helpfulness feedback with successful task completion.

Context preparation should identify essential missing information, ask focused
clarifying questions, and assemble the user's objective, relevant context,
constraints, and success criteria. Preserve uncertainty and expose assumptions;
never invent missing context or quietly change the user's intent. Access only
sources the user has authorized. Avoid unnecessary clarification rounds.

First experiment: compare an original prompt with a locally prepared version on
comparable tasks. Record any user-supplied clarification as added information,
so its effect is distinguishable from prompt rewriting alone. Compare task success,
quality, total latency, clarification burden, retries, and total external API cost,
including preparation/evaluation costs when applicable. Run equivalent inputs
against local and frontier models when evaluating provider capability.

The first local Evaluation Lab is implemented; see `EVALUATION_LAB.md` and
`DEVELOPMENT_LOG.md`. No frontier provider, credentials, paid calls, external judging,
or automatic routing is authorized by this design agreement. Local trials use
user-defined rubrics and explicit human assessment; any future cloud trials require
explicit opt-in and spending controls. The chat organization feature remains deferred
to the final milestone.

### Lab direction update — real conversations are the test set

User clarified that everyday chats, rather than hand-written example prompts, should
supply evaluation material. The Lab now starts from completed chat answers, links back
to their source conversation, and imports existing outputs/measurements without extra
inference. New chat message inputs are recorded for replay; historical context is
explicitly labeled reconstructed. Criteria chosen after an answer are labeled post-hoc,
not presented as predeclared tests. Custom experiments remain optional. Every completed
turn is available to evaluate; it is not automatically graded or treated as successful.

## 12. Next main-site milestone — Make everyday chat easier to use

1. **Retry and model switching — implemented.** The latest stopped or failed
   reply offers Retry and a choice of installed model. Each attempt keeps its
   own model, elapsed time, and measurements. The retry reuses the recorded
   input and leaves the original attempt in the conversation. For older replies
   without recorded input, it reconstructs the request from saved messages.
2. **Make conversations easier to find.** Add manual rename and local search across
   titles and message text. Open the matching conversation from the result. Build
   this before the deferred model-assisted organizer so users can find and label
   their own chats as the library grows.
3. **Show when a conversation is outgrowing its context.** Put the omitted-message
   count near the composer before sending. On each reply, make the model and context
   available alongside the existing measurements.

The first slice is ready when a failed or stopped reply can be retried with the same
model or a different installed model, both attempts survive restart, and the retry
is recorded as a separate inference. Check the flow with Ollama unavailable, with no
installed models, and on a narrow screen.

## 13. Next milestone — Settings and frontier handoff in chat

Build a Settings page and connect one frontier provider to the existing chat
flow. Use the real OpenAI API as the first frontier provider. The local model should complete whatever it can before
a handoff, then give OpenAI a focused brief for the remaining work. The
Evaluation Lab remains parked, with saved experiments accessible at /lab.
Conversation search and rename remain separate work.

### Settings and chat UI

- Add **Settings** to the main sidebar and serve it at /settings. Persist the
  app-wide routing preference and spending limit in SQLite across restarts.
  Default to **Always local**, including for existing installations. Snapshot
  the routing preference at the start of each turn so a settings change applies
  to the next turn.
- Show the four modes below as a radio group with a short description of when
  each mode sends text off the device. Show provider readiness, the configured
  frontier model, and a daily cloud spending limit. Keep the OpenAI API key in
  server configuration and return only readiness to the browser. Reject saves
  for cloud-enabled modes until the key, model, and positive spending limit
  are configured. Clearly explain what needs to be set up.
- Display the active routing mode near Send. Keep the installed local model
  picker for modes that use it. In **Always frontier**, show the configured
  frontier model in its place. Label replies with the provider and model.
  Preserve the local answer when showing a frontier continuation.

| Mode | Behavior |
| --- | --- |
| **Always local** | Send to Ollama. Every turn stays on the device. |
| **Manual handoff** | Send to Ollama first. Offer **Continue with OpenAI** on the local reply. Generate the handoff brief locally, then show the exact outgoing text and estimated charge. The user can remove or edit content and confirms each send. A handoff always retains a locally prepared summary and focused task. |
| **Automatic handoff** | Send to Ollama first. When the local assessment identifies a specific unresolved task that OpenAI can take over, generate and validate the same handoff brief and send it automatically within the limit. Enabling this mode requires explicit acknowledgment in Settings that request content may leave the device without per-turn confirmation. Show why the app handed off. |
| **Always frontier** | Send directly to OpenAI on Send, with bounded conversation context and a clear indication that the request goes to OpenAI. Enabling the mode requires explicit acknowledgment in Settings. This route skips local inference and handoff preparation. |

### Handoff rules

- Both handoff modes use the same preparation path. The local model produces
  a concise summary of the request and work so far, relevant facts and constraints,
  the unresolved part or requested review, and a focused instruction for OpenAI.
  Have it distinguish provided facts from draft claims and assumptions. Include
  the latest user request and bounded source excerpts needed to do the remaining
  work. Prefer exact excerpts for requirements and evidence that would lose
  meaning in a summary.
- Validate that the brief contains a summary and focused task and fits the input
  limit. Treat local-generated content as untrusted input and enforce routing,
  provider, and budget on the server. If Ollama is unavailable, preparation
  fails, or the brief is unusable, keep the local result and show the failure.
  Both handoff modes require a valid brief before any frontier generation.
- For automatic handoff, use an explicit structured disposition such as
  **Answered**, **Needs user input**, or **Needs frontier help**. For the last
  disposition require a concrete unresolved task and a usable brief. Treat
  uncertain or invalid dispositions as local outcomes. Ask the user for
  essential missing facts. A low confidence score alone cannot trigger a call.
  Limit automatic handoff to one frontier generation per user turn.
- In manual mode, preview the final outbound payload, including any text added
  by the app, before sending it. Recalculate the estimate if the user edits it.
  In automatic mode, show the handoff reason and make the sent brief inspectable
  in the thread. Always frontier sends bounded chat context according to its
  own direct route.

### Provider, usage, and failure handling

- Adapt OpenAI streaming to the existing browser chat events and reuse the local
  conversation and telemetry stores. Accept Stop during either phase. Save the
  local reply and the separate frontier attempt with their relationship, route
  reason, provider, model, status, latency, and reported token usage. Keep any
  failed or stopped partial output labeled in history.
- Before a paid generation, reserve a conservative charge against the persisted
  daily limit using bounded input, maximum output tokens, and the configured
  model's rates. Reserve atomically so concurrent requests cannot exceed the
  limit. Reconcile against reported usage when available. Keep unresolved spend
  reserved when a cancelled or failed call could still be billed. Use the same
  guard for every frontier route. Label estimates and token-derived charges in
  Usage, and show unknown usage as unknown.
- Surface unavailable providers, missing configuration, and budget exhaustion
  in context. Keep the local result available on a failed handoff. Always
  frontier reports a blocked send and lets the user change modes in Settings.
  A different route requires a user choice. Never echo the API key or raw
  request bodies to diagnostic logs.

### Build order and acceptance

1. Add Settings persistence and chat mode indicators. Verify all four choices
   survive a restart, existing installs start local, and the current local
   send, retry, and stop flows still work.
2. Add the OpenAI adapter using the real API. Read the user-supplied key from
   the server environment. Implement the spending guard, streaming, persistence,
   and Always frontier first. Test routing and budget logic offline. Gate the
   live integration checks on the configured key, model, and spending limit.
3. Implement shared local brief preparation and manual preview, then automatic
   routing. Verify the outgoing content in both handoff modes. Test that
   dismissing the preview, a complete local answer, missing user facts,
   invalid preparation, or an exhausted budget produces zero frontier
   generation calls. Verify an automatic handoff sends at most once and
   preserves the local reply. Cover Settings and chat on narrow screens.
4. Run the existing Python and browser suites. Verify that successful, stopped,
   and failed attempts retain accurate status and usage after restart. Once the
   user configures credentials and a limit, run a small paid smoke test against
   the real OpenAI API with synthetic prompts. Check that Always frontier skips
   Ollama, both handoff modes send the focused brief, and streamed replies and
   reported usage are saved. Keep paid tests opt-in.

### Evaluate after the flow works

Use a small set of representative requests and write success criteria first.
Compare local-only, local plus handoff, and frontier-only on the same requests.
Measure answer quality, total wait including local preparation, and frontier
tokens and spend. Use the results to decide where local work earns its time and
where automatic handoff needs tighter triggers.

## 14. Focus reset — November 16, 2026

Current direction is `VISION.md`: simple local chat, relevant frontier help when a
request needs stronger reasoning or verification, and a small real-chat evaluation
space. File uploads/folder access, chat organization, autonomous features, and product
administration remain later work. Ordinary model/privacy/spending Settings are distinct
from a future staff/admin console. Favor a focused VS Code development workflow.

Next implementation work should simplify the existing conversation and handoff path,
not introduce another surface or integration. Consider Chat/Lab/Settings as the visible
structure and keep detailed analytics secondary. These are proposed changes; no current
routing mode, data, navigation, account, or device configuration was changed by this
planning update. Retain existing cloud/handoff work while reducing visible complexity.

## 15. Customer discovery before selecting a delivery model

November 16, 2026: user requested a broad map of potential customers and actual AI
workflows before choosing an audience or fixing where LocalFirst lives. See
`docs/research/customer-landscape-2026-11-16.md` and `customer-segments.csv` in the same
directory. The map covers 30 overlapping customer types, likely buyers, workflow and
billing hypotheses, possible local/frontier splits, placement options and blockers.

Proposed first research cohort: automation agencies, marketing/content agencies with
actual usage-based costs, and small development agencies; compare with MSP/channel
partners and fixed-subscription users. This is an interview shortlist, not a market
selection. Verify bills, repeat tasks, quality criteria, current tools, hardware and
willingness to adopt before choosing a desktop chat, companion, API layer or shared
local deployment. No outreach, pilots, paid requests, product integrations or new
implementation work was performed or authorized by this desk research.

## 16. Product architecture — November 16, 2026

Sequencing clarified November 17 in milestone 17 below: personal daily use comes first.

User requested a comprehensive, simple architecture brief, starting with an executive
summary and favoring tables/diagrams. `ARCHITECTURE.md` recommends one desktop app,
shared local engine, managed Ollama runtime and SQLite; supporting implementation
requirements are in `docs/architecture/engineering-notes.md`. Reuse the current stack.

First prove private runtime packaging, signing, streaming and clean shutdown on a
clean Mac without developer tools. Then implement hardware recommendation/manual
entry, consented resumable verified model setup and recovery. Keep customer discovery
in parallel; the supported artifact/device matrix and winning workflow remain open.
The under-one-minute ambition must distinguish full cold setup from cached-model and
interaction times. No universal multi-GB download guarantee is proposed.

Retain the small real-chat Lab and existing handoff work. Optional direct provider keys
can serve a technical pilot; effortless public frontier access needs a separately
designed managed billing/gateway path. Customer/staff consoles, files, organization and
workers stay staged later. This milestone records a proposal, not implemented features.

## 17. Personal-use week and guided setup — November 17, 2026

User clarified the setup target: under one minute **excluding actual downloads**, with
at most five clicks on the normal recommended path and clear guidance throughout.
Count required install/launch and permission actions. Keep optional manual hardware
entry; automatic preparation transitions into chat without another confirmation.

The immediate milestone is a useful everyday product: simplify chat/help and fix real
interruptions, then use the existing app for ordinary work for about a week. Record
brief friction notes and reuse saved chats/the existing Lab selectively. Fix blockers
as they appear. Production packaging, new feedback infrastructure and formal experiment
setup are not prerequisites for this week.

Review whether the app is naturally useful, handles context/help clearly, preserves
history and recovers reliably before considering marketing, billing, customer admin or
internal “god mode.” Those surfaces remain deferred. Packaging and guided onboarding
follow the personal-use findings; retain the long-term shared-engine design.

## 18. PDF uploads for everyday chat — November 20, 2026

User chose PDF uploads as the first file capability, replacing the proposed PowerPoint
start. Add a file picker/drag-drop to the existing chat, local text extraction and
page references. Save extracted pages with local chat for follow-ups; discard original
bytes. Keep PDF conversations local across routing modes, retries and handoff paths.

Use bounded page excerpts for long documents and disclose coverage. Clearly report
scanned/unreadable pages; OCR, image/chart understanding, other file types, browsing
and file-management interfaces remain separate work. Implementation specification:
`docs/implementation/pdf-chat.md`. Marketing, billing and admin remain deferred.
