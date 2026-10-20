# SEO Agent Generic Live Analysis MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use strict RED → GREEN verification.

**Goal:** 增加通用公开 HTTPS 网站的真实 SEO 分析 Web profile，同时冻结 NovaCNC Demo，并复用同一 planning workflow 和 artifacts。

**Architecture:** 保留 `DemoComposition`，新增薄 `LiveComposition` 和 `LiveApplicationService`。所有 planning entry points 使用同一个 crawl-based audit contract；Live 和 Demo 分库，共享 bounded workflows 和通用 read-side presenters。

**Tech Stack:** Python 3.12、FastAPI、Jinja2、SQLite、stdlib `unittest`、httpx、Trafilatura、Tavily、DeepSeek。

**Spec:** `docs/superpowers/specs/2026-10-04-generic-live-seo-analysis-design.md`.

## Global Constraints

- 实施分支必须是 `feat/live-site-analysis`。
- 基线必须是 `fedcb3b7a8ffb3e3480c9807d5831ddd89dfc148`。
- Demo 必须零网络、零 API key 可用。
- Live 只接受公开 HTTPS 网站。
- 不放宽 SafeHtmlFetcher、DNS rebinding 或 `198.18.0.0/15` 防护。
- CrawlSeoAuditor 不得发起网络访问。
- Live 主流程在 Draft Review 停止。
- 不扩展 GEO，不自动调用 WordPress。
- 所有自动测试使用 fake/local transports；公网只允许人工 smoke。
- 每个 GREEN 后先运行 targeted regression，再进入下一任务。
- Live Web 的状态变更 POST 必须先通过本地 Host allowlist 与 process-local CSRF token 校验；token 不持久化、不记录、不进入 URL，也不作为认证。
- 每个进程最多允许一个 RUNNING Live Web analysis；拒绝重复提交时不得创建第二个 job/run 或发起第二次外部请求。此限制不改变 CLI planning 语义。
- `create_app()` 在 Tavily/DeepSeek 均未配置时必须成功；Demo 完整可用，Live 显示 unavailable，Live POST 零 job/run/network。
- SQLite v3 只为 `analysis_run_inputs` 扩展；`PlanningFailure.failure_kind` 仅为进程内分类，持久化的 canonical failure 仍是现有 `WorkflowRun` sanitized error。
- Research、content opportunities、change plan、content draft 四个 Live generation adapters 都必须尊重 `target_language=en`，且不得包含矛盾的中文限定指令。
- normalized Website URL 总长度上限为 2048 个字符，覆盖 scheme、host、path 与 query。
- 不 commit、不 push；Task 17 不由 agent 执行，只交付人工操作说明。

## Review Focus

- Unicode/IDNA host、default port、fragment、credentials 和 private IP literal：Task 2 覆盖。
- v1/v2 legacy run 没有 input row：Task 3 覆盖。
- title/description 不得由 H1 或正文推断为 SEO metadata：Task 4 覆盖。
- 缺少任一 provider 配置时不能创建 run/job：Task 8–9 覆盖。
- mixed DNS、Fake-IP、redirect-to-private 和 profile/run 串读：Task 13–14 覆盖。
- missing/incorrect CSRF、hostile Host 和 token/error 泄漏：Task 10 覆盖。
- near-consecutive Live double submission 和 terminal-state release：Task 9 覆盖。
- zero-key `create_app()`、Demo usability 和 Live unavailable：Task 10 覆盖。
- 四个 DeepSeek generation adapter 的 English contract：Task 7 覆盖。
- 2048-character normalized URL boundary：Task 2 覆盖。

---

## Task 1: Git/baseline guard

**Files**

- 不修改文件。
- 这是执行前 gate，不应创建依赖当前分支名的 unittest。

**Named RED guard**

- `branch_guard_feat_live_site_analysis_at_demo_baseline`

**RED command**

```powershell
$branch = git branch --show-current
$head = git rev-parse HEAD
if ($branch -ne "feat/live-site-analysis" -or
    $head -ne "fedcb3b7a8ffb3e3480c9807d5831ddd89dfc148") {
    throw "Implementation baseline mismatch: branch=$branch head=$head"
}
```

**Minimal production change**

- 无。
- 若 guard 失败，停止；不得自动在 `main` 上实现或重写用户 Git 状态。

**GREEN command**

- 重复运行同一 guard，要求 exit 0。

**Targeted regression**

```powershell
git status --short --branch
git diff --name-only
```

要求实施开始前无意外改动。

---

## Task 2: LiveAnalysisInput normalization and validation

**Files**

- Create: `src/foreign_trade_geo_agent/core/live_analysis.py`
- Test: `tests/test_live_analysis_input.py`

**Interfaces**

```python
DEFAULT_LIVE_SEO_GOAL: str

@dataclass(frozen=True, slots=True)
class LiveAnalysisInput:
    website_url: str
    seo_goal: str = DEFAULT_LIVE_SEO_GOAL
    target_language: str = "en"
    display_identity: str = field(init=False)

def normalize_live_website_url(value: str) -> str
```

**Named failing RED tests**

