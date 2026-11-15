# LocalFirst · MVP 1

A local chat workspace for Ollama. FastAPI serves a dark, responsive HTML/CSS/vanilla-JavaScript interface; SQLite saves conversations on this machine. No frontend build, cloud inference, authentication, telemetry, or model downloads.

## Setup and launch (macOS)

Requires Python 3.11+ and Ollama. Verified here with Python 3.13.2 and installed `llama3.2:3b`.

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

Ollama must also be running. Open the Ollama app, or, if it isn't already serving, run `ollama serve` in a separate terminal. LocalFirst never starts the Ollama service or installs models. It connects only to `http://127.0.0.1:11434`; it ignores HTTP proxy environment variables.

## Use

- Select an installed model in the top bar. `llama3.2:3b` is preferred when available. The refresh button retries model discovery after an Ollama outage.
- Type a prompt and press **Enter** or the arrow button. **Shift+Enter** adds a newline.
- Use **Stop** to abort a response. The upstream stream closes; partial output is retained as incomplete and excluded from later model context.
- Use **New conversation** to start fresh. Select a saved conversation in the sidebar to resume it, including after a server restart. The mobile menu opens the sidebar; Escape closes it.
- The latest 12 completed messages plus the new prompt are sent as context. Earlier messages remain saved; a notice identifies omitted history. Failed/stopped assistant messages are excluded. There is no summarization.
- Each reply shows the actual model reported by Ollama, request duration, and prompt/output token counts when provided. Missing counts show `—`. Duration is measured at the backend from request processing through model completion, including model discovery/loading, excluding browser rendering.
- Replies identify local generation and **$0 external API spend**. This does not include local hardware, electricity, or other compute costs.

Only one response can run at once across tabs. Model switching and conversation navigation are disabled in the active tab during generation. Errors never trigger automatic retries, provider fallbacks, or model downloads.

## Files and storage

```text
app/main.py             FastAPI routes, stream lifecycle, single-generation guard
app/ollama_adapter.py   Local Ollama discovery and streaming adapter
app/storage.py          SQLite persistence and bounded history
app/static/             HTML, CSS, vanilla JavaScript; no build step
 tests/                 Mocked automated tests and opt-in real smoke check
```

The database is created on first launch at `data/localfirst.sqlite3`, relative to the project location, regardless of the launch working directory. This directory is ignored by Git. Messages and metadata are saved in plaintext; no chat content is written to diagnostic logs. To back up history, stop the app first and copy the `data/` directory. Keep it private. No personal files, accounts, or credentials are needed.

Interrupted replies are marked stopped at next startup. Output is saved at response completion, failure, or cancellation; abruptly killing the process can lose the partial text currently being generated. Completed history survives restart.

Development is loopback-only: retain `--host 127.0.0.1`. Host validation and same-origin write checks are included. This is a single-user development app, not a server for a LAN or the public internet. No authentication or multi-process generation locking is included.

## Tests

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests use temporary SQLite databases and mocked Ollama responses. They do not require Ollama or download models. Coverage includes model discovery, streaming events, model switching, follow-up context, restart persistence, context bounds, error storage, empty/invalid/truncated streams, timeouts, offline errors, input validation, concurrent requests, origin/host checks, and cancellation closing the upstream iterator.

Optional real integration smoke check (requires Ollama and the already installed `llama3.2:3b`):

```sh
.venv/bin/python tests/smoke_local.py
```

This starts a temporary server on a loopback port, uses a temporary database, tests real incremental responses, follow-up recall, server restart, and HTTP cancellation, then terminates its server. It does not modify your normal conversations or stop Ollama.

Additional checks when Node is installed (Node is not needed to run the app):

```sh
node --check app/static/app.js
.venv/bin/python -m compileall -q app tests
.venv/bin/python -m pip check
```

## Limits and troubleshooting

- **Ollama unavailable:** Open Ollama or run `ollama serve`, then click refresh. Confirm `curl http://127.0.0.1:11434/api/tags` works. API errors display in the interface without crashing the app.
- **No models / model removed:** Refresh and choose an installed model. The app never pulls one automatically.
- **Empty or interrupted output:** An error or stopped status appears; partial replies never become successful context. Send another prompt when ready.
- **Timeouts:** Ollama has a 5-second connect timeout, a 120-second read inactivity timeout, and generation has a 180-second total limit. Model discovery has a 5-second timeout. Try a shorter prompt when these limits are reached.
- **Long conversations:** History is bounded by message count, not by exact token length. The adapter requests a 4,096-token model context and at most 2,048 output tokens; Ollama may truncate oversized input internally. No performance or quality guarantees are made for larger installed models on 16 GB memory.
- **Formatting:** Messages are rendered safely as plain text. Markdown formatting, code highlighting, rename/delete, export, and attachments are outside this milestone.
- **Browser QA:** Real HTTP/stream/restart/cancellation checks passed. Browser appearance, mobile layout, and click interactions still need manual verification; no automated browser was used.
- **Test warning:** The installed Starlette TestClient emits a deprecation warning about its httpx integration. All tests pass using the pinned httpx version; production adapter behavior is unaffected. No extra HTTP client was added solely to silence the warning.

See [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) for executed checks and results.

Technical references: [Ollama chat API](https://docs.ollama.com/api/chat), [model listing](https://docs.ollama.com/api/tags), [FastAPI streaming responses](https://fastapi.tiangolo.com/advanced/custom-response/).
