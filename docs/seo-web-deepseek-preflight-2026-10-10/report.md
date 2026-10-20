# Web 单次 DeepSeek 实验：离线集成预检

**READY：浏览器离线集成通过，完整回归 1771 项通过；仅等待新的明确 TEST-only Web 授权。** 准备的是新的 SYNTHETIC / TEST-only Web 实验，不是生产能力或真实模型效果验收。本轮 DeepSeek 真实请求 0、余额查询 0、WordPress 写入 0；没有部署或 Git 写操作，临时预检服务已停止。

## 调用路径审计

既有 `/mvp/generate` 路由只接受 `csrf_token` 与 `binding_sha256`。原有 `LocalGeneration` 必须显式注入 `MockArticleExecutor`；它重新构造当前合成任务的请求，以请求/快照摘要命名本地 reservation。GET 生成的五分钟 ticket 只是防过期提交窗口，会随页面访问更新，不能作为付费模型许可。

旧 `prepare_seo_article_experiment.py` / `prepare_seo_e_only_experiment.py` 从 CLI 载入冻结输入，校验源码与输入摘要，使用目录内 `live-attempt` 占位并调用 retained receiver。其 `prepare_web_preview` 只把成功结果复制到 Web 展示包，不支持浏览器发起模型调用。历史真实 CLI 运行甚至曾被原生 Finalizer 拒绝，不能当成 Web 成功。本轮没有调用旧 CLI live 入口，也没有复用旧授权。

生产 `runtime.build_planning_workflow` 的 admission 和 `DeepSeekContentDraftWriter` 的直接网络限制保持原状。新独立启动器复用 `content_draft_request_payload`、`OneShotTransport`、`receive_candidate` 的请求构造、准确字节限制、响应安全扫描和原样留存；模型正文交给 `ContentDraftWorkflow(CapturedWriter, max_repair_attempts=0)`，随后复用 SQLite History 与原生 Review。生产 Writer/Gate 不承担这次实验授权。

实际新路径：浏览器点击现有表单 → 服务端冻结包与当前 Intake 校验 → 独立 SQLite permit commit → `MockTransport`（将来明确授权后才能装配真实 transport）→ 原生 Draft → 独立 SQLite → `/mvp/article`。不是重新运行 CLI 生成。

## 实验许可与安全边界

- `storage/web_experiment.py` 是独立服务端账本，不读写 P1 或 Intake 授权。LIVE 固定在 `%LOCALAPPDATA%/foreign-trade-geo-agent/web-experiment/permits.sqlite3`，没有浏览器或启动参数覆盖路径；Mock 用单独离线测试账本。
- permit ID 与 bundle 都有唯一约束，绑定服务器绝对目录、请求 SHA-256、模式、明确截止时间、预算 1。没有更新、续期或重发接口；LIVE arming 的截止时间必须在未来一小时以内。
- `BEGIN IMMEDIATE` + `synchronous=FULL` + 显式 commit 成功后，才创建结果目录和执行任务；凭据读取和真实 transport 创建更晚。commit、目录或持久化失败也不会退还已消费许可。
- 浏览器不能提供模型、密钥、许可、截止时间、路径、journal 或 live 开关。重复 POST、并发页面、独立服务对象、进程重启均不重新调用。没有 resume-request 或自动 retry。
- 服务端持有完整冻结原生输入、任务快照和确切请求字节；启动、提交、执行前和候选保存前核对当前快照、Plan、P/S/E 与源码。HTTP guard 只允许确切 endpoint / POST / body，一次请求且无 redirects / transport retries / trust_env。
- TEST-only 结构复核只刷新内部五分钟 freshness 时间戳，每次要求当前快照摘要一致、原生输入有效且重新构造的请求逐字节不变。它不改变冻结证据、续期 permit 或产生人工语义签核。
- Validator 拒绝留存原始 envelope、原样 rejected candidate、usage、诊断；不选为成功文章。超时和断连为 UNKNOWN，候选保存或 await 后版本改变为 INCOMPLETE。完成诊断不能保存时为 UNKNOWN / RETENTION_UNCONFIRMED；可能存在原始文件，但不宣称成功、不推算 usage、不重试。
- 生产 Draft、WordPress 和人工签核权限始终为 false。生产入口未新增此 executor；只有独立 operator launcher 装配它。

已知 P1 问题仍未修复：历史记录显示换 journal、回滚 journal 和跨进程不同 journal 可以重复消费。新 Web 路径不读取这些 receipt，不使用它们授权；固定独立账本 + bundle 唯一约束 + 服务器目录绑定阻断同一许可通过复制 journal 重用。单测另起两个 Python 进程，仅一个 CLAIMED，另一个 REJECTED。

