# Evaluation Lab — first implementation

A local workbench at `/lab`, grounded in actual saved chat turns. Every completed
answer appears in a paginated chat inbox and has an Evaluate in Lab link in chat.
Choose an answer, review its success criteria, and import its existing answer and
metrics as the baseline without inference or new telemetry. Custom tasks remain
optional. Criteria for a saved baseline are explicitly declared after the answer.

New chat generations save their exact role/content message input separately from
telemetry. Older turns reconstruct the latest 12 completed messages preceding the
actual user prompt and are labeled reconstructed, not recorded. Neither method
establishes what context the model internally retained. Imported runs replay those
roles/messages; prepared runs retain prior messages and replace only the final user
prompt, plus any separately declared new context. Post-hoc criteria are withheld from
faithful replays; preparation can see the criteria. Editing source prompt/context
creates a custom task variation rather than an exact replay.

For custom tasks, define the prompt, supplied context, success criteria, and an optional exact/contains
reference check before running. References are withheld from preparation and execution.
Run original prompts, request a structured local context check/draft, review/edit that
draft and explicitly accept it, then run the prepared variant. Store any added user
context separately so rewriting and new information are distinguishable.

Use the existing Ollama adapter and global generation lock. Track preparation and
execution attempts in the content-free inference ledger with purpose/task/run IDs.
Keep task text, preparation artifacts, outputs, and human assessments only in Lab
storage. Lab calls count toward global inference usage. Safe additive Lab tables (including chat baselines and source provenance) plus
a transactional telemetry migration allow non-chat attempts without fake conversations.
Interrupted operations become cancelled, not successful evaluations.

Show actual model/latency/token/cost metrics and raw submitted inputs. Human verdicts
(pass, fail, insufficient context, uncertain) are separate from inference completion
and mechanical string checks. Require an assessment for each criterion plus rationale;
a human pass requires every criterion to pass. Keep historical versions and results.

No frontier integration, paid requests, external judges, automated routing, code
execution, filesystem tools, or autonomous context access. Future frontier work requires
separate opt-in, credentials, spending controls, and actual comparable answer generation.

Validation: migration/persistence/restart, immutable revisions/snapshots, reference
non-disclosure, prompt provenance/added context, parser failure, deterministic checks,
human review constraints, API validation/model availability, streaming/disconnect/
timeout/global lock, browser create/prepare/review/run/compare/reload/stop flows, and
an isolated real-Gemma smoke test. No synthetic outcomes in the user's database.
