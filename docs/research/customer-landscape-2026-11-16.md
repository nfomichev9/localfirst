# LocalFirst customer discovery map

Research date: November 16, 2026. First-pass focus: US small businesses and adjacent
buyers/channels, consistent with the current product discussion. This is a broad map
of 30 customer types, not an exhaustive list of industries or a validated market size.
Segments overlap; do not add them together for TAM. Individual tasks and billing
arrangements matter more than an industry label.

**Status:** desk research plus explicit hypotheses. No customer interviews, paid
pilots, verified customer invoices, savings benchmarks, or willingness-to-pay studies
were conducted. Proposed local tasks are candidates to test, not established Gemma
capabilities. Candidate placement is deliberately open. No app change is authorized
by this research; the prior focused product scope and stop-server request remain.

## What we need to learn

A useful customer has a recurring task, a meaningful pain, control over a reducible
bill (or another reason to pay), a reachable buyer, a workable deployment path, and
an acceptable way to judge output quality. Heavy AI use alone is not enough.

Separate the **user** doing the work, the **buyer** approving spend, the **implementer**
installing software, and the **bill owner** who captures savings. An agency may pay
its client's API charges, pass those charges through, or never see them.

## Candidate map

Workflow examples reflect published broad task categories or sector reports. Each
row explicitly states where the customer/fit inference goes beyond the source.
The accompanying CSV contains buyer, billing, local/frontier split, proposed form,
objections and evidence status for every row.

| Customer type | How they may use AI | First discovery position |
| --- | --- | --- |
| AI automation agencies | Client workflows: classify requests, extract fields, summarize records, draft replies | First interviews |
| Small AI software companies | In-product assistants, labeling, extraction, generated summaries | First interviews |
| Managed service providers / IT consultancies | Ticket triage, troubleshooting drafts, client documentation, deployment help | Channel interviews |
| Software development agencies | Code explanation, implementation, test generation, documentation | First interviews |
| Independent developers / indie founders | Build products, debug, write tests, draft specifications | Second interviews |
| Product / QA / technical documentation teams | Acceptance criteria, release notes, bug triage, test-case drafts | Second interviews |
| Marketing / content agencies | Campaign variants, repurpose supplied copy, summarize briefs, draft client reports | First interviews |
| SEO / web agencies | Content briefs, metadata, page variants, review summaries | Second interviews |
| Freelance writers / social media managers | Rewrite posts, newsletter drafts, outlines, repurpose supplied transcripts | Second interviews |
| Consultants / professional service boutiques | Meeting-note summaries, proposals, client memos, research synthesis | Second interviews |
| Research / analyst boutiques | Compare source material, extract facts, synthesize reports | Second interviews |
| Customer support teams / BPOs | Ticket summaries, category labels, response drafts, knowledge answers | Second interviews |
| E-commerce brands / marketplace sellers | Descriptions, catalog cleanup, review summaries, customer replies | Second interviews |
| Sales development / lead generation agencies | Prospect summaries, outreach drafts, follow-ups, CRM notes | Second interviews |
| Recruiting / staffing agencies | Job descriptions, candidate summaries, outreach and interview preparation | Later or qualified interviews |
| Real estate brokerages / property managers | Listing copy, tenant correspondence, property summaries | Later |
| Accounting / bookkeeping firms | Client correspondence, document summaries, explanation drafts | Later |
| Law firms / legal operations boutiques | Correspondence, document summaries, drafting and legal research | Later |
| Insurance agencies / brokers | Client messages, summarize submissions and policy material | Later |
| Healthcare practice administration | Administrative drafts, appointment information and internal summaries | Later |
| Nonprofits / grant-writing consultants | Grant drafts, donor letters, program summaries and reports | Second or later |
| Education / tutoring / training businesses | Lesson outlines, exercises, feedback drafts and study material | Later |
| Construction / trades / estimating offices | Proposal text, project correspondence, summarize specifications | Later |
| Manufacturing / logistics operations | SOP drafts, incident summaries, work instructions and supplier messages | Later |
| Hospitality / restaurants / event businesses | Promotions, review replies, staff communications and planning | Later |
| Small business owners / coaches / generalists | Brainstorming, emails, planning and everyday questions | Comparison interviews |
| Design / video / creative studios | Concepts, image/video generation, scripts and client briefs | Later |
| Large enterprise AI / IT teams | Shared assistants, API governance, routing, monitoring and evaluation | Later |
| Local government / public agencies | Public information drafts, internal document summaries and correspondence | Later |
| Individual AI power users / students | Writing, studying, planning, coding and experimentation | Comparison interviews |

## Billing determines whether savings can be sold

