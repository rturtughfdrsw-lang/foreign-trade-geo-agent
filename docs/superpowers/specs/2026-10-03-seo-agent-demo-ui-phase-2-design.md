# SEO Agent MVP Demo UI — Phase 2 Design

## Purpose

Phase 2 adds a deterministic, loopback-only Web entry point over the existing,
already-tested WordPress delivery and read-back verification workflows. It is
the final mentor-demo path:

```
Draft Review
→ Delivery Setup
→ Create WordPress Draft
→ Delivery Result
→ Verify Draft
→ Verification Result
```

Phase 2 reuses the real WordPress logic. The Web package only adds a new entry
point; it does not re-implement WordPress REST semantics, create-outcome
classification, verification classification, fingerprint logic, retry logic,
delivery safety, or provenance validation.

## Goal and Non-Goals

In scope:

- a deterministic Demo WordPress Sandbox (real adapter + `httpx.MockTransport`);
- per-run target identity to keep independent demo runs independent;
- a 7-step workflow rail (Start, Progress, Results, Change Plan, Draft Review,
  WordPress Delivery, Verification);
- delivery setup / delivery result / verification result screens;
- explicit human-intent checkbox that is not a persisted approval record;
- strict no-retry behavior for uncertain create outcomes, plus an explicit
  retry path for `FAILED_DEFINITELY`;
- a hard no-network composed contract and an ambiguous-create safety contract;
- an owned-process Windows one-click launcher.

Out of scope (unchanged from Phase 1 / core):

- real WordPress, production Live Mode, customer credentials;
- publish, update existing post, delete;
- automatic retry or automatic reconciliation;
- approval persistence, login, accounts, roles, teams, billing, multi-tenant;
- cloud deployment, Shopify, Webflow, GEO expansion;
- production recovery P0 or a notification system.

## Existing Delivery / Verification APIs Reused

The following exist and are already unit/contract tested; Phase 2 reuses them
unchanged:

- `ApprovedWordPressDraftDeliveryWorkflow` (`workflows/approved_wordpress_delivery.py`)
  with `deliver(ApprovedWordPressDraftDeliveryRequest)` →
  `ApprovedWordPressDraftDeliveryResult` (`.attempt`, `.delivery_result`,
  `.reconciliation_required`).
- `WordPressDeliveryWorkflow` (`workflows/wordpress_delivery.py`) with
  `WordPressDeliveryStatus = SUCCESS | FAILED_DEFINITELY | UNKNOWN | BLOCKED`;
  it begins a `PENDING` attempt, calls the publisher, finishes the attempt, and
  enforces duplicate-create safety through `_blocking_attempts`.
- `WordPressDraftVerificationWorkflow` (`workflows/wordpress_verification.py`)
  with `verify(WordPressVerificationRequest(attempt_id))` →
  `WordPressDraftVerificationResult`; it takes a
  `draft_reader_factory: Callable[[str], WordPressDraftReader]`.
- `WordPressRestDraftPublisher` and `WordPressRestDraftReader`
  (`adapters/wordpress_rest.py`); both accept `transport: httpx.AsyncBaseTransport`,
  and when a transport is injected neither resolver, DNS, nor socket access is
  performed.
- `SQLiteHistoryStore` and `SQLiteHistoryReader` (`storage/sqlite.py`); the
  store exposes `begin_wordpress_attempt`, `finish_wordpress_attempt`,
  `get_wordpress_attempt`, `list_wordpress_attempts`,
  `list_wordpress_attempts_for_draft`, `find_wordpress_attempts_by_fingerprint`,
  `append_wordpress_verification`, and `list_wordpress_verifications`. The
  reader only exposes `get_wordpress_attempt` and `list_wordpress_verifications`,
  so Phase 2 reads attempts through the store (the Demo already owns a store).
- Core models `WordPressAttemptState` (`PENDING/SUCCESS/FAILED_DEFINITELY/UNKNOWN`),
  `WordPressVerificationOutcome` (`VERIFIED/NOT_FOUND/MISMATCH/UNKNOWN/UNRESOLVED`),
  `WordPressVerificationLookupKind` (`REMOTE_ID/NONE`),
  `WordPressVerificationFailureKind`, `WordPressDraftAttempt`, and
  `WordPressVerification`.