- `LiveAnalysisInputTests.test_normalizes_idna_host_default_port_empty_path_and_fragment`
- `LiveAnalysisInputTests.test_preserves_bounded_path_and_query`
- `LiveAnalysisInputTests.test_rejects_http_credentials_whitespace_backslash_and_malformed_port`
- `LiveAnalysisInputTests.test_rejects_localhost_private_loopback_link_local_reserved_and_benchmark_literals`
- `LiveAnalysisInputTests.test_rejects_unsupported_language_and_oversized_goal`
- `LiveAnalysisInputTests.test_accepts_normalized_url_at_2048_characters`
- `LiveAnalysisInputTests.test_rejects_normalized_url_over_2048_characters`
- `LiveAnalysisInputTests.test_defaults_to_english_goal_and_hostname_identity`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_live_analysis_input -v
```

Expected: import/type failures because the module does not exist.

**Minimal production change**

- 用 stdlib URL parsing 和现有 `UrlOrigin` 做纯语法规范化。
- 只接受 `https`。
- 去除 fragment；空 path 变 `/`。
- 规范化 IDNA/lowercase host 和 default port。
- literal IP 必须是公开地址；最终 DNS 安全仍由 SafeHtmlFetcher 决定。
- 完成规范化后对完整 Website URL 施加 2048 字符上限，path/query 也计入。
- goal 去首尾/合并空白并限制 300 字符。
- 第一版 language 只允许 `en`。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_live_analysis_input -v
```

Expected: all tests pass.

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_history_core tests.test_safe_html_fetcher -v
```

---

## Task 3: SQLite v3 and atomic analysis inputs

**Files**

- Modify: `src/foreign_trade_geo_agent/core/history.py`
- Modify: `src/foreign_trade_geo_agent/core/ports.py`
- Modify: `src/foreign_trade_geo_agent/storage/sqlite.py`
- Rename/update: `tests/test_history_migration_v1_to_v2.py` → `tests/test_history_migration_to_v3.py`
- Modify: `tests/test_sqlite_history_store.py`
- Modify: `tests/test_history_core.py`
- Test helper if needed: `tests/history_v2_fixtures.py`

**Interfaces**

```python
@dataclass(frozen=True, slots=True)
class AnalysisRunInput:
    run_id: str
    website_url: str
    seo_goal: str
    target_language: str
    display_identity: str

HistoryStore.create_analysis_run(
    run: WorkflowRun,
    analysis_input: AnalysisRunInput,
) -> None

HistoryStore.get_analysis_run_input(
    run_id: str,
) -> AnalysisRunInput | None

HistoryReader.get_analysis_run_input(
    run_id: str,
) -> AnalysisRunInput | None
```

**Named failing RED tests**

- `SQLiteHistoryStoreTests.test_initializes_v3_schema_with_analysis_run_inputs`
- `SQLiteHistoryStoreTests.test_create_analysis_run_atomically_persists_run_and_input`
- `SQLiteHistoryStoreTests.test_analysis_input_failure_rolls_back_run`
- `SQLiteHistoryStoreTests.test_analysis_input_run_id_must_match`
- `SchemaMigrationTests.test_empty_database_initializes_directly_to_v3`
- `SchemaMigrationTests.test_v1_database_migrates_to_v3_without_fabricating_inputs`
- `SchemaMigrationTests.test_v2_database_migrates_to_v3_without_fabricating_inputs`
- `SchemaMigrationTests.test_existing_demo_database_migrates_without_changing_wordpress_rows`
- `SchemaMigrationTests.test_legacy_run_without_input_remains_readable`
- `SchemaMigrationTests.test_read_only_v1_and_v2_reader_returns_no_analysis_input_without_migrating`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_history_core tests.test_sqlite_history_store tests.test_history_migration_to_v3 -v
```

**Minimal production change**

- `_SCHEMA_VERSION = 3`，readable versions 为 `{1, 2, 3}`。
- 新库直接创建 v3。
- v1 顺序执行 v1→v2、v2→v3。
- v2 只执行 v2→v3。
- 新表只追加，不 backfill。
- store 原子插入 `runs` 和 `analysis_run_inputs`。
- read-only reader 在 schema `<3` 时直接返回 `None`。
- 不触碰 WordPress DDL 和方法。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_history_core tests.test_sqlite_history_store tests.test_history_migration_to_v3 -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_content_draft_review_readonly tests.test_approved_wordpress_delivery_workflow tests.test_wordpress_verification_workflow -v
```

---

## Task 4: Harden title and meta-description provenance

**Files**

- Modify: `src/foreign_trade_geo_agent/adapters/_page_worker.py`
- Modify: `tests/test_page_extractor.py`
- Modify: `tests/fixtures/page_extraction/article.html` only if an additional fixture is required

**Interfaces**

- 保留 `PageExtractionResult.title` 和 `.description`。
- 不增加网络或新 model 字段。
- `_extract_static_fields()` 改为直接返回 bounded document title、meta description、canonical、H1、H2。

**Named failing RED tests**

- `TrafilaturaPageExtractorTests.test_missing_title_is_not_inferred_from_h1`
- `TrafilaturaPageExtractorTests.test_title_comes_from_first_bounded_title_element`
- `TrafilaturaPageExtractorTests.test_missing_meta_description_is_not_inferred_from_body`
- `TrafilaturaPageExtractorTests.test_meta_description_name_matching_is_case_insensitive`
- `TrafilaturaPageExtractorTests.test_title_and_meta_description_respect_metadata_limits`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_page_extractor -v
```

