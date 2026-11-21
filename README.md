# LocalFirst · Local inference and analytics

Current product direction: [VISION.md](VISION.md). Focus on simple local chat, focused frontier help, and a small Lab using real conversations; file access and product administration are deferred.

Next milestone: use the existing product for everyday work for about a week and fix the friction found there. Marketing, billing and admin surfaces stay deferred. Guided onboarding targets at most five clicks and under one minute excluding actual downloads.

Proposed product architecture: [ARCHITECTURE.md](ARCHITECTURE.md), with an executive summary, onboarding/hardware flow, system diagrams and staged desktop packaging plan. This describes future productization; setup below is the current development app.

A local chat workspace for Ollama. FastAPI serves a dark, responsive HTML/CSS/vanilla-JavaScript interface; SQLite saves conversations on this machine. Cloud inference is opt-in from Settings. The app requires no frontend build, authentication, external analytics, or model downloads. Content-free inference telemetry stays in the same local SQLite database.

PDF uploads are available in chat: use **+** or drag a PDF onto the conversation,
then ask a question. Sending with no typed question requests a summary. PDFs are read
locally; the latest attached PDF stays available for follow-ups and after reopening.
PDF conversations use a local model even when ordinary chat is configured for cloud
routing. Start a new chat to return to ordinary routing.

This first version reads selectable PDF text, with page labels. It does not interpret
scanned pages, images, charts or visual layout. Unreadable pages are reported; larger
documents use selected excerpts with visible coverage rather than claiming a full read.
Limits: 10 MiB, 150 pages, 300,000 extracted characters, and 4 KB per PDF question.
Original PDF bytes are discarded after extraction; page text and filenames stay in
the existing local SQLite database. There is no document library or original-file archive.

Web search is available with **Search** beside **+** in the composer. Enable it,
then ask a self-contained question (up to 600 characters). Only that message is sent
as a DuckDuckGo query; the selected local model answers using up to four search
excerpts. Inline numeric citations link to the retrieved sources; expand **Sources**
for titles, links, query and retrieval time. Sources and the actual model input are
saved locally with the reply and survive reopening/retry. A retry reuses successful
search results; an interrupted/failed search is attempted again.

Search is off initially and resets when starting/opening a chat. While enabled it
applies to each new message until switched off. Search turns use local inference in
every routing mode and make no paid model calls; the saved routing preference stays
unchanged. PDF conversations keep Search disabled and remain offline. Stop also
cancels a search in progress. Search errors are explicit; the app does not silently
answer from model memory when retrieval failed.

This version reads search excerpts, not full articles or websites. Search indexing
can lag, excerpts can disagree, and model citations are not proof of correctness.
DuckDuckGo's public HTML endpoint has a Lite fallback, a shared 15-second timeout,
response limits and no arbitrary URL fetching. It can still be rate limited or
change markup; a dedicated search API can replace this small adapter later.

## Setup and launch (macOS)

Requires Python 3.11+ and Ollama. Verified here with Python 3.13.2 with local Ollama models.

In Terminal or VS Code's terminal:

```sh
cd /Users/nfomichev/Desktop/localfirst
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in your browser. Keep this terminal running; press **Ctrl+C** to stop. Use one server worker. The environment and dependencies have already been created in this workspace, so subsequent launches only need:

```sh
cd /Users/nfomichev/Desktop/localfirst
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**After pulling or editing backend code, restart Uvicorn, then refresh the browser.** Static files are read from disk immediately, but Python routes and database migrations load at server startup. An older running server can therefore show new Markdown while `/usage` returns 404 and new replies lack telemetry. Replies generated before the telemetry migration keep their original history but have no inference ledger records.

Ollama must also be running. Open the Ollama app, or, if it isn't already serving, run `ollama serve` in a separate terminal. LocalFirst never starts the Ollama service or installs models. It connects only to `http://127.0.0.1:11434`; it ignores HTTP proxy environment variables.

## OpenAI routing and spending

