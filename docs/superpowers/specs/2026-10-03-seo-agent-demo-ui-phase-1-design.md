# SEO Agent MVP Demo UI — Phase 1 Design

## Purpose

Phase 1 adds a local, single-user Web demonstration for the existing SEO
planning product. The UI must demonstrate the real internal planning and
read-only review behavior without contacting customer websites, model
providers, search providers, audit providers, or WordPress.

The demonstrated path is:

1. Start
2. Analysis Progress
3. Audit / Results
4. Change Plan
5. Draft Review

WordPress delivery and verification remain outside the Web UI. Their existing
code and product boundaries are unchanged.

The baseline release is recorded by the annotated `seo-mvp-v1` tag, whose
peeled commit is `89cadef2f2ba81c1eec77d0f62c2058f2a14c7ae` and whose message is
`SEO Agent MVP v1`.

## Product Truthfulness

The UI exposes only one fixed target and two fixed planning inputs:

- Company: `NovaCNC Machinery`
- Display and workflow URL: `https://novacnc.example/`
- SEO goal and workflow research question:
  `Improve product-page SEO and content coverage`
- Language and workflow target language: `English` / `en`

These values are read-only. The start page labels the environment as `DEMO
MODE`, `Deterministic external boundaries`, and `NovaCNC Machinery —
deterministic site snapshot`. It does not imply that an arbitrary website can
be analyzed.

## Architectural Boundary

The implementation adds an isolated vertical slice under
`src/foreign_trade_geo_agent/web/`. Nothing in `core/`, `workflows/`,
`storage/`, `reporting/`, `runtime.py`, or `cli.py` imports the Web package.
Removing the Web package therefore leaves the existing agent and CLI intact.

The Web package does not contain a second planning pipeline. Its composition
root directly constructs and reuses:

- `SiteCrawlWorkflow`
- `TrafilaturaPageExtractor`
- `SiteContentPacketBuilder`
- `IndustryResearchWorkflow`
- `ContentOpportunityWorkflow`
- `ChangePlanWorkflow`
- `ContentDraftWorkflow`
- `EndToEndWorkflow`
- `SQLiteHistoryStore` and `SQLiteHistoryReader`
- `ContentDraftReviewWorkflow`
- existing core requests, reports, validators, and serialization

Only the external ports are replaced by deterministic Demo implementations.
The Web composition does not import `foreign_trade_geo_agent.runtime`, because
that module owns production provider defaults.

## Web Package Responsibilities

The package contains these focused units:

- `__init__.py`: exports the app factory without constructing an app at import
  time.
- `__main__.py`: starts Uvicorn for local use.
- `app.py`: FastAPI factory, static/template configuration, and lifespan.
- `routes.py`: HTTP mapping only; routes call `DemoApplicationService` and do
  not access workflows, the registry, or SQLite directly.
- `application.py`: thin application service over the composed workflow,
  registry, history reader, review workflow, and presenters.
- `composition.py`: fail-closed Demo object graph using real workflows and
  deterministic external ports.
- `jobs.py`: single-process `LocalJobRegistry`, task ownership, and transient
  observer state.
- `presenters.py`: bounded human-readable view models derived from validated
  persisted domain reports.
- `demo_boundaries.py`: deterministic implementations of the crawl fetcher,
  site auditor, search provider, research writer, opportunity writer, change
  plan writer, and content draft writer.
- `fixtures/novacnc/`: HTML pages, robots response, and provenance manifest.
- `templates/`: server-rendered Jinja pages and polling partials.
- `static/`: bounded CSS, minimal JavaScript if necessary, pinned HTMX, and
  the HTMX license.

## Fail-Closed Demo Composition

`web/composition.py` explicitly supplies every external port. It never relies
on a constructor default that could instantiate a production adapter.

The deterministic crawl fetcher serves only the exact NovaCNC origin and a
fixed allowlist of fixture paths. It returns the controlled robots response
and HTML bytes using the existing fetch result domain models. Unknown hosts,
paths, redirects, or fetch types fail immediately. Extraction remains real:
the returned HTML is processed by `TrafilaturaPageExtractor` inside the real
`SiteCrawlWorkflow`.

The other deterministic boundaries return bounded provider-independent domain
responses that drive the existing workflows and their validation. They do not
read environment credentials and do not import or wrap DeepSeek, Tavily,
GeoOptimizer, `SafeHtmlFetcher`, or WordPress adapters.

The fixture manifest records a stable fixture identity, the source project
name, a source revision when known (otherwise an explicit unknown value), and
a capture/update note. Neither startup nor tests read the separate
`geo-test-site` repository.

## Progress Observer

The provider-independent progress contract is additive and lives with the
existing end-to-end orchestration models. `EndToEndWorkflow` accepts an
optional synchronous observer; the production default is `None`.

