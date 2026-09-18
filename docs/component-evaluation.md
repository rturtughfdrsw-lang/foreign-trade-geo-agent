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

### Python 3.12 复验（2026-09-18）

已在项目目标环境 Python 3.12 下复验。

- 实际解释器：CPython 3.12.10，64-bit；项目根目录 `.venv` 已由 `py -3.12 -m venv .venv` 重建。
- 安装结果：`geo-optimizer-skill==4.18.1` 及其基础依赖安装成功；`geo_optimizer` 和 `AuditResult` 可正常导入。
- 验证结果：现有 `scripts/verify_geo_optimizer.py` 正常返回 `geo_optimizer.models.results.AuditResult`。`example.com`（0.143 s）和 `www.python.org`（0.002 s）仍因当前 DNS 返回 `198.18.0.x` 而被 SSRF 防护拒绝；`127.0.0.1` 仍被正确拒绝。
- 与 Python 3.14 的差异：未观察到 API、返回对象类型、顶层字段或安全拒绝行为的差异；两者均可安装、导入和运行该 PoC。此次复验不改变“公网成功 audit 尚待正常 DNS 环境验证”的结论。

当前 Windows 开发环境使用 TUN/Fake-IP DNS，因此本机无法完成真实公网站点的成功 audit。这是开发环境限制，不是组件失败；后续真实网络集成测试必须在 DNS 返回真实公网 IP 的 Linux/CI 或云环境中运行。

## Elmo - Phase 1: Project and Deployment Audit

### 审计范围与项目身份

