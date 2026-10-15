# WordPress 最小离线交付闭环验收

日期：2026-10-11（Asia/Shanghai）。本轮完成工作台预览、独立 TEST-only 样本经既有 WordPress adapter / delivery workflow 创建 Mock draft、SQLite 留存及浏览器重启验收。真实 WordPress 请求 0、DeepSeek 请求 0、余额查询 0。生产 NO-GO、P1 未修复、PostgreSQL BLOCKED 保持。

## 入口与复现

本次本地入口：

- 真实候选审核：http://127.0.0.1:8021/mvp/article?version=0
- 所选版本交付预览：http://127.0.0.1:8021/mvp/delivery?version=0
- 独立 Mock 交付与记录：http://127.0.0.1:8021/mvp/delivery/test
- 重启后的成功结果：http://127.0.0.1:8021/mvp/delivery/test?sample=success#delivery-result

服务关闭后，从仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.web_wordpress_offline --directory .data/wordpress-offline-20261011 --port 8021
```

默认端口 8012 在本机已占用，第一次启动因此失败；没有终止占用端口的其他服务，改用 8021。验收过程中已关闭浏览器页和本轮服务，随后以新服务进程重新打开成功记录。启动器不加载 `.env`、不装配 FrozenWebExecutor 或任何模型许可；模型生成入口返回 409。该工作台只允许固定内置 MockTransport 发起交付。

本地验收包是既有 `.data/web-deepseek-ready-20261010` 的必要文件副本，仅复制 session、候选 History/Intake、交互 Intake 和所选生成结果/History，不复制凭据或签发新许可。原包所有复制文件摘要保持不变；副本原生文章 History、原始选择/结果也逐字节不变。既有工作台 `evidence()` 会在 GET 时追加本地 intake_checks，故副本交互 Intake 的 SQLite 文件摘要改变，但 intake_snapshots 三条记录与原包逐行相同。第一次全文件字节不变断言因此失败，查明后改用分别核对文章字节、证据快照和本地检查记录，不宣称整个副本只读。

## 实际浏览器结果

| 项目 | 观察结果 | 截图 |
| --- | --- | --- |
| 打开现有审核页、选择 v0、查看预览 | LIVE / PENDING_REVIEW，原始 E1 条件、引用和冻结快照保留；创建按钮禁用 | `01-real-article-blocked.jpg` |
| 独立成功样本创建 | Mock 201，id=701，status=draft；正文与所选样本逐字匹配 | `02-mock-success.jpg` |
| API 拒绝 | Mock 401，failed_definitely，保留受控响应与脱敏错误 | `03-mock-failure.jpg` |
| 未刷新页面再次提交 | 返回已有记录，duplicate=1；没有第二次 Mock 请求 | `04-duplicate-blocked.jpg` |
| 超时 | unknown；无 HTTP 响应、无远端 ID，不推断失败且不重试 | `05-mock-timeout.jpg` |
| 正文 v2 | INVALIDATED；旧 TEST-only 决定失效、按钮禁用 | `06-body-version-invalidated.jpg` |
| 新证据快照 | INVALIDATED；旧 TEST-only 决定失效、按钮禁用 | `07-evidence-invalidated.jpg` |
| 关页、停服、重启、重新打开 | 同一 attempt/id=701/绑定摘要保留，按钮仍禁用 | `08-result-after-restart.jpg`、`09-restarted-result-viewport.jpg` |

以上三次 Mock API 请求均为 `POST https://wordpress-offline.example/wp-json/wp/v2/posts`，请求字段仅 title/content/status，status 固定 draft。没有请求已有文章路径，没有 publish、PUT、PATCH、DELETE 或其他目标站点操作。成功样本是另一篇固定合成文章，不是本轮未批准的 DeepSeek 候选；没有将真实文章、其 E1 或本地审核记录转换为测试批准。

## 请求、响应与持久化

- `success-request-response.json`：完整合成请求，201/draft/id=701 受控响应，以及原生 WordPressDraftAttempt。
- `failure-request-response.json`：完整合成请求、401 受控响应、auth_failed 脱敏结果。
- `timeout-request-response.json`：完整合成请求，response/status=null，unknown/timeout 原生结果。
- `verification.json`：原候选身份、原文件摘要、实际副作用计数和验收检查。

