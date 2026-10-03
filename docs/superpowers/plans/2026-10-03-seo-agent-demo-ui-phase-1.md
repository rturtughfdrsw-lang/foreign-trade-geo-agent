# SEO Agent MVP Demo UI — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, deterministic, no-network Web UI for the existing SEO planning and read-only draft-review workflow.

**Architecture:** Add an isolated `foreign_trade_geo_agent.web` vertical slice whose composition root supplies deterministic implementations only for external ports and directly constructs the existing workflows, extractor, domain models, serialization, and SQLite storage. FastAPI routes call one thin `DemoApplicationService`; an in-memory single-process registry supplies live progress while SQLite remains canonical and refreshable.

**Tech Stack:** Python 3.12, FastAPI, server-rendered Jinja2, vendored HTMX 2.0.11, minimal CSS, asyncio background tasks, SQLite, standard-library `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-03-seo-agent-demo-ui-phase-1-design.md`

## Global Constraints

- Demo identity is fixed to `NovaCNC Machinery` and `https://novacnc.example/`.
- The exact research question is `Improve product-page SEO and content coverage`; target language is `en` and displayed as `English`.
- `web/composition.py` must not import `foreign_trade_geo_agent.runtime` or copy planning orchestration; it directly reuses the existing workflow classes.
- Demo composition must explicitly replace every external port and must never instantiate DeepSeek, Tavily, GeoOptimizer, production `SafeHtmlFetcher`, or WordPress adapters.
- Default Demo database is `.data/demo-ui/history.sqlite3`, never `.data/history.sqlite3`; tests inject temporary databases and no schema changes are allowed.
- The server defaults to `127.0.0.1`, never `0.0.0.0`; LAN/public deployment is out of scope.
- The observer is optional and best-effort; the production default remains `None`, and observer failures cannot change artifacts, run status, return values, or original exceptions.
- Routes call only `DemoApplicationService`; they do not query SQLite, call workflows, or inspect registry state directly.
- Use no React, Vite, Streamlit, Node/npm, Tailwind build, CDN asset, CLI subprocess, WebSocket, Redis, Celery, or queue framework.
- Generated and fixture content stays untrusted; no `Markup`, Jinja `safe`, Markdown-to-HTML conversion, or direct HTML insertion.
- Phase 1 exposes no approval, WordPress delivery, or verification action. The only delivery affordance is disabled text: `Continue to Delivery Setup — Coming in Demo Phase 2`.
- Implementation follows RED → GREEN. Do not commit or push any change.

## Review Focus

- Run creation failure: no fabricated run ID and no `run_started`/`run_finished` observer events; covered in Task 1.
- Unknown fixture host/path: fail closed locally without DNS or socket access; covered in Tasks 3 and 8.
- Orphaned persisted RUNNING run: render `Interrupted — operator check required`, do not poll or resume; covered in Tasks 4 and 6.
- Missing, duplicate, or malformed persisted artifacts: application service fails with sanitized errors instead of mixing evidence; covered in Task 5.
- Hostile Website Evidence, External Research, and Draft text: each remains escaped through the HTTP rendering path; covered in Task 7.

---

### Task 1: Add the provider-independent progress observer seam

**Files:**
- Modify: `src/foreign_trade_geo_agent/core/orchestration.py`
- Modify: `src/foreign_trade_geo_agent/workflows/end_to_end.py`
- Modify: `tests/test_end_to_end_workflow.py`

**Interfaces:**
- Produces: `EndToEndProgressEventKind`, `EndToEndProgressEvent`, and `EndToEndProgressObserver` in `core.orchestration`.
- Produces: optional `progress_observer: EndToEndProgressObserver | None = None` constructor parameter on `EndToEndWorkflow`.
- Event fields: `kind`, persisted `run_id`, and `stage: EndToEndStage | None`; run events require `stage is None`, stage events require one of the six visible stages and never `SITE_CONTENT`.

- [ ] **Step 1: Write failing observer model and workflow tests**

