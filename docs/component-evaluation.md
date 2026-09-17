# Third-Party Component Evaluation

本文档用于记录候选第三方开源项目、服务或工具的评估。每个组件在完成实际调研前不得填写结论。

## geo-optimizer-skill

### 审计范围与基线

- 仓库：[`Auriti-Labs/geo-optimizer-skill`](https://github.com/Auriti-Labs/geo-optimizer-skill)
- 审计日期：2026-09-18
- 审计基线：`main` commit [`6121db348dda9fe87c6068e9d8e706bc09af3add`](https://github.com/Auriti-Labs/geo-optimizer-skill/commit/6121db348dda9fe87c6068e9d8e706bc09af3add)，包版本 `4.18.1`
- 审计方式：只读检查 README、项目元数据、LICENSE、源码、测试、CI、发布记录和 PyPI 元数据；未安装或运行该包，因此运行时兼容性与真实网站结果仍需最小验证。

### 1. 项目基本信息

- **主要语言与技术栈**：Python，使用 setuptools/`src` 布局。基础运行依赖为 Click、Requests、BeautifulSoup4、lxml 和 urllib3；FastAPI、Uvicorn、MCP、httpx、LLM SDK 等均为可选依赖。证据见 [`pyproject.toml`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/pyproject.toml)。
- **Python 要求**：`>=3.9`，项目元数据列出 3.9–3.13；这与我们的 `>=3.11` 要求兼容。PyPI 当前也显示 Python `>=3.9`。证据见 [`pyproject.toml`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/pyproject.toml) 与 [PyPI](https://pypi.org/project/geo-optimizer-skill/)。
- **当前活跃度**：高。审计基线前一日仍有提交，`v4.18.1` 于 2026-09-17 发布，PyPI 同日存在通用 `py3-none-any` wheel。证据见 [`v4.18.1` release](https://github.com/Auriti-Labs/geo-optimizer-skill/releases/tag/v4.18.1) 与 [PyPI 发布记录](https://pypi.org/project/geo-optimizer-skill/#history)。活跃迭代同时意味着 Adapter 必须防范字段和评分规则快速变化。
- **License**：MIT。许可证允许使用、复制、修改、合并、发布、分发、再许可和销售，但分发软件或其实质部分时需保留版权和许可声明，且软件不提供担保。证据见 [`LICENSE`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/LICENSE)。
- **商业使用**：允许，受上述 MIT 条件约束。此处是技术审计结论，不替代正式法律意见。

### 2. 使用方式

#### CLI

基础安装后提供 `geo` 命令。单站审计的机器输出调用方式为：

```text
geo audit --url https://example.com --format json
```

还支持 sitemap 批量审计、缓存、历史保存、阈值、回归检测和多种报告格式。CLI 在执行前做 URL 安全校验，并将 JSON 结果写到 stdout。证据见 [`audit_cmd.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/cli/audit_cmd.py) 与 [`formatters.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/cli/formatters.py)。

#### Python library

存在明确的公开 API：`from geo_optimizer import audit, audit_async, AuditResult`。`audit` 是 `run_full_audit` 的公开别名，返回 dataclass `AuditResult`，不是打印文本。证据见 [`geo_optimizer/__init__.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/__init__.py) 与 [`results.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/models/results.py)。

公开入口是清晰的，但“跨 minor 版本长期稳定”的保证没有在 Python 类型层形成版本化合约；`AuditResult` 在近期版本持续增加字段。因此应固定依赖版本，并只在 Adapter 内访问第三方类型。

#### JSON 输出

- CLI 的 `--format json` 输出合法、适合程序解析的 JSON，包含 URL、时间、总分、band、error、八类 checks、score breakdown、recommendations，以及按条件出现的补充检查。解析方必须先检查 `error`，否则无法区分“真实 0 分”和“目标站不可达后生成的默认空结果”。证据见 [`format_audit_json`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/cli/formatters.py#L59-L224)。
- README 声称 CLI JSON 在 minor 版本间保持稳定，但当前 CLI JSON 本身**没有** `schema_version` 字段。版本化 `schema_version: 1` 和冻结 fixture 实际用于 Web API 序列化。证据见 [`formatters.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/cli/formatters.py)、[`web/app.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/web/app.py#L1510-L1618)、[`test_audit_contract.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/tests/test_audit_contract.py) 与 [`audit_result_v1.json`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/tests/fixtures/audit_result_v1.json)。

#### REST API

支持自托管 FastAPI：安装 `[web]` extra 后运行 `geo-web`，提供 `GET /api/audit` 和 `POST /api/audit` 等端点；POST body 为 `{ "url": "..." }`。审计端点包含 SSRF 校验、限流、可选 Bearer Token、60 秒应用层超时和版本化 Web JSON。证据见 [`web/app.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/web/app.py#L735-L801) 与 [`web/cli.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/web/cli.py)。

这证明存在 REST 实现，但不等于项目承诺了适合作为外部依赖的托管公共 API。若使用该方式，我们需要自行部署和运维服务。

#### MCP

支持。安装 `[mcp]` extra 后可运行 `geo-mcp`。源码实现了 `geo_audit`、`geo_citability`、`geo_compare`、`geo_gap_analysis` 等工具，并返回 JSON 字符串。证据见 [`pyproject.toml`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/pyproject.toml) 与 [`mcp/server.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/mcp/server.py)。

### 3. 与 MVP 最相关的功能

| 能力 | 审计结论 | 实现证据与限制 |
|---|---|---|
| 单网站 audit | 已实现 | `audit(url)`/`run_full_audit(url)`；抓取首页及站点辅助端点后返回 `AuditResult`。[`audit.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/audit.py#L714-L912) |
| GEO score | 已实现 | 0–100 总分、band 和八分类 breakdown；评分是项目自己的规则体系，不应等同于搜索引擎官方指标。[`scoring.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/scoring.py) |
| 技术 SEO / AI crawlability | 已实现 | robots.txt、AI citation bots、meta/canonical/OG、JSON-LD、语言/RSS/新鲜度、CDN/WAF bot 探测、无 JS 内容可见性、AI discovery endpoints。[`audit.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/audit.py#L795-L893) |
| Citability | 已实现，属启发式 readiness | 核心 audit 生成 `CitabilityResult`（分数、grade、method scores、top improvements）。它评估页面是否“容易被引用”，不是实际 AI 引用观测。[`results.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/models/results.py#L217-L244) |
| Recommendations | 已实现 | 根据检查结果生成字符串列表，包含 robots、llms.txt、schema、meta、内容和 JS 等建议。建议结构目前不是稳定的带 ID/严重级别对象。[`audit.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/audit.py) |
| Competitor compare | 已实现但接口分散 | MCP `geo_compare` 最多比较 5 个 URL；本质是分别 audit 后按分数排序。Python 顶层公开 API 未导出 compare。[`mcp/server.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/mcp/server.py#L279-L326) |
| Gap analysis | 已实现 | `run_gap_analysis` 对两个站点执行 audit，再按类别差异生成行动项；模块未从顶层公共 API 导出。[`gap_analysis.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/gap_analysis.py) |
| Citation tracking | 部分实现，不能作为无 Key 本地能力 | `geo citations` 会调用 Perplexity/OpenAI/Anthropic/Groq/MiniMax/Gemini/DeepSeek 或显式选择 SerpBase。真实 source URL 主要依赖 Perplexity 或 SERP provider；普通参数模型更多是 brand knowledge 检查。需要 API Key，且结果非确定性。[`citations_cmd.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/cli/citations_cmd.py) 与 [`citations.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/citations.py) |

结论上，它最强的是“输入侧 readiness/技术诊断”，并不能单独替代我们计划中的独立 AI visibility、brand mention 和长期竞品观测数据源。

### 4. 输入与输出

#### 最小输入

- 单站 audit 最少只需要一个可公开访问的 HTTP/HTTPS URL；裸域名会补为 `https://`。
- sitemap 批量模式另需 sitemap URL；默认最多 50 个页面、并发 5。证据见 [`audit_cmd.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/cli/audit_cmd.py) 与 [`batch_audit.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/batch_audit.py)。

#### 典型输出字段

`AuditResult` 当前主要包含：

- 身份与状态：`url`、`timestamp`、`http_status`、`page_size`、`audit_duration_ms`、`error`。
- 评分：`score`、`band`、`score_breakdown`。
- 评分子结果：`robots`、`llms`、`schema`、`meta`、`content`、`signals`、`ai_discovery`、`brand_entity`。
- 引用准备度：`citability`。
- 信息型检查：`cdn_check`、`js_rendering`、`webmcp`、`multimodal`、`negative_signals`、`prompt_injection`、`trust_stack`、RAG/embedding/content decay/platform profile 等。
- 可执行输出：`recommendations`。

完整字段见 [`AuditResult`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/models/results.py#L983-L1047)。

#### 数据结构稳定性

- Python 结果使用 dataclass，不是 Pydantic；类型定义清楚，便于 Adapter 映射。
- Web API 有 `schema_version: 1` 和 contract tests；CLI JSON 是手工选择字段并包含条件字段，未携带 schema version。
- `AuditResult` 字段增长很快，评分规则、建议文案和信息型模块更可能变动。不得把它直接作为我们的 `core` 模型或持久化 schema。
- JSON 适合程序解析，但 Adapter 必须：检查进程退出码与 `error`；容忍未知字段和缺失的可选字段；校验分数范围；记录第三方版本；不要按建议文案做业务判断。

### 5. 外部依赖与网络行为

#### 核心 audit

- 基础 audit 不要求 LLM API Key。默认情况下，它访问目标站点本身，包括首页、`/robots.txt`、`/llms.txt`、`/llms-full.txt`、`/.well-known/ai.txt`、`/ai/summary.json`、`/ai/faq.json`、`/ai/service.json`，并用浏览器及多个 AI bot User-Agent 再请求首页以探测 CDN/WAF 差异。证据见 [`audit.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/audit.py#L795-L835) 与 [`audit_cdn.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/audit_cdn.py)。
- 可选 brand sentiment 只有在配置 `brand_name` 时才会走 LLM provider。为保证 MVP 的核心诊断可重复，应禁用该配置。
- “完全本地运行”需要准确表述：分析逻辑在本地执行且无需第三方 SaaS/API，但 audit 必然联网访问被审计站点；它不是离线审计。

#### 需要 Key 的能力

- `geo citations` 需要 `PERPLEXITY_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GROQ_API_KEY`、`MINIMAX_API_KEY`、`GEMINI_API_KEY`、`DEEPSEEK_API_KEY` 或显式 SerpBase 的 `SERPBASE_API_KEY`。
- 相关外部服务包括 Perplexity、OpenAI、Anthropic、Groq、MiniMax、Google Generative Language、DeepSeek 和 `api.serpbase.dev`；具体 provider 由配置选择。证据见 [`llm_client.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/llm_client.py) 与 [`serp_provider.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/serp_provider.py)。
- 这些能力涉及费用、配额、数据出境、供应商波动和非确定性，不应偷偷包含在第一版 `audit_site` 中。

### 6. 部署与运行

- **pip 安装**：可以，PyPI 当前提供 `geo-optimizer-skill 4.18.1` 的通用 wheel。证据见 [PyPI](https://pypi.org/project/geo-optimizer-skill/)。
- **Docker**：核心 CLI/Python library 不需要 Docker。仓库提供面向 FastAPI + 前端的 `Dockerfile.web`，属于可选的 Web 部署方式。证据见 [`Dockerfile.web`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/Dockerfile.web)。
- **Windows**：从依赖、`py3-none-any` wheel 和 pathlib 用法看，Windows 直接 `pip install` 与 library/CLI 运行应当可行；README 的 bash 安装脚本不是 Windows 方案。仓库 CI 目前仅在 Ubuntu 上运行 Python 3.9/3.11/3.12/3.13，没有 Windows runner，因此 Windows 兼容性仍标记为**未确认，需实测**。证据见 [`.github/workflows/ci.yml`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/.github/workflows/ci.yml)。

单站 audit 的大致步骤：规范化并校验 URL；抓取首页；抓取同源辅助端点；解析 HTML/robots/llms/schema/meta/content；以多个 User-Agent 探测 CDN/WAF；计算八类分数、citability 和信息型检查；生成建议；返回 dataclass 或 JSON。

### 7. 集成风险

1. **输出与评分漂移**：项目更新非常快。Web JSON 有 v1 contract tests，但 Python dataclass 与 CLI JSON 会增加可选字段，CLI JSON 没有 schema version；评分权重和建议文案也可能改变。必须锁版本、保留 source version、做 Adapter contract fixtures。
2. **网络超时与请求放大**：HTTP 层默认有超时、指数退避、最多 10 次重定向和 10 MB body 限制；但一次 audit 会产生多次同源请求，CDN 检查还会用多个 bot User-Agent 访问首页。大站 sitemap 批量审计默认 50 页、并发 5，可能造成较长运行时间、WAF 触发或对客户站点造成压力。证据见 [`http.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/utils/http.py)、[`audit_cdn.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/audit_cdn.py) 与 [`batch_audit.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/core/batch_audit.py)。
3. **SSRF 风险仍需纵深防御**：项目已经实现 URL scheme/凭据/私网与保留地址阻断、DNS 解析校验、IP pinning、每跳 redirect 重验、response size 限制，并有专门测试。证据见 [`validators.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/utils/validators.py)、[`http.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/utils/http.py) 与 [`test_ssrf_hardening.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/tests/test_ssrf_hardening.py)。但我们的入口仍应独立做 URL allow-policy、DNS/egress 限制和调用超时，不能把安全责任完全下放给依赖。
4. **同步调用阻塞**：公开 `audit()` 是同步网络任务；未来放入 FastAPI 时不能直接占用 event loop。可以在线程池/任务队列中调用，或验证 `audit_async` 后使用其可选 httpx 依赖。
5. **错误语义**：连接失败和非 200/203 会返回带 `error` 的 `AuditResult`，而不是总是抛异常；Adapter 必须先判断 `error`，不能把默认 score `0` 当作有效诊断。
6. **第三方 API 依赖**：核心 audit 可避开 API Key；citation/brand visibility 功能不可避免地依赖外部 provider、费用与非确定性。应拆成独立 Adapter 能力，不与技术 audit 混为一个接口。
7. **接口分层不一致**：compare/gap 在 MCP 或内部模块中存在，但没有全部纳入顶层 Python public API。直接导入 `geo_optimizer.core.*` 会增加升级风险。
8. **评分解释风险**：GEO score 是该项目基于自身规则实现的 readiness 指标，不是 ChatGPT、Google、Perplexity 等平台官方分数。产品界面和报告必须明确这一点。

### 8. MVP 集成方式建议

**建议选择 A：Python library 直接调用。**

原因：

- 项目明确导出 `audit()` 与 `AuditResult`，这是真正的公开 Python API，不需要依赖内部模块。
- 与我们的 Python 技术栈一致，基础依赖规模可控；可以直接在 Adapter 内映射 dataclass，保留类型与错误语义，并方便单元测试。
- 相比 CLI subprocess，避免 Windows 下的 executable 定位、参数 quoting、stdout/stderr 编码、进程 timeout/kill 和 JSON 半截输出问题。
- CLI JSON 虽机器可读，但当前没有 Web API 的 `schema_version`，因此它并没有明显优于 Python API 的结构稳定性。
- MCP 面向 AI 工具编排，增加协议和可选依赖，而且工具返回 JSON 字符串；这与第一版固定 Workflow 的确定性调用方式不匹配。
- REST 需要我们额外部署和运维 `geo-web` 服务，只有在未来需要进程/语言级隔离或独立扩缩容时才值得考虑。

采用 A 的条件：固定经过验证的精确版本；只调用顶层 `geo_optimizer.audit`；在受控 worker/thread 中执行；Adapter 立即把结果转换成内部模型；禁止 core 引用任何 `geo_optimizer.*` 类型；保留 CLI + JSON 作为故障隔离备选方案，而不是首选。

### 9. 最小 Adapter 边界（设计，不实现）

建议第一版只暴露单站技术诊断能力：

```text
audit_site(url) -> SiteAuditResult
```

`SiteAuditResult` 内部只保留以下稳定业务字段：

- `target_url`
- `audited_at`
- `status`: `succeeded | partial | failed`
- `provider`: 固定为 `geo-optimizer-skill`
- `provider_version`
- `overall_score`: 0–100；仅在成功时有效
- `score_band`: 内部枚举，不直接依赖第三方字符串
- `category_scores[]`: `{category, score, max_score}`，category 使用我们自己的枚举
- `crawlability`: HTTP status、robots 是否存在、citation bots 是否可访问、被阻止/缺失的 bot、CDN 是否疑似阻止、是否依赖 JS、`noindex` 信号
- `discovery`: `llms.txt` 是否存在/基本完整度、AI discovery endpoint 数量
- `structured_data`: schema types、Organization/Product/Article/FAQ 等关键布尔值、richness score
- `on_page`: title/description/canonical/H1、word count、external citation count、freshness 信号
- `citability`: score、grade、top improvements；明确标注为 readiness heuristic
- `brand_entity`: 名称一致性、sameAs/知识图谱支柱、About/Contact 等有限信号
- `recommendations[]`: `{category, message, priority?, source_code?}`；无法可靠映射 priority 时保持为空，不根据英文文案猜测
- `diagnostics`: audit duration、目标 HTTP 状态、可重试错误类型和安全过滤后的错误信息

不进入 core 的内容：第三方 dataclass、`raw_schemas` 全量内容、第三方插件结果、条件型实验字段、LLM raw response、CLI/Web 专用 alias、建议文案解析规则。若为排障需要保留原始 JSON，应作为带访问控制和保留期的 provider artifact 存储，并与核心业务模型分离。

竞品比较不应成为第一个 Adapter 方法。第一版可以由我们的 Workflow 对多个 URL 分别调用 `audit_site`，再用内部归一化数据比较；这样无需依赖未公开的 `geo_optimizer.core.gap_analysis` 接口。

### 10. 最终结论

- **是否建议进入 MVP**：是，限于 GEO/技术 readiness 诊断，不把它当作完整 AI visibility 或真实 citation tracking 数据源。
- **建议程度**：**有条件推荐**。

最重要的 3 个优点：

1. 公开 Python API、CLI JSON、REST 和 MCP 多种集成面，且 MIT 允许商业使用。
2. 核心 audit 无需 LLM/API Key，覆盖 robots、llms.txt、schema、meta、内容、AI discovery、CDN/JS 和 citability，贴合 MVP 技术诊断需求。
3. 有 dataclass 模型、Web JSON contract tests、SSRF/HTTP 测试和持续发布，工程基础明显强于只有 README/脚本的原型。

最重要的 3 个风险：

1. 发布节奏快、字段和评分规则持续扩张；Python/CLI 接口没有完整的跨 minor schema 保证。
2. 网络请求数量和重试会放大单次/批量审计成本，需额外的超时、并发、速率和 egress 控制。
3. 实际 brand mention/citation tracking 依赖外部 LLM/SERP API，不能由无 Key 的核心 audit 覆盖，也不应与 readiness score 混淆。

### 下一步最小验证

在不进入正式 Adapter 开发前，建立一个**隔离的临时验证环境**，锁定 `geo-optimizer-skill==4.18.1`，只验证以下内容：

1. Windows + 项目目标 Python 版本上能否从 PyPI 安装、导入 `geo_optimizer.audit` 并正常卸载/删除临时环境。
2. 对 3 个受控目标运行 Python API：正常静态站、不可达站、明确受 WAF/JS 影响的站；记录耗时、请求量、`error` 语义和关键字段。
3. 同时运行一次 CLI `--format json`，比较 Python dataclass、CLI JSON 和 Web v1 contract 的字段差异。
4. 用固定 fixture 写一次“第三方输出 -> 候选内部字段”的映射草案，并模拟未知字段、缺失字段与 score 变化；不写生产 Adapter。
5. 复核 Windows 编码、DNS pinning、redirect SSRF、超时取消和并发上限。验证通过后再确定版本锁定策略与 Adapter 实现计划。

当前不建议在最小验证中启用 `geo citations`、任何 LLM provider、MCP 或 Web/Docker extra；它们不是判断单站技术诊断 Adapter 是否可用的必要条件。

## Runtime Validation

### 验证范围与环境

- 测试日期：2026-09-18
- 操作系统：Windows（当前开发机）
- 解释器：CPython 3.14.6，64-bit；本机 `py -0p` 未发现 Python 3.12 或 3.13。
- 隔离环境：项目根目录 `.venv`，未修改系统 Python。
- pip：26.1.2
- 被测包：`geo-optimizer-skill==4.18.1`
- 调用入口：公开 API `from geo_optimizer import audit`；验证脚本为 `scripts/verify_geo_optimizer.py`，仅用于 PoC，不是 Adapter。
- 未启用：LLM/API Key、`geo citations`、MCP、REST/Web、Docker、批量 audit。

### 安装与导入结果

- **安装成功**：`pip install geo-optimizer-skill==4.18.1` 在 `.venv` 完成；基础依赖包括 Click、Requests、BeautifulSoup4、lxml、urllib3。
- **Python 3.14 观察**：上游元数据只声明至 Python 3.13，但本次安装成功获取了 `lxml-6.1.3-cp314-cp314-win_amd64.whl`，并成功导入 `geo_optimizer`。
- **公开 API 观察**：`geo_optimizer.__version__ == "4.18.1"`，且 `geo_optimizer.audit` 为可调用对象。

这证明该包在当前 Windows + Python 3.14 环境中至少可安装和导入；不等同于上游正式承诺支持 Python 3.14。项目长期运行时仍应优先评估 Python 3.12，以降低后续 FastAPI、Pydantic、数据库驱动与 AI SDK 的生态风险。

### 实际 Python API 调用结果

| 目标 | 实际结果 | 耗时 | 返回类型 / 关键字段 |
|---|---|---:|---|
| `https://example.com` | 未执行内容 audit；安全校验拒绝 | 0.150 s | `geo_optimizer.models.results.AuditResult`；`error="Unsafe URL: URL points to a non-public address."`，`score=0`，`http_status=0` |
| `https://www.python.org` | 未执行内容 audit；安全校验拒绝 | 0.001 s | 同上 |
| `http://127.0.0.1` | 正确被拒绝；未进行 localhost 访问 | 0.000 s | 同上 |

每次调用都返回真实 `AuditResult` dataclass，而不是抛出异常；观察到的顶层字段包括 `url`、`timestamp`、`score`、`band`、`robots`、`llms`、`schema`、`meta`、`content`、`recommendations`、`http_status`、`citability`、`score_breakdown`、`error`、`cdn_check`、`js_rendering`、`brand_entity`、`trust_stack` 等。这与静态审计中 `AuditResult` 的 dataclass 和“失败返回带 error 的结果对象”结论一致。

### 公共 URL 未完成的根因

本机运行时 DNS 解析结果如下：

```text
example.com      -> 198.18.0.145
www.python.org   -> 198.18.0.144
```

`198.18.0.0/15` 是保留的网络基准测试地址范围；CPython 的 `ipaddress` 在本机将上述地址标记为非全局/私有。geo-optimizer 的 URL validator 明确阻止该范围，并在 DNS 解析后拒绝所有非公网结果；因此两个公共域名被拒绝的原因是当前网络/DNS 环境，而不是 audit 逻辑或 Python 3.14 安装失败。该行为与上游 SSRF 防护实现一致，见 [`validators.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/utils/validators.py) 和 [`http.py`](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/6121db348dda9fe87c6068e9d8e706bc09af3add/src/geo_optimizer/utils/http.py)。

本验证没有修改 DNS、没有把保留 IP 当作可访问公网地址、没有绕过 SSRF 校验，也没有扫描局域网。因此：

- localhost 拒绝验证：**通过**。
- Windows 安装、导入和真实返回对象验证：**通过**。
- `example.com` / `python.org` 的成功公网 audit、真实评分、完整推荐内容和端到端耗时验证：**未完成，受本机 DNS 环境阻塞**。

### 与静态审计的对照与新风险

- 一致：公开 `audit()` 可调用、版本为 `4.18.1`、返回 `AuditResult` dataclass、失败使用 `error` 字段而不是总是抛异常、localhost 被 SSRF 保护阻止。
- 未能确认：在本机对正常公共站点的成功审计耗时、非零 score、score breakdown、recommendations 内容，以及 Python 3.14 的长期稳定性。
- 新风险：严格 DNS/IP SSRF 校验会与将公共域名解析到保留地址的代理、沙箱或企业网络策略冲突。未来 Adapter 必须把这类结果映射为“环境/网络校验失败”，绝不能误报为客户网站的 GEO score 为 0。

### 运行验证后的建议

仍建议以 **Python library 直接调用** 作为候选首选方案：安装、导入、公开入口和返回对象已在 Windows 上得到实际验证；当前障碍发生在库应当执行的安全边界，而不是进程调用或 JSON 解析边界。

但这一建议附带两个前置条件：

1. 在 DNS 返回真实公网 IP 的受控网络环境中，使用 Python 3.12（优先）或经确认可用的 Python 3.14，完成两个公共网站的成功 audit 验证。
2. 正式 Adapter 将 `result.error`、HTTP 状态和网络/SSRF 拒绝建模为失败状态，不把默认 `score=0` 持久化为有效业务诊断。

## Evaluation Template

### Component

- 名称：
- 仓库或官网：
- 评估日期：
- 评估人：

### 功能

### API

### 输入

### 输出

### 技术栈

### License

### 部署方式

### 活跃度

### 与其他组件功能重叠

### 是否值得接入 MVP

- 结论：
- 依据：
- 接入前置条件或风险：