- `wordpress_request_fingerprint(target_site_key, request)` and the SQLite
  partial unique index on `(target_site_key, request_fingerprint)` for
  `PENDING/SUCCESS/UNKNOWN`.

The schema is already `PRAGMA user_version = 2` with both
`wordpress_draft_attempts` and `wordpress_draft_verifications`. Phase 2 adds no
schema.

The authoritative composed pattern is `tests/test_mvp_composed_flow.py`, which
already runs the real adapter over `httpx.MockTransport` through
planning → review → delivery → verification, and asserts POST=1, GET=1,
UNKNOWN→UNRESOLVED (GET=0), and a second create is BLOCKED (POST still 1).

## Demo WordPress Sandbox

The sandbox is:

```
real WordPressRestDraftPublisher / WordPressRestDraftReader
+ deterministic httpx.MockTransport
+ fixed, clearly non-real sentinel credentials
+ deterministic per-run target origin
```

Sentinel credentials (code constants only, never read from environment):

```text
demo-user
demo-application-password-not-a-secret
```

The transport handler is deterministic and stateless:

- `POST /wp-json/wp/v2/posts` requires the JSON body `status == "draft"` and
  returns `201 {"id": 41, "status": "draft", "link": f"{origin}/?p=41"}`.
- `GET /wp-json/wp/v2/posts/41` returns
  `200 {"id": 41, "status": "draft", "link": f"{origin}/?p=41", "title": {"rendered": ...}, "content": {"rendered": ...}}`.
- Any `PUT`, `PATCH`, `DELETE`, or unknown path raises `AssertionError`.

`origin` is derived from the incoming request URL, so the sandbox is stateless
and survives process restart: a persisted `SUCCESS` attempt (with
`remote_post_id = 41` and its `target_site_key`) can always be read back
VERIFIED by the same handler.

### Sanitized observations, no credential-bearing Request retention

The transport never retains `httpx.Request` objects (they carry the
`Authorization` header). It records only a bounded, sanitized observation:

```text
DemoWordPressRequestObservation:
  method            # POST | GET
  path              # the exact API path
  requested_status  # POST body "status" value, or None
  remote_post_id    # GET path post id, or None
```

It never stores `Authorization`, `username`, `application_password`, complete
headers, or the raw `httpx.Request`. Tests assert POST/GET counts, absence of
PUT/PATCH/DELETE, expected endpoint paths, and `POST status == draft` solely
from these sanitized observations.

## Per-Run Target Identity

The Demo draft content is fixed, so a fixed target origin would make every run
produce the same `wordpress_request_fingerprint` and a later run would be
blocked by an earlier `SUCCESS/UNKNOWN` attempt.

The service therefore derives a per-run mock origin server-side:

```text
target_site_url = "https://demo-wordpress-{run_id}.example"
```

`run_id` is a canonical UUID (valid DNS label characters), and `.example` is
the RFC 6761 reserved TLD. Each run gets a distinct `target_site_key`, so each
run has a distinct fingerprint and no false cross-run duplicate blocking.
Within one run, repeated create is still correctly blocked by the fingerprint
guard and the SQLite unique index. The origin passes
`normalize_wordpress_https_url` / `site_key_from_url` /
`_host_is_statically_denied`, and because a MockTransport is injected, no DNS
or socket is ever touched.

Delivery and verification use the same origin: delivery posts to
`target_site_url`, and verification's `draft_reader_factory(site_key)` builds a
reader with `base_url = site_key`, which normalizes to the identical site key.

## Backend / UI Boundary

Routes call only `DemoApplicationService`. The service constructs existing
domain requests, calls existing workflows, reads the store, and maps to
presenters. Routes never touch workflows, SQLite, adapters, or the MockTransport
directly.

`DemoComposition` gains:

- `history_store: SQLiteHistoryStore` (the same store used by planning, and
  used for read-back navigation/refresh);
- a shared `DemoWordPressTransport` (wrapped in `httpx.MockTransport`);
- `delivery_workflow(target_site_url: str) -> ApprovedWordPressDraftDeliveryWorkflow`
  (builds a fresh publisher per target with sentinel credentials and the shared
  transport);
- `verification_workflow() -> WordPressDraftVerificationWorkflow` (shared;
  `draft_reader_factory = lambda site_key: WordPressRestDraftReader(...)`).

## Route Design

Single recommended shape:

```text
GET  /runs/{run_id}/drafts/{draft_id}/delivery
POST /runs/{run_id}/drafts/{draft_id}/delivery
GET  /runs/{run_id}/deliveries/{attempt_id}
POST /runs/{run_id}/deliveries/{attempt_id}/verify
GET  /runs/{run_id}/deliveries/{attempt_id}/verification
GET  /healthz
```

- `GET` has no create/verify side effect.
- Create and Verify are `POST` only.
- A successful `POST` returns `303` to the result `GET` (PRG; refresh-safe).
- `run_id` / `draft_id` / `attempt_id` come from the path and are validated
  against persisted state (`attempt.run_id == run_id`), else a sanitized 404.
- The target site is never browser-controlled.

## Application Service Extensions

- `load_delivery_setup(run_id, draft_id)`: resolve the CONTENT_DRAFT artifact
  and draft; if an attempt already exists, show the already-created/blocked
  state or redirect to the result; otherwise return the setup view.
- `create_wordpress_draft(run_id, draft_id, *, intent_confirmed: bool) -> attempt_id`:
  refuse when `intent_confirmed` is false; derive the per-run target; construct
  `ApprovedWordPressDraftDeliveryRequest`; await the real delivery workflow.
- `load_delivery_result(run_id, attempt_id)`: read and present the create
  outcome.
- `verify_wordpress_draft(run_id, attempt_id)`: validate ownership then await
  the real verification workflow.
- `load_verification_result(run_id, attempt_id)`: read the attempt plus any
  verification row; present the two orthogonal outcomes; derive `NOT_ATTEMPTED`
  when no verification row exists.

Navigation is extended to 7 steps and recovers from SQLite via
`list_wordpress_attempts`, `get_wordpress_attempt`, and
`list_wordpress_verifications`.

## Navigation State Model

Seven steps: `start / progress / results / changes / draft / delivery /
verification`, with Phase 1 linear gating preserved (only the immediate next
step is `available`; earlier steps are `completed`; later steps are `locked`).

- Draft Review current, CONTENT_DRAFT present: `delivery` available,
  `verification` locked.
- Delivery current, attempt exists:
  - `SUCCESS`: delivery completed, verification available.
  - `UNKNOWN` / `PENDING`: delivery completed (uncertain), verification
    available (verification resolves to UNRESOLVED).
  - `FAILED_DEFINITELY`: delivery completed, verification locked
    (not applicable).
- Verification current, verification row present: verification active/completed.

When an attempt exists, the delivery step links to
`/runs/{run_id}/deliveries/{attempt_id}`; otherwise it links to the delivery
setup. URL refresh recovers this entirely from SQLite.

## Attempt and Verification Selection

A draft may legitimately own multiple delivery attempts because
`FAILED_DEFINITELY` allows an explicit retry. The current UI selection is
deterministic:

- delivery setup / navigation use the draft's latest attempt (max by
  `attempted_at`, tie-break by `attempt_id`);
- verification result uses the current attempt's latest verification record
  (max by `verified_at`, tie-break by `verification_id`);
- older attempts and verifications remain append-only history; Phase 2 exposes
  no history UI.

"Latest" relies on the store's stable ascending ordering:
`list_wordpress_attempts_for_draft` orders by `attempted_at ASC, attempt_id ASC`
and `list_wordpress_verifications` orders by `verified_at ASC, verification_id
ASC`; the service selects the last element. It never relies on unordered list
iteration.

## Delivery Setup UX

Shows:

- `DEMO MODE` (context bar).
- `Selected draft` `D1` plus draft title / change context.
- `Destination: Demo WordPress Sandbox`.
- `Target: https://demo-wordpress-{run_id}.example`.
- Safety line: `Create-only · Draft-only · No publishing · No updates · No deletes`.
- `NovaCNC is the analyzed Astro demo site. The WordPress Sandbox is a separate
  deterministic delivery target.`
- Checkbox: `I reviewed this draft and intend to create a WordPress draft.`
- Single button: `Create WordPress Draft`.

The button cannot create without the checkbox; the service re-checks it. The
checkbox carries HTML `required` semantics, and the service independently
rejects `intent_confirmed=False` with no create POST. The forbidden-action test
asserts the exact executable CTA wording `Publish`, `Approve & Publish`,
`Push Live`, `Deploy`, `Update Existing Post` are absent. The safety disclosure
words `No publishing`, `No updates`, `No deletes` remain allowed.