| Current payment | What LocalFirst could change | What not to claim |
| --- | --- | --- |
| Direct metered API spending | Reduce or improve paid calls the customer actually owns. | Every avoided token was cash saved. Account for credits, discounts and retries. |
| Subscription with paid overages | Possibly reduce overages or avoid a capacity upgrade. | Fewer prompts automatically reduce the fixed base fee. |
| Fixed subscription with unused allowance | Potentially offer privacy, speed or workflow value, or enable a real downgrade. | Less use by itself saved the subscription price. |
| AI bundled into CRM/helpdesk/office software | Often the vendor or integrator must be the customer, or an actual lower tier must exist. | Token routing cuts an end user's bundled bill without a pricing change. |
| Image/video generation credits | Current text routing may help scripts/briefs only. | A local text model replaces expensive media generation. |

First request a redacted real bill and examples of paid work. Separate paid cash,
included/promotional credits, and modeled token cost. Compare against an appropriate
cheaper-cloud/caching baseline, not only the most expensive frontier model.

## Initial interview shortlist — hypotheses, not a winner

1. **AI automation agencies**: strongest first question for the usage-cost thesis.
   They may have repeated tasks and control API routing. Find out who owns the bill,
   whether they already optimize model choice, and where a reliable local worker
   would run. A candidate first task is structured extraction from supplied text.
2. **Marketing/content agencies with actual overages or API usage**: strongest way
   to test an approachable chat/companion product. Existing chat can demonstrate
   rewriting/repurposing supplied content. A candidate first task is turning a
   client-provided brief into a set of drafts. Brand review and real economics matter.
3. **Small software development agencies**: useful comparison for heavy model usage
   and preference to stay in existing tools. First test bounded documentation or
   test-description work, not autonomous code replacement. Require relevant quality
   checks; one costly defect can erase inference savings.

Also interview **MSPs** as a potential channel/implementation partner and **ordinary
fixed-plan users** as a contrast group. Neither is automatically the paying customer.
Small AI software companies are a parallel API-design-partner pool if agency interviews
point strongly toward a gateway. Do not select them simply because API spend is visible.

## Preserve options for where LocalFirst lives

| Possible form | Customer condition that supports it | Principal adoption test |
| --- | --- | --- |
| Desktop chat, close to current app | Users willingly move routine conversations into it. | Does changing tools cost more time/value than the product saves? |
| Companion/plugin in an existing workflow | Users want current chat/IDE/office tools, plus context preparation or selective help. | Is there a supported integration and access to the needed context? Do not assume arbitrary Claude/ChatGPT app calls can be intercepted. |
| API gateway / connector / SDK | Customer owns usage-based calls and can configure the calling tool. | Can it route through a dependable local/private worker with acceptable latency and uptime? |
| Shared local team deployment | IT or an MSP will operate it, and multiple users justify the setup. | Who installs, patches, monitors and pays for the hardware/support? |
| Browser interface with a local worker | User prefers browser access but truly local execution remains essential. | Will they install and trust the required local component? A browser UI alone does not establish local inference. |

These are alternatives for discovery, not features to implement together. Keep the
current chat as a prototype and demonstration while researching actual workflow fit.
Local deployment is a method; the paying benefit might instead be cost control,
less off-device data, reliable execution or better prepared requests. Test which one
buyers value rather than claiming all of them at once.

## Discovery plan

Start with 15 interviews: five automation agencies, five marketing/content agencies,
and five development agencies. These are research targets, not estimated conversion
rates. Add a few MSP/channel and fixed-subscription contrast interviews as access allows.
Recruit through the founder's network and relevant professional communities; do not
send outreach or collect sensitive material without explicit permission.

In each conversation ask for a demonstration of work, rather than only an opinion:

1. Show the last actual task you used AI for: tool, prompt/context, output and correction.
2. Which tasks recur, how often, and how many people do them? Who judges success?
3. What do you pay: seats, API, overages, credits, per-resolution fees or bundles?
   Can you share a redacted usage breakdown? Who bears the bill and gets savings?
4. Which failures cost time, cause harm or lose trust? When is a stronger model needed?
5. What would they refuse to lose from their current tool: sources, files, history,
   integrations, coding tools, collaboration, mobile access or model choice?
6. What hardware is already available, when is it online, and who could administer it?
   Do not buy or require a Mac mini before learning whether setup is acceptable.
7. Would they change chat apps, configure a supported provider endpoint, install a
   companion, or need IT approval? Which option can they actually try?
8. What cheaper models, caching, budgets or existing controls have they already tried?
9. Who can approve a purchase and what would a small paid pilot need to prove?
10. Will they provide a permissioned, sanitized sample of repeated tasks and agree
    success criteria in advance? A real sample and a pilot commitment beat vague interest.

No exact spend threshold is established. Qualify on enough *avoidable* expense or
other demonstrated value to cover a plausible price and the full deployment burden.
Avoid asking leading questions such as “would you like to save 80% on AI?”

## How to choose after interviews