**Minimal production change**

- 在已有 no-network lxml tree 中读取：
  - 第一个 `<title>`。
  - 第一个 `meta[name=description][content]`，name 大小写不敏感。
- 继续使用 `_clean_text` 和 `max_metadata_chars`。
- 不用 Trafilatura 的 title/description fallback 填充这两个 SEO 字段。
- 正文、date 和 structured content 保持原实现。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_page_extractor -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_page_worker tests.test_site_crawl_workflow tests.test_site_content_packet -v
```

---

## Task 5: CrawlSeoAuditor

**Files**

- Create: `src/foreign_trade_geo_agent/workflows/crawl_seo_audit.py`
- Modify: `src/foreign_trade_geo_agent/core/audit.py`
- Modify: `src/foreign_trade_geo_agent/core/ports.py`
- Modify: `src/foreign_trade_geo_agent/workflows/__init__.py`
- Test: `tests/test_crawl_seo_audit.py`

**Interfaces**

```python
class PlanningSiteAuditor(Protocol):
    def audit_crawl(self, report: SiteCrawlReport) -> SiteAuditResult: ...

class CrawlSeoAuditor:
    source = "crawl-seo-audit"
    source_version = "1"

    def audit_crawl(self, report: SiteCrawlReport) -> SiteAuditResult: ...
```

增加 `AuditEvidenceCategory.CRAWL`。

**Named failing RED tests**

- `CrawlSeoAuditorTests.test_scores_only_fields_present_in_successful_crawl_pages`
- `CrawlSeoAuditorTests.test_failed_extraction_is_not_reported_as_missing_metadata`
- `CrawlSeoAuditorTests.test_detects_duplicate_title_description_and_canonical_in_bounded_sample`
- `CrawlSeoAuditorTests.test_canonical_is_checked_for_syntax_and_exact_origin`
- `CrawlSeoAuditorTests.test_word_count_uses_extracted_body_only`
- `CrawlSeoAuditorTests.test_internal_link_check_uses_crawled_page_links`
- `CrawlSeoAuditorTests.test_evidence_and_breakdown_sum_to_transparent_score`
- `CrawlSeoAuditorTests.test_does_not_claim_schema_open_graph_noindex_noai_or_llms`
- `CrawlSeoAuditorTests.test_audit_performs_no_network_access`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_crawl_seo_audit -v
```

**Minimal production change**

- 实现规格中的七组权重和 band 阈值。
- 最多五页下保持 evidence 数量不超过现有 96 上限。
- recommendations 只由具体失败 evidence 产生。
- canonical 检查不跟随 URL。
- 不注入 fetcher，不接收 URL 字符串。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_crawl_seo_audit -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_geo_optimizer_adapter tests.test_site_optimization_workflow tests.test_history_serialization -v
```

---

## Task 6: Migrate the complete planning audit contract

**Files**

- Modify: `src/foreign_trade_geo_agent/workflows/end_to_end.py`
- Modify: `src/foreign_trade_geo_agent/runtime.py`
- Modify: `src/foreign_trade_geo_agent/web/demo_boundaries.py`
- Modify: `src/foreign_trade_geo_agent/web/composition.py`
- Modify: `tests/test_end_to_end_workflow.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_mvp_composed_flow.py`
- Modify: `tests/test_web_demo_composition.py`

**Interfaces**

- `EndToEndWorkflow.__init__(planning_site_auditor: PlanningSiteAuditor, ...)`
- `build_planning_workflow(..., planning_site_auditor: PlanningSiteAuditor | None = None)`
- `DemoPlanningSiteAuditor.audit_crawl(report)`
- EndToEnd 使用 `HistoryStore.create_analysis_run()`。

**Named failing RED tests**

- `EndToEndWorkflowTests.test_planning_auditor_receives_the_exact_crawl_report`
- `EndToEndWorkflowTests.test_planning_workflow_never_calls_url_audit`
- `EndToEndWorkflowTests.test_analysis_run_and_input_are_created_atomically_before_crawl`
- `EndToEndWorkflowTests.test_audit_exception_becomes_sanitized_failed_run`
- `RuntimeCompositionTests.test_default_planning_auditor_is_crawl_seo_auditor`
- `RuntimeCompositionTests.test_default_planning_composition_does_not_construct_geo_optimizer`
- `DemoCompositionTests.test_demo_auditor_implements_crawl_based_contract`
- `DemoCompositionTests.test_new_demo_run_persists_fixed_analysis_input`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_end_to_end_workflow tests.test_runtime tests.test_mvp_composed_flow tests.test_web_demo_composition -v
```

**Minimal production change**