Add tests named:

```python
def test_progress_event_rejects_invalid_stage_shape(): ...
async def test_progress_observer_reports_successful_stage_order(): ...
async def test_progress_observer_reports_failed_stage_and_run_finish(): ...
async def test_observer_exception_does_not_change_success_result_or_artifacts(): ...
async def test_run_creation_failure_emits_no_progress_events(): ...
```

Assert the exact successful order `run_started`, six start/complete pairs, then `run_finished`; an audit failure emits `stage_started(SITE_AUDIT)`, `stage_failed(SITE_AUDIT)`, then `run_finished`; an observer that raises on every call produces the same `EndToEndRunResult` and persisted artifacts as a non-raising observer; and `create_run` failure yields no event.

- [ ] **Step 2: Run the observer tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_end_to_end_workflow -v
```

Expected: FAIL because the progress event types and constructor parameter do not exist.

- [ ] **Step 3: Implement the minimal observer contract and notifications**

Add the three interfaces above. Wrap each observer invocation in `try/except Exception`. Emit `run_started` only after `create_run` succeeds; after that point, attempt exactly one `run_finished` from a terminal `finally` path. Instrument the existing stages without changing their ordering, validation, persistence, or failure results; do not extract a second orchestration path.

- [ ] **Step 4: Run the observer tests and existing planning regression**

Run the Task 1 command again, then:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_mvp_composed_flow tests.test_runtime -v
```

Expected: PASS; runtime construction remains valid without supplying an observer.

### Task 2: Add bounded Demo dependencies, package assets, and the NovaCNC snapshot

**Files:**
- Modify: `pyproject.toml`
- Create: `src/foreign_trade_geo_agent/web/__init__.py`
- Create: `src/foreign_trade_geo_agent/web/fixtures/novacnc/manifest.json`
- Create: `src/foreign_trade_geo_agent/web/fixtures/novacnc/robots.txt`
- Create: `src/foreign_trade_geo_agent/web/fixtures/novacnc/index.html`
- Create: `src/foreign_trade_geo_agent/web/fixtures/novacnc/machines.html`
- Create: `src/foreign_trade_geo_agent/web/static/htmx-2.0.11.min.js`
- Create: `src/foreign_trade_geo_agent/web/static/HTMX-LICENSE.txt`
- Test: `tests/test_web_demo_assets.py`

**Interfaces:**
- Produces: optional dependency group `demo = ["fastapi>=0.115,<1", "uvicorn>=0.30,<1", "python-multipart>=0.0.9,<1"]`.
- Produces: package data for `templates/**/*.html`, `static/*`, and `fixtures/novacnc/*`.
- Produces: self-contained exact-origin fixture with a manifest recording identity, source project, source revision or explicit unknown value, and capture/update note.

- [ ] **Step 1: Write failing package and fixture tests**

```python
def test_demo_extra_is_bounded_and_does_not_duplicate_jinja(): ...
def test_novacnc_manifest_and_required_fixture_files_are_packaged(): ...
def test_htmx_is_pinned_local_and_license_is_present(): ...
def test_base_package_import_does_not_import_fastapi(): ...
```

Parse `pyproject.toml` with `tomllib`; assert `fastapi`, `uvicorn`, and `python-multipart` exist only in `[project.optional-dependencies].demo` and none appears in base `project.dependencies`; also assert all three requirements are bounded, no Jinja2 entry is duplicated in the extra, the fixed HTMX filename/content version and upstream license are present, and the NovaCNC manifest fields are complete. Import the base package in a fresh subprocess and assert `fastapi` is absent from `sys.modules`.

- [ ] **Step 2: Run the asset tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_assets -v
```

Expected: FAIL because the optional group and Web assets do not exist.

- [ ] **Step 3: Add the minimal dependency metadata and exact vendored assets**

Add the bounded extra and package-data entries. Add a small two-page NovaCNC HTML graph and deterministic robots file. Vendor the exact upstream HTMX 2.0.11 minified distribution and Zero-Clause BSD license; templates added later must reference only `/static/htmx-2.0.11.min.js`.

- [ ] **Step 4: Install the Demo extra and run the asset tests GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[demo]"
.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_assets -v
```