Keep every criterion **unknown** until evidence is obtained:
- Verified avoidable variable spending or another budgeted pain.
- Repeated, bounded tasks that a local model demonstrably completes well.
- Clear quality checks and tolerable error consequences.
- Control of routing, data and deployment; practical existing hardware.
- Willingness to adopt at a reachable acquisition/support cost.
- A buyer with authority, urgency and an actual pilot commitment.

Then run a small matched-workflow pilot with agreed success criteria. Compare the
customer's current approach, an appropriately optimized cloud baseline, and LocalFirst.
Include preparation, retries, evaluation, latency, local running costs, setup/hardware
allocation, our proposed fee, and the time spent correcting outputs. Price human time
only with explicit agreed assumptions. Never equate reduced vendor token estimates
with verified cash savings.

A segment earns priority when customers show a recurring pain, give representative
work, and commit to a pilot that can demonstrate net value. No defensible TAM, savings
percentage, pricing or final ICP can be inferred from AI-adoption surveys alone.

## Evidence and sources

Sources establish use cases and constraints; they do not establish LocalFirst demand,
customer bills, willingness to install local software, or achievable savings.

- **S1 — Federal Reserve Banks, 2026 Report on Employer Firms**, published March 3,
  2026, using the 2025 SBCS. Among surveyed AI-using small employer firms, writing/
  marketing, individual productivity, and planning/analysis are leading uses. This is
  a weighted convenience survey, not a random census. Use-task percentages are not
  the share of all small businesses spending on tokens.
  https://www.fedsmallbusiness.org/reports/survey/2026/2026-report-on-employer-firms/
- **S2 — Federal Reserve Bank of San Francisco**, July 15, 2026 qualitative brief on
  the 2024 SBCS. Describes communications, marketing, service, visuals, analysis and
  more specialized operations, plus implementation and accuracy barriers. Older
  response period; useful for workflow breadth, not current adoption counts.
  https://www.frbsf.org/research-and-insights/publications/community-development-research-briefs/2026/07/ai-adoption-in-small-businesses-2024-sbcs/
- **S3 — Anthropic Economic Index, Economic primitives**, January 15, 2026, analyzing
  November 2025 Claude use. Interactive augmentation and API automation differ;
  coding is prominent. Vendor/platform-specific data, with model-assisted task
  classification, not a representative survey of all small businesses.
  https://www.anthropic.com/research/anthropic-economic-index-january-2026-report
- **S4 — Intuit QuickBooks Small Business Insights**, July 2026 findings. Survey
  reports marketing, customer service and data processing as leading AI-assisted
  tasks and integration as an important digital-tool obstacle. Vendor-sponsored
  self-report; AI-enabled software includes more than explicit chatbot/API use.
  https://quickbooks.intuit.com/r/small-business-data/small-business-insights/
- **S5 — SHRM Talent Trends**, March 24, 2025 article, survey of HR professionals.
  Describes AI use for job descriptions, resume review and candidate searches.
  Not a staffing-agency-only or small-firm-only sample.
  https://www.shrm.org/topics-tools/news/talent-acquisition/shrm-talent-trends-2025-recruitment-challenges
- **S6 — ABA-hosted 8am article, 2026**, discussing general-purpose versus legal
  tools and survey evidence. Vendor-authored trade publication; illustrates legal
  workflows, not independent proof that local routing meets professional needs.
  https://www.americanbar.org/groups/law_practice/resources/law-technology-today/2026/difference-between-general-and-legal-specific-ai-tools/
- **S7 — Thomson Reuters Institute**, June 9, 2026, 2026 State of Tax Professionals.
  Global tax-professional survey and vendor commentary on AI-enhanced existing tools.
  Does not establish small US accounting firms' direct API spending or willingness to switch.
  https://www.thomsonreuters.com/en/institute/reports/state-of-tax-professionals-report-2026
- **S8 — Salesforce State of Sales announcement**, February 2026 search result;
  reports AI use in prospecting, forecasting, lead scoring and email drafting.
  Vendor-sponsored sales-organization research, not small lead-generation firms.
  Full page retrieval timed out in this session; treat its use here as adjacent,
  search-result-level evidence rather than a fully reviewed primary report.
  https://www.salesforce.com/news/stories/state-of-sales-report-announcement-2026/
- **S9 — Anthropic pricing and API billing**, checked November 16, 2026. Fixed plans,
  credits and metered usage have different cash economics. Some plans include API
  credits; unused allowance reduction is not automatically cash savings.
  https://claude.com/pricing
  https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage
- **S10 — Anthropic API pricing**, checked November 16, 2026. Cloud baselines should
  account for less-expensive model choices and caching/batching where applicable.
  https://platform.claude.com/docs/en/about-claude/pricing
- **S11 — US Census**, May 26, 2026 analysis of BTOS. Firm size/industry differ and
  the AI question broadened in November 2025. Do not combine these results with
  differently defined surveys into one adoption/TAM number.
  https://www.census.gov/library/stories/2026/05/ai-use-businesses.html