本实验信任本机操作员和服务器文件系统。它不抵抗同账户恶意篡改程序、修改系统时钟、删除/回滚固定许可账本；不得备份恢复该账本以重用许可。缺失或不可读取账本 fail closed。这不是生产级抗回滚授权系统，也没有宣称解决 P1 / PostgreSQL。若将来要求对恶意本机管理员或权威账本回滚也成立，需要另行设计；不能据此开放生产。

## 浏览器验收证据

最终源码上的实际 UI 操作和截图在 `browser-evidence.json` 与 `browser-*.png`；服务端记录核对在 `verification.json`。原始测试材料在 `.data/web-deepseek-final-20261010/`，均为合成资料。

| 场景 | 观察结果 |
| --- | --- |
| 成功 | 点击后 RUNNING → SUCCEEDED；1 次 Mock；SQLite Draft / Review；Web 正文有 E1 → CL3 |
| Validator 拒绝 | VALIDATION_FAILED；1 次；原始响应、拒绝候选、Mock usage、诊断保留 |
| HTTP 503 | REQUEST_FAILED；1 次；错误响应保留，无成功候选 |
| 超时 | UNKNOWN；1 次；禁止重试 |
| 无 usage | SUCCEEDED；usage=null，页面明确未返回，不编造数值 |
| 并发重复点击 | 两个浏览器页面同时点击，同一 permit 只调用 1 次 |
| 重启后重复提交 | 终止并重启服务器，浏览器通过 offline-only replay 表单 POST 同一冻结请求；次数仍为 1 |
| 断连 | ReadError 模拟及关闭浏览器页面后重新访问均不重发；UNKNOWN |
| 版本过期 | 另一浏览器页更新 E 版本，旧生成页提交被拒绝；permit 未占用，模型调用 0 |
| 结果留存失败 | 原始 response / model text 留存，完成诊断注入失败；UNKNOWN，未选择候选，许可已消费 |

replay 表单仅存在于 `web_deepseek_offline_preflight.py`，不会进入普通 Web 或 LIVE 启动器；它使用新进程 CSRF，仍 POST 现有生成路由且不创建许可。原生权限、WordPress、秘密输出拒绝和既有文章编辑流程继续由针对性与完整测试覆盖。

## 新冻结包

运行目录：`E:/Codex程序/foreign-trade-geo-agent/.data/web-deepseek-ready-20261010`。资料保存和 recheck 已由实际浏览器完成，没有点击生成，没有签发 LIVE permit。冻结文件副本位于本报告旁的 `frozen/`，运行目录的文件保持原样。

| 项 | 冻结值 |
| --- | --- |
| Bundle SHA-256 | `f573be4c0cf539984c9ba1c4cdf13856fdf3a02fc3c4adcfa0737ffd27bf99c0` |
| 请求 SHA-256 | `8ed4e1fa85f01505193d899879e1399154a9f913398a34edbef355d949a35734` |
| 源码清单 SHA-256 | `1f66a0bbc3375192dae267ec7f634b231d41a4d0343aad9ea72f20317f15f09f`，156 个源码/模板/资源摘要 |
| 原生输入 SHA-256 | `e54dc75a389c72b8b1949e43292b761b7f9e8016706d7d7d2b27df15d15d8e3d` |
| 客户 | `SYNTHETIC-NOVACNC` |
| 项目 | `5b98ca0e-b0a3-45f2-bc93-d7ac14b6243b` |
| 任务 / Plan ID | `2fd1d50c-d1c1-46fb-841c-228ffcdbf445` |
| 版本 | task 1 / Plan 2 / E 2 / revision 3 |
| Intake SHA-256 | `8fa01547bce62864ccc4cdf77bd0c4c88de453d40ec9dfd368d2c02efd02aeea` |
| 模型 / 参数 | deepseek-flash / thinking disabled / temperature 0 / max_tokens 3000 |
| 请求大小 | 11,412 UTF-8 bytes；system 6,895 bytes，user 4,034 bytes |
| 执行上限 | 1 request、60 秒；请求 ≤16,000 bytes、响应 ≤65,536 bytes；自动重试 0 |

`native-input.json` 完整包含 Plan、P/S 和 E 证据及引用范围；`snapshot.json` 包含确切任务和全部证据版本。摘要是完整请求的冻结，不是仅冻结页面显示的标题。没有做 tokenizer 精确计数或模型质量验收。