Expected: installation succeeds and all asset tests PASS.

### Task 3: Build deterministic external boundaries and fail-closed composition

**Files:**
- Create: `src/foreign_trade_geo_agent/web/demo_boundaries.py`
- Create: `src/foreign_trade_geo_agent/web/composition.py`
- Test: `tests/test_web_demo_composition.py`

**Interfaces:**
- Produces constants `DEMO_COMPANY_NAME`, `DEMO_SITE_URL`, `DEMO_RESEARCH_QUESTION`, and `DEMO_TARGET_LANGUAGE` with the exact global values.
- Produces deterministic port implementations `DemoCrawlFetcher`, `DemoSiteAuditor`, `DemoSearchProvider`, `DemoResearchWriter`, `DemoContentOpportunityWriter`, `DemoChangePlanWriter`, and `DemoContentDraftWriter`.
- Produces immutable `DemoComposition` with `db_path: Path`, `history_reader: SQLiteHistoryReader`, `review_workflow: ContentDraftReviewWorkflow`, and `planning_workflow(progress_observer: EndToEndProgressObserver | None) -> EndToEndWorkflow`.
- Produces `build_demo_composition(db_path: str | Path) -> DemoComposition`.

- [ ] **Step 1: Write failing boundary and composition tests**

```python
async def test_fixture_fetcher_serves_only_exact_novacnc_allowlist(): ...
async def test_demo_composition_runs_real_planning_chain_into_sqlite(): ...
def test_demo_composition_has_no_runtime_or_production_provider_dependency(): ...
```

Assert robots and both HTML pages use existing `HtmlFetchResult`; an unknown host or path raises a sanitized local exception before any resolver call; the composed workflow returns `SUCCEEDED` with the six artifact types in order; the stored page evidence proves `TrafilaturaPageExtractor` processed fixture HTML; and the composition source/import graph contains no `runtime`, DeepSeek, Tavily, GeoOptimizer, `SafeHtmlFetcher`, or WordPress adapter. Run `test_demo_composition_runs_real_planning_chain_into_sqlite` under process-level guards that raise `AssertionError` from `socket.getaddrinfo`, `socket.create_connection`, `socket.socket.connect`, `socket.socket.connect_ex`, and asyncio event-loop connection creation, proving the deterministic composition → real workflow → real Trafilatura → real SQLite path is no-network from Task 3 onward.

- [ ] **Step 2: Run the composition tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_composition -v
```

Expected: FAIL because deterministic boundaries and composition are missing.

- [ ] **Step 3: Implement deterministic ports and direct real-workflow wiring**

Construct `SiteCrawlWorkflow(DemoCrawlFetcher, TrafilaturaPageExtractor, ...)` and the existing packet, research, opportunity, change-plan, draft, and end-to-end workflows directly. Each writer returns the smallest valid provider-independent generation that produces P1/P2, A#, S1, R1, C1, and at least D1 through existing validators. Initialize the existing SQLite store at the injected path and create the existing read-only review workflow; add no SQL or schema.

- [ ] **Step 4: Run composition and crawl/planning regressions GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_composition tests.test_site_crawl_workflow tests.test_end_to_end_workflow -v
```

Expected: PASS.

### Task 4: Add local job ownership and canonical progress recovery

**Files:**
- Create: `src/foreign_trade_geo_agent/web/jobs.py`
- Create: `src/foreign_trade_geo_agent/web/application.py`
- Create: `src/foreign_trade_geo_agent/web/presenters.py`
- Test: `tests/test_web_jobs.py`
- Test: `tests/test_web_application_progress.py`

