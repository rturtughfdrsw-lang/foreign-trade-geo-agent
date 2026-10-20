# 首个真实商业 SEO 场景：验收准备与端到端能力核查

日期：2026-10-10（Asia/Shanghai）。核查对象：当前 `E:/Codex程序/foreign-trade-geo-agent` checkout；只读参考其他已有工作树。**结论：优先准备真实公开 B2B 网站的只读 SEO 审计案例；已提出候选，但抓取规则和用途许可尚未核清，未启动原生抓取。项目以虚拟 NovaCNC 为主，没有已确认的真实客户资料；整篇商业文章验收留待客户补证及合法授权。生产 NO-GO、PostgreSQL BLOCKED 保持。** 本轮没有生成商业文章，没有修改源码、Prompt、Gate、Validator 或 P1。

## 1. 核查依据、范围与工作树差异

已阅读当前仓库 `AGENTS.md`、`README.md`、`docs/architecture.md`，并检查 runtime、CLI/Live composition、各原生 workflow、core contracts、Intake journal、Draft admission、只读 Review 和对应测试。

用户指定的两份文件在当前 checkout **不存在**。通过 `git worktree list` 和本地文件查找，实际只读查阅：

- `C:/Users/31969/.codex/worktrees/explain-offline-diagnosis/foreign-trade-geo-agent/docs/explain-final-offline-quality-2026-10-10/report.md`
- 同目录 `commercial-seo-acceptance-plan.md`、`verification.json` 和已有 P1 失败记录。

没有复制或整合该工作树的实现。对两区 `src/**/*.py` 按换行规范化后比较：94 个共有文件文本相同，8 个共有文件不同；参考区另有 `adapters/explain_draft.py`、`adapters/explain_review.py`、`core/explain_draft.py`、`storage/explain_draft.py`、`workflows/explain_admission.py` 五个当前区没有的模块。因此，后续 RouteDock 的 TEST-only EXPLAIN bridge 和独立执行 journal **不能计为本 checkout 已有生产能力**。字节 hash 与文本比较用途不同，没有把 CRLF/LF 差异称为功能差异。

另外只读查阅 `p1-postgresql-consumption` 工作树的 `docs/explain-content-quality-2026-10-10/report.md`，确认 PostgreSQL 的历史阻断背景；未探测、安装或启动数据库。可机读核查摘要、输入摘要和本轮验证结果见 [verification.json](verification.json)。

本轮的真实 DeepSeek/Tavily 请求、项目 crawler 执行、WordPress 写入、部署及 Git 历史操作均为 0。未读取 `.env` 或导出凭据。按用户补充要求，对候选网站做了少量 Web 检索与人工式页面读取，结果在下一节单列；没有把它记为原生 Crawl／Audit 运行或客户授权。第四节历史库来源的真实性判断仍仅针对本地保留记录。

## 2. 优先选取真实公开网站：只读 SEO 审计案例

### 2.1 选站标准与候选判断

先筛选公开经营网站，核对产品分类、英文内容、供应／询价页面及网站所称运营主体；再确认 exact-origin、robots、使用条款与允许的资料保存／分析用途。不能因为搜索引擎收录、网页能打开或 robots 没写禁止就宣称已获客户授权。本站全部企业／性能宣称都标作 **PUBLIC_WEB_OBSERVATION / 客户未确认**；网站运营主体的法律身份与域名控制关系也不由品牌名自动证明。