完整本地记录位于 `.data/wordpress-offline-20261011/wordpress-mock/exchanges.sqlite3`；每个绑定的原生 History/Artifact/Attempt 在同目录对应 SHA-256 子目录的 `history.sqlite3` 中。claim 在调用 adapter 前提交，绑定 TEST profile、样本/文章版本、正文摘要、证据全文/摘要、固定目标、精确最终请求和模拟响应类型；result 绑定原生 run/artifact/D1/attempt。SQLite claim 主键及只追加事件阻断同一固定本地 journal 中的重复提交；成功、确定失败、pending、unknown 都不自动重试。崩溃/结果保存失败保留 consumed/pending 状态，提示核对，不伪造成功。

页面表单只接受 CSRF、版本或样本选择和 expected binding 摘要。approval/signature/permission、目标 URL、正文或状态字段一律拒绝。摘要只是并发前置条件，不是授权。凭据使用固定显式离线占位值，不从环境读取；请求观察器不保存 headers/auth，页面、记录和日志均无凭据。单测还使用生产凭据 sentinel 与禁网 socket 验证这些边界。

此 TEST journal 依赖受信本机文件系统，不能抵抗删除、复制、换根目录或回滚；**没有修复生产 P1，也不是生产授权账本**。内置测试决定只供固定 Mock 样本技术验收，不能签发或验证生产人类签核。

## 真实文章阻断与入口

原生 run=`3425b49c-74e2-46aa-a800-27c2b76ed8e7`，artifact=`2559b26b-844b-454a-bd24-ff8d42f0c017`，D1/v0。原包与副本此 run 的 wordpress_draft_attempts 均为 0；当前证据摘要仍为 `8fa01547bce62864ccc4cdf77bd0c4c88de453d40ec9dfd368d2c02efd02aeea`。

1. QUALITY_NEEDS_REVISION：此前真实模型文章的商业质量评估需修订；没有人类质量批准。原生成功和英文可读不构成批准。本轮未修改或重新生成它。
2. TRUSTED_SIGNOFF_REQUIRED：本地操作员未认证，LOCAL_REVIEW_COMPLETE 和本地 revalidation 都不构成可信签核。
3. TEST_ONLY_EVIDENCE：当前 DraftCustomerEvidence 的 review_status 是 TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF，既有 `core/wordpress_draft.py::build_wordpress_draft_request` 明确拒绝交付。没有删掉或伪装该标记。
4. TARGET_NOT_AUTHORIZED：没有配置/批准真实目标站点，页面也不能传入目标。
5. P1_GLOBAL_CONSUMPTION_BLOCKED：已知全局一次性消费保证未成立。历史阻断包含 journal 回滚、换 journal、跨进程不同 journal 双消费，本轮没有重测或修改它们。

本轮工作台的执行入口为 `POST /mvp/delivery` → `OfflineWordPressDelivery.block_real`。它重新读取所选文章和当前证据并比较预览摘要，随后**无条件拒绝生产交付**；拒绝发生在装配生产 publisher、读取凭据、消费生产授权以及发起 WordPress 请求之前。P1 字样是对已知未解决前置条件的诊断，并非新增了一个能验证 P1 的生产检查器。Mock 入口是独立 `/mvp/delivery/test`，无法选择真实文章或解除以上阻断。

需准确区分旧低层入口：`ApprovedWordPressDraftDeliveryWorkflow` 只校验持久化 artifact/D# 并委派交付；其名字不证明它验证人类签核或 P1。既有 `cli.py::_run_deliver` → `runtime.build_delivery_workflow` 也未接入新的可信签核/全局消费服务。既有 workflow 的 fingerprint 唯一约束只对其 HistoryStore 有效，不能声称阻断跨 journal 的生产授权重放。本轮未执行、开放或改造这些生产入口；当前 E-only 原文还会被既有请求构造器拒绝。未来生产开放必须在所有真实写入口、装配 publisher 前统一验证授权，不能只依赖按钮禁用。

## 距真实草稿交付的最小条件

可信签核至少需要来自服务端受信身份源的以下信息，不能由页面自报：