- EndToEnd 删除 `audit_site(url)` 分支和 audit thread timeout。
- 同步调用 bounded `audit_crawl(crawl)`。
- planning runtime 默认构造 `CrawlSeoAuditor`。
- Demo auditor 接受并验证 NovaCNC crawl report。
- EndToEnd 从 request 建立 `AnalysisRunInput`，用原子接口创建 run。
- GeoOptimizer 与 SiteOptimizationWorkflow 保持不变。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_end_to_end_workflow tests.test_runtime tests.test_mvp_composed_flow tests.test_web_demo_composition -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_geo_optimizer_adapter tests.test_site_optimization_workflow tests.test_cli -v
```

---

## Task 7: English research and deterministic query

**Files**

- Create: `src/foreign_trade_geo_agent/core/research_query.py`
- Modify: `src/foreign_trade_geo_agent/core/ports.py`
- Modify: `src/foreign_trade_geo_agent/workflows/industry_research.py`
- Modify: `src/foreign_trade_geo_agent/workflows/end_to_end.py`
- Modify: `src/foreign_trade_geo_agent/adapters/deepseek_research.py`
- Modify if required: `src/foreign_trade_geo_agent/adapters/deepseek_content_opportunity.py`
- Modify if required: `src/foreign_trade_geo_agent/adapters/deepseek_change_plan.py`
- Modify if required: `src/foreign_trade_geo_agent/adapters/deepseek_content_draft.py`
- Modify: `src/foreign_trade_geo_agent/web/demo_boundaries.py`
- Test: `tests/test_research_query.py`
- Modify: `tests/test_industry_research_workflow.py`
- Modify: `tests/test_deepseek_research_adapter.py`
- Modify: `tests/test_deepseek_content_opportunity_adapter.py`
- Modify: `tests/test_deepseek_change_plan_adapter.py`
- Modify: `tests/test_deepseek_content_draft_adapter.py`
- Modify: `tests/test_end_to_end_workflow.py`

**Interfaces**

```python
def build_research_query(
    crawl: SiteCrawlReport,
    seo_goal: str,
    *,
    max_chars: int = 300,
) -> str

IndustryResearchWorkflow.run(
    query: str,
    target_language: str,
) -> ResearchReport

ResearchWriter.write_report(
    question: str,
    materials: tuple[ResearchMaterial, ...],
    target_language: str,
) -> ResearchGeneration
```

**Named failing RED tests**

- `ResearchQueryTests.test_query_uses_hostname_first_successful_title_h1_and_goal`
- `ResearchQueryTests.test_query_omits_missing_fields_and_is_bounded_to_300_chars`
- `IndustryResearchWorkflowTests.test_passes_target_language_to_writer`
- `IndustryResearchWorkflowTests.test_performs_exactly_one_search_with_constructed_query`
- `DeepSeekResearchWriterTests.test_english_request_contains_no_chinese_only_instruction`
- `DeepSeekContentOpportunityTests.test_english_request_contains_no_chinese_only_instruction`
- `DeepSeekChangePlanAdapterTests.test_english_request_contains_no_chinese_only_instruction`
- `DeepSeekContentDraftAdapterTests.test_english_request_contains_no_chinese_only_instruction`
- `DeepSeekResearchWriterTests.test_untrusted_material_remains_serialized_user_data`
- `EndToEndWorkflowTests.test_research_query_is_built_after_crawl`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_research_query tests.test_industry_research_workflow tests.test_deepseek_research_adapter tests.test_deepseek_content_opportunity_adapter tests.test_deepseek_change_plan_adapter tests.test_deepseek_content_draft_adapter tests.test_end_to_end_workflow -v
```

**Minimal production change**

- 确定性构造 hostname/title/H1/goal query。
- 只使用首个成功页面；不调用 LLM 生成 query。
- DeepSeek system prompt 改为按 validated target language 输出。
- 逐一检查 research、content opportunities、change plan、content draft adapters；仅在缺少传递或存在矛盾指令时做最小 additive 修改。
- `target_language=en` 时四个 adapter 的 prompt 均明确要求 English，且不得包含中文-only 输出要求。
- 保留 `[S#]`、无 URL、untrusted materials 边界。
- Demo writer 明确接受并验证 `en`。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_research_query tests.test_industry_research_workflow tests.test_deepseek_research_adapter tests.test_deepseek_content_opportunity_adapter tests.test_deepseek_change_plan_adapter tests.test_deepseek_content_draft_adapter tests.test_end_to_end_workflow -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_tavily_search_adapter tests.test_content_opportunity_workflow tests.test_change_plan_workflow tests.test_content_draft_workflow -v
```

---

## Task 8: LiveComposition and provider readiness

**Files**

- Modify: `src/foreign_trade_geo_agent/runtime.py`
- Modify: `src/foreign_trade_geo_agent/web/composition.py`
- Test: `tests/test_web_live_composition.py`
- Modify: `tests/test_web_no_network.py`

**Interfaces**

```python
def planning_provider_configuration_ready(
    environ: Mapping[str, str] | None = None,
) -> bool

@dataclass(slots=True)
class LiveComposition:
    history_store: HistoryStore
    history_reader: HistoryReader
    providers_ready: bool

    def planning_workflow(
        self,
        observer: EndToEndProgressObserver | None = None,
    ) -> EndToEndWorkflow