Existing installations start in Always local. On macOS, open **Settings → Chat →
Connect**, paste your OpenAI API key, choose the cloud model and **Save connection**.
The app verifies authentication/model access with a metadata request without generating
a response. Restricted keys need model-metadata read access as well as chat completion
access. Keys are stored in native macOS Keychain; SQLite stores only the model and an
opaque credential reference. Stored keys are never returned by the API.

This connection uses the OpenAI API. LocalFirst does not use your existing ChatGPT or
Codex login. Connecting does not enable cloud routing or raise the daily limit.

Alternatively, edit the git-ignored `.env` file in the project root:

```dotenv
OPENAI_API_KEY=paste-your-key-here
OPENAI_MODEL=gpt-6-luna
```

Save the file and restart LocalFirst. Exported shell values take precedence over
file values; either configured key takes precedence over a saved Keychain connection.
A blank key falls back to the saved connection. Custom/test databases do not load
the project file unless explicitly configured to do so.

Open Settings, set a daily limit (start with $0.01), choose a route, and save.
Settings has two sections: **Chat** for response mode and cloud configuration,
and **Spending** for the daily limit and used/reserved usage. Changes are saved only
when you choose **Save settings**; **Reset** discards unsaved edits. Automatic and
cloud-only mode changes retain the explicit permission check. Close or press Escape
to return to chat.
The cap is enforced in this app's database and resets at local midnight. Every
OpenAI call reserves an upper estimate for the bounded text and at most 256
completion tokens. The app makes no automatic HTTP retries. Usage shows
token-derived charges at standard uncached rates and reserves estimates when
OpenAI did not report usage. The limit applies to requests through this app
using the same database.

In **Ask before cloud help** mode, **Continue with OpenAI** prepares an editable brief.
Missing connection/limit errors include a Settings link beside the answer. Connecting
from that link returns to the same conversation. Cancel sends nothing; only **Send to
OpenAI** dispatches the reviewed brief. If local brief formatting fails, the preview
offers labelled saved-source excerpts for review instead. Automatic handoff still
fails closed when local preparation is invalid.


To check the real OpenAI integration with three synthetic requests, launch
`PYTHONPATH=. .venv/bin/python tests/smoke_openai.py serve` with the same
environment variables. This uses a temporary database and a deterministic
local adapter. Save a $0.01 limit with Always local at
`http://127.0.0.1:8013/settings`, then run
`PYTHONPATH=. .venv/bin/python tests/smoke_openai.py run` in another shell.
The run command explicitly opts in to paid requests.


## Use

- Select an installed model in the top bar. `gemma4:e2b` is preferred when installed and appears as **Lightweight · Gemma 4 E2B**. Llama remains selectable; on machines without Gemma the app initially selects Llama, or the first installed model. Requests never silently switch models after generation starts. The refresh button retries model discovery after an Ollama outage.
- Type a prompt and press **Enter** or the arrow button. **Shift+Enter** adds a newline.
- Use **Stop** to abort a response. The upstream stream closes; partial output is retained as incomplete and excluded from later model context.
- Use **New conversation** to start fresh. Select a saved conversation in the sidebar to resume it, including after a server restart. The mobile menu opens the sidebar; Escape closes it.
- The latest 12 completed messages plus the new prompt are sent as context. Earlier messages remain saved; a notice identifies omitted history. Failed/stopped assistant messages are excluded. There is no summarization.
- Each reply shows the actual model reported by Ollama, request duration, and prompt/output token counts when provided. Missing counts show `—`. Duration is measured at the backend from request processing through model completion, including model discovery/loading, excluding browser rendering.
- Assistant Markdown renders while streaming and after reopening history: headings, emphasis, lists, inline/fenced code, highlighted common languages, tables, and links. Raw Markdown remains in SQLite. Rendering uses locally vendored Marked, DOMPurify, and Highlight.js; images and embedded media are excluded.
- Expand the metrics under a reply for input/output counts, generation speed, and first-token time. Helpful / unhelpful feedback is optional and saved locally. Older replies show telemetry unavailable.
- Open **Evaluation Lab** from the sidebar (or `/lab`) to define a task and success criteria, test the original prompt, request a local context check, and compare a reviewed prepared prompt. See the walkthrough below.
- Open **Usage & analytics** from the sidebar (or `/usage`) for overview cards, model performance, and interactive daily request/token/cost charts. Filter by period/model; Refresh includes new activity.
- Replies identify local generation and **$0 external API spend**. This does not include local hardware, electricity, or other compute costs.

