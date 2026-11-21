# LocalFirst — focused product vision

Updated November 20, 2026. This is the current product direction. It takes precedence
for scope and priorities over older roadmap expansions; implementation notes remain
in PROJECT_PLAN.md and DEVELOPMENT_LOG.md.

## The promise

A simple local chat that gets stronger help when needed.

Handle suitable requests locally. When a request needs stronger reasoning or a
second opinion, obtain focused help from a frontier model with the relevant context,
under the user's privacy and spending choices. Keep the experience one coherent chat.

The product hypothesis is that local work can reduce paid inference while preserving
acceptable quality and latency. This is a hypothesis to measure, not a savings claim.
Local share alone is not the goal. Optimize cost per successful task alongside quality,
latency, reliability, and privacy.

## Customer and delivery discovery

The current chat is a prototype and test vehicle. The paying audience and final
product placement remain open: desktop chat, a companion in existing tools, an API
layer, or a shared local deployment. Choose after workflow and billing interviews;
do not treat the existing UI as a commitment to the final business model. See
[the customer discovery map](docs/research/customer-landscape-2026-11-16.md) and its
[30-segment worksheet](docs/research/customer-segments.csv). Segment priorities are
hypotheses, not validated demand or savings. This discovery does not authorize new
integrations or expand the current implementation scope.

Keep that research as a reference. The current milestone is personal daily use of the
product for about a week, fixing what gets in the way. Marketing, billing and customer/
staff admin work remain deferred until the experience has been reviewed.

## Productization architecture

[ARCHITECTURE.md](ARCHITECTURE.md) proposes one desktop installation around the shared
local engine: no customer terminal/Python/Ollama setup, optional local hardware
recommendation or manual entry, explicit model-download consent, and local chat without
a mandatory account. Apple Silicon is the initial packaging candidate; wider hardware
support and final delivery placement still need evidence. Keep future extensions/API
clients able to reuse the engine rather than building several products now.

The onboarding target is **under one minute excluding actual downloads, with at most
five clicks on the normal recommended path**, including required install/launch and
permission actions. Guide the user through each step, automatically advance to chat
when ready, and keep manual hardware entry available as an optional branch. Download
time is measured separately; other setup work still counts. This is a product target,
not an implemented result.

## Three spaces, with different priorities

| Space | Role | Priority |
| --- | --- | --- |
| Chat | Everyday conversations, local answers, clarification, and frontier help. | Primary product. |
| Lab | Review actual chat answers and compare approaches against explicit criteria. | Small supporting space. |
| Admin / “god space” | Internal product operations, provider/budget policy, health, failure investigation, and evaluation oversight. | Deferred beyond the personal-use week and later productization needs. |

Ordinary settings for model choice, permission to use cloud, and spending limits are
not the future admin console. Do not introduce an unrestricted client-side admin
shortcut. Staff permissions and auditability belong to the later productization design.

## The core conversation

1. User asks naturally; the local model handles a suitable request.
2. If essential information is missing, ask a focused question. Do not invent context
   or send a vague request onward when the user can supply the missing facts.
3. If stronger reasoning or verification is needed, prepare the goal, relevant facts,
   constraints, unresolved question, and clearly marked assumptions for frontier help.
4. Send only what is needed under the user's configured consent and spending limits.
   Manual help is the simplest starting experience. Automatic escalation must earn
   its place through evaluation; a local confidence score alone is not a correctness check.
5. Continue in the same conversation, with the provider and handoff understandable.
   Retain the original local response and show errors honestly.

Frontier confirmation is evidence, not guaranteed truth. Where possible, use reference
facts, executable checks in an appropriately isolated future test environment, or human
review. Do not assume a model can solve a task because it can critique an answer.

## The Lab should serve the chat

Real completed chat turns supply the test material. Reuse the saved response and
measurements without running or charging again just to create a baseline. Preserve
message-level context and label reconstructed history honestly. There is no need to
make users retype everyday conversations as artificial benchmark prompts.

Let the user define/review success criteria, record pass/fail/insufficient-context/
uncertain with evidence, and compare local, prepared, and frontier answers where those
providers are available and authorized. Distinguish post-hoc criteria from predeclared
ones, model judgments from human judgments, and added information from wording changes.
Measure total inference work and wait, including preparation and retries. Do not make
routine chatting require experiment setup or an assessment after every reply.

Keep the Lab compact. It is not a parallel application or a research framework that
must be completed before the chatbot can be useful.

## Excellent execution means

- **Calm:** polished streaming, readable Markdown, comfortable typography, and a clear
  primary action. Instrumentation supports the conversation without dominating it.
- **Useful:** correct enough for the intended task; essential missing context is surfaced.
- **Continuous:** chat history and relevant context survive; a handoff does not feel
  like starting from scratch with a second chatbot.
- **Trustworthy:** source/provider, off-device content, spending, assumptions, and
  unavailable measurements are understandable. No invented confidence or savings.
- **Reliable:** Stop, persistence, outages, cancellation and budget limits work. Tests
  focus on actual failure modes, not feature count.
- **Focused:** hide advanced configuration from the everyday path and avoid asking
  users to manage a model fleet or agent system to have a conversation.

## Keep, simplify, defer

**Keep now:** local chat, one lightweight local default, focused frontier help,
persistent history, unobtrusive metrics, and a small Lab grounded in real chats.
User explicitly brought PDF uploads into scope for daily use: attach a PDF, extract
text locally, and ask Gemma questions with page references. Keep the first version
simple; no original-file archive or document-management product. Page text may remain
with local chat for follow-ups. Clearly disclose unreadable pages and excerpts.

**Simplify next:** the path through the existing chat, handoff, Settings and Lab. The
repository already contains four routing modes and cloud-provider work. Retain that
work while deciding which controls deserve prominence; this vision update does not
delete implementations, change saved modes, or revoke prior user choices.

**Defer:** marketing/landing pages, billing infrastructure, customer/staff admin,
other attachment types, OCR/visual PDF reading, desktop/folder access, autonomous tools, chat folders/indexing and scheduled
agents. No new file access or external
integrations until separately requested. Do not build product administration now.

**Development workflow:** favor a focused VS Code workflow. Cross-device Codex/mobile
setup is not a product milestone. Do not perform pairing, unpairing, account changes,
or uninstallations based on the preference expressed here.

## Next step

Make the existing app comfortable enough to use for ordinary daily work, then use it
for about a week. Simplify the chat/help path and fix the interruptions found in real
use: ask, clarify, get stronger help, continue, return later. Packaging is useful when
it removes launch friction, but a distributable build is not required to begin the week.

Keep brief notes on the task, friction and whether stronger help was useful; reuse
saved chats and the existing Lab selectively. Routine chatting should not require
running experiments or filling forms. Review the week before choosing further product
work or considering business surfaces. The review should establish whether the app is
naturally useful and dependable, not merely whether a feature checklist passes.

A proposed simplified navigation is **Chat**, **Lab**, and ordinary **Settings**.
Detailed usage can remain accessible from Settings. This is a design direction, not an
already-applied navigation change. Admin stays deferred.

Before adding any feature, ask: does it improve this conversation, make a handoff more
useful, or give us evidence that answers are good enough? Otherwise, park it.