- 审计日期：2026-09-18。
- 官方仓库：[`elmohq/elmo`](https://github.com/elmohq/elmo)。仓库 README 把项目定义为开源、可自托管的 AI visibility 平台，并链接到 `elmohq.com`；官网又链回该 GitHub 组织，可与 AllenNLP 的同名 ELMo 等项目区分。证据：[`README.md`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/README.md)、[Elmo 官网](https://www.elmohq.com/)。
- 本次静态审计固定在 `main` commit [`6bc0224776190213e56c311aa4713e229bdc2522`](https://github.com/elmohq/elmo/commit/6bc0224776190213e56c311aa4713e229bdc2522)（2026-09-16）。当时最新 GitHub Release 为 [`v0.4.1`](https://github.com/elmohq/elmo/releases/tag/v0.4.1)（2026-09-15，tag `2cf9af409d741992aa2da96c3da0eae019113276`），且发布后已有 12 个 main commits，属于近期活跃维护。
- 版本元数据有一处需后续注意的不一致：该 commit 的根 [`package.json`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/package.json) 仍写 `0.2.13`，而 Web/Worker package 与最新 Release 为 `0.4.1`。因此本审计以 commit hash 为准，不把根 package 版本单独视为可靠的部署版本标识。

### License 与商业使用

- 仓库中的真实 [`LICENSE.md`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/LICENSE.md) 是标准 **MIT License**，版权归 Blue Whale Software, LLC。
- MIT 明确允许使用、复制、修改、合并、发布、再许可和销售，因此允许商业使用。如分发 Elmo 软件或其实质部分，需保留版权和许可声明；许可证同时明确不提供保证。
- 将 Elmo 作为独立服务部署，再由我们的系统通过 API 调用，**从 Elmo 本身的 MIT License 看没有明显的商业集成风险**，且没有 copyleft 或网络服务开源条款。这一结论不覆盖各 LLM、抓取商和数据供应商的条款，那些需独立评估。

### 技术栈与运行拓扑

- 项目形态：**多服务平台**，以 pnpm workspace + Turborepo 组织的 TypeScript monorepo，不是轻量库。根 [`package.json`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/package.json) 要求 Node.js 24.x 和 pnpm；[`architecture.mdx`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/docs/content/docs/developer-guide/architecture.mdx) 列出 Web、Worker、CLI 和共享 packages。
- 前端：React 19、TanStack Start/Vite、Tailwind CSS 4、shadcn/ui；Web 应用同时提供仪表盘和 `/api/v1` REST API。证据：[`apps/web/package.json`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/package.json)、[`architecture.mdx`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/docs/content/docs/developer-guide/architecture.mdx)。
- 后端：同一 TypeScript/Node.js 代码库内的 TanStack Start/Nitro Web server，共享业务逻辑、配置、OpenAPI spec 和 Drizzle schema 位于 `packages/*`。证据：[`Dockerfile`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/docker/Dockerfile)、[`AGENTS.md`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/AGENTS.md)。
- 数据库：PostgreSQL（官方配置文档要求 15+，CLI 当前默认生成 `postgres:18-alpine`），通过 Drizzle ORM 管理 schema 和 migration。证据：[`configuration.mdx`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/docs/content/docs/developer-guide/configuration.mdx)、[`compose.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/cli/src/compose.ts)。
- 队列/Worker：独立 `apps/worker` 进程使用 **pg-boss** 执行调度、AI evaluation、citation tracking 和 report 任务；作业队列也存在 PostgreSQL，未见 Redis 或独立消息中间件要求。证据：[`apps/worker/package.json`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/worker/package.json)、[`architecture.mdx`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/docs/content/docs/developer-guide/architecture.mdx)。
- 容器：多阶段 Dockerfile 生成独立 Web、Worker 和 DB migration 镜像；Docker Compose 是官方自托管入口。

### 标准部署方式

1. 全局安装官方 CLI：`npm install -g @elmohq/cli`。
2. 运行 `elmo init`；交互式选择 Docker 内 PostgreSQL 或外部 PostgreSQL，配置 AI/scraping provider，并生成 `~/.elmo/elmo.yaml` 和包含密钥的 `.env`。
3. 运行 `elmo compose up -d`。默认 Compose 服务为 `postgres`、一次性 `db-migrate`、`web` 和 `worker`；选择外部数据库时省略前两个本地数据库相关服务，但 Web 和 Worker 仍会运行。

证据：[`README.md`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/README.md)、[`apps/cli/README.md`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/cli/README.md)、[`init.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/cli/src/commands/init.ts)、[`compose.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/cli/src/compose.ts)。

仓库没有静态 `docker-compose.yml`/`compose.yml` 或 `.env.example`；这些配置是 CLI 生成物。核心环境项包括 `DATABASE_URL`、`DEPLOYMENT_MODE`、`BETTER_AUTH_SECRET`、`ELMO_ENCRYPTION_KEY`、`APP_URL`/`VITE_APP_URL`、至少一组 AI/scraping provider 凭据和 `SCRAPE_TARGETS`；遥测可以通过 `DISABLE_TELEMETRY=1` 关闭。证据：[`config.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/cli/src/config.ts)、[`configuration.mdx`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/docs/content/docs/developer-guide/configuration.mdx)。

### 是否必须部署整套 Elmo

**对官方支持的自托管路径，结论是“实质上是”。** Web 服务提供 REST API，Worker 执行定时 prompt/AI evaluation，PostgreSQL 同时保存数据和 pg-boss 作业队列；只取 AI visibility 数据也依赖这三部分。可以用外部 PostgreSQL，但官方文档和 CLI 未提供独立的“visibility-only”、headless worker 或轻量数据库方案。自行拆分非官方拓扑是否可靠，本阶段**未确认**。如使用 Elmo Cloud 的托管 API，则不需我们自己部署这套基础设施，但 Cloud/API 条款和稳定性不在本阶段范围内。

### 阶段判断

- 部署复杂度：**中等偏高**。官方 CLI 降低了 Compose 配置门槛，但运行时仍需 Docker Compose、Web、Worker、PostgreSQL、migration、密钥管理、至少一个外部 AI/scraping provider，并需承担 provider 调用成本。
- 独立服务集成适配度：**形态上明显适合**。它本来就是可自托管的独立平台，Web 应用提供 REST API，与我们的 Python 主项目可通过进程/部署边界隔离。但 API 认证、实际数据 contract、版本稳定性和所需 provider 组合尚未审计，因此本阶段不作最终 MVP 接入结论。
- 当前最大风险：Elmo 不是一个可直接嵌入 Python 进程的小型数据库，而是带独立数据库、Worker 和外部 provider 凭据/成本的完整平台。我们若只需其中一部分 AI visibility 数据，运维和供应商成本可能超过 MVP 收益；这是下一阶段功能/API 审计需要量化的核心问题。

## Elmo - Phase 2: Function and API Audit

### 审计范围

- 审计日期：2026-09-18。
- 继续以 `main` commit [`6bc0224776190213e56c311aa4713e229bdc2522`](https://github.com/elmohq/elmo/commit/6bc0224776190213e56c311aa4713e229bdc2522) 为固定证据基线。
- 本阶段仅做源码、OpenAPI、数据库 schema 和测试的静态审计；未安装或运行 Elmo，未验证真实 provider 账户、调用费用或生产负载表现。

### 1. 实际功能确认

| 能力 | 状态 | 源码证据与边界 |
| --- | --- | --- |
| Brand 管理 | **已确认** | 数据库包含 brands，REST API 支持创建、查询和更新品牌，并保存名称、域名、别名、启用模型和 cadence。证据：[`schema.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/db/schema.ts)、[`openapi.json`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/api-spec/src/openapi.json)。 |
| Prompt / Query tracking | **已确认** | prompts 保存问题、标签、启停状态和 premium models；prompt runs 还保存 provider 返回的 web queries。创建已启用 prompt 后会建立调度任务。证据：[`prompts-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/prompts-core.ts)、[`process-prompt.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/worker/src/jobs/process-prompt.ts)。 |
| AI visibility | **已确认** | visibility 由指定时间窗内 `brandMentioned / runs` 聚合而成，并提供日序列、按模型拆分和汇总。证据：[`analytics-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/analytics-core.ts)。 |
| Brand mention | **已确认** | 每条模型回答会分析品牌名、别名和裸域名；实现是大小写不敏感的字符串包含判断，不是 LLM 二次判定。证据：[`mentions.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/mentions.ts)、[`process-prompt.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/worker/src/jobs/process-prompt.ts)。 |
| Citation | **已确认** | 各 provider adapter 从结构化 citation/annotation/source 字段抽取 URL，去重后保存 URL、domain、title 和位置；不会把仅提供给模型、但模型未引用的搜索结果算作 citation。证据：[`text-extraction.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/text-extraction.ts)、[`schema.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/db/schema.ts)。 |
| Competitor comparison | **已确认** | competitors 保存名称、域名和别名；每次 run 按与品牌相同的规则记录命中的竞争对手，analytics 再计算排行和趋势。证据：[`mentions.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/mentions.ts)、[`analytics-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/analytics-core.ts)。 |
| Share of voice | **已确认** | SOV 以品牌和竞争对手在 runs 中的 mention 次数为基础，输出 leaderboard、品牌占比和时间序列。它是 mention share，不等同于搜索流量份额。证据：[`analytics-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/analytics-core.ts)、[`visibility-stats.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/lib/visibility-stats.ts)。 |
| Historical trend | **已确认** | prompt runs 和 citations 都持久化 `createdAt`；API 接受时间窗并计算日序列、前期对比和 citation 变化。历史 metric/snapshot 主要是读取时聚合，不是独立 snapshot 表。证据：[`schema.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/db/schema.ts)、[`analytics-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/analytics-core.ts)。 |
| Opportunities / recommendations | **已确认，但 API 为 experimental** | 源码先构造 7/30 天 visibility、平台、prompt/competitor 和 citation landscape 的确定性 digest，再进行一次结构化 LLM completion，保存 append-only 报告；schema 失败最多重试三次并可回退到上次成功报告。证据：[`opportunities.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/opportunities.ts)、[`openapi.json`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/api-spec/src/openapi.json)。 |

### 2. AI visibility 数据产生流程

真实监控链路如下：

`Enabled Prompt -> pg-boss scheduler -> model/provider target fan-out -> provider response -> text/citation normalization -> deterministic mention analysis -> prompt_runs/citations -> read-time analytics`

1. 已启用的 prompt 在创建时调用 `createPromptJobScheduler`；Worker 取出 prompt、brand 和 competitors，并按 `SCRAPE_TARGETS` 与品牌启用模型解析运行计划。证据：[`prompts-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/prompts-core.ts)、[`process-prompt.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/worker/src/jobs/process-prompt.ts)。
2. 每个 target 调用统一的 provider `run(model, prompt, { webSearch, version })`，得到正文、原始响应、搜索 query、citations 和 model version。Provider contract 同时支持抓取消费者页面的 `scraped` 模式和直接模型 API 的 `api` 模式。证据：[`providers/types.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/providers/types.ts)。
3. 当前 registry 包含 Olostep、Bright Data、Oxylabs、Cloro、DataForSEO，以及 OpenAI、Anthropic、Mistral、OpenRouter 的直接 API adapter；model catalog 包含 ChatGPT、Claude、Google AI Mode/Overview、Gemini、Copilot、Perplexity、Grok、Mistral、DeepSeek、Kimi、Qwen。具体可运行组合由 `SCRAPE_TARGETS` 和已配置凭据决定，不代表每个模型都能由每个 provider 获取。证据：[`providers/index.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/providers/index.ts)、[`models.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/config/src/models.ts)、[`scrape-targets.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/config/src/scrape-targets.ts)。
4. 自托管用户必须提供所选 AI 或 scraping provider 的 API Key；未发现 Elmo 为自托管实例代付或内置通用 provider 凭据。消费者表面监测通常依赖 scraping provider，直接 API 模式则使用相应模型厂商凭据。证据：[`configuration.mdx`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/docs/content/docs/developer-guide/configuration.mdx)、[`providers/index.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/providers/index.ts)。
5. Brand/competitor mention 使用品牌名、别名和裸域名做大小写不敏感子串匹配；citation 使用各 provider 返回的结构化来源字段归一化。常规 monitoring 的这两步不追加 LLM 分析调用。证据：[`mentions.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/mentions.ts)、[`text-extraction.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/text-extraction.ts)。
6. 每个成功 run 保存原始回答、模型/provider、web search 状态、queries、品牌/竞品 mentions 和 citations。Visibility、SOV、citation share 与历史序列之后从这些事实表聚合；没有独立的 response、mention、metric 或 snapshot 表。证据：[`schema.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/db/schema.ts)、[`analytics-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/analytics-core.ts)。

### 3. 调用量与成本结构

Self-hosted 的常规请求量近似为：

`启用 prompts × 选定 targets（model + provider + web-search）× 每日 firing 次数 × RUNS_PER_PROMPT`

- 默认 cadence 是 24 小时，默认 `RUNS_PER_PROMPT=5`；可通过品牌 cadence、启用模型、prompt 启停、`SCRAPE_TARGETS` 和 replication 调整。premium target 的 replication 固定为 1。证据：[`constants.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/constants.ts)、[`policy.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/run-policy/policy.ts)。
- Worker 对一个 prompt 的 target/replication 组合用 `Promise.allSettled` 并发执行，本地 `process-prompt` worker concurrency 为 10。作业本身 `retryLimit=0`，避免整组 fan-out 失败后整组自动重付；但 provider adapter 自身可对瞬时错误重试或轮询，实际 HTTP/provider 请求数可能高于逻辑 run 数。证据：[`process-prompt.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/worker/src/jobs/process-prompt.ts)、[`handlers.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/worker/src/handlers.ts)、[`scrape-shared.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/providers/registry/scrape-shared.ts)。
- 全部 targets 失败时，下一次 cycle 会按 0.25、0.5、1、2、4、8 小时退避后再回归正常 cadence；因此故障期可能产生额外尝试。部分失败不会让整个 prompt job 失败。证据：[`run-backoff.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/run-backoff.ts)、[`process-prompt.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/worker/src/jobs/process-prompt.ts)。
- 常规 mention、citation 和 analytics 不额外调用分析 LLM；opportunities 是单独的一次结构化 LLM completion，schema 不合格时最多三次尝试，并有约六天 freshness cache。证据：[`opportunities.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/opportunities.ts)。
- 仓库的 provider 单次成本数字被源码明确标注为粗略 placeholder，不是账单或实时价格，不能据此给客户报价。成本必须以实际 provider 合同和选定 target 实测。证据：[`cost.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/usage/cost.ts)。

### 4. REST API

OpenAPI 版本为 `1.1.0`，base path 为 `/api/v1`。所有请求使用 `Authorization: Bearer <token>`；可用实例级 `ADMIN_API_KEYS` 或 dashboard 签发的 `elmo_...` organization key。Organization key 有 read/read-write scope、组织与可选品牌限制，并受限流和 plan 限制。除标记 `x-stability: experimental` 的 operation 外，官方 spec 承诺响应 shape 只增加字段；因此这些不是单纯偶然的前端私有 route，而是有外部 contract 的 API。证据：[`openapi.json`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/api-spec/src/openapi.json)、[`api-auth.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/lib/auth/api-auth.ts)、[`v1-route-conformance.test.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/lib/api/__tests__/v1-route-conformance.test.ts)。

| 能力 | 方法与路径 | 主要输入 / 输出 | 稳定性 |
| --- | --- | --- | --- |
| Brand | `GET/POST /brands`；`GET/PATCH /brands/{brandId}` | 创建输入含 id/name/domains，可带 aliases、competitors、prompts；输出品牌、域名、别名、启停、模型和 cadence | 稳定 |
| Prompt | `GET/POST /prompts`；`GET/PATCH /prompts/{promptId}` | 创建输入 brandId/value/tags；PATCH 可修改 value/enabled/tags/premiumModels。启用后由 scheduler 执行 | 稳定 |
| Run / response | `GET /prompts/{promptId}/runs`；`GET /prompts/{promptId}/runs/{runId}` | 列表返回 model/provider、mention、queries、citationCount 等摘要；单条另含 answer text 和 citation 列表 | 稳定 |
| Visibility / SOV | `GET /brands/{brandId}/analytics?start=&end=` | visibility 时序、SOV、按模型 visibility、run/prompt/citation totals | 稳定 |
| Mention / citation snapshot | `GET /prompts/{promptId}/snapshot` | 给定日期窗的 mention totals/top-K 与 citation totals/top-K | 稳定 |
| Citation | `GET /brands/{brandId}/citations/domains`；`.../citations/urls` | domain/URL 的 count、share、promptCount、前期变化、isNew、category 等 | 稳定 |
| Competitor | `GET/POST /competitors`；`GET/PATCH/DELETE /competitors/{competitorId}` | 名称、域名、别名及品牌归属 | 稳定 |
| Prompt performance / query | `GET /brands/{brandId}/prompt-performance`；`.../query-fanout` | prompt mention rates、运行时间，以及模型产生的 web queries | 稳定 |
| Opportunities | `GET /brands/{brandId}/opportunities` | 最新机会报告及生成状态、summary、机会项和 risks | **experimental** |

重要限制：本次未发现面向外部 API 的 `POST /run-now` 或同步执行单次 monitoring endpoint。外部集成可以创建/启用 prompt，再由 Worker 调度；若我们的 Python 系统要求“立即执行并等待结果”，需自行编排轮询或确认是否接受其异步 cadence，不能假设存在同步触发 API。证据：[`openapi.json`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/api-spec/src/openapi.json)、[`prompts-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/prompts-core.ts)。

### 5. 数据模型与建议的内部边界

数据库事实模型已经确认：

- `brands`：名称、website/additional domains、aliases、enabled models、cadence、organization 和时间戳。
- `prompts`：文本、启停、tags、system tags、premium models 和时间戳。
- `competitors`：brand 归属、名称、domains、aliases 和时间戳。
- `prompt_runs`：prompt/brand、model/provider/version、web-search、raw output、web queries、brand mention、competitor mentions 和时间戳。
- `citations`：run/prompt/brand/model、URL、domain、title、citation index 和时间戳。
- `usage_events`：organization/brand/prompt、event type、provider/model、web-search、units、估算成本和时间戳。
- `brand_opportunities`：append-only 的 report、model 和时间戳。

没有单独的 `response`、`mention`、`metric` 或 `snapshot` 表；回答和 mentions 在 `prompt_runs`，aggregates/snapshots 在读取时计算。证据：[`schema.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/packages/lib/src/db/schema.ts)、[`analytics-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/analytics-core.ts)。

未来若定义我们的 `VisibilityResult`，建议只保留业务稳定字段，而不泄漏 Elmo schema：

- 查询范围：`brand_id`、`window_start`、`window_end`、`measured_at`。
- 覆盖范围：`prompt_count`、`run_count`、`successful_run_count`、`failed_run_count`、实际使用的 model/provider 集合。
- 核心指标：`visibility_rate`、按 model/provider 的 run count、mention count、visibility rate。
- 竞争数据：规范化的 entity、mention count、share of voice；不要保存 Elmo competitor row。
- 引用数据：citation count，以及必要的 domain/URL/count/prompt coverage 摘要；原始 provider citation payload 不进入 core。
- 历史：日粒度 visibility/SOV/citation points，明确区分“无采样”和真实 0。
- 可追溯性：`source`、`source_version`、采样配置摘要和 warning/error；建议额外保存覆盖率，避免只看百分比而忽略 provider 失败。

原始回答若因审计、调试或重新计算需要保存，应进入受控 storage 层并设保留期，不应作为 `VisibilityResult` 的核心字段。

### 6. 与 geo-optimizer 的边界

| 维度 | geo-optimizer-skill | Elmo |
| --- | --- | --- |
| 核心问题 | “这个站点是否具备 GEO/技术可抓取与可引用条件？” | “真实 AI surfaces 在一段时间内是否提及/引用品牌，竞争份额如何变化？” |
| 主要方式 | 对网站执行一次性/批量技术 audit，检查 robots、llms.txt、schema、meta、内容、crawlability、citability 并生成建议 | 定时把 prompts 发送到多个 model/provider，保存回答/queries/citations，聚合 visibility、SOV 和历史趋势 |
| Competitor | 对 URL 分别 audit，按技术分数比较或做 category gap | 在同一批 AI 回答中识别品牌和竞争对手 mentions，计算 SOV 和时间序列 |
| Citation | `citability` 是页面被引用的 readiness heuristic；`geo citations` 可调用 LLM/SERP provider，但依赖 API Key，真实 source URL 覆盖取决于 provider | 在每个 scheduled run 中规范化 provider 的真实 citation fields，并持久化 domain/URL 及历史变化 |
| 历史监测 | 有 audit history/regression，但重点是站点技术状态 | 原生持续 prompt monitoring，并围绕 runs/citations 提供 visibility、SOV、模型拆分和趋势 API |

因此两者只有“竞争分析”“citation”这些名称上的局部重叠，测量对象不同。geo-optimizer 已足够承担 MVP 的网站 readiness audit；其 `citability` 不能替代真实 AI visibility，现有 `geo citations` 也没有证据表明能直接覆盖 Elmo 的多 provider 调度、标准化 citation、SOV 和持续历史聚合。若第一版只需一次、少量 prompts 的品牌/citation 快照，可以复用 geo-optimizer 的 citation 能力做低成本实验；若产品承诺稳定的多模型趋势与竞品 SOV，则不能把它视为 Elmo 的完整替代。证据：本文件的 [geo-optimizer 功能审计](#与-mvp-最相关的功能)、Elmo [`process-prompt.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/worker/src/jobs/process-prompt.ts) 和 [`analytics-core.ts`](https://github.com/elmohq/elmo/blob/6bc0224776190213e56c311aa4713e229bdc2522/apps/web/src/server/analytics-core.ts)。

Elmo 确实提供了“持续历史监测”能力，而且这是相对 geo-optimizer 最明确的增量：调度器持续产生带时间戳的 runs/citations，API 按时间窗返回日序列、前期对比和 SOV。但 metric/snapshot 是读取时计算，且生产可靠性、provider 失败覆盖率和数据质量尚未经过我们的运行验证。

### 7. MVP 路线比较

| 路线 | 开发量 | 运维复杂度 | 调用成本 | 可控性 | 第一个客户 PoC 价值 |
| --- | --- | --- | --- | --- | --- |
| **A. 完整 Elmo 独立服务 + REST API** | 我方业务代码较少，但仍需部署、认证、异步轮询和 Adapter 映射 | **高**：Web + Worker + PostgreSQL + migration + Docker + provider secrets | 默认每 prompt/target 每日重复 5 次，模型/抓取商增多后线性放大；故障重试另计 | 中：provider breadth 和 analytics 成熟，但调度/API/DB 运维受 Elmo 设计约束 | 能快速展示多模型、SOV、citation、历史 dashboard；对单客户早期验证可能过重 |
| **B. 自建轻量 VisibilityMonitor** | **中**：需实现固定 prompt、少量 provider、结果归一化、mention/citation、持久化和简单历史指标 | **低到中**：复用本项目数据库/worker，不引入整个平台 | 最容易限制为少量 prompts × 1–2 providers × 明确频率 | **高**：内部 schema、错误/覆盖率、成本上限和同步/异步流程由我们控制 | 最贴合首客：能证明“是否被提及/引用、与竞品差距、变化”而不承担完整平台成本 |
| **C. 第一版不做 AI visibility** | 最低 | 最低 | 无模型监控成本 | 高，但能力范围最窄 | 可先交付 audit + 内容优化，但无法证明优化是否改变真实 AI visibility，削弱 GEO 产品差异化 |

### 8. 决策结论

**当前不建议接入完整 Elmo，推荐 MVP 路线 B。**

Elmo 最有价值、也最难自行快速复制的部分，是：多种消费者 surface/API provider 的统一适配与 citation 归一化；定时运行、并发、退避和历史事实数据；基于这些数据的 visibility/SOV/citation analytics。它不是只有 UI 的空壳，其能力真实存在。但对第一个客户 PoC，部署完整平台的 Web、Worker、PostgreSQL 和 provider 组合，成本与运维边界明显大于我们当前需要验证的业务假设。

第一个客户 PoC 的最小可行方案应是一个受限的轻量 `VisibilityMonitor`：

1. 由客户确认一小组固定 prompts、品牌 aliases/domains 和 3–5 个竞争对手。
2. 只接 1–2 个能合法返回回答与 citation 的 provider/model；明确版本、web-search 状态和单次成本。
3. 每个 prompt/provider 每个周期只运行 1 次，保存时间戳、回答、citation、成功/失败和 latency。
4. 先用可解释的 deterministic matching 计算品牌/竞品 mention；保存原始事实，以便以后重算。
5. 输出 visibility rate、SOV、citation domains/URLs 和简单日/周历史；指标同时展示成功 runs 与失败/缺失覆盖率。
6. 不在首版复制 Elmo 的全 provider matrix、复杂 dashboard、机会报告或高级 citation volatility。

若 PoC 证明客户愿意为多 surface、更高频率、更完善 provider retry 和成熟 analytics 付费，再进行 Elmo 隔离部署的运行验证，并比较“扩展自研 Monitor”与“Elmo REST Adapter”的总拥有成本。Elmo 可作为后续平台候选和实现参考，但目前不进入项目依赖或部署基线。

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