Gemma 4 requests use `think: false` for this lightweight chat trial, keeping the existing 4,096-token context and 2,048-token output limit. The app does not download models automatically. To install the selected model manually, use `ollama pull gemma4:e2b`, then restart LocalFirst after backend changes and refresh the browser.

PDF requests use a 16,384-token context, with conservatively bounded input text and
recent history; ordinary chat keeps the existing context settings. The exact submitted
PDF excerpts and page coverage are saved for retry and Lab provenance. Parsing uses
the small pinned `pypdf` dependency in a timed, cancellable local subprocess. Existing
environments need the updated `requirements.txt` installed before using PDF uploads.

Only one response can run at once across tabs. Model switching and conversation navigation are disabled in the active tab during generation. Errors never trigger automatic retries, provider fallbacks, or model downloads.

## Files and storage

```text
app/main.py             FastAPI routes, stream lifecycle, single-generation guard
app/ollama_adapter.py   Local Ollama discovery and streaming adapter
app/storage.py          SQLite persistence and bounded history
app/telemetry.py        Inference ledger, migrations, analytics calculations
app/documents.py        Local PDF extraction worker and bounded page-labelled context
app/lab.py              Lab API, bounded local inference, context preparation and checks
app/lab_storage.py      Versioned task snapshots, operations, human review
app/static/             HTML, CSS, vanilla JavaScript; no build step
 tests/                 Mocked automated tests and opt-in real smoke check
```

The database is created on first launch at `data/localfirst.sqlite3`, relative to the project location, regardless of the launch working directory. This directory is ignored by Git. Messages and metadata are saved in plaintext; no chat content is written to diagnostic logs. To back up history, stop the app first and copy the `data/` directory. Keep it private. No personal files, accounts, or credentials are needed.

An additive, idempotent migration creates the inference ledger without rewriting existing conversations. Historical messages are not backfilled with guessed metrics. Interrupted replies are marked stopped and running inference attempts cancelled at next startup; unavailable counts and durations remain null. Output is saved at response completion, failure, or cancellation; abruptly killing the process can lose the partial text currently being generated. Completed history survives restart.

Development is loopback-only: retain `--host 127.0.0.1`. Host validation and same-origin write checks are included. This is a single-user development app, not a server for a LAN or the public internet. No authentication or multi-process generation locking is included.

## Tests

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests use temporary SQLite databases and mocked Ollama responses. They do not require Ollama or download models. Coverage includes model discovery, streaming events, model switching, follow-up context, restart persistence, context bounds, error storage, empty/invalid/truncated streams, timeouts, offline errors, input validation, concurrent requests, origin/host checks, and cancellation closing the upstream iterator.

Optional real integration smoke check (requires Ollama and an installed model; uses the app preference unless `--model` is supplied):

```sh
.venv/bin/python tests/smoke_local.py --model gemma4:e2b
```

This starts a temporary server on a loopback port, uses a temporary database, tests real incremental responses, follow-up recall, server restart, and HTTP cancellation, then terminates its server. It does not modify your normal conversations or stop Ollama.

Browser tests use a temporary database and fake streaming model, launch installed Chrome, and assert Markdown/XSS behavior, persistence, metrics, feedback, analytics, keyboard chart inspection, mobile width, and absence of external requests. Node 20+ and local Chrome are needed only for these checks:

```sh
npm ci
npm test
```