**Interfaces:**
- Produces immutable `LocalJobSnapshot(job_id, run_id, events, active, failure_message)`.
- Produces `LocalJobRegistry.create_job() -> str`, `observer_for(job_id) -> EndToEndProgressObserver`, `attach_task(job_id, task: asyncio.Task[object]) -> None`, `get_job(job_id) -> LocalJobSnapshot | None`, `get_job_for_run(run_id) -> LocalJobSnapshot | None`, and `shutdown() -> Awaitable[None]`.
- Produces `DemoStartResult(job_id: str)` and `DemoProgressView(location, run_id, stages, terminal, polling, interrupted, message)`.
- Produces `DemoApplicationService(composition: DemoComposition, jobs: LocalJobRegistry)`.
- Produces `DemoApplicationService.start_demo_analysis() -> DemoStartResult` and `get_progress(*, job_id: str | None = None, run_id: str | None = None) -> DemoProgressView`.

- [ ] **Step 1: Write failing registry and progress-service tests**

```python
async def test_start_creates_job_and_returns_before_gated_workflow_finishes(): ...
async def test_observer_associates_persisted_run_and_real_stage_state(): ...
async def test_completed_sqlite_run_recovers_without_memory_job(): ...
async def test_running_sqlite_run_without_active_job_is_interrupted(): ...
async def test_background_failure_is_sanitized_and_stops_polling(): ...
async def test_registry_shutdown_cancels_and_awaits_owned_tasks(): ...
```

Use a gated fake workflow factory only for background timing tests and a temporary real SQLite store for refresh tests. Assert interrupted progress has `polling is False`, contains the exact operator-check copy, and never schedules a replacement task.

- [ ] **Step 2: Run the job/application tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_jobs tests.test_web_application_progress -v
```

Expected: FAIL because registry, service, and progress view do not exist.

- [ ] **Step 3: Implement the minimal registry, background runner, and progress presenter**

Registry mutation remains synchronous and event-loop local. The service builds an `EndToEndRunRequest` only from the four fixed Demo constants, attaches the registry observer, and owns no planning logic. For a known run ID, read `WorkflowRun` through `SQLiteHistoryReader` before consulting transient events. Map the six stages to Waiting/Running/Complete/Failed without percentages.

- [ ] **Step 4: Run Task 4 tests and composition regression GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_jobs tests.test_web_application_progress tests.test_web_demo_composition -v
```

Expected: PASS.

### Task 5: Present persisted Results, Change Plan, and real Draft Review

**Files:**
- Modify: `src/foreign_trade_geo_agent/web/application.py`
- Modify: `src/foreign_trade_geo_agent/web/presenters.py`
- Test: `tests/test_web_presenters.py`
- Test: `tests/test_web_application_results.py`

**Interfaces:**
- Produces `DemoResultsView` containing audit score/band/observations, `WebsiteEvidenceView` rows, `OpportunityView` rows, and draft navigation IDs.
- Produces `DemoChangePlanView` containing `ChangeView` rows whose evidence is separated into Website Evidence, SEO Audit Evidence, and External Research.
- Produces `DemoDraftReviewView` wrapping the validated `ContentDraftReviewView` plus fixed read-only/approval/delivery copy.
- Produces `DemoApplicationService.load_results(run_id) -> DemoResultsView`, `load_change_plan(run_id) -> DemoChangePlanView`, and `review_draft(run_id, draft_id) -> DemoDraftReviewView`.

- [ ] **Step 1: Write failing persisted-presentation tests**

```python
async def test_results_are_recovered_from_sqlite_with_a_p_r_metadata(): ...
async def test_change_plan_separates_three_evidence_classes(): ...
async def test_not_detected_is_not_presented_as_confirmed_missing(): ...
async def test_draft_review_uses_real_review_workflow_and_is_read_only(): ...
async def test_missing_duplicate_or_malformed_artifacts_fail_sanitized(): ...
```

Run the real Demo planning workflow into a temporary DB, construct a fresh service/empty registry, and load every view from SQLite. Snapshot business rows before/after review to prove no write. Corrupt or duplicate test history through test-only helpers and assert the browser-facing error contains no raw payload or provider text.

