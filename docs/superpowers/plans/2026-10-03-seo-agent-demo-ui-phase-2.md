# SEO Agent MVP Demo UI — Phase 2 Implementation Plan

> For agentic workers: implement task-by-task with strict RED → GREEN. Each task
> names its failing tests and a targeted regression command. Do not create all
> templates at once. Preserve every Phase 1 no-network / XSS / safety contract.

## Global Constraints

- Reuse existing core/workflow/adapter/storage code; do not change production
  delivery/verification semantics or the SQLite schema (`user_version = 2`).
- Demo sandbox uses real `WordPressRestDraftPublisher` / `WordPressRestDraftReader`
  over a deterministic `httpx.MockTransport`.
- The transport records only sanitized observations, never credential-bearing
  `httpx.Request` objects.
- Sentinel credentials are code constants; never read `.env` or `WORDPRESS_*`.
- Routes call only `DemoApplicationService`.
- `GET` never mutates; create and verify are POST-only with 303 → GET.
- `UNKNOWN`/`PENDING` never retry; `FAILED_DEFINITELY` allows only an explicit
  human-intent re-create.
- Loopback only; no real external service; no login/auth; no approval
  persistence.
- Do not commit or push in this phase (the user issues that separately).

## Recommended Order

1. Demo WordPress sandbox transport
2. Demo composition integration
3. Application service delivery/verification
4. Delivery Setup
5. Delivery Result
6. Verification
7. UNKNOWN/UNRESOLVED + FAILED_DEFINITELY retry semantics
8. 7-step navigation / refresh recovery
9. Full no-network composed contracts
10. Visual integration
11. Owned-process Windows launcher
12. Full regression

---

## Task 1: Deterministic WordPress sandbox transport

**Files:** add `src/foreign_trade_geo_agent/web/demo_wordpress.py`; add
`tests/test_web_demo_wordpress.py`.

**Interfaces:** `DEMO_WORDPRESS_USERNAME`, `DEMO_WORDPRESS_APPLICATION_PASSWORD`,
`DEMO_WORDPRESS_POST_ID = 41`, `demo_wordpress_origin(run_id) -> str`,
`DemoWordPressRequestObservation`, and `DemoWordPressTransport`.

- Step 1 — failing tests:
  - `test_post_returns_deterministic_draft`
  - `test_get_returns_same_origin_draft`
  - `test_put_patch_delete_and_unknown_paths_fail_closed`
  - `test_observations_are_sanitized_and_omit_authorization`
  - `test_per_run_origin_is_valid_and_distinct`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_wordpress -v`
- Step 3 — implement the handler plus sanitized observations.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_wordpress tests.test_wordpress_rest_adapter tests.test_wordpress_rest_reader_adapter -v`

## Task 2: Demo composition integration

**Files:** modify `src/foreign_trade_geo_agent/web/composition.py`; extend
`tests/test_web_demo_composition.py`.

**Interfaces:** `DemoComposition.history_store`,
`DemoComposition.wordpress_transport`,
`DemoComposition.delivery_workflow(target_site_url)`,
`DemoComposition.verification_workflow()`.

- Step 1 — failing tests:
  - `test_composition_exposes_delivery_and_verification_workflows`
  - `test_delivery_workflow_injects_shared_mock_transport_not_real_transport`
  - `test_composition_does_not_load_production_runtime` (existing guard).
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_composition -v`
- Step 3 — wire the shared store/transport and factory methods.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_composition tests.test_mvp_composed_flow -v`

## Task 3: Application service delivery/verification

**Files:** modify `src/foreign_trade_geo_agent/web/application.py`; add
`tests/test_web_delivery_application.py`.

**Interfaces:** `load_delivery_setup`, `create_wordpress_draft`,
`load_delivery_result`, `verify_wordpress_draft`, `load_verification_result`;
sanitized `DemoApplicationError` on invalid ids or missing intent.

- Step 1 — failing tests:
  - `test_setup_without_attempt_returns_draft_and_sandbox_target`
  - `test_create_without_intent_raises_and_posts_nothing`
  - `test_create_success_persists_attempt_and_returns_attempt_id`
  - `test_load_result_success`
  - `test_verify_success_appends_verified`
  - `test_unknown_create_verifies_to_unresolved_with_zero_get`
  - `test_failed_definitely_is_not_applicable`
  - `test_draft_from_other_run_is_rejected_with_zero_post`
  - `test_attempt_from_other_run_is_rejected`
  - `test_verify_attempt_from_other_run_rejected_before_workflow`
  - `test_unknown_draft_id_in_valid_run_fails_sanitized`
  - `test_latest_attempt_is_selected_deterministically`
  - `test_latest_verification_is_selected_deterministically`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_application -v`
- Step 3 — implement the five service methods over existing workflows/store.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_application tests.test_approved_wordpress_delivery_workflow tests.test_wordpress_delivery_workflow tests.test_wordpress_verification_workflow -v`