## Delivery Setup Selection Semantics

`load_delivery_setup(run_id, draft_id)` resolves the draft's latest attempt:

- none, or latest outcome `FAILED_DEFINITELY`: render Delivery Setup with a
  fresh unchecked intent checkbox; the next create POST produces a new attempt.
- latest outcome `SUCCESS`: show or redirect to the existing delivery result;
  no new create.
- latest outcome `UNKNOWN` / `PENDING`: show or redirect to the uncertain
  delivery result; no retry.

Never redirect solely because attempts exist.

## Delivery Result UX

- `SUCCESS`: `Draft created`, `Remote Post ID`, `Create outcome: SUCCESS`,
  `Status: draft`; primary CTA `Verify Draft →`.
- `UNKNOWN`: `WordPress may have created the draft.` and the fixed warning
  `Do not retry create while remote state is uncertain.`; no create retry.
- `PENDING`: `Creation request is still unresolved.` plus the same warning.
- `FAILED_DEFINITELY`: `Draft creation failed before a confirmed create.`;
  `Verification not applicable`; no Verify CTA.
- `BLOCKED`: if an existing `SUCCESS`, `This exact draft was already created.`;
  if `PENDING/UNKNOWN`, `Creation is blocked pending manual reconciliation.`

Create never triggers automatic verification; the user must explicitly click
`Verify Draft`.

## FAILED_DEFINITELY Retry Semantics

`FAILED_DEFINITELY` is not `UNKNOWN`/`PENDING`: no ambiguous remote create is
believed to remain. Verification is `NOT APPLICABLE` (zero GET, zero
verification row). The user may explicitly return to Delivery Setup and Create
again, but only through a new explicit human-intent checkbox and a new delivery
attempt; automatic retry is forbidden and the existing
workflow/fingerprint/history semantics decide legality.

On the failed attempt's Delivery Result, the secondary CTA is
`Try Delivery Again`, which links back to Delivery Setup. The workflow is never
a dead end.

## Verification UX

The page states `Verification performs a read-only WordPress GET.` and shows
both orthogonal `Create outcome` and `Verification outcome`.

- `VERIFIED`: `Draft confirmed in WordPress`, `Remote status: draft`, `Remote Post ID`.
- `NOT_FOUND`: `Draft was not found at the recorded post ID`.
- `MISMATCH`: `Remote post does not match the expected draft`.
- `UNKNOWN`: `WordPress could not be reached or interpreted safely`.
- `UNRESOLVED`: `No safe remote lookup could be performed`.
- `FAILED_DEFINITELY` (create): `Verification not applicable`.

For uncertain remote state the fixed warning
`Do not retry create while remote state is uncertain.` is always shown.

## Refresh / Restart Strategy

Delivery and verification results recover from SQLite only; no login, session,
or cookie. The stateless sandbox means a persisted `SUCCESS` attempt with a
remote id can be verified after a service restart. No production schema is
added.

## Human Intent vs Approval Semantics

The checkbox expresses intent for the current create HTTP request only. It is
not a persisted approval. No `approved_at`, `reviewer`, `approval table`, role
system, or permission system is added. Draft Review keeps
`Approval record: NOT RECORDED` and `Review does not record approval.`; it is
never changed to `Approved`.

## No-Retry / Ambiguous State Handling

For `UNKNOWN` / `PENDING`:

- the UI shows the no-retry warning and never renders an executable create
  button;
- the workflow/fingerprint guard and the SQLite unique index block a repeat
  POST (`BLOCKED`, POST count remains 1);
- explicit verification resolves to `UNRESOLVED` with `lookup_kind=NONE` and
  zero GET;
- `UNKNOWN → SUCCESS`, `SUCCESS → FAILED`, automatic reconciliation, and
  guessing remote posts are forbidden.

## Security / Secrets

Phase 1 constraints continue: loopback only, no external network,
DNS/socket/asyncio tripwire, no DeepSeek/Tavily/GeoOptimizer/SafeHtmlFetcher/real
WordPress, Jinja autoescape, no `Markup`, no `|safe`, no generated HTML
insertion, SQLite as canonical state. Phase 2 additionally requires:

- `GET` must not mutate; create/verify are POST-only;
- PRG refresh safety;
- double-click safety at the workflow/DB layer;
- path-supplied run/draft/attempt ids validated against persisted state;
- target site not browser-controlled;
- sentinel credentials never enter rendered HTML, SQLite bytes, logs, or
  sanitized errors;
- no login/auth system.

## Cross-Object Ownership Validation

Every browser-supplied id is validated against persisted ownership before any
side effect:

- a `draft_id` must belong to the run's CONTENT_DRAFT artifact, else a
  sanitized failure with zero POST;
- an `attempt_id` must satisfy `attempt.run_id == run_id`, else reject before
  any GET and append no new verification;
- a delivery request that mixes a run and a draft/attempt from another run is
  rejected with POST=0 / GET=0.

## Hard No-Network Contract

The composed flow
`Start → Planning → Results → Change Plan → Draft Review → Delivery Setup →
Create → Delivery Result → Verify → VERIFIED` must run with
`socket.getaddrinfo`, `socket.create_connection`, `socket.socket.connect(_ex)`,
and `asyncio.BaseEventLoop.create_connection` all patched to raise
`AssertionError`. Only the deterministic MockTransport handles WordPress REST.
Assert exactly one POST create and exactly one GET verify, and no PUT, PATCH,
DELETE, publish, second POST, or extra endpoint.

## Happy-Path Composed Contract

From a temporary SQLite database:

```
P1/A1/S1/R1/C1/D1
→ real review workflow
→ explicit intent
→ real ApprovedWordPressDraftDeliveryWorkflow
→ real WordPressRestDraftPublisher → MockTransport (exactly one POST, draft)
→ SUCCESS attempt + remote id
→ verification initially NOT_ATTEMPTED
→ explicit Verify → real WordPressDraftVerificationWorkflow
→ real WordPressRestDraftReader → exactly one GET
→ VERIFIED appended
```

Also assert the create attempt is not rewritten by verification.

## UNKNOWN / UNRESOLVED Contract

With the MockTransport POST raising a post-dispatch timeout:

- create outcome `UNKNOWN`, remote id absent, POST count = 1;
- UI shows the no-retry warning;
- explicit Verify → `UNRESOLVED`, `lookup_kind=NONE`, GET count = 0;
- a second Create → `BLOCKED`, POST count still = 1;
- attempts remain 1 and verifications remain 1 (UNRESOLVED).

## Visual Integration

Reuse the accepted Phase 1 visual language (navy / teal / light slate, small
amber warnings, dark green success). Only add the delivery setup, delivery
result, verification result templates, the 7-step rail, and create/verification
status badges. Extend CSS; do not redesign the UI.

## Windows One-Click Launcher

Recommended: a single `.cmd` wrapper plus a standard-library-only Python helper
(no PowerShell dependency, no PyInstaller, no Docker, no exe). Phase 2 also adds
a tiny `GET /healthz` returning a fixed `seo-agent-demo` marker so the launcher
can distinguish an already-running Demo from an unrelated process.

Launcher lifecycle:

- Case A — Demo already running (`/healthz` returns the correct marker):
  open the browser only; do not start a server, do not take ownership of the
  existing process, do not terminate anything.
- Case B — port 8000 is occupied by another process (no correct marker): print
  a clear error; do not kill anything; do not launch the Demo.
- Case C — launcher starts a new Demo with the validated interpreter
  `.venv\Scripts\python.exe` (never PATH `"python"`):
  `subprocess.Popen([str(venv_python), "-m", "foreign_trade_geo_agent.web"])`.
  Retain child ownership, poll `/healthz` until ready, open the browser, and
  stay alive printing:
  `SEO Agent Demo is running.` / `Press Ctrl+C to stop.` On Ctrl+C or normal
  shutdown, terminate only the owned child, wait for graceful exit, and use a
  bounded fallback kill only for that owned child.

The launcher must never kill an already-running Demo it did not start, never
kill an unrelated port-8000 process, and never leave an owned Uvicorn orphan
after normal exit. All three cases are tested.

Port classification is explicit and never conflates a health-check failure with
a free port:

- `/healthz` returns the correct marker → an existing Demo;
- the TCP/HTTP endpoint is reachable but returns a wrong marker, an error, or a
  non-Demo response → occupied by another process (clear error, kill nothing);
- the connection is refused → the port is free.
