# LocalFirst — MVP 1 Implementation Plan

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