## Task 4: Delivery Setup

**Files:** modify `web/routes.py` and `web/presenters.py`; add
`web/templates/delivery_setup.html`; add `tests/test_web_delivery_routes.py`.

**Interfaces:** `GET /runs/{run_id}/drafts/{draft_id}/delivery`.

- Step 1 — failing tests:
  - `test_setup_renders_selected_draft_and_sandbox_target`
  - `test_setup_renders_intent_checkbox_and_exact_create_cta`
  - `test_forbidden_action_cta_strings_are_absent`
  - `test_setup_checkbox_has_required_semantics`
  - `test_hostile_draft_context_is_escaped_in_setup`
  - `test_setup_get_has_no_side_effect`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_routes -v`
- Step 3 — implement the setup presenter and template.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_routes tests.test_web_result_routes -v`

## Task 5: Create POST and Delivery Result

**Files:** modify `web/routes.py` and `web/presenters.py`; add
`web/templates/delivery_result.html`; extend `tests/test_web_delivery_routes.py`.

**Interfaces:** `POST /runs/{run_id}/drafts/{draft_id}/delivery` (303) and
`GET /runs/{run_id}/deliveries/{attempt_id}`.

- Step 1 — failing tests:
  - `test_create_post_redirects_to_result`
  - `test_result_shows_success_draft_remote_id_and_verify_cta`
  - `test_create_without_checkbox_is_sanitized_and_posts_nothing`
  - `test_repeat_create_is_blocked_and_posts_once`
  - `test_result_get_has_no_side_effect`
  - `test_hostile_draft_context_is_escaped_in_result`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_routes -v`
- Step 3 — implement create/result routes and presenter.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_routes tests.test_web_delivery_application -v`

## Task 6: Verification

**Files:** modify `web/routes.py` and `web/presenters.py`; add
`web/templates/verification_result.html`; add
`tests/test_web_verification_routes.py`.

**Interfaces:** `POST /runs/{run_id}/deliveries/{attempt_id}/verify` (303) and
`GET /runs/{run_id}/deliveries/{attempt_id}/verification`.

- Step 1 — failing tests:
  - `test_explicit_verify_redirects_and_shows_verified`
  - `test_verification_result_shows_two_orthogonal_outcomes`
  - `test_verification_get_has_no_side_effect`
  - `test_failed_definitely_result_shows_not_applicable_and_no_verify_cta`
  - `test_not_attempted_is_derived_before_verify`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_verification_routes -v`
- Step 3 — implement verify/verification routes and presenter.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_verification_routes tests.test_wordpress_verification_workflow tests.test_wordpress_verification_core -v`

## Task 7: UNKNOWN/UNRESOLVED and FAILED_DEFINITELY retry semantics

**Files:** modify `web/presenters.py` and `web/templates/delivery_result.html`;
add `tests/test_web_delivery_safety.py`.

**Interfaces:** uncertain-state no-retry copy and the `Try Delivery Again`
secondary CTA for `FAILED_DEFINITELY`.

- Step 1 — failing tests:
  - `test_unknown_result_shows_no_retry_warning_and_no_create_cta`
  - `test_unknown_verify_is_unresolved_with_zero_get`
  - `test_unknown_second_create_is_blocked_and_posts_once`
  - `test_failed_definitely_shows_try_delivery_again`
  - `test_failed_definitely_retry_requires_new_intent_and_new_attempt`
  - `test_three_attempts_selection_points_to_latest_success`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_safety -v`
- Step 3 — implement the copy/CTA and the retry flow through the existing workflow.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_safety tests.test_web_delivery_routes tests.test_web_verification_routes -v`

## Task 8: 7-step navigation and refresh recovery

**Files:** modify `web/presenters.py` (nav steps) and `web/application.py`
(navigation); add `tests/test_web_navigation_phase2.py`.

**Interfaces:** seven rail steps and SQLite-recovered delivery/verification
states.

- Step 1 — failing tests:
  - `test_rail_has_seven_steps_in_order`
  - `test_delivery_available_when_draft_exists`
  - `test_verification_available_after_success`
  - `test_verification_locked_for_failed_definitely`
  - `test_refresh_recovers_delivery_and_verification_from_sqlite`
  - `test_navigation_points_to_latest_attempt`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_navigation_phase2 -v`
- Step 3 — extend `_NAVIGATION_STEPS` and navigation state derivation.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_navigation_phase2 tests.test_web_presenters tests.test_web_progress_routes -v`