def build_live_composition(
    db_path: str | Path,
    *,
    provider_configuration_ready: bool | None = None,
    test_overrides: ...,
) -> LiveComposition
```

**Named failing RED tests**

- `LiveCompositionTests.test_missing_tavily_or_deepseek_configuration_is_not_ready`
- `LiveCompositionTests.test_placeholder_configuration_marks_ready_without_network`
- `LiveCompositionTests.test_default_wiring_uses_safe_fetcher_crawl_auditor_tavily_and_deepseek`
- `LiveCompositionTests.test_live_composition_has_no_wordpress_delivery_or_verification_boundary`
- `LiveCompositionTests.test_demo_composition_builds_with_zero_provider_keys`
- `WebNoNetworkTests.test_building_live_composition_performs_no_network_access`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_composition tests.test_web_no_network -v
```

**Minimal production change**

- 新增 Live composition，复用 runtime 的 production-safe构造。
- readiness 只检查非空配置，不打印值。
- adapter 构造不得调用网络。
- Demo composition 不依赖 readiness。
- Live composition 不包含 WordPress workflow factories。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_composition tests.test_web_no_network -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_runtime tests.test_web_demo_composition tests.test_web_phase2_composed -v
```

---

## Task 9: LiveApplicationService

**Files**

- Create: `src/foreign_trade_geo_agent/web/live_application.py`
- Modify: `src/foreign_trade_geo_agent/web/__init__.py`
- Test: `tests/test_web_live_application.py`

**Interfaces**

```python
class LiveApplicationError(RuntimeError): ...

@dataclass(frozen=True, slots=True)
class LiveStartResult:
    job_id: str

class LiveApplicationService:
    def start_live_analysis(
        self,
        analysis_input: LiveAnalysisInput,
    ) -> LiveStartResult
```

**Named failing RED tests**

- `LiveApplicationServiceTests.test_unconfigured_server_rejects_before_job_run_or_network`
- `LiveApplicationServiceTests.test_unconfigured_message_is_fixed_and_sanitized`
- `LiveApplicationServiceTests.test_invalid_input_creates_no_job_or_run`
- `LiveApplicationServiceTests.test_configured_submission_schedules_one_background_workflow`
- `LiveApplicationServiceTests.test_completed_live_run_has_required_analysis_input`
- `LiveApplicationServiceTests.test_provider_failure_persists_failed_run_without_fabricated_artifacts`
- `LiveApplicationServiceTests.test_second_near_consecutive_start_is_rejected_before_job_run_or_network`
- `LiveApplicationServiceTests.test_terminal_live_job_releases_single_active_slot`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_application -v
```

**Minimal production change**

- readiness 是第一道 gate。
- validation 通过后才创建 job。
- 在同一个 local job registry/service 临界区内检查并占用单一 active Live slot；RUNNING 时使用固定 sanitized message 拒绝第二次 start。
- 被拒绝的第二次 start 不创建 job、不创建 run、不调用 workflow/fetch/search/LLM；terminal state 后释放 slot。只约束 Live Web，不改变 CLI。
- background task 调用 shared EndToEndWorkflow。
- exception 进入已有 job failure sanitation。
- 不增加 delivery methods。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_application -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_application_progress tests.test_web_jobs tests.test_end_to_end_workflow -v
```

---

## Task 10: Live Start routes and UI

**Files**

- Modify: `src/foreign_trade_geo_agent/web/app.py`
- Modify: `src/foreign_trade_geo_agent/web/routes.py`
- Modify: `src/foreign_trade_geo_agent/web/__main__.py`
- Create: `src/foreign_trade_geo_agent/web/request_integrity.py`
- Modify: `src/foreign_trade_geo_agent/web/templates/start.html`
- Modify: `src/foreign_trade_geo_agent/web/templates/base.html`
- Modify: `src/foreign_trade_geo_agent/web/templates/error.html`
- Modify: `src/foreign_trade_geo_agent/web/static/app.css`
- Test: `tests/test_web_live_routes.py`
- Modify: `tests/test_web_app.py`
- Modify: `tests/test_web_entrypoint.py`

**Named failing RED tests**

- `LiveRouteTests.test_start_page_offers_demo_and_live_analysis_modes`
- `LiveRouteTests.test_live_form_contains_url_editable_goal_and_fixed_english`
- `LiveRouteTests.test_valid_submission_redirects_to_profile_scoped_job`
- `LiveRouteTests.test_invalid_url_renders_safe_validation_error`
- `LiveRouteTests.test_unconfigured_submission_returns_sanitized_service_message`
- `LiveRouteTests.test_provider_keys_never_appear_in_html`
- `LiveRouteTests.test_live_form_contains_process_local_csrf_token`
- `LiveRouteTests.test_missing_csrf_is_rejected_before_job_run_or_network`
- `LiveRouteTests.test_incorrect_csrf_is_rejected_before_job_run_or_network`
- `LiveRouteTests.test_hostile_host_is_rejected_before_service_call`
- `LiveRouteTests.test_legitimate_local_form_post_succeeds`
- `LiveRouteTests.test_api_key_and_csrf_token_never_appear_in_sanitized_errors`
- `WebAppTests.test_demo_and_live_use_separate_db_paths_and_job_registries`
- `WebAppTests.test_demo_start_route_remains_backward_compatible`
- `WebAppTests.test_create_app_without_provider_keys_keeps_demo_usable_and_live_unavailable`
- `WebAppTests.test_zero_key_live_post_creates_no_job_run_or_network`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_routes tests.test_web_app tests.test_web_entrypoint -v
```