- [ ] **Step 2: Run the presenter/application tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_presenters tests.test_web_application_results -v
```

Expected: FAIL because the persisted page views and service methods are missing.

- [ ] **Step 3: Implement bounded presenters over validated artifacts**

Load exactly one required artifact per type with `SQLiteHistoryReader`, check its existing payload class/status, and map only bounded display fields. Resolve the content-draft artifact ID, then call `ContentDraftReviewWorkflow.review` with `ContentDraftReviewRequest`; do not reproduce provenance joining. Keep internal IDs secondary and preserve external-research labeling.

- [ ] **Step 4: Run Task 5 and existing review regressions GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_presenters tests.test_web_application_results tests.test_content_draft_review_workflow tests.test_content_draft_review_readonly tests.test_content_draft_review_renderer -v
```

Expected: PASS.

### Task 6: Add the FastAPI factory, local lifecycle, Start, and Progress screens

**Files:**
- Create: `src/foreign_trade_geo_agent/web/app.py`
- Create: `src/foreign_trade_geo_agent/web/routes.py`
- Create: `src/foreign_trade_geo_agent/web/templates/base.html`
- Create: `src/foreign_trade_geo_agent/web/templates/start.html`
- Create: `src/foreign_trade_geo_agent/web/templates/progress.html`
- Create: `src/foreign_trade_geo_agent/web/templates/partials/progress_panel.html`
- Create: `src/foreign_trade_geo_agent/web/templates/error.html`
- Create: `src/foreign_trade_geo_agent/web/static/app.css`
- Test: `tests/test_web_app.py`
- Test: `tests/test_web_progress_routes.py`

**Interfaces:**
- Produces `DEFAULT_DEMO_DB_PATH = Path(".data/demo-ui/history.sqlite3")`.
- Produces `DemoServiceFactory = Callable[[Path, LocalJobRegistry], DemoApplicationService]` for test-only app injection without exposing workflows to routes.
- Produces `create_app(*, db_path: str | Path = DEFAULT_DEMO_DB_PATH, service_factory: DemoServiceFactory | None = None) -> FastAPI`.
- Produces GET `/`, POST `/start`, GET `/jobs/{job_id}`, and GET `/runs/{run_id}/progress`; routes obtain only the lifespan-owned `DemoApplicationService`.

- [ ] **Step 1: Write failing app-factory and Start/Progress route tests**

```python
def test_app_factory_constructs_without_network_or_creating_a_run(): ...
def test_start_page_shows_exact_fixed_inputs_and_demo_disclosures(): ...
def test_start_post_returns_job_progress_without_waiting_for_workflow(): ...
def test_progress_partial_replaces_url_after_run_started(): ...
def test_terminal_and_interrupted_progress_stop_htmx_polling(): ...
def test_routes_need_no_session_and_set_no_required_cookie(): ...
```

Assert local HTMX URL only, no CDN, no editable site/goal/language fields, the exact `Runs the real internal SEO workflow using deterministic demo boundaries.` explanation, the persistent Demo Mode banner, 750ms polling only for active work, `HX-Replace-Url` after run association, and no polling attribute in terminal/interrupted HTML.

- [ ] **Step 2: Run the Web app/route tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_app tests.test_web_progress_routes -v
```

Expected: FAIL because the app factory and routes do not exist.

- [ ] **Step 3: Implement the minimal FastAPI shell and lifespan**

Mount static files, configure Jinja with HTML autoescape, and have lifespan construct the composition, registry, and service and call registry shutdown. Render the restrained shared shell with a roughly 230px workflow rail, 64px context bar, 1100–1200px bounded content, Segoe UI-first system fonts, and six-stage progress rail. The POST starts one background task and returns the job progress location immediately.

- [ ] **Step 4: Run Task 6 tests and base CLI import regression GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_app tests.test_web_progress_routes tests.test_cli tests.test_runtime -v
```