Set `PLAYWRIGHT_CHANNEL` to another installed supported browser channel if needed, or install Chrome first. `PYTHON` can override the test server Python executable (defaults to `.venv/bin/python`).

Additional checks (Node is not needed to run the app):

```sh
node --check app/static/app.js
node --check app/static/markdown.js
node --check app/static/usage.js
.venv/bin/python -m compileall -q app tests
.venv/bin/python -m pip check
```

## Evaluation Lab · parked

Visit **http://127.0.0.1:8000/lab** to open saved experiments. The current product focus is chat.

1. The Lab opens the latest completed answer. Pick a different one in **Recent answers**
   to open that specific answer.
2. Read the request, local API charge, runtime, and answer. Choose **Rate answer** to
   start with suggested criteria, or **Edit criteria** to set your own. The Lab saves
   the existing answer and measurements as a baseline without making a model call.
3. Assess each criterion,
   select pass/fail/insufficient context/uncertain, and record evidence or rationale.
   A human pass requires every criterion to pass; merely completing a response is not
   a pass. Optional reference checks are mechanical evidence, not overall verdicts.
4. Under **Experiment tools**, **Check context & draft** asks the selected installed local model to flag missing
   essentials, ask clarifying questions, state assumptions, and suggest a prompt.
   It sees your criteria but never the current saved answer/reference. Advice may be
   wrong; nothing retrieves files or executes tools.
5. Inspect the draft, choose **Use this draft**, edit it, and put new facts in
   **Additional context you supply**. Explicitly confirm it before **Run prepared**.
   For unchanged chat source fields, replay retains previous message roles/content
   and replaces only the final user prompt, with your explicit additions. **Run
   original** replays the saved message input, including when selecting another model.

New turns record the message input sent to Ollama. Older turns are labeled
**reconstructed context**, using the last 12 completed messages before that turn's
user prompt; future messages and incomplete answers are excluded. Actual internal
model truncation is not recorded. Criteria declared after the original chat are
withheld from faithful replays so the original input stays comparable. If source
prompt/context are edited, the next trial is a custom variation, not an exact replay.
The source link opens the original conversation. Old replies without inference-ledger
metrics retain only known message measurements; unavailable fields stay null.

**New experiment** and the collapsed **Optional manual examples** still support custom
tasks, but real chats are the default test set. Exact/contains reference values are
withheld from all generation and preparation requests.

Changing and saving a task creates a new revision; each preparation/trial retains its
original snapshot, exact submitted prompt, output, provenance, metrics, and assessment.
A preparation from another task or revision cannot be attached to a prepared run.
Additional information changes the experiment: better results cannot automatically
be attributed to rewriting alone. For model comparison, use the same task revision,
variant, and context, then change the installed model selector.

**Frontier comparison is not configured.** This Lab performs no paid calls, external
judging, automatic routing, or code execution. Future frontier work needs explicit
opt-in, credentials, spending controls, and actual answer runs to measure capability.
Human review and simple reference checks provide the first local evaluation workflow.

Lab task text, references, drafts, outputs, and human notes are stored in separate
plaintext SQLite tables on this machine. Chat message inputs are recorded in a separate local content table for replay.
Only IDs, purpose, model, status, and numeric measurements enter telemetry. Lab calls are included in global Usage, including
preparation attempts. Summed recorded inference time includes the saved chat baseline plus preparation/trials and excludes
your clarification/review time. It is not a measured end-to-end task duration.

Use **Stop** to close an active Lab stream; partial output is retained. Chat and Lab
share the single-generation guard. Interrupted operations become cancelled on restart.
The existing 4,096-token context and 2,048-token output cap still apply; character
limits bound inputs but cannot guarantee that every input fits the model context.
Malformed preparation JSON is saved as an operation error for inspection/retry or a
manual draft; it never becomes an accepted prompt automatically.

Run the optional isolated real-Gemma Lab check with:

```sh
.venv/bin/python tests/smoke_lab.py
```