本轮禁止联网，因此费用采用明确的离线预算假设：输入预留 16,000 Token、输出 3,000 Token，假设输入 ¥10/百万 Token、输出 ¥20/百万 Token，得 ¥0.22；建议预留 ¥1。**这些是假设单价，不是当前 DeepSeek 报价，也不是账户侧金额封顶。** 当前费率未查询，真实 usage / 计费均未知。未来执行前如费率不能确认在该预算内，停止并重新确认，不查询余额。

## 将来明确授权的方式

必须由用户在聊天中重新明确给出以下内容，不能复用任何旧 CLI / P1 授权：

> 授权 bundle `f573be4c0cf539984c9ba1c4cdf13856fdf3a02fc3c4adcfa0737ffd27bf99c0`，许可 ID `WEB-TEST-F573BE4C-ONCE`，仅从 Web 点击发起一次真实 DeepSeek 生成。截止北京时间【明确日期时间，签发时起不超过一小时】，总请求预算 1，超时 60 秒，无自动重试，异常/UNKNOWN/INCOMPLETE 后停止。仅 SYNTHETIC TEST-only，不授权生产 Draft 或 WordPress，不查询余额。接受上述费用估计及其限制。

用户授权后，由受信任本机操作员执行（`<带时区截止时间>` 必须取用户给出的确切截止时间，例如 ISO 8601 `+08:00`）：

```powershell
.\.venv\Scripts\python.exe -m scripts.web_deepseek_experiment arm-live --directory .data/web-deepseek-ready-20261010 --bundle-sha256 f573be4c0cf539984c9ba1c4cdf13856fdf3a02fc3c4adcfa0737ffd27bf99c0 --permit-id WEB-TEST-F573BE4C-ONCE --expires-at '<带时区截止时间>'
.\.venv\Scripts\python.exe -m scripts.web_deepseek_experiment serve-live --directory .data/web-deepseek-ready-20261010 --bundle-sha256 f573be4c0cf539984c9ba1c4cdf13856fdf3a02fc3c4adcfa0737ffd27bf99c0 --permit-id WEB-TEST-F573BE4C-ONCE --port 8011
```

arm-live 只签发本地 permit，无 HTTP；serve-live 只启动 localhost 服务，不生成。随后浏览器访问 `http://127.0.0.1:8011/mvp/generate`，核对冻结摘要、版本和截止时间，再点击明确标注 TEST-only 单次真实调用的按钮。只有该 POST 才消费许可并发起模型请求。本轮两条 LIVE 命令均未运行，没有创建 LIVE transport 或加载真实密钥。

源码、输入、证据或任务发生变化必须重新冻结、重新取得明确授权；不能给旧许可续期或换 journal 重用。没有 usage 时保持未知，不查询余额推算。实验完成后停止，不自动尝试第二次。

## 变更与验证

新增 `storage/web_experiment.py`、`web/experiment.py`、两个独立 launcher 和 `tests/test_web_deepseek_experiment.py`。局部修改 `web/generation.py` 的 workflow 名与异常状态扩展点、`web/mvp_application.py` 的隔离候选读取及模式标识、两个 MVP 模板的状态与来源说明。保留开始时所有已有未提交变更。

针对性测试：`python -m unittest tests.test_web_deepseek_experiment tests.test_web_generation tests.test_web_mvp tests.test_web_article_review -q`，45 项通过。新增 14 项，包含跨进程竞争、缺失账本、占用失败、源码/请求篡改、任务/Plan/E 变化、await 后变化及完全 Mock 的 LIVE 分支装配测试。

最终完整回归：`python -m unittest discover -s tests -p "test_*.py" -v`，**1771 项通过，362.318 秒，退出 0**。日志 `full-regression.log`，SHA-256：`8f80d86f28ffd535e5549b44848a854878a14b3b4dcbbf3dc6ac3e627ffa08f8`。`git diff --check` 通过；有既有 LF/CRLF 提示。完整回归后再次核对冻结文件与全部 156 个代码摘要一致，新待授权运行目录没有 generation reservation。

迭代中出现并已修正：SQLite connection context 未 close 导致 Windows 临时文件占用、测试误用 Reader API、刻意不一致任务导致错误页 503 与预期 409 的测试断言。最初一次完整回归因已知测试断言修正被中止，不作为通过证据。已有 Starlette/httpx deprecation warning 未处理。

仍未验证：真实模型返回质量、真实 usage / 计费、生产身份与语义签核、生产一次授权抗回滚、PostgreSQL、WordPress 和部署。本轮没有扩展这些范围。
