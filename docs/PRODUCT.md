# Boldron — Product Definition & Roadmap

This is the *what* and the *when*. The *how you work in this repo* is in
[`../CLAUDE.md`](../CLAUDE.md). This document is a reference: read the parts a
task needs. It describes the destination; **it is not a mandate to build the
whole thing at once.**

---

## 1. What Boldron is

An AI software-engineering platform. Users describe software; specialized AI
agents build, test, review, deploy, and operate it. It is an **engineering
platform**, not a chatbot that generates code.

**Stack-agnostic.** Boldron builds software in the technology the customer
chooses — the user picks what they're building (website, SaaS, API, mobile, …)
and the stack (Python/Django·FastAPI·Flask, TS/Next.js·NestJS, Go, Java/Spring,
C#/.NET, Rust, PHP/Laravel, Ruby/Rails, Dart/Flutter, …). Agents reason about the
project's chosen stack rather than assuming one. The authoritative catalog is the
**Technology Registry** (`apps/technology`: languages, frameworks, databases,
deployment, infrastructure); the executable subset — stacks Boldron can generate
AND run today — is the **Stack Registry** (`apps/technology/stacks.py`), currently
`python-stdlib`, `django` (ORM + real test DB), `fastapi` (in-process API tests
via TestClient), `node` (Node built-in http + `node --test`, no npm),
and `go` (stdlib net/http + `go test`, no modules), extensible by adding a Stack +
scaffolder. Each stack runs only where its toolchain exists; where it doesn't
(e.g. no `go` binary), Boldron still generates the project and the runner skips
with an honest note rather than a fake pass. (Express needs an npm install, so it
stays generation-planned where npm/network is unavailable.) A project
carries a `technology` profile (`{backend, frontend, database, mobile}`) that the
agents read. **Django + Flutter are Boldron's reference stack** — the one it
bootstraps itself in — not a restriction imposed on customers; a requested stack
Boldron can't yet generate fails honestly ("generation planned"), never faked.

Users can: build websites, web apps, SaaS, APIs, and mobile apps; import,
analyze, improve, rebuild, and modernize existing/legacy software; deploy,
monitor, and maintain applications; export full source; deploy to their own
infrastructure or Boldron Cloud; and use multiple AI models and agents.

Product lifecycle: `BUILD → UNDERSTAND → IMPROVE → TEST → DEPLOY → OPERATE → MODERNIZE`.

## 2. Central runtime shape

```
USER → LEAD AGENT → AGENT ORCHESTRATOR → SPECIALIZED AGENTS → CONTROLLED TOOLS
     → CODE / INFRASTRUCTURE → TESTING → REVIEW → DEPLOYMENT
```

The Lead Agent coordinates. Specialists own specific responsibilities. The
Orchestrator owns communication, state, permissions, and execution. **Never a
single giant agent/prompt.**

### Agents

- **Initial:** Lead, Product, Requirements, Architect, Backend, Frontend,
  Database, Testing, Code Review, DevOps.
- **Later:** Mobile, Security, Commerce, Payment, Tax, Cloud, Monitoring,
  Scaling, Legacy Analysis, Migration.

Agents do not call each other directly — they go through the Orchestrator:
`Agent → Orchestrator → Task → Assigned Agent`. Each agent runs with **least
privilege** (e.g. the Frontend Agent cannot touch billing or production; the
Database Agent cannot mutate production data; deploys to production require
approval).

### Agent Orchestrator

Creates/assigns/tracks tasks; manages dependencies, execution, retries,
failures, approvals; tracks usage/cost; records decisions; maintains project
context. Execution must be **resumable** — a server restart must not lose task
state.

### Agent task model

Fields: `task_id, project_id, agent_id, parent_task_id, status, priority, input,
output, created_at, started_at, completed_at, model, tokens, credits, cost,
approval_required`.

States: `QUEUED, PLANNING, RUNNING, WAITING_FOR_TOOL, WAITING_FOR_AGENT,
WAITING_FOR_APPROVAL, COMPLETED, FAILED, CANCELLED, TIMEOUT, BLOCKED`.

## 3. Core subsystems (reference)

- **AI provider abstraction** — providers (Claude, OpenAI, Gemini, …) are
  replaceable behind one interface. Nothing depends on provider specifics.
  `App → Model Router → AIProvider → Provider → Model`.
- **Model Router** — picks a model by task type, complexity, context size,
  reasoning/quality/latency needs, customer preference, budget, availability.
  Optimizes quality + cost + speed + reliability. Never "most expensive by
  default."
- **Project intelligence** — persistent, structured per-project knowledge
  (requirements, architecture, business rules, tech decisions, schema, APIs,
  dependencies, known issues, agent decisions, deployment/infra, testing,
  security). Agents retrieve relevant context instead of re-sending the whole
  repo — for cost, consistency, and long-running projects.
- **Project digital twin** — a structured model of the built application
  (frontend/backend/db/APIs/auth/payments/jobs/external services/infra/
  monitoring), updated on change; answers "if I change X, what's affected?".
  **Built** as the Application Graph + Dependency Intelligence (see §7 platform
  systems): a node+edge model composed from real project data that powers impact
  analysis and Explain-my-application.
- **Build sandbox** — isolated execution with CPU/memory/timeout/network/
  filesystem/process limits; destroyed after use.
- **Cost & credit engine** — track AI/model/token/compute/storage/bandwidth/db/
  build/deploy/monitoring, attributable to org/project/agent/task/provider/model.
  Customers get **Boldron credits** (an abstraction over tokens; plans and
  values are config, never hard-coded). **Budget protection:** per-month/project/
  infra caps; on exhaustion, **stop** and offer wait / buy / upgrade / reduce
  scope — never silent charges. A project cost analyzer gives **ranges** and
  requests approval before expensive work.
- **Cloud abstraction** — one `CloudProvider` interface over AWS/Azure/GCP/
  DigitalOcean/Kubernetes/Boldron Cloud. **Boldron Cloud** is a simple managed
  deployment experience (compute/db/storage/bandwidth/backups) — not an attempt
  to become AWS in v1.
- **Export & portability** — every project exports full source + tests +
  migrations + Docker/infra config + env template + docs + API spec + deploy
  config, independently runnable. Customers may deploy to their own infra or
  leave entirely. **No artificial lock-in** — customers stay because Boldron is
  useful.
- **Operations & scaling** — post-deploy monitoring (CPU/mem/db/latency/errors/
  traffic/storage/availability/security); ops agents detect → analyze →
  recommend → fix → test → PR → approval → deploy. No autonomous destructive
  production actions by default. Scaling intelligence forecasts future needs and
  recommends before acting.
- **Commerce & internationalization** — generated software supports products/
  cart/checkout/orders/payments/refunds/tax, and currency/language/timezone/VAT/
  date-number-address formats. Payment gateways are abstracted; customer payment
  credentials belong to the customer. Do not assume any single locale.
- **Enterprise** — SSO/SAML/OIDC/RBAC/SCIM, audit logs, private networking,
  encryption, customer-managed keys, data residency, private deployment/models,
  IP restrictions, approval policies. Don't expose enterprise source to external
  AI providers unnecessarily.
- **Audit & observability** — record important operations (user/agent/task/tool/
  repo change/model/usage/cost/approval/deploy/infra/security). Boldron itself
  must be observable (agent success/failure rates, task duration, model latency,
  AI cost, credit consumption, build/test/deploy/infra failures). Never build
  systems that can't explain what happened.

## 4. Product modes

- **Build mode** — a plain-language request produces *actual working software*
  through the agent pipeline (requirements → spec → architecture → db → backend
  → frontend → tests → review → build → export/deploy). Never stop at specs.
- **Existing-software mode** — import (GitHub/GitLab/Bitbucket/ZIP/local),
  analyze (language/framework/deps/architecture/db/API/security/testing/infra),
  produce an intelligence report, then improve/rebuild/modernize/fix/optimize/
  add-features/migrate.
- **Legacy mode** — COBOL/mainframe/legacy Java/PHP/.NET/legacy DBs/ERP. Never
  blind full rewrites: discovery → inventory → dependency graph → business-rule
  extraction → risk analysis → modernization plan → incremental migration →
  parallel validation → controlled cutover. Mission-critical cutovers require
  human approval.

## 5. Architecture map

Modular monolith. Do not prematurely split into microservices. Target backend
apps (built phase by phase — only `core` exists today):

```
backend/apps/
  accounts/  organizations/  projects/  workspaces/  repositories/
  requirements/  architecture/  agents/  agent_runs/  model_router/
  ai_providers/  credits/  usage/  costs/  billing/  builds/  tests/
  security/  deployments/  infrastructure/  cloud/  monitoring/
  artifacts/  integrations/  audit/
```

Frontend (Flutter Web + Flutter mobile, added later, top-level `frontend/`):
Dashboard, Projects, Project Workspace, Agent Activity, Requirements,
Architecture, Code, Builds, Tests, Deployments, Infrastructure, Monitoring,
Costs, Billing, Settings. The **project workspace** is the central interface —
it shows what Boldron understands, what agents are doing, what changed, what it
costs, what needs approval, what failed, and what's ready.

## 6. V1 scope

V1 proves the first core loop, nothing more:

```
CREATE PROJECT → DESCRIBE SOFTWARE → Requirements Agent → Architect Agent
→ Agent task graph → Backend/Frontend/Database Agents → Testing Agent
→ Code Review Agent → WORKING APPLICATION → EXPORT
```

V1 standardizes the generated stack (Django + DRF, PostgreSQL, Flutter Web,
Flutter mobile, Docker). Additional frameworks come after the agent architecture
is proven.

**Post-V1: agents generate and run a real project.** `apps/codegen` parses
guarded `{path, content}` files, commits them to the project's git repo,
compile-checks Python, and (`run_repo_tests`) runs the repo's suite in the build
sandbox. The Backend Agent generates a COMPLETE, self-contained, stdlib-only
runnable project (flat layout, `test_*.py` included) — the sandbox has no network,
so stdlib-only is what actually runs — commits it, and compile-checks it. The
Testing Agent then RUNS that project's `python -m unittest` in the sandbox and
reports real ran/failure/error counts. The Database Agent likewise generates Django
model source. Offline (stub) generates nothing; compile failures and test failures
are reported, never hidden.

Django mode (`stack: "django"`): Boldron deterministically scaffolds the project
(settings, manage.py, a migration-free in-memory test DB) around the model's app
(models.py + ORM tests.py), so the Testing Agent runs `manage.py test <app>`
against a REAL test database — the ORM actually persists and queries. Verified end
to end (Backend → scaffold → Testing → real DB run). (Dart/Frontend execution is
the next refinement.)

## 7. Build order (phases)

Build in order; don't jump around. **Every feature ships with tests and is only
done when implemented + integrated + tested + verified** (see `../CLAUDE.md`).

| # | Phase | Status |
|---|-------|--------|
| 1 | Repository foundation | **done — runnable Django modular monolith + `core` health endpoint + test** |
| 2 | Users & organizations | **done — email-based custom User; Organization + role-based Membership tenancy; `/api/v1/me/`; admin; 17 tests** |
| 3 | Projects & workspaces | **done — Project (per-org tenant scope) + Workspace (per-project, one default); tenant-scoped API; 35 tests** |
| 4 | Agent framework | **done — Capability model + least-privilege catalog of the 10 agents; BaseAgent contract w/ enforced run() boundary; registry; read-only catalog API; 16 tests. Agent behaviour deferred to Phase 6 (needs AI providers)** |
| 5 | Agent Orchestrator | **done — durable AgentTask (11-state machine, deps, retries, approval, usage fields); Orchestrator service drives BaseAgent.run(); restart recovery; tenant-scoped task API + approve/cancel; run_agent_tasks command; 18 tests** |
| 6 | AI provider abstraction | **done — provider-independent CompletionRequest/Response interface; StubProvider (offline default) + real gated AnthropicProvider (ENV-only key); registry+gateway; provider catalog API; agent→provider proven through orchestrator offline; 11 tests** |
| 7 | Model Router | **done — picks provider+model by complexity/context/budget/preference over the model catalog (cheapest-sufficient default, prefer_quality flip, real>stub); failover on complete(); /ai/models/ + dry-run /ai/route/; 15 tests** |
| 8 | Project context & memory | **done — ContextEntry store (14 kinds, per-project); ProjectContext service set/add/get/digest; tenant-scoped API + digest endpoint; shared project-scoping helper extracted; 12 tests** |
| 9 | Requirements Agent | **done — first shipped executable specialist: BaseAgent subclass (registered runner) using Model Router + Project Context to extract & persist structured requirements; honest offline no-op; 10 tests. First agent task that really works end-to-end.** |
| 10 | Architect Agent | **done — reads requirements from context, designs components + tech decisions via router (HIGH complexity), upserts them as ARCHITECTURE/TECH_DECISION entries (idempotent re-run); honest offline no-op; fails without requirements; 9 tests** |
| 11 | Backend Agent | **done — reads architecture+requirements, designs the HTTP API (endpoints by module) via router, upserts as API entries keyed by method+path; honest offline no-op; fails without architecture. (Actual backend code-gen lands with artifacts/build/export, P16/18.) 9 tests** |
| 12 | Frontend Agent | **done — reads requirements+API, designs Flutter screens, upserts as SCREEN entries; least-privilege (no backend/billing); offline no-op; 7 tests** |
| 13 | Database Agent | **done — reads architecture/requirements/API, designs relational data models, upserts as SCHEMA entries; no prod-data capability; offline no-op; 8 tests** |
| 14 | Testing Agent | **done — reads requirements+API, designs test cases (unit/integration/e2e/acceptance), upserts as TESTING entries; offline no-op; 7 tests** |
| 15 | Code Review Agent | **done — reviews the accumulated design (reqs/arch/API/schema) for gaps/security, records REVIEW findings w/ severity; review-only capabilities; fails with nothing to review; 8 tests** |
| 16 | Build sandbox | **done — Sandbox interface + SubprocessSandbox: scratch workdir, POSIX rlimits (cpu/mem/fsize/nproc/nofile), wall-timeout via process-group kill, scrubbed env, path-traversal guard, bounded output. Network isolation NOT enforced (needs containers — documented); interface ready for a container backend. 9 tests** |
| 17 | Git integration | **done — ProjectRepo per-project local git tree: init (main), write_files (traversal-guarded), commit (per-commit bot identity, no global config), branch/checkout, diff, log, ls-files. Local only (no remotes). 6 tests** |
| 18 | Export | **done — build_export() packages a project into a zip: README, docs/ (reqs/arch/api/data-model/screens/tests/review from context), api-spec.json, data-model.json, .env.example, and git-tracked source/; tenant-scoped download endpoint. No lock-in. 8 tests** |
| 19 | Credits & usage | **done — CreditAccount (per-org balance/plan) + UsageRecord ledger (org/project/task/model attribution); cost from catalog pricing → credits (config CREDITS_PER_USD); orchestrator records usage+debits on completion and STOPS tasks when balance depleted (budget protection); balance/usage API. 13 tests** |
| 20 | Cost estimation | **done — project cost analyzer: per-agent + total credit/USD RANGES from real catalog pricing (stub-excluded, meaningful offline), risk level, recommended plan; POST /projects/{id}/cost-estimate/ dry-run. 10 tests** |
| 21 | Deployment | **done — CloudProvider abstraction (real local target materializes the export; aws/gcp/azure/do/k8s gated as unavailable); Deployment records; production is approval-gated (never autonomous); list/create/approve/run API. 11 tests** |

Beyond the core loop, many further systems are built as their own bounded apps —
project operations, incidents, comments, settings, auth, publishing & commerce,
mobile release, support, billing/usage, security & test ledgers, and more. The
platform-intelligence layer below is the most recent addition.

### Application platform systems (built on the core)

A layer of per-project intelligence and governance systems, each composed from —
or evaluated against — **real project data only**, honestly gated (unknowns stay
unknown, nothing is claimed that can't be evidenced), tenant-isolated server-side,
audited on mutation, customer-safe, and shipped with a web surface, Flutter
parity, and tests. Several reuse one shared business-rules condition engine.

| System | Status |
|--------|--------|
| **Application Graph + Dependency Intelligence** (§4–5) | **done — node+edge model of the app (features/screens/APIs/entities/mobile/…) composed from the capability map, context entries, mobile plan and screen data-needs; edges only connect nodes that exist; answers "what depends on X, affected if it changes". `GET /projects/<id>/graph/`. ~17 tests** |
| **Acceptance Criteria** (§3) | **done — promotes the criteria embedded in requirements into first-class, verifiable records; pending by default, only a person marks met (with who/when); "accepted" only when all resolved and ≥1 truly met. ~17 tests** |
| **Business Rules + engine** (§12–13) | **done — formal categorised rules with draft→active→retired lifecycle and a deterministic evaluation engine; reported *enforced* only when the engine can actually decide it, else *documented*. ~14 tests** |
| **Project Health Score** (§30) | **done — one composed signal from the real security/test/incident/acceptance/deploy ledgers; pillars with no evidence are *unknown*, score is the mean of measured pillars only (None when nothing is measurable — never a fake 100). ~9 tests** |
| **Workflow / Automation engine** (§10–11) | **done — trigger→conditions→actions firing from real platform events (incident/deploy/tests/security), honest per-action outcomes (done/skipped/failed), loop-safe. ~23 tests** |
| **Feature flags** (§19) | **done — off unless enabled; deterministic stable-hash percentage rollout + condition targeting (fails closed); `…/flags/evaluate/`. ~13 tests** |
| **Explain-my-application** (§29) | **done — plain-language, customer-safe account (what it is/does/is made of/state) composed from capabilities, graph, requirements, rules, acceptance, health; can explain one part by tracing the graph. ~13 tests** |
| **Policy engine** (§44) | **done — declarative governance (block/require-approval/warn) wired into the real deploy pre-flight (a block policy genuinely fails a deploy); only enforced scopes can be targeted; built-in guardrails surfaced read-only. ~23 tests** |
| **Localization / i18n** (§17–18) | **done — per-project locales (RTL auto-detected), translation strings, honest coverage; missing translations fall back to source and are flagged, never shown as translated; `…/i18n/bundle/`. ~14 tests** |
| **A/B testing** (§20) | **done — stable weighted assignment, real exposure/conversion counts; a winner is only declared when a two-proportion z-test clears a minimum sample and p<0.05, else inconclusive. ~17 tests** |
| **Compliance** (§16) | **done — controls per framework (GDPR/POPIA/WCAG/security); platform-provided controls auto-evidenced from real facts, the rest pending until attested *with evidence*; never self-declares "compliant". ~11 tests** |
| **Data quality** (§9) | **done — deterministic checks (not_null/unique/regex/range/allowed/min_length) evaluated against real rows; true violation counts and scores, never estimated. ~14 tests** |
| **Performance intelligence** (§41) | **done — real timing samples → honest p50/p95/max per surface, slowest-first, with per-label/default budget flags; empty until measured. ~13 tests** |

All verified end-to-end through the authenticated web app against seeded real
data (e.g. Health shows "2 measured signals of 5" with unmeasured pillars honestly
*unknown*; A/B shows a numerically-ahead variant still *inconclusive* until
significant).

### Legal & Compliance Engine (built on the core)

A production-grade legal/compliance subsystem — a versioned, auditable,
jurisdiction-aware engine, **never static pages**. It holds the same honesty
line throughout: no false compliance/certification claims, legal-entity and
contacts come from the environment only, legal records are tenant/staff-isolated
and audited, and nothing is destroyed or disclosed without an explicit human step.

| System | Status |
|--------|--------|
| **Legal Document engine** (§1–4) | **done — `apps/legal`: one immutable published version per type/jurisdiction/language, draft→review→approve→publish→supersede→archive; publishing freezes content + SHA-256 and a model guard rejects edits (a change is a new version). Extensible type + jurisdiction registry. ~22 tests** |
| **Versioned acceptance** (§1, §45–46) | **done — durable `LegalAcceptance` (document, version, hash, who, org, IP/UA/country, consent type, mandatory, method) — never a boolean; idempotent per version; a changed mandatory doc re-prompts. Public read API + staff authoring + customer Legal Center + staff console** |
| **Consent management** (§21–22, §60) | **done — `apps/consent`: cookie consent (necessary forced on, optional off until opted in, no dark patterns) + marketing opt-IN kept separate from service comms; append-only logs. ~12 tests** |
| **Privacy requests & export** (§17–19) | **done — `apps/privacy`: data-subject request workflow (access/export/correction/deletion/…) with status machine, deadline, reviewer; deletion is tracked not instant; secrets-safe export. ~14 tests** |
| **Jurisdiction + law enforcement** (§5, §71) | **done — counsel-configured jurisdiction requirements (never inferred; configured:false until set) + staff-only law-enforcement request log (customer data never auto-disclosed). ~8 tests** |
| **Trust Center** (§26, §28, §29) | **done — `apps/trust`: public subprocessor register, honest security overview (certifications:[] + explicit no-cert disclaimer), private responsible-disclosure intake. ~11 tests** |
| **Security incidents** (§30) | **done — security-incident workflow with breach notification gated behind an explicit assessment — never auto-sent. ~5 tests** |
| **Account lifecycle + appeals** (§42–43) | **done — `apps/governance`: active→restricted→suspended→terminated with recorded reason/evidence; suspension genuinely blocks building; appeals with a reviewed outcome (a reversal restores). ~15 tests** |
| **Application legal** (§62–68) | **done — `apps/app_legal`: per-project privacy scan, policy↔product consistency, a pre-deploy check that never says "compliant", change triggers, and a draft generator (counsel-review disclaimer, real features only). ~14 tests** |
| **License tracking** (§12) | **done — `apps/licenses`: dependency records + honest license classifier (copyleft/unknown flagged for review), attribution; never declares the project "legally safe". ~7 tests** |
| **Governance dashboard + footers** (§58–59, §69) | **done — staff governance overview from real DB counts; dynamic footer of published documents; transactional email legal footer from configured identity only** |

The engine is built to accommodate — not fake — the external step it cannot do:
the actual legal copy and jurisdiction-specific obligations must be drafted and
reviewed by qualified legal counsel before launch, via the draft→review→approve→
publish workflow with configurable entity/jurisdiction settings.

Full backend suite ≈1,550 tests green; `flutter analyze` clean.

## 8. Long-term destination

```
                    BOLDRON
        BUILD  ·  MODERNIZE  ·  OPERATE
                       |
              AGENT ORCHESTRATOR
                       |
                 MODEL ROUTER
                       |
             PROJECT INTELLIGENCE
                       |
             COST / CREDIT ENGINE
                       |
              CLOUD ABSTRACTION
        AWS · Azure · GCP · Boldron Cloud · Customer Infra
```

This is the destination, not the v1 deliverable. Build the simplest architecture
that can *evolve* into it.
```
ONE USER → ONE LEAD AGENT → MANY SPECIALIZED AGENTS → CONTROLLED TOOLS
→ REAL SOFTWARE → TESTED → DEPLOYED → OPERATED.
```

---

## Client Transparency Boundary

Boldron's customer experience is conversation-first: **"Tell Boldron what you
want to build."** The customer describes an outcome; Boldron plans, builds, tests,
secures and reports it. The customer sees **what Boldron accomplished — never how
its proprietary engine accomplished it.**

**Customer-facing UI MAY show:** project status, build progress (as plain-language
steps), the generated application and its code where appropriate, tests/results,
deployment status, errors, costs, usage, changes, approvals, and activity relevant
to their own project.

**Customer-facing UI MUST NOT show:** internal agent topology or names, proprietary
prompts or system instructions, model-routing algorithms, internal scoring,
orchestration architecture, agent-to-agent communication, internal decision logic,
internal infrastructure topology, secret provider configuration, or Boldron's own
source. Internal work is translated to outcomes via `apps/dashboard/labels.py`
(e.g. the "code_review" step renders as "Quality review"). Leak-guard tests in
`apps/dashboard/tests.py` and `apps/marketing/tests.py` enforce this.

Advanced (technical) users may see technical artifacts — repository, database,
APIs, tests, logs — but still never the proprietary engine internals above.

## Unified Commerce Principle (architectural rule)

Every e-commerce project Boldron creates MUST use the shared commerce engine
(`apps/publishing` — `ecommerce_service`, models, `payments`) as the single source of
truth for products, variants, pricing, inventory, carts, discounts, coupons,
shipping, checkout, payments, refunds, orders, customers, taxes, currency, order
status, notifications and sales reporting.

**One engine, multiple experiences.** Web, Android and iOS consume the SAME commerce
services and the SAME API layer (`apps/publishing/api.py`, mounted at
`/api/v1/stores/<subdomain>/…`: products, checkout, orders). Platform-specific
frontends may differ in UI/UX but MUST NOT duplicate core commerce business logic or
keep an independent commerce database. Every order records its `channel`
(web/android/ios/api/pos/whatsapp/admin) so one Boldron admin shows all channels.

A transaction on one channel is immediately reflected on the others because they all
read/write the one order/inventory database (e.g. an inventory decrement from an iOS
purchase is visible to Web and Android on their next read). New channels are added by
building another experience against the same API — never by rebuilding the engine.

Money logic (totals, tax, discounts, inventory reservation) is deterministic and
lives only in the engine; the AI generates the *experience*, not the ledger.