**优先预检候选为 COVNA 的 `https://www.covnavalve.com/`，备选为 DONJOY 的 `https://www.donjoyvalve.com/`；两者目前都不是已批准抓取的正式案例。** 选择前者主要因为页面展示的电动／气动阀分类、采购角色与产品选型信息适合作为有界审计对象；这是案例适合度判断，不是对企业资质、产品或合作关系的背书。[COVNA 首页](https://www.covnavalve.com/)、[电动阀分类页](https://www.covnavalve.com/motorized-actuated-valve/)

| 候选 | 产品／页面与 B2B 线索 | 目标市场证据 | 许可与当前结论 |
| --- | --- | --- | --- |
| COVNA / covnavalve.com | 本次 Web 能读到英文首页及电动阀分类，页面面向设备制造商、工程客户和经销商；有型号详情、About、Contact 导航 | 英文及多语言入口支持“跨境英语采购”研究假设；没有证据确认其主销国家、客户分布或某国优先级 | robots 读取失败，不能判为 Allow／Disallow／404；未核得明确的自动抓取及内容再利用许可。**选站候选 READY；原生抓取 BLOCKED／NOT_TESTED** |
| DONJOY / donjoyvalve.com | 首页展示卫生阀／泵、行业应用和技术资料导航，可研究产品与应用信息结构 | 英文与多语言入口、全球服务宣称仅是网站观察；具体市场未确认 | robots 同样未取得；版权页要求转载、摘录或镜像等使用取得书面授权，不宜直接转为存全文／模型输入案例。**备选保留，当前不推进内容摄入** |

上述页面观察可直接复核：[COVNA](https://www.covnavalve.com/)、[DONJOY 首页](https://www.donjoyvalve.com/)、[DONJOY 版权说明](https://www.donjoyvalve.com/copyright-notice)。DONJOY 的 [Terms of use](https://www.donjoyvalve.com/terms-of-use) 主要讨论 cookie，并不提供 crawler 许可。这里记录站点条款作为操作前提，不作法律结论。

本次读取 `https://www.covnavalve.com/robots.txt` 和 `https://www.donjoyvalve.com/robots.txt` 均为 Web 工具“不可取得”，**不是源站确认的 404、无 robots 或允许抓取**。COVNA 的水处理与 Selection Guides 导航目标，本次 Web 分别报告 404；型号详情、About、Contact 的后续读取也未取得可用内容。前两项只能作为待原生安全 fetcher 复核的链接问题线索，后几项不能标成网站故障。Web 可读亦不证明项目 crawler 的 DNS／robots／HTML 提取一定成功；部分 Web 结果有较旧缓存标记，不是本轮源站状态快照。

同品牌有多个相似域名的搜索结果，未核实其关系，不合并事实或跨域补页。本案若后续选 COVNA，仅针对 `https://www.covnavalve.com:443`；不把其他拼写域名、CDN、社交站或跳转目标纳入默认权限。

### 2.2 抓取许可与公开页面范围

正式启用 crawler 前须形成一条可审记录：选定 origin、操作者的具体审计授权、robots 获取时间／内容摘要及该 user-agent 的路径判断、站点使用条款 URL／日期、允许的请求规模与资料保存／模型使用范围。robots 是抓取指令，不能替代内容使用许可；用户授权也不能覆盖源站拒绝或访问控制。若规则无法取得、明确禁止或用途不清，就保留 BLOCKED，改选站或使用获得许可的离线快照，不改安全策略。本轮没有联系站方申请许可。

拟议上限为现有 **5 页、depth 1、并发 1、35 attempts、25 MiB wire／50 MiB decoded、120 秒**，遵守 robots／crawl-delay 和 exact-origin。候选页面角色是首页、一个分类、一个型号详情、About、Contact／一篇相关说明；**这不是已抓到的五页清单**。单 seed BFS 未必能在 depth 1 触达它们，应先核真实链接和 seed，再按实际可达页面报告覆盖，不能为了凑五类页面扩大深度或跨域。已有验证脚本的 depth 2 选项不自动扩展本案范围。

公开详情页和真实的同源 HTML 链接可成为范围候选；登录、询价表单提交、站内搜索／非空 query frontier、账户／后台／购物车、验证码、下载文件、图片／视频及外域资源不进入此次默认内容审计。不点击发送询盘，不绕过访问限制；产品 PDF 仅记录公开入口，不下载或假定原生 PDF 摄入已支持。

通过许可预检后，首轮只运行 **Crawl → Packet → CrawlSeoAuditor**，检查页面可抓取／提取、title、meta、H1/H2、canonical、正文和已观察内链。原生 `plan` 会构造真实研究／规划 provider，**不能用它当作无模型只读审计命令**；`scripts/verify_site_crawl.py` 已有独立有限抓取诊断入口，但尚未导出完整 Packet＋Audit 验收包，本轮也没有执行它的 live 路径。

### 2.3 搜索意图研究可行性

建议先限定“英文、海外 OEM／水处理设备采购”这一读者假设，具体国家 **NOT_CONFIRMED**。可以把美国英语作为后续研究测试市场，但不能写成企业实际主营市场。需在正式研究前固定国家／语言／日期／设备及查询集合；若工具不能提供地区化结果，就标为一般英语检索，不能声称已验证美国 SERP 或排名。

| 查询假设 | 待验证意图 | 可用公开研究方式与限制 |
| --- | --- | --- |
| electric actuated ball valve manufacturer | 找供应商／产品分类、商业调查 | 比较类别页、制造商介绍与询价信息；不能仅因 SERP 有供应商就推定转化价值 |
| electric actuated ball valve water treatment selection guide | 理解选型因素与工况、信息需求 | 本轮已做一般英语探索检索，能找到供应商指南及制造商资料入口；说明可研究，不证明需求量、当地意图或正确技术答案 |
| 实际型号 + datasheet / voltage / connection | 核对具体配置、采购前确认 | 型号及配置由实际页面核实；没有客户资料时只报告网页提供／未观察到的信息，不写参数结论 |

本轮探索可见面向工程采购的供应商指南，例如 [MARS 的 actuated ball valve guide](https://www.marsvalvenok.com/news/actuated-ball-valve-guide)，以及 [Swagelok 制造商选型资料入口](https://www.swagelok.com/-/media/Distributor-Media/L-N/NCTN/Services/Swagelok-Actuated-Ball-Valve-Selection-Guide.ashx?hash=D7F152F73EA0A4DA90C8653ABCAFF7AB9B48A7C5&la=en)。仅用于判断研究材料可获得性，未下载／验证整份资料，不能作为 COVNA 产品依据。后续须人工筛除无来源聚合／生成式营销材料，保留真实发布日期、页面类型、问题及来源适用性，不按搜索结果排序背书。

因此：**公开意图研究可行性 READY（已初探）；目标国真实 SERP／查询量／本企业实际询盘与转化意图 NOT_TESTED**。不访问 Search Console／Analytics，不假装拥有私域数据。公开审计交付的是观察、机会假设和 Evidence Intake 缺口清单；没有客户授权就不升级成受背书的商业正文。

## 3. 后续商业文章场景及验收目标

**推荐候选：真实外贸阀门制造商的一款实际型号，面向一个海外市场的 OEM 采购工程师，改进其现有英文产品／应用说明页，解释水介质适用条件、判断依据、不能推出的结论和询价前需提供的信息。** 企业、型号、市场、页面 URL 和标题目前均待客户提供，不把它们写成既定事实。EPDM 等材料名称也须由真实配置确认，不预设该产品使用何种材料。

选择理由：买家决策问题具体，能够逐项核对型号、配置、介质、工况、方法和排除条件；有真实技术负责人时可形成有责任的事实审核。单页 EXPLAIN 扩展与现有 Intake 的受限 profile 接近，避免把第一案扩大为复杂比较、安装安全指导或多型号推荐。LumenSeal/V7 仅可复用测试结构，不能复用其中的性能或证书。历史 CNC 场景保留为备选：目前也缺真实客户资料，且几何、工艺、产能与安装的义务范围更广；已有 CNC 演示资产不是优先选择它的真实性依据。

选择场景的前提是客户愿意提供资料与技术审核者。若先获得完整、授权的另一类 B2B 产品材料，可按同一标准改选品类，不能硬编码阀门域名、材料词或义务答案。架构接收通用站点 URL、统一模型与 ports；“任意合法授权网站”表示不限定某品牌，不保证所有网站都能抓到足够内容。动态渲染、robots 拒绝、登录后资料、深层页面及超预算网站都可能成为明确阻断。

**主验收对象是完整拟议页面／文章的正文质量。** 最小实施形态可以是一个合法 section 扩展加原页面的完整只读预览，但必须阅读全文，检查原文冲突、重复、意图和采购价值。单节通过不能代替整页通过；如果客户实际需要从零撰写独立长文，应明确登记为新文章能力需求，不将拼接多个 section 描述为原生整篇生成。

| 商业目标 | 当前结论 |
| --- | --- |
| 理解真实产品、客户业务与采购角色 | **NOT_TESTED**：有网页观察与研究链，无真实客户 brief 和理解正确性审核 |
| 发现有依据的 SEO 内容机会 | 原生引用／范围约束有离线验证；真实案例的机会价值 **NOT_TESTED** |
| 理解买家搜索意图 | **NOT_TESTED**：没有本案实际查询、SERP 或匿名询盘依据；模型推荐与标题词不是意图证明 |
| 判断任务证据是否充分 | 有逐义务、版本绑定的人工 reviewer 接口；通用自动语义判断未实现，真实 reviewer 接入 **BLOCKED** |
| 缺证时发起 Evidence Intake | 有本地登记、请求、提交、重规划子链；主 CLI/Live 自动转入 Intake **BLOCKED** |
| 证据充分且授权后生成专业内容 | 当前生产 **BLOCKED**；材料齐全或 CANDIDATE_FOR_REVIEW 都不授予 Draft 权限 |
| 形成可供人工审核的 SEO Draft | 既有／fixture Draft 可只读审阅；本案新 Draft **BLOCKED**，整篇商业质量 **NOT_TESTED** |

## 4. 现有材料清点：可复用内容与真实性

对当前 `.data` 中 60 个 SQLite 文件只读查询，排除 `verified-checkout`、`turn-final-files` 镜像目录；按 run/artifact ID 去重后有 76 个 run、369 个 artifact。站点分布为 `geo-test-site.pages.dev` 31、`novacnc.example` 5、`example.com` 40；其中 47 个 failed、29 个 succeeded。artifact 行为 SITE_CONTENT 74、SITE_AUDIT 74、INDUSTRY_RESEARCH 73、CONTENT_OPPORTUNITY 66、CHANGE_PLAN 49、CONTENT_DRAFT 33。**这些是历史行清点，不是本轮全部通过当前验证器的数量，更不是商业成功率；旧成功、mock、失败实验和同 run 多 Draft 均不能升级为商业验收。** 参考 EXPLAIN 工作树 `.data` 另查到 1 个 SQLite 文件，无 `runs` 历史统计；未把它加入上述业务 run 数。

| 材料 | 实际位置／依据 | 分类、可复用用途及限制 |
| --- | --- | --- |
| NovaCNC 本地 HTML | `src/foreign_trade_geo_agent/web/fixtures/novacnc/{index.html,machines.html,robots.txt,manifest.json}` | **合成 fixture**。manifest 标注 curated snapshot、source revision unknown；用于确定性抓取、提取、Demo 和 UI，不能证明真实企业、产品或业务 |
| 公开部署测试站的历史抓取 | `.data/smoke/`、`.data/live-ui/history.sqlite3` 等；`docs/review-packages/evidence-sufficiency-2026-10-08-v2/source-provenance.json` | **真实发生的历史抓取／执行记录，所抓企业内容为合成**。`snapshots/DemoDisclosure.astro` 和 `experiment-baseline.md` 明示 NovaCNC 虚构、非营业制造商、不能接单；公开域名不改变内容性质 |
| 冻结网站／审计／规划包 | 上述 v2 包的 `snapshots/{site_content,site_audit,industry_research,content_opportunity,change_plan}.json` 及 manifest | 可复用 artifact lineage、hash、P/S/A 引用和负例审阅方法。原始 run 为 failed，历史部署 commit／工程作者资格未知；不构成客户签核或技术正例 |
| 历史外部研究结果 | 上述历史库的 INDUSTRY_RESEARCH、v2 `snapshots/industry_research.json` | 保留了真实公共域名 URL 的搜索摘录，例如 Global CNC、ManufacturingTomorrow、BusinessWire、研究报告及商业目录；另含 `research.example` 等 fixture。**公共来源候选与合成来源必须逐条分开**，不能对整个 S catalog 一概称“真实权威资料” |
| 外部研究可用程度 | `core/research.py`、`workflows/industry_research.py` | 保留 bounded text 和 URL，分类固定为 EXTERNAL_RESEARCH_CONTEXT / UNVERIFIED_SEARCH_RESULT。本轮未读回网页核真、核时效或核授权，不能证明型号参数、客户背书或阀门技术事实；CNC 市场摘录亦不能直接迁移到阀门场景 |
| 客户补证示例 | `docs/customer-evidence-intake-synthetic-2026-10-09/`、`intake-native-planning-synthetic-2026-10-09/`、`draft-execution-synthetic-2026-10-09/` | **显式合成**的出口包装、LumenSeal/V7、BellHarbor/F9 等；用于请求、缺证、冲突、版本失效和待审行为。脚本化 HUMAN verdict 不是真人客户签核；证书／数值不可转用 |
| RouteDock 冻结请求、输出和质量审阅 | 参考工作树的 `docs/explain-*-2026-10-10/` | **合成场景、部分真实模型响应、编辑判断**。可复用预算与漏限定反例的方法，不能作为工业产品资料、真实采购意图或专业文章正例；本轮不再调 Prompt |
| 历史真实 Draft 负例 | `docs/seo-draft-live-acceptance-2026-10-08.md`；run `58681c3b-2611-490a-93f1-0ec5f2e89f4e`，真实 Draft `0c58bab3-6807-4d18-add8-6b0fb534dcfc` | **真实模型调用、合成／薄材料、质量 NO-GO**。不能与同 run 的准备 mock Draft 混用；证明“合法 JSON／引用通过仍可能空泛”，不能证明商业生成就绪 |
| 客户确认的真实型号资料、询盘、查询数据、授权 | 在本次检查的仓库、上述历史库和参考包中 **未找到可确认的完整材料包** | 不等于用户没有这些材料；只表示本次无法据现有项目资产选出可直接开验的真实客户。客户事实、人工确认和模型推断均不得自动补齐 |

来源分层必须同时保留两件事：**来源类型**（公开网页／客户提交／合成／推断）和**核验状态**（仅观察、来源待核、适用性待审、客户确认、存在冲突）。客户确认某个文本也不等于第三方认证有效或性能可泛化。hash 证明字节绑定，不证明真实性或语义支持；网页观察到某宣称，只证明网页如此写。

### 最小材料缺口

以下材料按义务覆盖准备，不规定凑够多少文件。缺失证书或案例时可以不写；缺少目标问题的核心事实时必须补证或由客户明确调整任务。

| 缺口 | 最小交付内容 | 当前状态 |
| --- | --- | --- |
| 真实对象与用途 | 企业／网站及目标页、真实型号与配置、一个市场／语言、采购角色、目标问题、客户负责人；资料保存及生成用途范围 | MISSING |
| 网站上下文 | 客户授权的首页／公司、分类、目标产品、相关技术、联系页面 HTML 或导出；原 URL、日期、快照摘要、版本／完整性说明 | MISSING。现有合成抓取不能替代 |
| 意图依据 | 可匿名化的实际查询／询盘／销售 FAQ，记录时间、市场、语言、原问题与期望页面类型；若不足，再申请具体市场的搜索研究 | MISSING。拟议关键词只是调查假设 |
| 解释所需产品事实 | 型号／配置／材料原文；拟写的性能或兼容性结论对应介质、单位、工况、方法、适用范围、限制／排除与未规定属性；版本、原文定位、来源负责人 | MISSING。不得套入 V7 或 F9 数值 |
| 必需义务与质量基线 | 客户和工程审核者确认的问题清单、可支持答案边界、待确认项；原页面全文作为比较基线 | MISSING。由分析人员编制，不由关键词覆盖生成 SUPPORTED |
| 有责任的审核与权限 | 可核实的客户资料提交者、技术审核者和英文 B2B 编辑；逐项决定、冲突处理、时效／重审和用途授权 | MISSING；同时存在生产身份接入能力阻断 |

若真实资料仅为 PDF/DOCX，可先人工核对并无损转为 UTF-8 文本，保存原件与文本摘要、页码／段落对应；当前 `text_document` 不是 PDF/DOCX/OCR 导入器。OCR 不清、来源不明或条件无法定位仍是缺口，不虚构 locator。未授权披露的客户信息不放入公开报告。

## 5. 原生完整链路：入口、契约、绑定和状态

状态口径：**READY** 仅表示本轮离线验证覆盖的实现／接口可工作，不表示该商业案例已验收；**BLOCKED** 表示存在已知缺材料、接口或授权；**NOT_TESTED** 表示本轮未验证真实运行／语义能力。各阶段须同时读“离线实现”与“真实商业”两列。

统一入口是 `plan --site --question --language --db` → `runtime.build_planning_workflow` → `EndToEndWorkflow.run(EndToEndRunRequest)`；Live 也使用该 runtime。当前主链是 **Crawl → Packet → Audit → Research → Opportunities → Change Plan → Draft 拒绝**。Intake 尚未成为主链的自动分支，Review 是既有 Draft 的独立只读入口。

| 阶段 | 实际接口和输入 → 输出 | 版本／证据绑定 | 离线实现 | 真实商业及阻断 |
| --- | --- | --- | --- | --- |
| Crawl／Packet | `SiteCrawlWorkflow.run(site_url)` → `SiteCrawlReport`；`SiteContentPacketBuilder.build(report)` → `SiteContentPacket`／SITE_CONTENT | 同次 crawl 成功页面生成 P#；final_url、正文、结构和截断标记保留；artifact 有 run_id／artifact_id／payload_version／created_at | **READY** | **BLOCKED（许可预检未完成）／NOT_TESTED（原生真实抓取）**：候选站已初探，公网 DNS、robots、exact-origin、安全及预算拒绝保持；静态抓取不能保证全部内容 |
| Audit | `CrawlSeoAuditor.audit_crawl(report)` → `SiteAuditResult`／SITE_AUDIT | 消费同次 crawl，A# 随 Opportunity audit catalog 传递；不另联网 | **READY** | 本案 **NOT_TESTED**。覆盖 title/meta/H1/H2/canonical/正文量/观察到的内链等；不是 schema、noindex、排名或全站缺页证明 |
| Research | `IndustryResearchWorkflow.run(question, language)`；SearchProvider + ResearchWriter → `ResearchReport`／INDUSTRY_RESEARCH | 保存实际交给 writer 的 bounded S# materials、标题、URL 和未验证分类；同 run artifact | **READY** | **NOT_TESTED**：真实来源适用性与意图未审。本轮不调用搜索或 DeepSeek；默认至多一次 search、一次研究生成，仅 en；有研究文本不等于搜索意图已证实 |
| Opportunities | `ContentOpportunityWorkflow.run(packet, research, audit)` → `ContentOpportunityReport`／CONTENT_OPPORTUNITY | R# 回指 P/S/A catalog、候选主题和 retained source material；finalizer 校验范围与动作 | **READY** | **NOT_TESTED**：真实业务理解、机会优先级与潜在买家价值没有实证。S-only 不能证明客户缺页；P-only 摘录特殊 scope 不能替代普通 EXPLAIN 研究路径 |
| Change Plan | `ChangePlanWorkflow.run(packet, opportunity, *, task_id, customer_context)` → `ChangePlanReport`／CHANGE_PLAN | C#→R#、目标 P#、locator、操作及内容点；重规划保留原 P/S/A 与任务范围 | **READY** | 本案 **NOT_TESTED**。主题合法不证明能解释；原生合法 Plan 是当前 Intake 登记前提；没有早期缺口通用接入 |
| Evidence Intake | `EvidenceIntakeWorkflow.register → customer_request/check → submit → replan → review_candidate`；`EvidenceTask`、`ContentDraftInput`、`CustomerSubmission` → request／snapshot／check／PlanningReviewCandidate | project/customer/task、task/plan/evidence/revision、snapshot SHA-256、全文与来源 locator、精确审核 spans、CAS；客户 E# 独立 context，不冒充 P/S | **READY（受限本地子链）** | 生产整合 **BLOCKED**：无 CLI/Live Intake 路由、可信客户身份和当前真人 reviewer。仅一个 EXPAND_SECTION、全 EXPLAIN 内容点；要求人员明确义务；不自动判充分，CANDIDATE_FOR_REVIEW 无执行权 |
| Draft | `ContentDraftWorkflow.run(ContentDraftInput)` → `ContentDraftReport`／历史 CONTENT_DRAFT；生产 runtime 装配 `ProductionDraftAdmission` | 既有 D#→C#→R# 与 P/S/A grounding；Input 本身仅四字段，无 task/epoch 身份。当前 Intake admission 可检查绑定但始终拒绝执行 | **READY（拒绝行为／fixture 契约）** | **BLOCKED**：生产 `INTAKE_EXECUTION_BLOCKED`、writer=0，无新 Draft artifact；真实 DeepSeek Draft adapter 非 MockTransport 直接拒绝。客户证据不能经默认路径进入生成；不能把拒绝称为正常商业成功 |
| Review | `review --run-id --artifact-id --draft-id [--format json]` → `ContentDraftReviewWorkflow.review(request)`／view | 同 run 且唯一的 SITE_CONTENT／Opportunity／Plan，加选定 Draft 的 provenance；SQLite read-only | **READY（既有 Draft inspection）** | 新商业 Draft **BLOCKED**，整篇事实／语义审核 **NOT_TESTED**。此命令不记录 reviewer／approved_at，不是签核；不消费当前客户 Intake 决定或生成整页差异预览 |

**持久化与绑定的具体限制：**

1. 前五阶段在同一 run 逐个追加；后续失败不回滚。原生 CrawlReport 不作为独立稳定 artifact 保存。业务 run 的 payload_version 是序列化版本，不能当作文档修订号。P1/S1/A1 仅是各输入 catalog 内的局部 ID，跨 run 不具有恒定身份。
2. SITE_CONTENT 是 bounded 观察，默认正文每页 600 字符，并保留部分结构化内容；不是网站全文档案。`SiteContentEvidence` 没有独立原 HTML hash／抓取日期字段，artifact 创建时间不等于原文版本证明。正式验收须保留授权原快照及映射。
3. Research 默认最多 5 来源、每源 1200 字符、总计 6000；`ResearchMaterial` 不记录上游裁剪前全文、发布日期或原文 hash。Opportunity 后续的截断标记不能恢复先前已丢失的限定；需对实际可消费文本逐义务审查，不能仅审外部全文后假定模型已看到。
4. Intake 新提交使 plan_bound=False；原生重规划产生新绑定、版本／digest，旧 check 不继承；无 reviewer、缺证、无关、矛盾、失效或不确定判断不能放行。来源是否过期／真实适用仍依赖人工，不是自动日期真实性检测。
5. Intake V1 没有 History run/artifact ID 外键；登记者必须明确导入正确目标及义务。只凭内容相同的 DraftInput 不能恢复其证据 epoch；新 digest 不能包装旧授权。旧文档中“未装配 guard 的默认 runtime”描述已被 10-09 生产拒绝边界取代，以当前代码与本轮测试为准。
6. 默认 run 仍以 FAILED 表示 Draft 拒绝，没有原生 WAITING_FOR_EVIDENCE/REVIEW 的可恢复主链状态。当前没有顶层自动恢复／stale-run 清理；不能承诺补资料后 CLI 从停点自动继续。

参考区独立 TEST EXPLAIN 消费能够使用专门冻结目标、充分性与执行 receipt、journal 和 coverage proof，但依赖 synthetic 身份及 TEST 装配，未进入当前 checkout。其已审文本／refs 精确覆盖也不是任意改写的语义蕴涵保证。原生 NEW_RESOURCE 有 sections schema，**这不等于客户补证 EXPLAIN profile 已支持从零商业长文**；当前 16 claim 等全局／局部预算保持，不能以拆 Draft、删必要条件或静默降任务规避。

## 6. 最小执行方案与停止点

**当前优先执行的准备方案是第二节的公开网站选站预检与零模型审计定义**，已完成候选人工式初探，停止在 robots／用途许可未明与原生抓取未测；无需假设先有客户。以下步骤则是后续升级为整篇商业内容验收时的材料与授权方案，两者不混作同一通过结论。

下面是后续执行方案，本轮只完成其验收基础与离线能力核查。当前无需模型或 WordPress 权限即可开展材料准备；没有材料时不得手填成功商业 artifact。

1. **先确认一个真实客户／型号／页面与授权 brief。** 收到第四节最小材料包，技术负责人确认目标问题及必要义务；核对来源类型、可用范围、真实型号、保密和冲突。至少固定三个来自实际查询／询盘的情景问题；若暂时没有意图依据，保存为意图待验证，不能通过该维度。
2. **冻结网站与资料。** 单独获准抓取后走原生 Crawl／Packet／Audit；若仅允许离线，使用客户授权、核对过的 HTML 注入 fetch ports，标明离线重放。以目标产品页为 seed 可减少 depth 1 触达风险；仍不能保证抓到全部背景页。保存原页面全文、日期、hash、实际 bounded input 和截断影响，不扩大抓取权限。
3. **研究与初始规划。** 已授权真实 provider 才运行 Research／Opportunity／Plan；本轮继续不调用。现有真实历史 artifact 可用时先核验其对象／版本／来源，否则使用 fixture 只能验工程连接。没有合法本案 EXPLAIN Plan 时报告该前置阻断，不伪造 heading、subject_ref、S 来源或 SUCCESS 绕过登记条件。
4. **逐义务补证和重规划。** 一个合法 EXPLAIN 扩展登记为 EvidenceTask。每个问题可有多个 requirement，保存 required_fact、intended_use、现有不足、允许方式及精确原文；提交后运行原生 replan。缺项回客户，待审项交技术审核者；无关／冲突材料保留，客户明确同意才调整整点范围，不能降为宣传概述悄悄过关。
5. **停在当前可用边界。** 导出当前 snapshot／Plan／request／逐义务审核候选及来源对照。真实 reviewer 接入和执行权限不成立时保持 BLOCKED；CANDIDATE_FOR_REVIEW 只说明候选可审。此时可验资料准备及工程子链，不能验新文章质量。
6. **未来生成另设进入条件。** 需独立完成生产任务／审核／用途授权、P1 全局消费及部署验收，并获得特定冻结输入的真实模型授权。技术允许与用户授权两项都满足才考虑生成，不能借 TEST 工具绕过生产停点。预登记请求预算、失败停止和是否允许修复；不从当前 workflow 可能存在的 repair 能力推定已授权额外请求。
7. **整篇质量审核。** 对合法生成结果导出实际全文、claims、来源／span、原页与拟议整页差异，按第七节由技术审核者和英文编辑评价。若只有一个 section，就同时审原页全文，清楚标注预览不等于 native NEW_RESOURCE。原页事实冲突或需改动超出已准任务时，登记缺口并停止，不以单节合格交付整页合格。

建议一次主案例加少量必要负例：缺关键工况／方法、条件相互冲突、材料更新使旧审核失效。预期均须阻断且 writer=0。充分材料的正例在真实审核／授权工程尚未成立时仅到候选，不能预写 Draft PASS。未来文章若无依据、漏限定或无法满足全部预算，应保存失败和原因，停止；不返回 RouteDock 无限调 Prompt。

后续验收包最低包含：brief／权限记录、意图依据、原页全文／快照、原生 artifact 身份、实际消费文本、EvidenceTask／submission／snapshot／check、必要义务 ledger、未决项与冲突、候选／未来 Draft 实际正文、逐断言来源映射、两角色全文评价与结论。原件缺失或来源真实性未核时明确标记，不能用 hash 或批准人身份补足事实。

## 7. 整篇文章质量标准

以下为本案预先提出的验收门槛，不是已证实的行业评分标准。先审核义务清单本身，再审成文；来源覆盖和单句引用合法不能代替完整条件、解释义务或全文价值。

### 7.1 自动化可验证项

| 检查 | 接受／停止标准 | 能证明的边界 |
| --- | --- | --- |
| 原生契约、预算、引用 | parser／finalizer／stable validation 全通过；未知 refs、越权操作、超限或字段错误拒绝 | 证明机器契约，不证明专业事实或原创性 |
| 冻结与版本 | 实际输入／输出／ledger 摘要、task/Plan/evidence/revision、run/artifact 映射一致；新版本使旧审阅失效 | 当前原生与 Intake 已有部分能力；完整商业包的跨层映射尚需落实，不能标为全部自动化已实现 |
| 来源与原文定位 | ID 可解析、span／quote 精确匹配、缺行／重复行／失效记录不接受 | 证明文本和记录绑定；不能证明来源权威、适用或句义蕴涵 |
| 审核记录完整性 | 每项必要义务都有正文位置与明确决定，PARTIAL／FAIL／PENDING 不计通过 | 可核记录完整；不自动认证身份或判定 reviewer 的结论正确 |
| 边界与副作用 | 生产拒绝、缺证／陈旧输入 writer=0；只读 Review 无业务写入，WordPress=0 | 本轮离线测试有覆盖；不替代真实生产部署或 P1 验收 |

数值／单位、词面重复、claim 数量、长度和相似度仅按现有能力辅助检查。当前规则不能保证任意技术关系正确，也不能靠低相似度证明原创性、专业价值或不侵权；高相似度亦不能单独证明低质量或 SEO 惩罚。

### 7.2 必须由人进行的语义与全文判断

技术审核者应熟悉该型号与应用资料，英文编辑应理解目标 B2B 买家；尽可能独立审阅，记录分歧及证据裁决。生成助手的编辑意见不能代替责任人的签核。

| 维度 | 具体问题与交付证据 | 合格门槛 |
| --- | --- | --- |
| 搜索意图匹配 | 对照实际查询／询盘逐问检查；读者是在确认型号、判断适用条件还是比较采购方案？正文是否用合适的页面类型回答？ | 已确认主要问题全部覆盖；无真实意图依据则 **NOT_TESTED**，不得靠关键词命中通过 |
| 专业事实准确 | 整篇每条产品断言对应型号／配置、来源原文与适用范围，区分公开宣称和经核实的客户事实 | 0 无依据产品参数／认证／案例，0 关系反转、重大跨型号或跨工况外推 |
| 证据可追溯 | 正文断言→精确来源；必要义务→正文位置双向对照；区分原页、新节、推断和待确认项 | 所有需证断言有适用依据；装饰引用不计支持，全部必要义务明确覆盖 |
| 限定／否定完整 | 测试前提、介质、单位、条件、方法、排除、未规定属性、操作顺序是否保留？泛化免责声明是否偷换特定限制？ | 必要含义 100% 明确覆盖，PARTIAL 不通过；不可用总括免责声明代替具体否定 |
| 解释深度与信息增量 | 读者能否理解何时适用、为何按资料这样判断、何时需工程确认？对照原页／摘录基线指出实际改善 | 三个真实情景问题均有有据答案；至少两处记录减少了何种具体误解；合句、同义替换和添加连接词不算充分增量 |
| 结构与可读性 | 读完整篇，核查标题、术语首次解释、定义→条件→判断→限制的顺序、指代和重复；检查插入位置 | 0 影响采购判断的歧义／重大结构冲突，必要条件清楚可定位，不堆关键词或凑篇幅 |
| 买家实际问题 | 目标角色能否据文形成询价信息、筛除不适用情形、知道哪些问题应交供应商确认？ | 不只复述“这些因素很重要”；每个主要问题有答案或明确有理由的待确认项 |
| 无依据营销承诺 | 是否把测试结果变为全工况、寿命、交期、认证、适配、排名或询盘保证？ | 0 无依据承诺；没有证书资料时不写已认证，也不写“没有认证” |
| 人工审核可执行 | 全文、原页差异、来源、版本、待办、审核身份与结论是否可读；是否明确 Draft／未批准状态？ | 技术与编辑均明确通过，分歧已解决；只读 review 命令成功不算批准 |

结构、专业解释、可读性、意图可按 1–5 分辅助评估，预设各至少 4 分，每分须有具体段落与问题依据。评分不能抵消任何事实硬失败。整篇通过只证明这个案例在冻结范围内可用，不证明任意网站、所有客户或模型一般能力。没有新文章时，本轮不产生内容评分。

### 7.3 当前不能证明的 SEO 效果

排名、索引覆盖、展示、点击、CTR、自然询盘和收入全部 **NOT_TESTED**。本轮不发布、不接分析后台，也没有前后对照或观察期。未来须另行授权发布及数据读取，固定页面／查询、基线、业务周期和混杂变更；不能用一篇文章、词面统计或单次涨跌证明 SEO 因果效果，更不作效果承诺。

## 8. 生产阻断与本次验收的关系

| 阻断 | 本次材料／离线核查能否继续 | 对未来商业内容验收的影响 |
| --- | --- | --- |
| 真实材料、查询意图与客户授权缺失 | 可以列需求和验工程负例，不能补造事实 | 直接阻断本案可信机会、证据充分性及全文质量正例；需要客户材料 |
| 无模型的 Crawl＋Packet＋Audit 完整导出入口尚缺 | 可先人工选站、用已有 workflow 做离线组合 | 不宜用 `plan` 替代公开只读审计；这是下节建议的最小工程任务 |
| 主链没有 Intake 登记／请求／待审入口及 run/artifact 对照 | 可通过本地 Python 接口做 fixture 子链验证 | 后续客户文章阶段仍需受限任务导入与请求入口，不在当前选站任务顺带实现 |
| 可信身份、当前人工语义审核源、保护的 production host／key／clock／revocation／恢复验收未完成 | 可以收集资料和准备人审，不能伪造批准 | 阻断正式审核和执行授权；客户愿意审核不等于生产签核基础设施成立 |
| 客户证据 Draft 用途与当前生产消费路径未开放 | 可以到原生重规划／候选，默认保持 writer=0 | 即使材料充分也不能从默认 CLI/Live 生成；不以“修 Prompt”解决授权问题 |
| P1 全局一次性消费失败 | 不影响只读材料清点／无模型离线验证 | 历史日志三项失败：同路径 journal 回滚后调用=2、换 journal 后调用=2、跨进程不同 journal 双 CLAIMED；生产一次授权保证未成立。本轮未重跑或修改它们 |
| PostgreSQL **BLOCKED** | 不影响现有 SQLite 历史和 Intake 子链核查 | 历史记录为无现成实例，用户要求按 BLOCKED；不能用 SQLite/mock 替代 PostgreSQL 验收。本轮未重新探测可用性，未解决权威库整体回滚／恢复问题 |
| 客户补证 profile 与整篇新文章需求不匹配 | 可以先定义拟议整页验收及缺口 | 单 EXPLAIN 扩展不等于 NEW_RESOURCE 商业支持；若必须从零长文，应另提最小契约／消费方案，本轮不扩 schema 或预算 |
| Review 只 inspection、无整页语义签核闭环 | 可审历史 Draft 和准备人工表 | 新文生成后仍需全文审核、差异预览与责任人记录；批准不能从 review exit 0 推导 |

客户资料读取／保存与用途授权、具体站点抓取／搜索授权、特定冻结输入的模型生成授权属于不同范围；前者不自动包含后者。生产工程条件和真实业务授权均须满足。WordPress 创建 Draft 与发布继续是独立动作，本案最小内容验收不依赖 CMS 写入，本轮没有此类授权或操作。

## 9. 下一轮最有价值的一项工程任务

**建议：补齐“零模型 Crawl → Packet → Audit 的只读验收包导出入口”。** 这直接服务用户优先开展的真实公开网站审计，避免用会调用研究／规划模型的 `plan` 完成纯审计，也无需等待客户材料或 PostgreSQL。现有 `scripts/verify_site_crawl.py` 已复用安全 crawler 并输出有界诊断，应扩展其现有能力或在现有 runtime 增加小型 audit composition，不另写抓取器。

最小方案（仅提案，本轮未实现）：

- 入口接收明确的审计 origin／seed、许可预检记录与既有有限预算；本地 fixture 模式先验，live 模式仅在具体站点操作授权和预检成立时显式调用。记录是许可证据，不由一个布尔值宣称系统自动认证。
- 复用 `SiteCrawlWorkflow`、`SiteContentPacketBuilder`、`CrawlSeoAuditor`，导出已有模型的只读文件包及 manifest：真实请求／最终 URL、抓取时间、停止／robots 状态、页面覆盖、文本／结构截断、输入／输出 hash、观察分类和审计范围。使用独立本地文件，不新增 History artifact 根类型或变更数据库 schema。
- Research／Opportunity／Plan／Draft／WordPress 依赖均不构造；缺 robots、重定向越界、部分页面或字节／时间停止如实记录，不能生成全站缺失结论。测试以临时目录／fake transport 验证零模型、零 CMS、来源绑定和失败停止。
- 不实现身份签核、自动充分性、PDF/OCR、长文 schema，也不修改 crawler 安全策略、Gate／Validator／P1。公开页始终是 observed 信息，后续商业写作仍须 Evidence Intake 和独立授权。

后续真实客户资料收集按第四节最小包推进，但不是公开只读审计的虚构前提。P1／PostgreSQL 的修复必须作为单独明确范围的任务，由其已有安全方案和部署前提约束，不并入本轮。Planning→Intake 任务导入仍是商业文章阶段的已知缺口，此时不同时开启第二项工程任务。

## 10. 本轮实际验证、改动与交付边界

本轮在当前 checkout 的 `.venv` 中确认 import 指向本仓库后运行以下针对性命令；12 个模块，**363 tests，33.625s，OK，exit 0**：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_runtime tests.test_end_to_end_workflow tests.test_site_crawl_workflow tests.test_crawl_seo_audit tests.test_industry_research_workflow tests.test_content_opportunity_workflow tests.test_change_plan_workflow tests.test_intake_native_planning tests.test_evidence_intake tests.test_draft_execution_boundary tests.test_content_draft_review_workflow tests.test_content_draft_review_readonly -v
```

这些测试复用外部 fixture／MockTransport 和临时 SQLite，验证接口、来源范围、部分／完整补证、无关／矛盾材料、旧版本／并发拒绝、默认 runtime 保留五个 artifacts 后阻断 writer、真实 Draft adapter 拒绝非 mock transport，以及 Review 只读。没有新写功能测试、没有改变断言；363 项 unittest 无失败。**未运行完整 discover、live/integration scripts、P1 或 PostgreSQL 验收**。参考区的 224／13 项通过和 P1 三项失败是已读历史证据，不混入本轮成绩。

本地文档核查脚本首次把相对 NUL 的 `git diff --no-index --check` 内容差异 exit 1 错当成失败，触发一次 AssertionError；直接检查确认无 whitespace diagnostics，只有 LF/CRLF 提示。修正该临时脚本对 no-index 退出码的解释后重跑；仍要求无空白错误或其他错误输出。常规 `git diff --check` exit 0，未改项目测试或生产校验。

只新增本目录 `report.md`、`verification.json`；原始日志、起始文件摘要和清点脚本记录存于 ignored `.data/commercial-seo-readiness-20261010/`。核对起始 417 个非忽略文件全部保留，未覆盖既有用户改动；没有 commit／push／merge。源码、生产规则与 Prompt 无变更。

**交付结论：真实公开网站的候选、许可停点、页面与市场边界已建立；优先推进只读审计准备。整篇商业文章所需客户材料包、原生链路缺口和质量标准亦已列清，没有假定存在真实客户数据。完成本报告后停止，等待下一轮决策。**
