# MVP 本地文章审核、修订和反馈验收

日期：2026-10-10，Asia/Shanghai。本轮只实现已有文章页的本地操作闭环。

本地入口：[文章审核与修订](http://127.0.0.1:8011/mvp/article)。服务仅绑定 loopback，已保留运行。
使用上一轮保存且原生离线重放通过的真实 DeepSeek E-only 文章，未重新调用模型。
NovaCNC、NCX7 和全部产品参数始终为 **SYNTHETIC / TEST ONLY**，不是实际产品事实。

## 实际浏览器操作

使用独立工作台 `.data/article-review-20261010/web/`，从上一轮
`.data/seo-e-only-word-boundary-20261010/result-3/web/` 复制已有候选和当前 Intake。
没有替换原实验、冻结响应或默认 `.data/seo-mvp`。

候选 run：`c01ce5ed-0d73-448f-92d7-2016263b1a55`；
artifact：`b08a4eee-5a64-4b67-a67b-4565fabec264`；D1。

1. 浏览器打开全文、两个节标题及 12 条原始陈述。展开完整 E1，核对 CL3 → E1、证据 v2、F1、locator 和字符区间 `[46, 239]`。
2. 填写保留测试身份、参数和限制、调整结尾采购询问的意见，保存 v1，状态“需要修改”。
3. 将结尾 CTA 改为 `Prepare a focused enquiry and ask the supplier how the stated test applies to your planned cutting cycle.`；E1 原句、参数、型号、测试条件和限制逐字保留。
4. 保存 v2。即使提交时选择“本地审核完成”，正文变化仍强制重置为“待审核”，并明确 `PENDING_REVALIDATION`。
5. 实际刷新，确认正文和意见恢复；点击下载按钮，下载 `novacnc-synthetic-version-2.md`。
6. 实际停止本轮 loopback 服务后重新启动，再次在浏览器刷新；正文、意见、状态和版本历史恢复。
7. 正文不变，仅将本地状态保存为“本地审核完成”，产生 v3；页面仍明确待重新核验、无可信人工签核或生产权限；实际下载 v3。
8. 在浏览器回看 v0，原始 CTA 保留，历史版本只读；返回最新版本继续可编辑。最终源码版本的服务再次重启后，v3 仍恢复。

实际下载目录为 `C:/Users/31969/Downloads/`。下载后的字节与对应版本 renderer 的 UTF-8 输出完全相同；副本保存在验收目录中。

证据：[浏览器与文件核验 JSON](seo-article-review-acceptance-2026-10-10/browser-verification.json)、
[浏览器状态](seo-article-review-acceptance-2026-10-10/browser-final-state.txt)、
[v2 Markdown](seo-article-review-acceptance-2026-10-10/novacnc-synthetic-version-2.md)、
[v3 Markdown](seo-article-review-acceptance-2026-10-10/novacnc-synthetic-version-3.md)。

![本地审核完成仍待重新核验](seo-article-review-acceptance-2026-10-10/05-complete-still-unverified.png)

## 实现与信任边界

复用现有 FastAPI/Jinja、MVP facade、原生 `ContentDraftReviewWorkflow` 和 Markdown renderer。
v0 始终直接读取原生 Draft，所有用户保存都是对该 Draft 的追加记录，不创建第二套 DraftItem、模型生成链或交付流程。

本地记录使用工作台内 `local-draft-review.sqlite3`。现有 Intake journal 对 schema 作精确校验，故不向其表内插入文章数据，也不迁移 HistoryStore。
本地 journal 复用现有严格 dataclass JSON codec；以 SQLite 事务、主键和 UPDATE/DELETE 拒绝触发器保留历史。
每条记录包含版本、父版本、完整正文及 SHA256、意见、状态、核验状态、保存时间、原生 Draft 身份/内容摘要、冻结证据快照摘要和保存时当前证据摘要。

每次保存都追加记录，包括仅改意见或状态。页面支持 v0 / v1…历史回看、原文对照及按版本下载。
每篇最多 100 次保存、正文 16,000 字符、意见 2,000 字符；UTF-8 表单字节也有界，换行统一为 LF。
文章写入使用已有 loopback Host + CSRF 校验，拒绝重复字段、未知字段、伪造状态、签核/权限字段、超限和非法输入。
陈旧标签页/证据快照的提交拒绝并回显未保存输入，不能覆盖最新版本。

**任何正文变化**均重置本地状态并保持待重新核验，包含改参数、型号、条件、限制、改回原文及文字修饰。
没有用字符串匹配或旧 claim 标签伪称重新校验。P/S/E 映射明确属于原始正文的历史资料；修订 Markdown 不把旧 claim 标记插入新正文。
当前 Intake 快照变化时，旧本地结论在当前页面失效；保存时的历史状态及证据绑定仍保留。

“本地审核完成”只表示未认证本地操作员登记的反馈。原始 TEST reviewer 仍为
`TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF`；无真人签核、生产 Draft 授权或 WordPress 请求。
`/mvp/approve`、`/mvp/deliver` 仍不存在，既有生产 Gate、P1 和 PostgreSQL 未修改。

核验确认原候选数据库、diagnostics 和原模型正文/HTTP 响应摘要未变；原候选 WordPress attempts=0。
没有模型/余额请求、第三方抓取、WordPress 写入、发布、部署、commit、push 或 merge。

## 验证记录

最终测试命令、数量、耗时、退出码和迭代失败详见
[test-verification.json](seo-article-review-acceptance-2026-10-10/test-verification.json)。

新增 `tests/test_web_article_review.py`，覆盖本地记录/重启、原文不可覆盖、正文修改失效、后续本地完成不能清除待核验、型号/条件/限制变化、历史导出、陈旧标签页和证据版本、请求完整性与 XSS、LF、最大 UTF-8 正文/意见、100 次保存上限、append-only、损坏 journal 和失败首次保存恢复。
相关 39 项测试已通过，55.740 秒，退出 0；包括原生 Draft Review workflow、renderer 和只读历史验证。
最终稳定源码的完整回归：**1736 项 / 493.038 秒 / OK / exit 0**。

观察并修复的失败：

- 初始新增 7 项测试因缺编辑入口失败；随后页面缺 UNREVIEWED 提示导致一个既有测试失败，已恢复提示。
- 测试自身 SQLite 连接未显式关闭，导致 Windows 临时文件清理失败；改用 `closing`。
- 审查发现首次版本冲突会回滚 schema 却留下空文件；新增回归先观察 503≠409，再将合法 schema 初始化独立提交，修复后可继续保存。
- 最大四字节 UTF-8 正文+意见被旧表单预算误拒绝为 413；新增回归并单独调整文章表单预算，证据表单限额保持原值。
- 开发过程中的首轮完整回归为 **1732 项 / 462.699 秒 / 8 errors / exit 1**。8 个错误均为既有 retention 模块的 `EXPERIMENT_CODE_CHANGED`：测试冻结后本轮仍在修改源码。单独重跑其中首存失败用例通过；最终完整回归在源码稳定后重新执行，保留首轮失败日志，不将它称为通过。

已有 Starlette/httpx deprecation warning、asyncio slow-task 和 Demo launcher 模拟提示保留，不更换依赖或削弱断言。
审查者还实际验证四个独立客户端同时首存：仅一条成功、版本不被覆盖、随后可正常读取并追加。

## 修改文件

- `src/foreign_trade_geo_agent/core/content_draft_review.py`：有界本地修订契约、文本/摘要验证、存储 Protocol。
- `src/foreign_trade_geo_agent/storage/content_draft_review.py`：追加式 SQLite journal、事务与版本冲突、严格读回。
- `src/foreign_trade_geo_agent/reporting/content_draft_review.py`：本地版本 Markdown 与历史引用隔离。
- `src/foreign_trade_geo_agent/web/mvp_application.py`：原始候选读取、修订保存/恢复、版本/证据绑定与失效状态。
- `src/foreign_trade_geo_agent/web/mvp_routes.py`：已有文章页 POST、指定版本 GET/Markdown、表单预算和失败回显。
- `src/foreign_trade_geo_agent/web/templates/mvp.html`：版本历史、全文对照、编辑器、反馈/状态、测试与权限边界提示。
- `src/foreign_trade_geo_agent/web/static/mvp.css`：编辑器、状态选择及版本导航样式。
- `tests/test_web_article_review.py`：11 项新增测试。
- `README.md`：操作说明与本报告入口；本报告及验收材料为新增。

以上文件部分在本轮开始前已有未提交改动；本轮在其上增量开发，保留其他修改。未执行 Git 写操作。

## 剩余 MVP 阻断与限制

- 自由改写后仍无自动重新构建 claim、语义证据核验或可信真人签核；修订保持待核验，不能交付生产。
- 真实客户资料的真实性/适用性、专业文章深度及商业 SEO 质量仍需独立判断；本合成短文没有获得生产质量批准。
- Web 单次真实生成、失败/usage 交互、正式证据/文章签核与 WordPress delivery composition 仍未接入；P1 保持原状、PostgreSQL 仍 BLOCKED。
- 这是单个本地操作员工作台。首次创建 journal 的极短窗口内，同时首存的竞争请求可能暂时收到 503；竞态结束可恢复，原文不变且最多一个版本成功。未增加多人审批系统。
- 本地文件可被拥有主机权限的人修改；触发器和 hashes 用于工程追溯，不是身份认证或防主机管理员篡改的信任体系。

本轮完成后停止，不自动进入下一轮。

## 本地重启入口

如果本轮服务已停止，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe .data/article-review-20261010/serve.py
```

该脚本仅调用既有 app factory，使用 `lifespan=off` 展示 MVP 路由，不初始化旧 Demo/Live 服务。
不重新准备资料、不发起模型调用。恢复入口仍为 `http://127.0.0.1:8011/mvp/article`。