Expected: PASS; CLI imports and behavior remain independent of FastAPI.

### Task 7: Add Results, Change Plan, Draft Review screens and three-path XSS coverage

**Files:**
- Modify: `src/foreign_trade_geo_agent/web/routes.py`
- Create: `src/foreign_trade_geo_agent/web/templates/results.html`
- Create: `src/foreign_trade_geo_agent/web/templates/changes.html`
- Create: `src/foreign_trade_geo_agent/web/templates/draft_review.html`
- Modify: `src/foreign_trade_geo_agent/web/static/app.css`
- Test: `tests/test_web_result_routes.py`
- Test: `tests/test_web_xss.py`
- Test: `tests/test_web_no_network.py`

**Interfaces:**
- Produces GET `/runs/{run_id}/results`, GET `/runs/{run_id}/changes`, and GET `/runs/{run_id}/drafts/{draft_id}`.
- Consumes only the three Task 5 service methods and view types.

- [ ] **Step 1: Write failing screen and hostile-text tests**

```python
def test_results_screen_renders_audit_evidence_and_opportunities(): ...
def test_change_screen_renders_human_fields_and_three_evidence_groups(): ...
def test_draft_screen_renders_full_review_and_read_only_semantics(): ...
def test_website_evidence_script_text_is_escaped(): ...
def test_external_research_script_text_is_escaped(): ...
def test_draft_script_text_is_escaped(): ...
def test_phase_one_has_no_approval_delivery_or_verification_route(): ...
def test_web_templates_and_python_use_no_safe_markup_escape_bypass(): ...
def test_invalid_run_or_draft_identifier_returns_sanitized_not_found(): ...
def test_start_to_draft_review_has_hard_no_network_tripwire(): ...
```

For each XSS test, inject `<script>alert(1)</script>` through the named view source over an HTTP request, assert the literal tag is absent, and assert `&lt;script&gt;alert(1)&lt;/script&gt;` is present. Assert templates contain no `|safe` and the disabled Phase 2 button cannot submit. For the no-network test, guard DNS, socket, asyncio connection creation, and known production provider constructors before using the default app composition; POST Start, poll to terminal, then request Results, Change Plan, and D1 Draft Review.

- [ ] **Step 2: Run result/XSS tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_result_routes tests.test_web_xss tests.test_web_no_network -v
```

Expected: FAIL because page routes/templates are absent; the no-network tripwire must not be the source of an unrelated test-client failure.

- [ ] **Step 3: Implement the three server-rendered screens**

Render presenter fields only. Use ordinary escaped interpolation and CSS `white-space` handling for complete draft text. Show evidence group titles and secondary monospace IDs, the four required review statements, and only the disabled Phase 2 delivery control.

- [ ] **Step 4: Run Task 7 and prior Web route tests GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_result_routes tests.test_web_xss tests.test_web_no_network tests.test_web_app tests.test_web_progress_routes -v
```

Expected: PASS.

### Task 8: Re-run and audit the complete hard no-network acceptance path

**Files:**
- No planned file changes.
- If the acceptance test exposes a leak, first add a narrower failing assertion to `tests/test_web_no_network.py`, then modify only the owning file under `src/foreign_trade_geo_agent/web/`.

**Interfaces:**
- Consumes `create_app(db_path=<temporary path>)` with the default real Demo composition.
- Adds no production network abstraction; this is an acceptance gate for the RED→GREEN test introduced in Task 7.

- [ ] **Step 1: Run the composed-flow tripwire independently**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_no_network -v
```

Expected: PASS. The test uses FastAPI's in-process client, reaches all five screens, observes six persisted artifacts in the temporary SQLite DB, and keeps every DNS/socket/provider guard active.

- [ ] **Step 2: If RED, preserve the tripwire and reproduce the narrow leak**

Do not whitelist outbound calls. Add a focused failing assertion for the exact import or call path, then make the minimal production correction: replace the dependency with the designed deterministic port or remove the accidental production import.

- [ ] **Step 3: Run the no-network and all Web tests GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_assets tests.test_web_demo_composition tests.test_web_jobs tests.test_web_application_progress tests.test_web_presenters tests.test_web_application_results tests.test_web_app tests.test_web_progress_routes tests.test_web_result_routes tests.test_web_xss tests.test_web_no_network -v
```