The only event types are:

- `run_started`
- `stage_started`
- `stage_completed`
- `stage_failed`
- `run_finished`

An event contains only its type, the persisted run ID, and the applicable
`EndToEndStage`. It carries no prompts, reasoning, provider payloads, secrets,
or raw exceptions.

The six user-visible stages are crawl, site audit, industry research, content
opportunity, change plan, and content draft. Site-content packet construction
remains part of the crawl transition rather than appearing as a seventh UI
stage.

Event order for a successful run is `run_started`, followed by one
`stage_started`/`stage_completed` pair for each stage, then `run_finished`.
The failing stage emits `stage_failed`. Once a persisted run has been
successfully created and `run_started` has been emitted, every subsequent
terminal workflow path attempts `run_finished` best-effort. If run creation
itself fails, the workflow does not manufacture a run ID and does not emit
`run_started` or `run_finished`. Observer calls are wrapped independently; an
observer exception is ignored and cannot alter persisted artifacts, run
status, return values, or the original workflow exception.

## Background Jobs and Canonical State

The application lifespan owns one `LocalJobRegistry` and its active asyncio
tasks. The implementation assumes one process and one worker. It adds no
Redis, Celery, WebSocket, or queue framework.

`POST /start` asks `DemoApplicationService.start_demo_analysis()` to create a
local job, schedule the composed planning workflow, and return immediately.
The first location is `/jobs/{job_id}` because a workflow run ID does not
exist until `EndToEndWorkflow` creates its persisted run. The `run_started`
observer event associates the local job with that run ID. A later polling
response replaces browser history with `/runs/{run_id}/progress`.

The registry is transient and records only live task identity and recent
allowed progress events. SQLite run and artifact records remain canonical.
Whenever a run ID is available, the application service consults SQLite for
terminal status and page data.

Demo v1 uses an isolated default database at
`.data/demo-ui/history.sqlite3`. It never defaults to the production CLI
database `.data/history.sqlite3`, so Web Demo runs and CLI history remain
separate. Startup prints the resolved absolute Demo database path alongside
the local URL. Tests always inject an independent temporary database. This
isolation uses the existing SQLite schema without a migration or schema
change.

On refresh:

- a completed or failed run is reconstructed from SQLite without registry
  state;
- a RUNNING run with a matching active task shows its observer-derived stage;
- a RUNNING run without a matching active task shows
  `Interrupted — operator check required` and is not resumed automatically.

Graceful lifespan shutdown cancels and awaits owned tasks. An abrupt process
failure may leave a persisted RUNNING row; the interrupted rule handles that
case after restart.

## Application Service

Routes depend on one `DemoApplicationService`. At minimum it exposes:

- `start_demo_analysis()`
- `get_progress()`
- `load_results()`
- `load_change_plan()`
- `review_draft()`

The service invokes existing public Python APIs. It does not use SQL, workflow
private members, the CLI, or duplicated business validation. It loads the
single expected artifact of each type through the history reader, verifies
the persisted payload type/status, and passes it to a presenter. Missing,
ambiguous, unsupported, or malformed history fails closed with a sanitized
Web error.

Draft review resolves the persisted content-draft artifact and calls the real
`ContentDraftReviewWorkflow` with `ContentDraftReviewRequest`. Evidence
resolution and provenance validation are not repeated in the Web package.

## URLs and HTTP Behavior

The stable routes are:

- `/` — fixed start screen
- `/jobs/{job_id}` — pre-run-ID progress location
- `/runs/{run_id}/progress` — refreshable progress screen
- `/runs/{run_id}/results` — audit, observations, site evidence, and
  opportunities
- `/runs/{run_id}/changes` — change plan
- `/runs/{run_id}/drafts/{draft_id}` — read-only draft review

HTMX polls progress at 750 milliseconds. Polling attributes are rendered only
while an active task is running. Terminal, failed, missing, and interrupted
responses contain no polling trigger. Navigation links become available only
when the required persisted artifacts exist.

The implementation uses no login, server session, required cookie, progress
percentage, token counter, fake timer, or simulated reasoning.

## Presentation and Evidence Semantics

The common shell uses a roughly 230px workflow rail, a 64px context bar, and a
bounded main column. It uses a Segoe UI-first system stack, off-white/light
slate backgrounds, deep navy text, restrained teal accents, amber warnings,
muted red failures, and dark green success. It avoids gradients, glass
effects, chat metaphors, avatars, terminals, typing animations, and excessive
cards.

The progress screen displays only Waiting, Running, Complete, or Failed for:

1. Website Crawl
2. SEO Audit
3. Industry Research
4. Content Opportunities
5. Change Plan
6. Content Draft

