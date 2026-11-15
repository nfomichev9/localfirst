# LocalFirst · Local inference and analytics

A local chat workspace for Ollama. FastAPI serves a dark, responsive HTML/CSS/vanilla-JavaScript interface; SQLite saves conversations on this machine. No frontend build, cloud inference, authentication, external analytics, or model downloads. Content-free inference telemetry stays in the same local SQLite database.

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

## Use

- Select an installed model in the top bar. `gemma4:e2b` is preferred when installed and appears as **Lightweight · Gemma 4 E2B**. Llama remains selectable; on machines without Gemma the app initially selects Llama, or the first installed model. Requests never silently switch models after generation starts. The refresh button retries model discovery after an Ollama outage.
- Type a prompt and press **Enter** or the arrow button. **Shift+Enter** adds a newline.
- Use **Stop** to abort a response. The upstream stream closes; partial output is retained as incomplete and excluded from later model context.
- Use **New conversation** to start fresh. Select a saved conversation in the sidebar to resume it, including after a server restart. The mobile menu opens the sidebar; Escape closes it.
- The latest 12 completed messages plus the new prompt are sent as context. Earlier messages remain saved; a notice identifies omitted history. Failed/stopped assistant messages are excluded. There is no summarization.
- Each reply shows the actual model reported by Ollama, request duration, and prompt/output token counts when provided. Missing counts show `—`. Duration is measured at the backend from request processing through model completion, including model discovery/loading, excluding browser rendering.
- Assistant Markdown renders while streaming and after reopening history: headings, emphasis, lists, inline/fenced code, highlighted common languages, tables, and links. Raw Markdown remains in SQLite. Rendering uses locally vendored Marked, DOMPurify, and Highlight.js; images and embedded media are excluded.
- Expand the metrics under a reply for input/output counts, generation speed, and first-token time. Helpful / unhelpful feedback is optional and saved locally. Older replies show telemetry unavailable.
- Open **Usage & analytics** from the sidebar (or `/usage`) for overview cards, model performance, and interactive daily request/token/cost charts. Filter by period/model; Refresh includes new activity.
- Replies identify local generation and **$0 external API spend**. This does not include local hardware, electricity, or other compute costs.

Gemma 4 requests use `think: false` for this lightweight chat trial, keeping the existing 4,096-token context and 2,048-token output limit. The app does not download models automatically. To install the selected model manually, use `ollama pull gemma4:e2b`, then restart LocalFirst after backend changes and refresh the browser.

Only one response can run at once across tabs. Model switching and conversation navigation are disabled in the active tab during generation. Errors never trigger automatic retries, provider fallbacks, or model downloads.

## Files and storage

```text
app/main.py             FastAPI routes, stream lifecycle, single-generation guard
app/ollama_adapter.py   Local Ollama discovery and streaming adapter
app/storage.py          SQLite persistence and bounded history
app/telemetry.py        Inference ledger, additive migration, analytics calculations
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

## Telemetry definitions

`GET /api/usage?days=30&model=...` aggregates real ledger entries across conversations;
`days=0` selects all time and an empty model selects all models. Periods are rolling
UTC windows; charts use daily UTC buckets and preserve empty days between observations.
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
