# 第三方 AI API 聚合平台技术与商业可行性调研

核查日期：2026-09-19

## 1. 调研范围与口径

本调研服务于 `foreign-trade-geo-agent` 的 AI visibility / citation 监测能力。结论仅基于核查日期时可访问的公开资料；没有注册账号、充值、创建 API Key 或发送付费请求。平台、模型、地区、价格和服务条款可能随时变化，正式采购前必须复核。

本文严格区分三种能力：

- **A：普通 LLM API**：模型只根据输入和自身参数生成文本，没有联网检索证据。
- **B：第三方搜索增强**：平台或其搜索供应商先检索网页，再把结果交给模型生成回答。
- **C：上游原生搜索**：聚合平台把搜索工具请求交给模型提供商自身的联网搜索能力。

调用 GPT、Claude 或 Gemini 的普通 API 不等于获得 ChatGPT、Claude 或 Gemini 网页产品的搜索结果。即使是 C，也只能称为对应 API 的原生搜索结果，不能声称复现消费级网页产品的排序、个性化或 UI 行为。

### 结论摘要

1. **OpenRouter 是最值得做跨模型联网搜索 PoC 的候选**。它有统一 API、明确的 Web Search server tool、结构化 `url_citation`、多搜索引擎，并能在部分模型上使用上游原生搜索。不过，大陆主体能否使用每个具体闭源模型受上游 Model Terms 和地区限制约束；Alipay 只是支付渠道，不能证明所有模型在中国大陆均可合法使用。
2. **阿里云百炼是国内可支付、主体和合同链路清晰的首选备选**。它支持多种模型和平台搜索增强，但这不是 ChatGPT/Claude 网页产品搜索。DashScope 能确认是否发生搜索、返回带 index 的 URL/title，并可在最终回答中启用 `[ref_N]` 角标，因此具备保守映射 citation 的官方机制；真实英文 B2B 查询的稳定性仍需 PoC 验证。
3. **火山方舟同样适合国内采购和搜索增强 PoC**，但当前公开资料对 API 中“最终引用”与“搜索候选”的严格对应关系不如 OpenRouter 清楚。
4. **SiliconFlow 适合普通多模型推理，不适合作为本阶段搜索型 visibility 数据源**：未找到其通用 Chat API 原生返回联网搜索及 citations 的官方证据。
5. **302.AI 技术接口覆盖较广，但暂不建议作为生产依赖**：公开 API 文档能证明 Tavily、通用搜索和 Perplexity Sonar 等能力；运营主体、国内支付方式、数据处理链路和现行法律文本的公开证据不足。

## 2. 平台对比表