## Task 9: Full no-network composed contracts

**Files:** modify `tests/test_web_no_network.py` (adjust the WordPress
constructor guard); add `tests/test_web_phase2_composed.py`.

**Interfaces:** hard no-network happy path and the ambiguous-create contract.

- Step 1 — failing tests:
  - `test_start_to_verified_has_hard_no_network_tripwire`
  - `test_ambiguous_create_contract_posts_once_and_gets_zero`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_phase2_composed tests.test_web_no_network -v`
- Step 3 — remove the now-legitimate WordPress constructor patches (keep the
  DNS/socket/asyncio tripwire), and assert exactly one POST and one GET.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_phase2_composed tests.test_web_no_network tests.test_web_demo_wordpress -v`

## Task 10: Visual integration

**Files:** modify `web/static/app.css`; extend `tests/test_web_visual_polish.py`.

**Interfaces:** delivery/verification component selectors and 7-step rail styles.

- Step 1 — failing tests: extend the CSS-contract test with
  `.delivery-setup`, `.delivery-result`, `.verification-result`,
  `.create-outcome`, `.verification-outcome`, and rail-7 selectors.
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_web_visual_polish -v`
- Step 3 — add the Phase 2 styles.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_visual_polish tests.test_web_demo_assets -v`

## Task 11: Owned-process Windows launcher

**Files:** add `GET /healthz` (modify `web/routes.py`); add
`scripts/start_demo.py` and `scripts/start-demo.cmd`; add `tests/test_launcher.py`.

**Interfaces:** `GET /healthz` returns the fixed `seo-agent-demo` marker; the
launcher implements Cases A/B/C.

- Step 1 — failing tests:
  - `test_healthz_returns_demo_marker`
  - `test_case_a_already_running_opens_browser_only`
  - `test_case_b_port_occupied_by_other_reports_error_and_kills_nothing`
  - `test_case_c_starts_owned_child_and_terminates_only_it_on_shutdown`
  - `test_launcher_uses_venv_python_not_path_python`
  - `test_port_classification_wrong_marker_is_occupied`
- Step 2 — RED: `.\.venv\Scripts\python.exe -m unittest tests.test_launcher -v`
- Step 3 — implement the healthz route and the stdlib-only launcher lifecycle.
- Step 4 — GREEN + regression:
  `.\.venv\Scripts\python.exe -m unittest tests.test_launcher tests.test_web_entrypoint -v`

## Task 12: Full regression

**Files:** no planned production changes; fix regressions with a focused failing
test first.

- Step 1 — all Web/Demo tests:
  `.\.venv\Scripts\python.exe -m unittest tests.test_web_demo_assets tests.test_web_demo_composition tests.test_web_jobs tests.test_web_application_progress tests.test_web_presenters tests.test_web_application_results tests.test_web_app tests.test_web_progress_routes tests.test_web_result_routes tests.test_web_xss tests.test_web_no_network tests.test_web_entrypoint tests.test_web_visual_polish tests.test_web_demo_wordpress tests.test_web_delivery_application tests.test_web_delivery_routes tests.test_web_verification_routes tests.test_web_delivery_safety tests.test_web_navigation_phase2 tests.test_web_phase2_composed tests.test_launcher -v`
- Step 2 — delivery/verification core + planning/review/runtime regressions:
  `.\.venv\Scripts\python.exe -m unittest tests.test_approved_wordpress_delivery_workflow tests.test_wordpress_delivery_workflow tests.test_wordpress_verification_workflow tests.test_wordpress_verification_core tests.test_wordpress_verification_reporting tests.test_wordpress_rest_adapter tests.test_wordpress_rest_reader_adapter tests.test_sqlite_history_store tests.test_history_migration_v1_to_v2 tests.test_mvp_composed_flow tests.test_site_crawl_workflow tests.test_end_to_end_workflow tests.test_industry_research_workflow tests.test_content_opportunity_workflow tests.test_change_plan_workflow tests.test_content_draft_workflow tests.test_content_draft_review_workflow tests.test_content_draft_review_readonly tests.test_content_draft_review_renderer tests.test_runtime tests.test_cli -v`
- Step 3 — full suite:
  `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- Step 4 — `git diff --check` and `git status --short`; do not commit or push.

## Verification and Reporting

Report per task: failing-test names observed RED, the minimal production change,
the targeted GREEN command result, and any regression found. Preserve all
Phase 1 no-network/XSS/read-only/approval-not-recorded contracts and the
production runtime defaults and SQLite schema.