For implementation boundaries and validation scope, see [EVALUATION_LAB.md](EVALUATION_LAB.md).

## Telemetry definitions

`GET /api/usage?days=30&model=...` aggregates real ledger entries across conversations;
`days=0` selects all time and an empty model selects all models. Periods are rolling
UTC windows; charts use daily UTC buckets and preserve empty days between observations.
Lab inference records use a null conversation ID plus purpose (`lab_prepare` / `lab_run`), task ID, and operation ID. Chat records retain their original conversation/message links and default `chat` purpose. Telemetry migration 2 preserves existing rows transactionally; migration 3 adds Lab artifact tables, and migration 4 adds chat-source provenance and baseline storage.

`PUT /api/inference/{request_id}/feedback` accepts `{"value":1}`, `-1`, or `null`.

- A request is a generation attempt admitted after HTTP validation and the busy guard. Model discovery failures and models removed before generation count as errors; blank/invalid requests, missing conversations, and busy rejections do not count. Discovery refreshes do not count.
- Success means a nonempty inference completed, **not** that the user's task succeeded. Errors, cancellations, and running attempts remain distinct. Failure/cancellation rates divide by all admitted attempts. Local/cloud shares divide by successful requests.
- Latency starts before model discovery and ends at generation completion or error/cancellation, excluding browser rendering. TTFT is time to first nonempty content chunk, which may contain several tokens. Restart recovery does not invent an end time.
- Token counts use Ollama `prompt_eval_count` / `eval_count`. Generation speed is `eval_count / (eval_duration / 1e9)`; no estimate is derived from text length or wall-clock latency. Averages use available samples; the dashboard exposes coverage. P95 is nearest rank with at least 20 finished measured attempts.
- Token/cost totals sum known measurements. Unknown values stay null and render as `—`; no observations are distinct from measured zero. All local external API costs are $0. Local electricity and hardware costs are excluded.
- Cloud-only cost and estimated API savings remain unavailable until a defensible pricing/token baseline is defined. There is no measured savings claim or cost-per-successful-task metric yet.
- The ledger contains IDs, timestamp, provider/model, local/cloud location, routing mode, metrics, status, and optional binary feedback. It stores no prompts, responses, or provider error text. Nullable task/benchmark IDs support later comparisons; no benchmark runner or routing is implemented.

## Limits and troubleshooting

- **Ollama unavailable:** Open Ollama or run `ollama serve`, then click refresh. Confirm `curl http://127.0.0.1:11434/api/tags` works. API errors display in the interface without crashing the app.
- **No models / model removed:** Refresh and choose an installed model. The app never pulls one automatically.
- **Empty or interrupted output:** An error or stopped status appears; partial replies never become successful context. Send another prompt when ready.
- **Timeouts:** Ollama has a 5-second connect timeout, a 120-second read inactivity timeout, and generation has a 180-second total limit. Model discovery has a 5-second timeout. Try a shorter prompt when these limits are reached.
- **Long conversations:** History is bounded by message count, not by exact token length. The adapter requests a 4,096-token model context and at most 2,048 output tokens; Ollama may truncate oversized input internally. No performance or quality guarantees are made for larger installed models on 16 GB memory.
- **Formatting:** User messages remain plain text; assistant Markdown is sanitized. Unknown code languages remain plain escaped code. Rename/delete, export, and attachments remain outside this milestone.
- **Browser QA:** Automated headless Chrome covers chat and dashboard flows at desktop/mobile widths. Other browsers and extensive manual accessibility checks remain to be done.
- **Test warning:** The installed Starlette TestClient emits a deprecation warning about its httpx integration. All tests pass using the pinned httpx version; production adapter behavior is unaffected. No extra HTTP client was added solely to silence the warning.

See [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) for executed checks and results.

Technical references: [Ollama chat API](https://docs.ollama.com/api/chat), [model listing](https://docs.ollama.com/api/tags), [FastAPI streaming responses](https://fastapi.tiangolo.com/advanced/custom-response/).