**Minimal production change**

- 保留现有 Demo `/start`、`/jobs/...`、`/runs/...` 路由。
- 新增 `/live/start`、`/live/jobs/...`、`/live/runs/...`。
- 根页面显示双 mode。
- `create_app()` 创建独立 Demo/Live service、DB 和 job registry。
- `create_app()` 启动时用 `secrets` 生成一个 process-local CSRF token；仅写入合法 state-changing forms，不持久化、不记录、不放入 URL。
- state-changing POST 在任何 service/job/run/network 操作前验证 Host 与 CSRF。Host allowlist 仅接受本 launcher 支持的 `127.0.0.1`/`localhost`（允许实际监听端口），失败使用固定 sanitized response。
- 至少保护 `POST /live/analyses`；若复用到现有 mutating Demo forms 不得改变冻结 Demo 行为。
- Live provider 未就绪时延迟 provider construction，Web app 与 Demo 仍可启动/使用；Live page 显示 unavailable，POST 零副作用。
- 默认 Live DB 为 `.data/live-ui/history.sqlite3`。
- entrypoint 文案从 Demo-only 改为 SEO Agent local Web。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_routes tests.test_web_app tests.test_web_entrypoint -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_progress_routes tests.test_web_result_routes tests.test_web_delivery_routes -v
```

---

## Task 11: Live progress and restart behavior

**Files**

- Modify: `src/foreign_trade_geo_agent/web/live_application.py`
- Modify: `src/foreign_trade_geo_agent/web/routes.py`
- Modify: `src/foreign_trade_geo_agent/web/presenters.py`
- Modify: `src/foreign_trade_geo_agent/web/templates/progress.html`
- Modify: `src/foreign_trade_geo_agent/web/templates/partials/progress_panel.html`
- Modify: `src/foreign_trade_geo_agent/web/templates/partials/workflow_rail.html`
- Test: `tests/test_web_live_progress.py`

**Named failing RED tests**

- `LiveProgressTests.test_active_job_reports_only_real_stage_events`
- `LiveProgressTests.test_refresh_recovers_completed_stages_from_live_database`
- `LiveProgressTests.test_running_run_without_active_job_is_interrupted`
- `LiveProgressTests.test_live_run_missing_required_input_is_invariant_failure`
- `LiveProgressTests.test_live_workflow_rail_stops_at_draft_review`
- `LiveProgressTests.test_progress_contains_no_percentage_timer_tokens_or_reasoning`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_progress -v
```

**Minimal production change**

- 复用六个 EndToEnd stages。
- 所有 Live URLs 保持 `/live/...`。
- restart 从 run/input/artifacts 恢复。
- 无 active job 的 RUNNING 显示 interrupted，不 resume。
- Live input 缺失显示固定 internal error；不猜测历史值。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_progress -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_application_progress tests.test_web_progress_routes tests.test_web_jobs -v
```

---

## Task 12: Shared Results, Change Plan, and Draft Review

**Files**

- Modify: `src/foreign_trade_geo_agent/web/presenters.py`
- Modify: `src/foreign_trade_geo_agent/web/application.py`
- Modify: `src/foreign_trade_geo_agent/web/live_application.py`
- Modify: `src/foreign_trade_geo_agent/web/routes.py`
- Modify: `src/foreign_trade_geo_agent/web/templates/results.html`
- Modify: `src/foreign_trade_geo_agent/web/templates/changes.html`
- Modify: `src/foreign_trade_geo_agent/web/templates/draft_review.html`
- Modify: `src/foreign_trade_geo_agent/web/templates/base.html`
- Modify: `src/foreign_trade_geo_agent/web/templates/partials/workflow_rail.html`
- Test: `tests/test_web_live_results.py`
- Modify: `tests/test_web_presenters.py`
- Modify: `tests/test_web_navigation_phase2.py`

**Interfaces**

```python
@dataclass(frozen=True, slots=True)
class AnalysisContextView:
    display_identity: str
    website_url: str
    seo_goal: str
    target_language: str
    live: bool
```

共享 result/change/draft view models 包含 `context`，Demo delivery view models 保持独立。

**Named failing RED tests**

- `LiveResultsTests.test_results_show_persisted_live_target_goal_and_language`
- `LiveResultsTests.test_results_show_crawl_derived_audit_evidence`
- `LiveResultsTests.test_change_plan_keeps_external_context_separate_from_website_evidence`
- `LiveResultsTests.test_draft_review_is_terminal_live_step`
- `LiveResultsTests.test_live_pages_contain_no_novacnc_demo_fixture_or_wordpress_copy`
- `PresenterTests.test_generic_page_labels_do_not_special_case_machines`
- `DemoNavigationTests.test_demo_still_has_delivery_and_verification_steps`
- `DemoNavigationTests.test_legacy_demo_run_without_input_uses_fixed_demo_context`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_results tests.test_web_presenters tests.test_web_navigation_phase2 -v
```