Results presenters expose score, band, important observations, page title,
page URL, bounded excerpts, opportunity title, priority, and rationale. A#,
P#, and R# identifiers are secondary monospace metadata.

The change-plan presenter exposes Change, Type, Target, Why, and Evidence.
Evidence is grouped as Website Evidence, SEO Audit Evidence, and External
Research. `NOT_DETECTED` is described as an audit outcome, never rewritten as
a confirmed missing customer-site fact. External research is visibly labeled
as external context rather than website evidence.

Draft review uses a wide body column and narrow context rail. It displays the
complete plain-text draft plus why the draft exists, change context,
opportunity, evidence, and limitations. It prominently states:

- `Human Review Required`
- `Review action: READ ONLY`
- `Approval record: NOT RECORDED`
- `Review does not record approval.`

The only delivery control is disabled/informational:
`Continue to Delivery Setup — Coming in Demo Phase 2`. No approval or delivery
operation is exposed.

## Template and XSS Safety

The Jinja environment retains autoescape for HTML templates. Website text,
provider text, draft text, titles, URLs, observations, and excerpts are always
passed as untrusted strings. The implementation does not use `Markup`, the
Jinja `safe` filter, or direct HTML insertion for generated content.

Draft bodies remain plain text and preserve readable line breaks through CSS
or escaped line-by-line rendering. They are not converted from generated
Markdown to trusted HTML.

End-to-end tests inject `<script>alert(1)</script>` through at least three
distinct untrusted paths: Website Evidence fixture text, External Research
deterministic text, and Draft text. For each path, the rendered HTML must not
contain the literal script tag and must contain its escaped representation.

## Hard No-Network Tripwire

One composed-flow test exercises the application from Start through planning,
Results, Change Plan, and Draft Review while a process-level network tripwire
is active. The tripwire makes DNS resolution and socket connection attempts
raise an assertion immediately. It covers synchronous and asyncio connection
paths used by ordinary Python HTTP clients, so a future unknown network
adapter cannot silently pass merely because known provider constructors were
not inspected.

The same test also guards the currently known production boundaries by making
construction or use of DeepSeek, Tavily, GeoOptimizer, production
`SafeHtmlFetcher`, and WordPress adapters fail. The socket/DNS tripwire is the
primary future-proof guarantee; the named guards produce clearer regressions
for today's architecture.

FastAPI's in-process test client is used so the test itself needs no listening
socket. Fixture reads and SQLite use remain local filesystem operations.

## Dependencies and Packaging

`pyproject.toml` gains a bounded `demo` optional-dependency group containing
FastAPI, Uvicorn, and python-multipart. Jinja2 remains in the existing primary
dependency list and is not duplicated. Importing the base package, CLI, core,
workflows, or runtime does not require the Demo extra.

HTMX `2.0.11` is vendored as a fixed minified file under `web/static/` with
its upstream Zero-Clause BSD license. Templates never use a CDN. Package-data
configuration includes Web templates, static files, and NovaCNC fixtures.

The local entry point is:

```powershell
python -m pip install -e ".[demo]"
python -m foreign_trade_geo_agent.web
```

Demo v1 listens on `127.0.0.1` by default and must not default to `0.0.0.0`.
Startup prints the local URL and resolved absolute Demo database path. LAN and
public deployment are not designed or documented in Phase 1. The README
describes Demo Mode only and explicitly states that it does not contact real
customer sites, providers, or WordPress.

## Test Strategy

Implementation follows strict RED → GREEN cycles. Focused tests cover:

- optional observer event order, failure paths, and observer-exception
  isolation;
- app factory construction without network or eager workflow execution;
- composition with deterministic boundaries and the real workflow chain;
- background start and job-to-run association;
- progress partials driven by real events and SQLite state, including polling
  termination;
- persisted Results and Change Plan presentation;
- real `ContentDraftReviewWorkflow` provenance and review-only semantics;
- refresh recovery for completed runs and interrupted detection for orphaned
  RUNNING runs;
- Jinja escaping of hostile Website Evidence, External Research, and Draft
  text as three separately asserted paths;
- the hard no-network Start-to-Draft-Review composed flow;
- absence of delivery and verification UI/actions.

Final verification runs the Demo/Web targeted tests; existing planning,
review, and runtime regression tests; the full unittest suite;
`git diff --check`; and `git status --short`. No live integration script or
external service is invoked.

## Non-Goals and Preserved Boundaries

Phase 1 does not add authentication, arbitrary target input, configurable
goals or languages, production deployment guidance, multi-process jobs,
resume behavior, WordPress delivery UI, verification UI, approval recording,
or schema changes.

Existing CLI behavior, production runtime defaults, WordPress create-only and
draft-only delivery, verification, GEO functionality, SQLite schema, and
artifact formats remain unchanged.