- 有权审核该客户/项目/任务的审核人身份与授权角色，明确的事实语义/适用范围核对及文章商业质量 APPROVED 决定。
- 精确原始 run/artifact/D#、本地文章版本、最终标题与正文/HTML 请求摘要，绑定 Plan/任务版本和证据快照版本及摘要。改正文、标题、证据或目标后重新核验并新签核。
- 被批准的规范化目标 origin（含有效端口），操作目的明确为 create-new-post/status=draft，禁止扩大到更新、发布或删除。
- 唯一签核/授权 ID、签核时间、有效期、受信签发方/验证锚和可验证签核完整性；撤销/过期状态可被服务端检查。不能把本地 TEST 决定、未验证 JSON 或用户填的签名当作这些信息。
- 生产全局一次性消费与持久化交付状态：不能因换 journal、并发或回滚重复消费；调用前提交 pending，成功或 unknown 都禁止自动重发。生产 P1 修复与相关部署验收属独立工程任务。

此外，需要正式客户证据的生产用途准入合约、合法的固定 WordPress 目标与安全凭据配置、必要部署/存储验收（包括当前 PostgreSQL 阻断），以及用户对**该确切版本、该目标的一次真实草稿创建**明确授权。当前内容渲染仅作为阻断预览，不能据此宣称已建立修订稿到生产原生 Draft 的可信签核/交付映射。

本轮没有新增生产放行分支、临时生产白名单、CMS 系统、账号/支付、多租户或安全框架。

## 文件与验证

新增：

- `web/wordpress_delivery.py`：预览、生产硬阻断、固定独立 Mock 样本及既有 adapter/workflow 装配。
- `storage/wordpress_mock.py`：隔离 append-only claim/exchange/result 记录。
- `web/saved_article.py`：只读选择已有 MOCK/LIVE 结果，禁用模型执行。
- `web/templates/mvp_delivery.html`：预览、阻断、Mock 与持久化结果页面。
- `scripts/web_wordpress_offline.py`：本地离线启动器。
- `tests/test_web_wordpress_offline.py`：16 项功能及安全边界测试。

小范围接入已有 `web/mvp_application.py`、`web/mvp_routes.py`、`web/templates/mvp.html`、`web/static/mvp.css`。其余用户已有修改未覆盖；没有修改现有 WordPress adapter/domain/workflow、生产 Gate、P1 或 PostgreSQL。

实际测试：

- 首轮新模块 15 项中 1 项断言失败，原因是错误假定质量阻断总排第一；保留缺证据环境的更高优先级核验阻断，修正断言以检查质量阻断仍存在。
- 相关 78 项，42.046 秒，OK：`tests.test_web_wordpress_offline tests.test_wordpress_rest_adapter tests.test_wordpress_delivery_workflow tests.test_approved_wordpress_delivery_workflow tests.test_web_article_review tests.test_draft_revalidation tests.test_web_mvp`。
- 最终新模块 16 项，6.701 秒，OK，含离线启动器拒绝模型请求的新覆盖。
- 首次完整 discover：1,787 项 / 381.899 秒 / exit 1，1 failure、0 errors。失败为既有 `test_change_plan_workflow.ChangePlanWorkflowTests.test_provider_failure_exception_timeout_and_no_retry`，期望 GENERATION_FAILED，实际 WORKFLOW_TIMEOUT。日志保留于 `full-regression-first.log`。该分支的 generation_timeout=10ms、total_timeout=50ms；单独复现 1 项 / 0.106 秒 / exit 0，见 `timeout-repro.log`。疑似调度负载相关，但单次复现通过不足以证明根因；没有修改该测试、超时值或工作流。
- 第二次完整 discover：**1,787 项 / 368.941 秒 / exit 0，OK，0 failures、0 errors、0 skips**；本次不并行运行其他测试或操作浏览器。准确命令为 `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q`。结果见 `verification.json` 与 `full-regression.log`，首次失败日志仍保留；没有删除断言、放宽超时或修改 Change Plan 实现。
- 出现既有 Starlette/httpx deprecation warning 与 asyncio slow-task diagnostics。完整日志中的 argparse/端口提示来自负例测试的受控输出，最终 unittest 结果以运行次数及 OK/FAILED 汇总为准。
- `git diff --check` 退出 0，有仓库既有 LF/CRLF 提示。没有 commit/push/merge、部署、生产 API、客户抓取或新的生产授权申请。

验收完成后停止后续工作。8021 的本地离线服务保留供查看；没有定时任务、自动请求、授权申请或生产执行。