**Minimal production change**

- 泛化共享 read-side 命名和 context。
- 删除 `machines` 页面特例和 Demo-only audit findings。
- Live navigation 不生成 delivery/verification destinations。
- Demo 路由、delivery 和 verification presenters 继续工作。
- 保留 `External context — not website evidence`。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_results tests.test_web_presenters tests.test_web_navigation_phase2 -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_application_results tests.test_web_result_routes tests.test_web_phase2_composed tests.test_web_visual_polish -v
```

---

## Task 13: SSRF, injection, and failure contracts

**Files**

- Create: `src/foreign_trade_geo_agent/workflows/planning_failures.py`
- Modify: `src/foreign_trade_geo_agent/workflows/end_to_end.py`
- Modify: `src/foreign_trade_geo_agent/web/live_application.py`
- Test: `tests/test_live_security_contracts.py`
- Modify: `tests/test_safe_html_fetcher.py`
- Modify: `tests/test_web_xss.py`
- Modify: `tests/test_site_content_packet.py`

**Interfaces**

```python
@dataclass(frozen=True, slots=True)
class PlanningFailure:
    failure_kind: str
    sanitized_error: str

def classify_crawl_failure(report: SiteCrawlReport) -> PlanningFailure
```

**Named failing RED tests**

- `LiveSecurityContractTests.test_localhost_and_private_literals_fail_before_transport`
- `LiveSecurityContractTests.test_mixed_dns_answer_fails_closed`
- `LiveSecurityContractTests.test_dns_rebinding_fails_closed`
- `LiveSecurityContractTests.test_redirect_to_private_fails_before_private_request`
- `LiveSecurityContractTests.test_fake_ip_198_18_range_remains_rejected`
- `LiveSecurityContractTests.test_oversized_and_decompression_bomb_responses_fail_bounded`
- `LiveSecurityContractTests.test_prompt_injection_text_remains_evidence_data`
- `LiveSecurityContractTests.test_provider_raw_error_and_stack_are_not_persisted_or_rendered`
- `WebXssTests.test_live_target_research_and_website_text_are_autoescaped`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_live_security_contracts tests.test_safe_html_fetcher tests.test_web_xss -v
```

**Minimal production change**

- 将现有 crawl/fetch failure 映射成稳定 sanitized failure kinds。
- `PlanningFailure.failure_kind` 只用于进程内 bounded mapping/presentation；不得声称其被 SQLite 持久化或在重启后可恢复。
- 失败持久化继续以现有 `WorkflowRun` sanitized failure/error 字段为 canonical；不得把 raw exception/provider payload 编入 `failure_kind`。
- SQLite v3 不为 `failure_kind` 增列，除非实现中出现被测试证明的真实 blocker；若出现必须先记录 plan ruling。
- 不修改 SafeHtmlFetcher 的允许网络范围。
- 不加入 proxy fallback。
- website/research injection 继续作为 JSON/data 进入 prompt。
- 模板继续 autoescape，禁止 `safe`/Markup。
- crawl limit with usable pages 是成功 warning，不是失败。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_live_security_contracts tests.test_safe_html_fetcher tests.test_web_xss -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_safe_http_transport tests.test_site_crawl_workflow tests.test_site_content_packet tests.test_deepseek_research_adapter -v
```

---

## Task 14: Two-domain, profile, and database isolation contracts

**Files**

- Create: `tests/live_composed_fixtures.py`
- Create: `tests/test_web_live_composed.py`
- Modify as failures require:
  - `src/foreign_trade_geo_agent/web/app.py`
  - `src/foreign_trade_geo_agent/web/routes.py`
  - `src/foreign_trade_geo_agent/web/live_application.py`

**Named failing RED tests**

- `LiveComposedTests.test_generic_domain_runs_full_live_workflow_without_novacnc`
- `LiveComposedTests.test_alpha_and_beta_domains_persist_independent_inputs_and_artifacts`
- `LiveComposedTests.test_each_results_page_displays_only_its_own_target`
- `LiveComposedTests.test_live_run_id_cannot_be_read_through_demo_service`
- `LiveComposedTests.test_demo_run_id_cannot_be_read_through_live_service`
- `LiveComposedTests.test_demo_and_live_databases_never_cross_query`
- `LiveComposedTests.test_live_composed_flow_never_constructs_wordpress_adapter`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_composed -v
```

**Minimal production change**

