# 文章修订稿最小重新核验验收

日期：2026-10-10，Asia/Shanghai。

已在现有文章页接入具体版本的重新核验、逐项结果、必填复核意见、明确结论和追加记录。
使用上一轮保存的真实 DeepSeek E-only 文章及 v1–v3；没有重新调用模型。
NovaCNC、NCX7、参数和资料始终为 SYNTHETIC / TEST ONLY，不能作为真实产品事实。

本地入口：[v2 核验记录](http://127.0.0.1:8012/mvp/article?version=2)。服务仅监听 loopback。
独立工作台 `.data/article-revalidation-20261010/web/` 复制自上一轮
`.data/article-review-20261010/web/`，保留原工作台及原实验。

## 浏览器实际操作

1. 打开已有 v2，确认其正文及末尾 CTA，原状态为 `PENDING_REVALIDATION`。
2. 点击“重新核验此版本”，查看全部 12 条结果、原始陈述、修订 CTA 及来源详情。
3. 展开 E1 完整冻结原文，核对型号、数值、单位、协议、温度、空载条件、适用范围及限制。
4. 填写本地复核意见，明确选择“已确认全文与适用范围；CTA 没有新增事实”，勾选已核对声明。
5. 点击“保存 v2 的核验记录”，状态成为 `LOCAL_REVALIDATION_COMPLETE`。
6. 打开 v3，仍是 `PENDING_REVALIDATION`，没有继承 v2 记录；没有增加文章版本或修改正文。
7. 返回 v2，刷新恢复状态，实际下载 Markdown。下载文件与 renderer 的 UTF-8 输出逐字节一致。
8. 停止本轮服务并重新启动，再次刷新，确认 v2 状态及完整意见恢复。

**复核意见由 Codex 浏览器自动化代填，并在记录内明确标识，不能称为真人签核。**
本轮验证的是本地操作闭环，不证明真实客户资料、技术陈述或文章商业质量已获专业批准。

![v2 记录、CTA 对照与权限边界](seo-article-revalidation-acceptance-2026-10-10/04-v2-record.jpg)

完整证据：[浏览器与文件核对 JSON](seo-article-revalidation-acceptance-2026-10-10/browser-verification.json)、
[完整页面截图](seo-article-revalidation-acceptance-2026-10-10/01-v2-saved-full.jpg)、
[重启后页面状态](seo-article-revalidation-acceptance-2026-10-10/browser-after-restart.txt)、
[实际下载的 v2 Markdown](seo-article-revalidation-acceptance-2026-10-10/novacnc-synthetic-version-2.md)。

## 逐项结果

| 原陈述 | 结果 | 引用与边界 |
| --- | --- | --- |
| CL1–CL2 | 来源绑定已重新核对 | P1 / S1；S 仍是未验证外部背景 |
| CL3 | 来源绑定已重新核对 | 仅 E1 v2；F1；原 locator；字符区间 `[46,239]`；完整原句、条件和限制未变 |
| CL4–CL11 | 来源绑定已重新核对 | P1 / S1；陈述及此前上下文逐字保留 |
| CL12 | CTA 待人工确认 | 显示原 CTA 和新 CTA；没有事实引用；原生技术重放通过后仍需本地明确复核 |

记录绑定原生 Draft 摘要、文章 v2、正文 SHA256、当前 Intake 摘要、规则版本、逐项结果、
意见、明确结论及保存时间。详细来源地址、内容 SHA256、locator、版本与范围绑定见 JSON。

## 实现边界

- 只处理原文不变，或原文唯一末尾 `CALL_TO_ACTION` 的替换且此前全文逐字不变。
  CTA 最多 300 字符、单句、有限请求动词句式。没有特定 CTA 句子白名单或 NovaCNC 放行分支。
  这些句式检查只筛选人工复核候选，不构成语义真实性证明。
- 从原生 Draft 的块与 claim 类型重建相同的临时 specification，调用已有
  `finalize_draft_item`，并核对渲染正文与指定版本完全一致。临时结果不写成第二个 Draft。
- 当前 Intake 必须与冻结快照及 native P/S/operation 范围一致；重新核对活动 E 的内容、
  内容摘要、来源名称、locator、证据版本、F 绑定和引用区间。E 陈述始终独立 E 引用。
- 超出有限正文规则时保守清除当前引用继承，包括修改节标题以扩大范围；没有用局部词汇
  匹配或正文中仍出现原句来宣称整个修订受支持。
- 明确选择“仍有问题”会保持待核验，并覆盖此前的本地完成状态。人工意见不能解除技术阻断。
- 每个文章版本单独核验；即使正文相同，新版本也不会继承其他版本的本地记录。
  Intake 摘要变化后，历史记录保留，当前完成状态失效。
- 核验保存同时锁定文章 journal 和 Intake 快照，重新计算服务端结果并核对表单摘要；
  过期文章、证据和核验表单拒绝。复用现有 loopback Host / CSRF、严格字段和有界输入。
- 新核验 journal 单独保存在 `local-draft-revalidation.sqlite3`，复用严格 dataclass codec、
  SQLite 事务及禁止 UPDATE/DELETE 的触发器；每篇最多 100 条核验记录。
  没有迁移既有 Intake/HistoryStore 或修改原文、修订 journal。

原生技术校验、未认证本地操作员复核、正式可信人工签核、生产授权是四个独立状态。
本轮只完成前两者的可操作记录，可信签核和生产授权始终为 false。

## 验证与审查

相关测试：`tests.test_draft_revalidation`、`tests.test_web_article_review`、`tests.test_web_mvp`、
原生 Draft Review workflow/renderer/readonly、`tests.test_evidence_intake`，
**71 项 / 39.928 秒 / OK / exit 0**。
日志：[targeted-tests.log](seo-article-revalidation-acceptance-2026-10-10/targeted-tests.log)。

首轮完整回归：**1746 项 / 412.236 秒 / failures=1 / exit 1**。
失败为既有 `test_change_plan_workflow.ChangePlanWorkflowTests.test_provider_failure_exception_timeout_and_no_retry`：
10ms generation timeout / 50ms total timeout 场景预期 `GENERATION_FAILED`，实际 `WORKFLOW_TIMEOUT`。
同一用例单独重跑 **1 项 / 0.077 秒 / OK / exit 0**。未修改相关流程、预算或断言；
该结果与两层短墙钟预算的调度竞争一致，但单次重跑不能证明不存在偶发失败。
保留 [首轮完整日志](seo-article-revalidation-acceptance-2026-10-10/full-suite.log) 和
[单独复验日志](seo-article-revalidation-acceptance-2026-10-10/timeout-isolated.log)。

稳定源码的第二轮完整回归：**1746 项 / 488.382 秒 / OK / exit 0**。
命令：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`。
证据：[最终完整日志](seo-article-revalidation-acceptance-2026-10-10/full-suite-final.log)、
[测试验证 JSON](seo-article-revalidation-acceptance-2026-10-10/test-verification.json)。
`git diff --check` 退出 0；Git 的既有 LF/CRLF 提示保留。

新增 10 项聚焦测试覆盖：7200→12000 rpm、删除空载条件、扩大 NCX7 范围、E→P/S 伪造、
替换/撤销证据及 locator/版本变化、完成后再保存文章版本、旧页面提交、未知新增事实、
带数值 CTA、明确人工拒绝、重启、append-only 和 CSRF，以及下面两项审查发现的回归。

另在真实历史文章工作台的临时副本中，先完成 v3 本地核验，再将正文 7200 rpm 改为
12000 rpm 保存 v4：v4 重置待审核及 `PENDING_REVALIDATION`，CL3 无可继承引用，v3 历史
记录保留。全过程禁止网络连接，实际验收工作台仍只有 v1–v3，未写入负例。
证据：[审核后修改正文验证](seo-article-revalidation-acceptance-2026-10-10/post-review-edit-verification.json)。

独立审查发现并实际复现两项问题：节标题扩大范围时仍保留 E 绑定；核验保存与 Intake
更新存在竞争窗口。分别新增先失败的测试并修复，复审无剩余重要问题，审查者独立运行
10 项新增测试通过。

开发中观察到的其他失败：首次测试缺入口/契约；待核验记录刷新未恢复；新增修订文字
字段尚未实现；数值 CTA 被句式层提前拒绝，随后改为交给原生校验拒绝；新增复核结论
字段尚未接入。修复后相关测试通过。验收辅助检查曾假设存在 `candidate/intake.sqlite3`，
以及误要求含追加 check 的 Intake 文件逐字节不变；已改为核对实际文件和全部快照行。
这些失败未计作通过。

既有 Starlette/httpx deprecation warning 等保留，没有更换依赖或削弱断言。

## 本轮修改文件

- `core/draft_revalidation.py`：有界版本核验契约及原生技术重放。
- `storage/content_draft_review.py`：追加核验 journal、文章版本保护。
- `storage/evidence_intake.py`：保存本地核验时保护 Intake 快照，复用既有事务。
- `web/mvp_application.py`：核验结果、保存、版本恢复与失效。
- `web/mvp_routes.py`：指定版本核验记录 POST、严格表单校验。
- `web/templates/mvp.html`、`web/static/mvp.css`：现有文章页的逐项结果、意见、结论及记录。
- `reporting/content_draft_review.py`：指定版本 Markdown 附带本地核验记录及权限边界。
- `tests/test_draft_revalidation.py`、`README.md`、本报告及验收目录。

上述部分文件本轮开始前已有未提交成果，本轮在其上增量修改。没有 Git 写操作。

## 保留与生产阻断

原生候选数据库、diagnostics、v1–v3 journal 和 session 与原工作台逐字节一致；
全部 Intake 快照行相同。既有 `customer_request` 读取流程会追加 Intake check，
因此 Intake 文件整体字节会变化，不宣称其整体不可变。WordPress attempts=0。

没有 DeepSeek/余额请求、外部抓取、WordPress 写入、部署、生产 Gate/P1/PostgreSQL 改动，
没有 commit、push、merge、rebase 或其他 Git 历史操作。

任意事实改写、新事实的语义证据核验、真实客户资料可信审核、正式真人身份签核、
生产文章质量批准及交付授权仍未实现；此功能不能让这些版本进入生产或 WordPress。
本地 hashes 和 SQLite 触发器用于工程追溯，不提供对主机管理员的身份认证或防篡改保证。

重启本轮本地入口：`.\.venv\Scripts\python.exe .data/article-revalidation-20261010/serve.py`。
完成本轮后停止，不自动进入后续功能开发。