Expected: PASS with every network tripwire still active for the composed-flow test.

### Task 9: Add the safe local entry point and Demo-only README instructions

**Files:**
- Create: `src/foreign_trade_geo_agent/web/__main__.py`
- Modify: `README.md`
- Test: `tests/test_web_entrypoint.py`

**Interfaces:**
- Produces `main() -> None`, resolving `.data/demo-ui/history.sqlite3`, printing its absolute path and `http://127.0.0.1:8000`, then invoking Uvicorn with `host="127.0.0.1"` and no `0.0.0.0` default.

- [ ] **Step 1: Write failing entrypoint and documentation tests**

```python
def test_entrypoint_defaults_to_loopback_and_isolated_absolute_database(): ...
def test_readme_documents_demo_extra_command_and_no_external_contact(): ...
```

Patch `uvicorn.run` and assert host, port, app factory, and printed resolved DB path. Assert README contains `python -m pip install -e ".[demo]"`, `python -m foreign_trade_geo_agent.web`, the loopback URL, Demo Mode only, and the no-customer-site/provider/WordPress disclosure.

- [ ] **Step 2: Run the entrypoint tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_entrypoint -v
```

Expected: FAIL because `web.__main__` and README Demo instructions are absent.

- [ ] **Step 3: Implement the local-only runner and minimal README section**

Keep production deployment, LAN binding, credentials, delivery, and verification out of the documentation. Do not load `.env` or production runtime configuration.

- [ ] **Step 4: Run entrypoint and full Web regression GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_entrypoint tests.test_web_no_network tests.test_web_app -v
```

Expected: PASS.

### Task 10: Run required regressions and final verification without external services

**Files:**
- No planned production changes.
- Modify the owning test/implementation task only if verification reveals a regression; reproduce any bug with a failing focused test before fixing it.

**Interfaces:**
- Produces verification evidence only; no commit, push, live API call, crawl, WordPress operation, delivery UI, or verification UI.

- [ ] **Step 1: Run all Demo/Web targeted tests**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_assets tests.test_web_demo_composition tests.test_web_jobs tests.test_web_application_progress tests.test_web_presenters tests.test_web_application_results tests.test_web_app tests.test_web_progress_routes tests.test_web_result_routes tests.test_web_xss tests.test_web_no_network tests.test_web_entrypoint -v
```

Expected: PASS.

- [ ] **Step 2: Run planning, review, and runtime regressions**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_site_crawl_workflow tests.test_end_to_end_workflow tests.test_industry_research_workflow tests.test_content_opportunity_workflow tests.test_change_plan_workflow tests.test_content_draft_workflow tests.test_content_draft_review_workflow tests.test_content_draft_review_readonly tests.test_content_draft_review_renderer tests.test_runtime tests.test_mvp_composed_flow -v
```

Expected: PASS.

- [ ] **Step 3: Run the full unittest suite**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS with no real external service calls.

- [ ] **Step 4: Check whitespace and final working-tree state**

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` exits zero; status lists only the approved spec and plan, `src/foreign_trade_geo_agent/core/orchestration.py`, `src/foreign_trade_geo_agent/workflows/end_to_end.py`, `tests/test_end_to_end_workflow.py`, Phase 1 files under `src/foreign_trade_geo_agent/web/`, focused `tests/test_web_*.py` files, `pyproject.toml`, and `README.md`.

- [ ] **Step 5: Prepare the A–O review report and stop**

Report tag result, implementation, architecture, no-network guarantees, progress behavior, screens, review semantics, XSS safety, dependencies, tests, verification, files, run instructions, remaining Phase 2 work, and risks. Do not commit or push.