- 测试使用 local fake crawl transport/resolver/search/LLM，但走真实 Live composition/workflows/storage/presenters。
- 生产代码仅修复测试暴露出的 profile ownership 检查。
- 不增加共享跨库 lookup。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_live_composed -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_phase2_composed tests.test_web_demo_composition tests.test_web_no_network -v
```

---

## Task 15: Demo and CLI regressions

**Files**

- Modify: `tests/test_cli.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_web_demo_composition.py`
- Modify: `tests/test_web_phase2_composed.py`
- Modify: `tests/test_mvp_composed_flow.py`
- Production files only if regressions reveal a compatibility defect

**Named failing RED tests**

- `CliTests.test_plan_uses_crawl_based_default_planning_audit`
- `CliTests.test_plan_persists_actual_site_goal_and_language`
- `RuntimeCompositionTests.test_geo_optimizer_remains_available_to_site_optimization_only`
- `DemoCompositionTests.test_demo_requires_no_tavily_or_deepseek_keys`
- `DemoCompositionTests.test_demo_start_through_verification_remains_deterministic`
- `DemoCompositionTests.test_new_demo_run_persists_fixed_input`
- `DemoCompositionTests.test_legacy_demo_history_without_input_remains_readable`
- `MvpComposedFlowTests.test_planning_still_stops_for_human_review`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_cli tests.test_runtime tests.test_web_demo_composition tests.test_web_phase2_composed tests.test_mvp_composed_flow -v
```

**Minimal production change**

- 只修复由新 contract 引起的兼容问题。
- 不改变 CLI WordPress approval boundary。
- 不改变 Demo fixture、输出顺序或 WordPress mock semantics。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_cli tests.test_runtime tests.test_web_demo_composition tests.test_web_phase2_composed tests.test_mvp_composed_flow -v
```

**Targeted regression**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_delivery_safety tests.test_wordpress_delivery_workflow tests.test_wordpress_verification_workflow tests.test_geo_optimizer_adapter -v
```

---

## Task 16: Documentation and full automated verification

**Files**

- Modify: `README.md`
- Modify: `docs/architecture.md`
- Test: `tests/test_documentation_contract.py`

**Named failing RED tests**

- `DocumentationContractTests.test_readme_describes_demo_and_live_profiles`
- `DocumentationContractTests.test_readme_documents_public_https_and_bounded_limits`
- `DocumentationContractTests.test_readme_states_live_stops_at_draft_review`
- `DocumentationContractTests.test_architecture_documents_crawl_based_planning_audit`
- `DocumentationContractTests.test_manual_web_smoke_is_marked_operator_only`
- `DocumentationContractTests.test_failure_kind_is_documented_as_internal_not_persisted`

**RED command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_documentation_contract -v
```

**Minimal production change**

文档明确：

- Demo/Live composition。
- Live DB 路径。
- provider readiness。
- crawl limits。
- audit evidence范围和不支持项。
- WordPress optionality。
- TUN/Fake-IP 处理。
- CLI diagnostic 和 Web manual smoke。
- v3 legacy behavior。
- persisted failure contract：仅现有 run sanitized error 跨重启可用，`failure_kind` 不持久化。
- Task 17 是 user/operator-only gate，自动化实施不得启动真实 Web Live smoke。

**GREEN command**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_documentation_contract -v
```

**Targeted regression**

先运行所有本计划涉及模块，再运行完整 suite：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

只有观察到 exit 0 和零 failures/errors 后，才能报告完整 suite 通过。

Task 16 完成前还必须按顺序记录以下真实命令结果：

1. 所有新增 Live targeted tests。
2. 所有 Web/Demo regressions。
3. CLI/runtime/planning regressions。
4. WordPress delivery/verification regressions。
5. migration/storage regressions。
6. 完整 unittest suite。
7. `git diff --check`。
8. `git status --short`。

---

## Task 17: Manual Web Live smoke gate

> **Operator-only:** agent 在 Task 1–16 后必须停止，不启动服务器、不提交真实 URL、不调用 Tavily/DeepSeek，也不把本任务标记为通过。仅向用户交付以下步骤。

**Files**

- 不修改文件。
- 操作说明已由 Task 16 写入 README。
- 这是人工 acceptance gate，不进入 unittest/CI。

**Named manual RED acceptance**

- `manual_web_live_smoke_public_https_to_draft_review`

**RED command**

在没有实施完成、没有 provider 配置或 TUN 返回 Fake-IP 时，该流程必须不能被宣称通过。实施完成后由操作员显式启动：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent.web
```

浏览器访问：

```text
http://127.0.0.1:8000/
```

**Minimal production change**

- 无；本任务只验证已经完成的产品路径。

**GREEN procedure**

1. 选择 Live Analysis。
2. 输入一个获准测试的真实公开 HTTPS URL。
3. 保留或编辑默认 SEO goal。
4. 点击 Analyze Website。
5. 等待真实六阶段 progress。
6. 打开 Results、Change Plan、Draft Review。
7. 记录 run ID、目标 hostname、crawl page count/stop reason。
8. 确认没有进入 delivery route。

**GREEN acceptance**

- 真实 hostname 正确。
- crawl evidence 与目标站一致。
- 无 NovaCNC/Demo-only 文案。
- 无 WordPress adapter 调用。
- Draft Review 为终点。
- page/depth/time limits 正确。
- 若故意模拟 provider failure，UI 只显示 sanitized message。

**Targeted regression**

可选 CLI operator diagnostic：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent plan `
  --site https://example.com `
  --question "Improve organic search visibility and content coverage" `
  --language en `
  --db .data/smoke/live-analysis.sqlite3
```

不得运行 `deliver`。

Task 1–16 已获批准，可按 strict RED → GREEN 执行；Task 17 保持人工验收 gate。
