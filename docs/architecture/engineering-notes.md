# LocalFirst — engineering notes

Companion to [the architecture brief](../../ARCHITECTURE.md). Proposed requirements,
not implemented features. Documentation checked November 16, 2026.

Priority clarified November 17: first make the existing product useful for about a
week of personal daily work. Marketing, billing and admin surfaces remain deferred.
Later guided onboarding targets under one minute excluding actual downloads and at
most five required clicks/activations, counting mandatory install/launch/OS prompts.
The requirements below do not make production packaging a prerequisite for daily use.

## 1. Desktop packaging decision

**Packaging recommendation:** Tauri 2 hosting the existing UI, with the existing Python
engine packaged as a private sidecar. Keep Rust limited to native integration. Tauri
supports external binaries, including packaged Python servers; PyInstaller includes
the interpreter so customers do not install Python.
[Tauri sidecars](https://v2.tauri.app/develop/sidecar/),
[PyInstaller packaging](https://pyinstaller.org/en/stable/operating-mode.html).

Prefer a one-folder Python bundle inside the app; PyInstaller's one-file mode extracts
at launch and starts more slowly. Include static assets and all required runtime files;
build/test per target OS and CPU architecture. One customer app need not be one binary.

| Alternative | Why it remains an alternative |
| --- | --- |
| Electron | Bundled Chromium/Node gives a consistent browser environment, with a larger shell. Use it if the packaging trial shows a material WebView problem. [Process model](https://www.electronjs.org/docs/latest/tutorial/process-model) |
| Native Swift UI | Attractive for a permanent Mac-only product, but requires replacing the working interface. |
| Rewrite the engine in Rust | Can reduce runtime packaging later; currently adds migration work without proving customer value. |

Tauri uses the OS WebView; that makes its shell lean, but the complete Python/runtime
bundle must be measured. Existing Chrome browser checks do not establish WebKit
compatibility. Test streaming, Markdown, copying, and cancellation in the actual shell.
[Tauri architecture](https://v2.tauri.app/concept/architecture/)

## 2. Managed runtime and artifact lifecycle

Ollama documents custom model storage/binding and a local-only switch
(`OLLAMA_NO_CLOUD=1`). Apply configuration only to our managed process. Keep frontier
access in our engine's authorized adapter, not a cloud-backed “local” model tag.
[Ollama configuration](https://docs.ollama.com/faq)

| Lifecycle | Required behavior |
| --- | --- |
| Catalog | Ship a last-known-good catalog. Pin approved artifact identity/digests, backend, byte size, context profile, minimum runtime, license and tested devices. A moved tag requires review. |
| Download | Explicit approval; HTTPS; resumable transfer; bounded retries/backoff; actionable proxy/network errors. Use the runtime's verified transfer support rather than inventing another downloader. |
| Verification | Match approved identities and digests before marking ready. A checksum is meaningful only when its manifest/source is trusted. Reject changed or corrupt artifacts. |
| Installation | Persist setup state across restarts; never load a partial artifact; enough staging space; atomic activation of a verified version. |
| Running | One generation at a time initially; unload on idle/memory pressure. No default login launch or permanent resident worker. |
| Update/remove | Separate app/runtime updates from multi-GB model upgrades. Preserve a working version during replacement; explicit deletion; never remove externally owned models. |

Ollama's documented pull API provides progress, resumed transfers and digest
verification. Test those behaviors in the **pinned bundled version**, including whether
cancel stops network transfer; a paused UI alone is insufficient.
[Pull protocol](https://github.com/ollama/ollama/blob/main/docs/api.md#pull-a-model)

**Packaging gate:** demonstrate that the chosen macOS runtime and acceleration files
can be redistributed, signed, launched privately, stopped, and updated on a clean
computer. Ollama's MIT license supports reuse, but bundled dependencies and model
licenses still need their notices checked. Do this before building elaborate onboarding.
[Ollama license](https://github.com/ollama/ollama/blob/main/LICENSE)

## 3. Local transport and response lifecycle

The packaged UI uses authenticated loopback requests to the same FastAPI engine.
The host supplies a per-launch secret in memory; the engine checks it and the exact
approved desktop origin on reads and writes. No token in URLs or logs. The development
browser entry remains separate. Runtime HTTP is private loopback with restricted
origins; it is not a public product API. Random ports alone are not authentication.

Use a per-user single-instance lock and one engine worker. A second window attaches
to that instance; it must not start another engine against the database and mistake
active attempts for crashed ones. Readiness requires an authenticated version/health
handshake, not merely finding an occupied port. Keep the development entry explicit.

The engine's session token does **not** authenticate Ollama's own HTTP port. Test the
pinned runtime's browser-origin behavior and management endpoints explicitly; do not
assume a proxy protects a still-reachable backend. Ollama documents default permitted
loopback origins. Restrict what the runtime supports, never expose it to the LAN, and
document that other software on the same account can reach local services.
[Runtime origins](https://docs.ollama.com/faq#how-can-i-allow-additional-web-origins-to-access-ollama)

Events carry request IDs, ordered text deltas and explicit completion/cancel/error
states. Keep raw Markdown authoritative, preserve existing smooth rendering, flush
buffered text on completion, and reject late updates after cancellation. Persist bounded
partial checkpoints so crashes lose at most a small unsaved tail. Closing the app must
cancel owned work and reap owned processes; never kill an external runtime.

Snapshot the actual submitted inputs, artifact digest, runtime/version, generation
settings and policy version for each attempt. Keep measured usage separate from
estimates, and unavailable values null. This makes Lab comparisons interpretable after
a model/runtime update. On cancellation or restart, persist one terminal state; never
replay a paid request automatically because its outcome is unknown.

## 4. Data, permissions and operational trust

| Data | Home and policy |
| --- | --- |
| Chats and exact submitted context | Local SQLite in the OS application-data directory; schema migrations and request provenance. |
| Lab tasks, original/prepared/frontier attempts and reviews | Same local database; importing a baseline does not rerun inference. No training or uploading by default. |
| Hardware/setup status and model metadata | Local settings/catalog; manual values labeled; no serial numbers, network scan or personal-file inventory. |
| Provider credentials | OS credential store, accessed through a narrow host/engine path; never browser storage, prompts or exports. |
| Weights and runtime files | Versioned application-owned directories; distinct from irreplaceable chat data. |
| Billing/license/team data, later | Hosted service only when needed; minimal identity, scoped membership, reservations, invoice records and audits. |
| Diagnostics | Content-free local logs with rotation. Optional, previewable support export; redact secrets and identifiers. Separate consent for any chat excerpt. |

| Risk or lifecycle event | Design requirement |
| --- | --- |
| Malicious model output | Sanitized Markdown, restrictive content policy, external links opened safely; no output gains shell/filesystem privileges. |
| Local API exposure | Loopback only, session authentication, origin/host validation and scoped native commands. Device malware is outside this protection. |
| Lost device / sensitive records | Current SQLite is plaintext. Do not promise encryption. Define threat model; use OS disk protection and qualify app-level encryption/key recovery before targeting sensitive industries. |
| Backup/restore | In-app consistent SQLite snapshot plus portable export; transactional, versioned import with validation. Never copy a live WAL database casually. |
| First desktop launch | Offer one-time import of existing prototype history; back it up and verify counts/links. Preserve the original database. |
| Deletion/uninstall | Distinguish chats, models, logs and app removal. Confirm data deletion; document OS backups and that secure physical erasure is not guaranteed. |
| Connectivity loss | Installed local chat and history work offline. Downloads resume; cloud fails visibly. A billing outage must not block history/export. Decide paid offline-entitlement grace before charging. |
| Updates | Signed/notarized macOS bundle, signed update artifacts, pinned compatible runtime, migration backup and staged rollout. Roll back the binary only with a compatible schema or restored backup. |

Tauri documents macOS signing/notarization, signed update verification, and scoped
native capabilities. These are release requirements to implement and test, not current
protections of this repository.
[macOS distribution](https://v2.tauri.app/distribute/sign/macos/),
[signed updates](https://v2.tauri.app/plugin/updater/),
[capabilities](https://v2.tauri.app/security/capabilities/).

**Local-only describes inference and content custody.** Model downloads and update
checks still contact servers, exposing ordinary connection metadata. Show this clearly;
separate cloud consent, optional diagnostics and update preferences. Once installed,
offer an offline path without mandatory background network calls.

For managed cloud access, disable request-body capture in gateway/proxy/APM logs and
check error paths too. Disclose the selected provider's retention terms; our own
no-content-storage policy cannot promise that a provider retains nothing.

## 5. Release verification

| Check area | Minimum release scenarios |
| --- | --- |
| Conversation | Streaming, Stop, disconnect, restart, duplicate submit, Markdown/XSS, long context, incomplete output and zero text loss/duplication |
| Accessibility | Keyboard/screen-reader onboarding and chat, progress announcements, error focus, text selection/copy and reduced-motion support |
| Distribution | Downloaded/quarantined app on a clean account; no developer tools; signature, upgrade, migration failure and compatible rollback |
| Setup/resources | OS/backend mismatch, offline/proxy, resume across app restart, disk full, changing memory pressure, model switch and battery/idle behavior |
| Privacy/spend | No unapproved cloud call, no wildcard local access, no secrets in logs/export, exhausted cap, concurrent reservations, unknown usage and no automatic paid retries |

The existing mocked Python/browser suite remains valuable. Add installer and actual
WebView/runtime smoke tests for each supported release configuration. Keep real paid
provider checks explicit, tiny and separate from ordinary CI. No Kubernetes, Redis,
vector database, microservice fleet, new frontend framework or training pipeline is
needed for this architecture.

