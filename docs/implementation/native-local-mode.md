# Native local mode on Intel Mac

## Original benchmark plan

1. Load a Gemma 3 270M Instruct GGUF from a user-selected folder in one launcher-owned llama.cpp process. Keep the process and model resident for the lifetime of the launcher.
2. Serve the existing chat UI on `127.0.0.1:8019` with same-origin streaming, cancellation, PDF text extraction, local history, and usage. The launcher starts the model before opening the local chat endpoint.
3. Preserve the browser-only route on `8018`, including **Test onboarding** and cached loading when the user types. Exercise the Ollama app with the same model and prompts.
4. Measure cold model readiness, warm time to first streamed text, and generation throughput. Verify that reloading the native page keeps the same llama.cpp process.

## Intel Mac results

Measured November 22, 2026, on a 2-core Intel Core i5-8210Y Mac with 8 GB RAM and macOS 14.7. Chrome was 157.0.8103.79. Values are medians with observed ranges in parentheses. Each mode had three cold loads and five warm chats.

The WebGPU figures are historical. Onboarding now configures the native llama.cpp model in the browser window.

| Mode | Cold model load | Warm time to first text | Generation speed |
| --- | ---: | ---: | ---: |
| Browser WebGPU at `8018`, q4f16 ONNX | 6.36 s (5.50–12.21) | 2.10 s (1.77–2.81) | 3.49 tok/s (3.03–3.56) |
| Native llama.cpp b12248, CPU, 2 threads, Q8_0 GGUF | 1.15 s (1.12–2.39) | 0.123 s (0.118–0.143) | 42.53 tok/s (40.54–43.39) |
| Ollama-backed app, Ollama 0.40.17, CPU, Q8_0 GGUF | 1.88 s (1.60–1.93) | 0.155 s (0.149–0.201) | 41.86 tok/s (38.08–43.43) |

Native generation ran about 12× faster than browser WebGPU on this Mac and was within the Ollama throughput range. The native tests reloaded the page before each warm prompt and confirmed the same llama.cpp process ID across all five reloads. The median replies contained 256 tokens in browser mode, 232 in native mode, and 209 in Ollama.

Native and Ollama used byte-identical GGUF weights from the locally installed `gemma3:270m` tag (`SHA-256 735af2139dc652bf01112746474883d79a52fa1c19038265d363e3d42556f7a2`). The native launcher loaded a copy directly from the chosen folder. Ollama reported using its own llama.cpp runner for the tag. The live app at `8000` was checked for model and routing settings. Benchmark chats ran through the same app code and live Ollama service with a temporary database at `18080`. A separate Ollama instance handled the cold loads.

## Measurement method

- Cold load measures readiness with model files already on disk and no model resident in the measured runtime. The browser sample starts on typing after a reload and ends when its cached WebGPU worker is ready. Native load runs from starting `llama-server` to its first successful health check. Ollama load runs from an explicit preload request to the response, after the isolated service reports the model unloaded. The operating system file cache was left in its normal state.
- Warm time to first token measures time from submitting a new chat request in Chrome to the first nonempty streamed text fragment. This includes each app's request path up to receipt in the browser, before rendering. Five prompts ask for ten short numbered facts on different topics. Each prompt starts a new conversation with Search off.
- Generation speed uses the browser worker's token callback intervals, llama.cpp's decode timings, and Ollama's evaluation counters. The browser and native mode use greedy decoding and a 256-token cap. The Ollama app uses its regular sampling settings and 2,048-token cap. [llama.cpp server API](https://github.com/ggml-org/llama.cpp/blob/b12248/tools/server/README.md) · [Ollama chat API](https://docs.ollama.com/api/chat)

## Reproduce

The current benchmark compares native llama.cpp with Ollama. Start a copy of the Ollama-backed app with a temporary database, connected to the usual Ollama service on `11434`. Start a second Ollama service for cold load measurements.

```sh
BENCH_DB_DIR=$(mktemp -d)
.venv/bin/python -c 'import sys, uvicorn; from app.main import create_app; uvicorn.run(create_app(sys.argv[1]), host="127.0.0.1", port=18080)' "$BENCH_DB_DIR/chat.sqlite3"
```

In another terminal:

```sh
OLLAMA_HOST=127.0.0.1:18087 OLLAMA_NO_CLOUD=1 OLLAMA_NOPRUNE=1 ollama serve
```

With the two Ollama endpoints running, run the benchmark from the repository root:

```sh
node tests/benchmark-modes.cjs /path/to/llama-server '/path/to/model folder'
```

The harness creates a temporary Chrome profile and starts and stops its own native launcher on `18089`. Use a folder containing one GGUF and, for matched weights, use the same GGUF bytes as the Ollama tag. The benchmark prints individual measurements as JSON lines.