| 平台 | 运营主体 | 大陆使用/支付 | 多模型 | 联网类型 | Citation / 来源 | 成本控制 | 当前判断 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [OpenRouter](https://openrouter.ai/) | OpenRouter, Inc.（美国纽约；见[服务条款](https://openrouter.ai/terms)） | 官方支持 Alipay，余额以 USD credits 计；大陆注册、企业发票与每个闭源模型的地区资格需人工确认 | 是，统一 API 接入大量模型 | A、B、C；`auto` 可在原生搜索和 Exa 之间切换 | `url_citation` annotation 提供答案引用来源；title 是否在所有 engine 下稳定返回需 PoC 验证 | 模型费 + 搜索费；支持 API key/组织预算上限 | **优先 PoC，有条件推荐** |
| [阿里云百炼 Model Studio](https://www.aliyun.com/product/bailian) | 阿里云计算有限公司（支付文档所示收款/结算主体） | 明确支持支付宝、银联、个人/企业网银、对公汇款；人民币账户体系 | 是，Qwen 及多家国内模型 | A、B；未发现其可代表 OpenAI/Anthropic 上游原生搜索的证据 | DashScope 可返回 URL/title/index，并用 `[ref_N]` 标注答案引用 | 按模型 token/调用计费；账户及云平台预算能力较成熟 | **国内备选，推荐 PoC** |
| [火山方舟](https://www.volcengine.com/product/ark) | 北京火山引擎科技有限公司（见[产品和服务协议](https://www.volcengine.com/docs/6256/68938)） | 支持支付宝、微信、个人/企业网银、对公汇款；支持大陆企业实名认证 | 是，以豆包及平台模型为主 | A、B；平台 Web Search / 联网内容插件 | 官方说明可展示联网资源 URL；API 中 URL/title 与最终答案的严格引用关系需验证 | 模型费用 + 搜索资源次数；可查账单，旧版价格文档需重新确认 | **第二国内备选，有条件推荐** |
| [SiliconFlow](https://siliconflow.cn/) | 北京硅基流动科技股份有限公司（见[充值协议](https://api-docs.siliconflow.cn/docs/legals/recharge-policy)） | 支付宝、微信、对公转账；实名和发票链路明确 | 是，以开放模型和国内模型为主 | 已确认 A；通用 API 的 B/C 未确认 | 未找到通用 Chat API 返回联网 citations 的官方证据 | 人民币按量计费，分级限流，可自动充值 | **不满足本轮搜索型需求** |
| [302.AI](https://302.ai/) | **未确认**；公开条款只以“302.AI”自称，未清楚列示法定主体 | 中文站点不等于大陆可采购；人民币、支付宝/微信、发票和企业合同条件 **未确认** | 是 | A、B；Perplexity Sonar 转发可能接近上游搜索，但链路身份未充分确认 | Perplexity 接口示例含 `citations` 与 `search_results`；通用搜索返回 URL/title | 有价格查询 API 和 PTC 计价；PTC 结算与法币关系需确认 | **仅保留调研，不建议当前生产 PoC** |

> 表中的“未确认”不是负面断言，而是公开证据不足。尤其不能用中文页面、模型名称或接口兼容性来推断运营主体、支付资格或上游原生搜索。

## 3. 各平台审计

### 3.1 OpenRouter

#### 身份、API 与商业使用

OpenRouter 的服务条款将其定义为 LLM aggregator，运营主体为 OpenRouter, Inc.。条款允许组织和商业用户使用服务并把模型能力集成到自己的产品，但要求用户同时遵守每个上游模型的 Model Terms。条款还明确：部分模型会对特定地区或实体限制访问，用户不得通过 VPN、代理等方式规避限制。因此，**OpenRouter 可注册或可付款不代表 GPT/Claude/Gemini 等每个模型都可由中国大陆主体使用**。[OpenRouter Terms](https://openrouter.ai/terms)

API 为 OpenAI-compatible HTTP 接口，使用 Bearer API key；快速入门给出的主路径为 `POST /api/v1/chat/completions`。[Quickstart](https://openrouter.ai/docs/quickstart)

#### 联网搜索分类

当前推荐接口是：

```json
{
  "model": "<model slug>",
  "messages": [{"role": "user", "content": "<prompt>"}],
  "tools": [
    {
      "type": "openrouter:web_search",
      "parameters": {"engine": "<engine>"}
    }
  ]
}
```

官方文档说明：

- `engine="auto"`：支持原生搜索的模型走上游原生搜索，否则回退 Exa。
- `engine="native"`：优先上游原生搜索；模型不支持时仍可能回退 Exa。
- `exa`、`parallel`、`perplexity`、Firecrawl BYOK：由 OpenRouter/第三方搜索服务增强模型，属于 B。
- 官方列出的原生搜索提供商包括部分 OpenAI、Anthropic、Google、xAI 和 Perplexity 模型，属于 C。

因此不能仅凭 `web_search` 判断 B 或 C；必须保存请求时选择的 engine、实际模型、实际路由 provider，并验证是否发生 fallback。官方还将该 server tool 标记为 Beta，API 和行为可能变化。[Web Search 文档](https://openrouter.ai/docs/guides/features/server-tools/web-search)

#### Citation、价格与额度

搜索来源通过消息中的 `url_citation` annotations 返回；官方文档确认搜索结果包含 URL、title 和内容摘录，并明确 Exa 摘录会以 `url_citation` 暴露给 API 调用方。不同 engine 下 title 的稳定位置仍应通过 PoC 样本验证，再映射为当前项目的 `Citation(url, title)`。搜索用量在 `usage.server_tool_use.web_search_requests` 中计数。核查时，Exa 按模式为每次 USD 0.007–0.015，Parallel 为每千次 USD 1 或 5，Perplexity Search 为每次 USD 0.005；原生搜索按上游提供商价格透传，均需另付模型 token 成本。价格应在 PoC 前再次确认。[Web Search 文档](https://openrouter.ai/docs/guides/features/server-tools/web-search)

OpenRouter 可为 API key 设置 USD spending limit，也支持日/周/月预算、模型/provider allowlist 和 ZDR guardrail，适合限制 PoC 成本。[API Key 限额](https://openrouter.ai/docs/api/api-reference/api-keys/create-keys)、[Guardrails](https://openrouter.ai/docs/guides/features/guardrails/overview)

官方支持页面列出主流银行卡、Alipay 和 USDC；余额以 USD credits 管理。没有找到微信支付、人民币计价、中国增值税发票或大陆企业合同的明确说明，这些必须人工询问。[Billing & Support](https://openrouter.ai/support)

#### 数据处理风险

输入会转发给实际模型提供商；不同 provider 的留存、训练和地域政策不同。OpenRouter 的隐私政策明确提示，provider 可能保存或用输入/输出改进模型。默认路由还可能改变实际 provider，因此商业监测应锁定 provider，启用合适的 ZDR/隐私设置，并保存实际路由元数据。[Privacy Policy](https://openrouter.ai/privacy/)、[Provider 数据政策表](https://openrouter.ai/providers/)

#### GEO 适用性

技术适配度最高，但必须先通过地区资格、付款、发票/税务和模型条款核验。适合测试“同一 prompt 在多个模型 API 原生搜索中的 mention/citation”，不应宣称复现 ChatGPT/Claude 网页产品。

### 3.2 阿里云百炼 Model Studio

#### 身份、支付与 API

阿里云账户支持支付宝、银联在线、个人/企业网银和对公汇款；支付方式以充值页面实际展示为准。企业采购、合同和发票路径比境外聚合商清楚。[阿里云充值文档](https://help.aliyun.com/zh/user-center/use-alipay-online-banking-to-recharge-online)

百炼提供正式 API、Bearer API key、OpenAI-compatible 和 DashScope 调用方式，并可通过模型列表接口查看 workspace 可用模型。模型目录包括 Qwen 及多家国内模型，但这不等于聚合了 ChatGPT/Claude 网页产品。[模型列表 API](https://help.aliyun.com/zh/model-studio/list-models)

#### 联网搜索分类与 Citation

百炼的联网能力是平台搜索增强（B）：Chat Completions 使用 `enable_search: true`，Responses API 使用 `tools=[{"type":"web_search"}]`；可通过 `forced_search: true` 强制搜索。官方没有证明这等同于 OpenAI 或 Anthropic 自身的原生搜索。

DashScope 响应在实际执行搜索时包含 `search_info` 和 `usage.plugins`，其中搜索结果包含 `index`、URL 和 title。它还支持 `enable_source=true`、`enable_citation=true` 和可配置的 `[ref_<number>]` 角标，最终回答中的 `[ref_N]` 可以关联 `search_results.index=N`。因此 Adapter 可以沿用当前 Perplexity Provider 的保守策略：只把最终回答实际引用的 index 映射成 `Citation`，不把全部搜索候选算作 citation。OpenAI-compatible Chat Completions 当前不能返回搜索来源或角标，也无法从响应明确判断是否执行搜索；这对可审计监测不够可靠。因此 PoC 应优先使用 DashScope。[百炼联网搜索](https://help.aliyun.com/zh/model-studio/web-search)

#### 数据与商业风险

百炼是面向企业和开发者提供的商业云服务，可在适用协议下集成到业务，但模型许可、生成内容责任和第三方模型条款仍由使用方逐项确认。协议索引明确写明 API 调用的 input/output 不用于模型训练或优化；统一保留期限和第三方模型的数据处理地点未从该索引确认。[百炼服务协议索引](https://docs.agent.bailian.aliyun.com/en/resources/agreements)

它适合国内客户 PoC 和平台搜索 visibility，但指标必须命名为“百炼搜索增强模型 visibility”，不能替代目标海外 AI 产品的 visibility。

### 3.3 火山方舟

#### 身份、支付与 API

通用协议的运营主体为北京火山引擎科技有限公司。平台支持大陆企业实名认证；在线充值支持支付宝、微信、个人/企业网银，也支持对公汇款。[产品和服务协议](https://www.volcengine.com/docs/6256/68938)、[充值 FAQ](https://www.volcengine.com/docs/6269/1412604)、[企业实名认证](https://www.volcengine.com/docs/6261/940503)

方舟提供模型 API/Responses API 和 API key。其模型范围以豆包及平台当前目录为准，不应把“业界主流模型”宣传语理解为可调用所有海外闭源模型。

#### 联网搜索分类与 Citation

方舟 Responses API 提供内置 Web Search，官方说明由平台获取实时公开网络信息，属于 B。联网内容插件支持公开域网页等数据源，公开文档称默认展示联网资源 URL。[Responses API 工具调用](https://www.volcengine.com/docs/82379/1958524)、[联网内容插件](https://www.volcengine.com/docs/82379/1359519)

但现有公开证据不足以确认 API 是否稳定返回“最终答案明确引用”的 URL/title annotation，还是仅返回被检索到的资源列表。这个差异必须在 PoC 中用真实响应验证；不能把所有资源卡片或搜索候选直接记为 citation。

联网插件的公开升级文档曾列出每月 2 万次公开网页搜索免费、超出后 4 元/千次，另计模型 token；该页面更新时间较早，采购前必须以当前控制台和最新计费页为准。[联网内容插件升级与计费说明](https://www.volcengine.com/docs/82379/1359519)

#### 数据与商业风险

火山引擎通用协议允许客户订购并在自己的产品中使用其技术服务，且有完整企业账单、合同和发票路径，适合国内商业采购；具体模型和输出仍受方舟专用条款及模型规则约束。输入输出留存、训练、内容审核和第三方模型传输也应以这些专用条款为准；本轮没有找到足以统一概括所有模型的数据保留期限，标记为 **未确认**。[产品和服务协议](https://www.volcengine.com/docs/6256/68938)

### 3.4 SiliconFlow

#### 身份、支付与 API

平台运营主体为北京硅基流动科技股份有限公司。充值协议明确支持支付宝和微信；财务说明另列出支付宝自动充值和对公转账。实名认证和发票流程公开，适合中国大陆主体采购。[充值协议](https://api-docs.siliconflow.cn/docs/legals/recharge-policy)、[财务 FAQ](https://api-docs.siliconflow.cn/docs/userguide/faqs/misc_finance)、[发票 FAQ](https://api-docs.siliconflow.cn/docs/userguide/faqs/invoice)

SiliconFlow 提供 Bearer API key 和按量计费的多模型推理，模型及限流随用量级别变化。[Rate Limits](https://api-docs.siliconflow.cn/docs/userguide/faqs/rate-limit-and-upgradation)

平台条款把服务描述为通过网页或 API 向开发者提供通用内容生成服务，未发现禁止一般商业集成的条款；但用户仍需对交互数据、生成内容、具体模型许可和对外服务合规负责，不能理解为平台对所有模型授予统一的无限商业许可。[平台使用协议](https://api-docs.siliconflow.cn/docs/legals/terms-of-service)

#### 联网搜索结论

本轮未在 SiliconFlow 通用 Chat API 官方文档中找到强制联网搜索、搜索引擎选择、结构化 URL/title citations 或上游原生搜索的证据。外部应用把 SiliconFlow 模型与 Tavily/Firecrawl 等组合，属于应用自身的 B，不能归因于 SiliconFlow API。

因此当前只能确认 A。它可作为未来的普通文本 Provider，但不能单独满足搜索型 visibility/citation 需求。

#### 数据处理风险

当前隐私资料显示平台收集模型名称、token、请求时间和状态码等调用日志；为内容安全与风控，还会处理 prompt 和输出内容。公开材料没有给出统一、明确的 prompt/output 保留期限，因此标记为 **未确认**。接入前应询问企业合同、保留期限、是否用于训练及删除机制。[隐私政策](https://api-docs.siliconflow.cn/docs/legals/privacy-policy)、[个人信息收集清单](https://api-docs.siliconflow.cn/docs/legals/personal-information-collection-list)

### 3.5 302.AI

#### 已确认能力

302.AI 有公开 Bearer API 文档和统一 Chat Completions 路径，能调用多种模型。它还提供：

- Tavily 搜索代理，返回 title、URL 和内容，属于 B。[Tavily Search](https://doc.302.ai/159738841e0)
- 通用搜索接口，可选择 Tavily、Exa、Perplexity、Search1 等搜索供应商，属于 B。[General Search](https://doc.302.ai/292859834e0)
- Perplexity Sonar 接口示例，响应包含 `citations` URL 列表以及带 title/URL/snippet 的 `search_results`。[Perplexity Search](https://doc.302.ai/ru/212459640e0)
- 价格查询 API，可按 endpoint 查询模型价格。[Price API](https://doc.302.ai/294868996e0)

Perplexity Sonar 路径很可能是上游搜索模型转发，但当前公开材料不足以确认上游账号主体、是否完整透传原生响应、路由是否会变更以及服务级承诺。因此本调研不把它确定为 C。

#### 商业与合规风险

公开使用条款允许付费使用平台，但其商业许可边界主要是通用表述，且条款和隐私政策文本较旧，未清楚列出法定运营主体、注册地址或适用的中国企业合同/发票安排；隐私政策还写明数据可能跨司法辖区处理。人民币、支付宝、微信、国内银行卡、发票、企业合同、退款和数据保留期限均未从可靠官方材料确认。[使用条款](https://price.302.ai/terms/)、[隐私政策](https://price.302.ai/en/privacy/)

在运营主体、付款、合同、数据处理和上游授权链条得到书面确认前，不建议把它用于客户数据或生产监测。

## 4. 与现有架构的关系

现有链路：

```text
VisibilityProvider
    -> ProviderResponse
    -> VisibilityMonitor
    -> VisibilityReport
```

### 4.1 最小 PoC 是否需要修改 core

**不需要。** 新增一个 Aggregator Adapter 即可完成最小 PoC：

- `ProviderResponse.provider` 保存聚合平台名，例如 `openrouter` 或 `aliyun-bailian`。
- `ProviderResponse.model` 优先保存响应中实际返回的 model；若平台只返回请求模型，则保存请求模型并明确其限制。
- `ProviderResponse.text` 保存最终回答。
- `ProviderResponse.citations` 只保存能够证明被答案引用的 URL/title；仅作为检索候选出现的结果不应伪装为 citation。
- 失败继续映射为 `FAILED`，不计入 mention rate 分母。

### 4.2 生产级可复现性是否需要扩展 core

**需要，但本轮不修改。** 当前 core 只能保存一个 `provider` 和一个 `model`，无法同时、无歧义地表达：

- 聚合平台；
- 实际上游 inference provider；
- 请求模型与实际解析模型；
- 搜索分类 A/B/C；
- 实际 search engine；
- 是否发生 fallback；
- citation 是答案引用还是检索候选；
- 请求配置/profile 的版本。

在进入历史趋势和商业报表前，应设计一个最小、provider-independent 的 provenance 结构，候选字段包括：

```text
aggregator
requested_model
resolved_model
upstream_provider
search_mode = NONE | PLATFORM_AUGMENTED | UPSTREAM_NATIVE
search_engine
search_performed
configuration_version
```

这应是独立的后续设计任务，不能把 OpenRouter、百炼或火山方舟的原始响应对象泄漏进 core。

### 4.3 Citation 的现有边界

现有 `Citation(url, title)` 足以承接 OpenRouter 的明确 `url_citation`，也能承接 Perplexity/其他平台明确标注的引用。它不适合保存 snippet、搜索排名、发布日期或“仅检索未引用”的 source。MVP 可以保守丢弃这些信息；若未来需要 citation quality、domain share 或 source ranking，应另建检索证据模型，而不是扩大 `Citation` 的语义。

## 5. GEO 监测适用性

### 5.1 可测量的指标

- OpenRouter + 上游原生搜索：可作为特定模型 API 原生搜索的 mention/citation 观测。
- OpenRouter + Exa/Parallel/Perplexity engine：是“指定模型 + OpenRouter 搜索增强”的观测。
- 百炼/火山方舟：是国内平台搜索增强模型的观测。
- SiliconFlow 普通 Chat：只是模型 recall/mention，不是实时搜索 visibility。
- 302.AI：只有在上游链路和引用语义确认后，才能决定指标命名。

不同类别的数据不能混合成一个不带来源说明的“GEO score”。历史趋势必须固定平台、模型、搜索模式、搜索引擎、prompt、地区和时间窗口，否则指标不可比。

### 5.2 不能宣称的内容

- 不能把 OpenRouter 的 GPT/Claude API 结果称为 ChatGPT/Claude 网页产品排名。
- 不能把平台搜索候选 URL 全部称为模型 citation。
- 不能把一次 prompt 的 mention rate 称为企业整体 GEO 得分。
- 不能横向比较 A、B、C 后得出单一、无条件的 share of voice。

## 6. 商业化风险

1. **地区与上游条款**：聚合平台不能消除模型提供商的地域限制。尤其 OpenRouter 条款明确禁止规避 Restricted Models。
2. **供应链变化**：动态模型别名、自动路由、搜索 fallback 和 Beta API 会改变历史指标含义。
3. **Citation 语义漂移**：有的平台返回“检索到的来源”，有的返回“答案明确引用”，两者不可混算。
4. **数据跨境与多方处理**：聚合平台、模型 provider、搜索 provider 可能分别处理 prompt、客户品牌和竞争对手信息。
5. **知识产权与商业许可**：平台条款之外还要遵守模型条款、搜索服务条款和输出使用限制。
6. **财务合规**：Alipay 可支付不等于人民币合同、合规发票或可抵扣税务凭证。
7. **可用性与下线**：模型、provider、价格和搜索工具可能无通知或短通知变更；Adapter 和历史数据必须记录版本。
8. **内容合规**：国内平台会执行实名和内容安全审查；海外平台也可能把请求转给不同司法辖区的服务商。

## 7. 最小 PoC 方案

### 推荐顺序

#### Gate 0：先人工确认，不充值

向 OpenRouter 官方支持确认并保留书面回复：

1. 中国大陆注册企业能否按当前条款使用目标模型及其 native web search；
2. Alipay 是否可由同一企业主体付款；
3. 是否提供企业发票、收据、合同或税务文件；
4. 目标模型的实际 provider、地区限制、ZDR 和数据保留；
5. `engine="native"` 在不支持时如何禁止回退，而不是静默转成 Exa；
6. 如何从响应或 usage 确认实际 search engine 和 routed provider。

任一关键问题无法得到满意答案，就不做 OpenRouter 付费 PoC，转向百炼。

#### Gate 1：OpenRouter 技术 PoC（条件通过后）

- 新建独立、低额度 API key，设置 USD 5 以内硬上限。
- 固定 1 个明确支持 native web search 的模型，不使用动态别名。
- 使用 3 个固定 B2B prompt，每个只请求一次，不重试。
- 显式请求 native search，并确保不能无提示 fallback。
- 保存 requested/resolved model、routed provider、search engine、search request count、answer、明确 citations、耗时和成本。
- 不上传客户机密，只用公开品牌（可继续使用 Flowserve）。

这一步的目标不是评估排名优劣，而是验证：大陆企业账户、付款、调用、原生搜索、引用解析和成本控制能否形成完整证据链。

#### Gate 2：阿里云百炼对照 PoC

- 使用同样 3 个 prompt 和一个固定 Qwen 模型。
- 使用 DashScope，设置 forced search，并启用 source 与 citation 角标。
- 验证英文 B2B prompt 的搜索触发、URL/title、`[ref_N]` 引用映射和跨境网站覆盖。
- 指标明确标为“百炼平台搜索增强”，不与 OpenRouter native search 直接合并。

火山方舟只在百炼的英文检索覆盖或引用结构不满足需求时做第三个 PoC。SiliconFlow 不进入本轮搜索 PoC。302.AI 在商业主体和数据链路确认前不进入付费 PoC。

## 8. 尚需人工确认的事项

### OpenRouter

- 大陆企业账户和目标模型的地区资格；禁止只测试“能否调用”而忽略上游条款。
- Alipay 实际付款、最小充值、退款、企业账单/发票/合同。
- native search 无回退配置及响应中的真实 engine/provider 证据。
- 目标 provider 的 ZDR、保留期限、训练政策和跨境处理地点。
- 搜索工具 Beta 状态下的版本变更通知与 SLA。

### 阿里云百炼

- 目标英文 prompt 能否稳定执行 forced search。
- 英文 B2B prompt 下 `[ref_N]` 与 `search_info.search_results.index` 是否稳定对应。
- 目标模型、搜索策略、区域和实时价格。
- 第三方模型是否把输入传到其他处理方，以及各模型专用条款。

### 火山方舟

- 当前 Responses API Web Search 的真实响应 schema。
- 是否返回答案级 citation annotation、URL 和 title。
- 最新搜索计费、免费额度、限流和英文网页覆盖。
- 输入输出留存、训练、审核和删除政策。

### SiliconFlow

- 是否存在尚未公开或企业专属的联网搜索/citation API。
- prompt/output 的保留期限、训练用途和企业数据处理协议。

### 302.AI

- 法定运营主体、注册地、合同主体和争议适用法律。
- 中国大陆企业注册、实名、人民币/支付宝/微信/银行卡、发票和退款。
- 上游模型与搜索服务的授权链、路由透明度和 SLA。
- prompt/output 的保留、训练、跨境传输、删除和子处理商清单。
- PTC 的法币含义、价格加成及成本上限机制。

## 9. 最终建议

**不应立即把任何聚合商接入生产。** 下一步最合理的动作是先做 OpenRouter 的人工商业资格核验；通过后，用一个固定模型做最多 3 次、带硬预算上限的 native-search PoC。若地区、付款或合同条件不满足，则改做阿里云百炼的搜索增强 PoC。

架构上，最小 PoC 只需新增 Aggregator Adapter，不必修改 core；但在保存历史趋势之前，必须补足 provider/search provenance，否则无法解释一条 observation 究竟来自普通 LLM、第三方搜索增强还是上游原生搜索。
