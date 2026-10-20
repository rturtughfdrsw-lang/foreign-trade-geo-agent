# Commercial Dev 本地开发反馈

范围：只扩展 Commercial Inspector，不接入模型、生产审批或 WordPress。

## 实施设计

沿用 HistoryReader 及现有 codec 读取真实 Run、Source/Evidence 和 Draft。
从 Run 页面选择 artifact，或直接对 Run 记录意见。正文和来源对象均来自
所选 Run，不创建示例文章。缺少 Draft 或接口时保持明确空状态。

原 Review 契约承载文章修订与复核状态；本功能使用独立追加式日志，避免
将未认证的本地意见误认成可信审批。唯一类型为 `LOCAL_DEVELOPER_FEEDBACK`。
只有“需要修改”和“观察意见”，没有“通过”或“批准”。

## 绑定与保存

固定数据库：本工作目录 `.data/commercial-feedback/feedback.sqlite3`，不使用
History 数据库或 VDemo 数据库写入反馈。GET 不创建数据库。

每条意见包含数据库标识、Run UUID、artifact UUID（或 `run`）、payload
版本、完整规范化对象的 SHA256、意见、需修改内容、提交 UUID 和 UTC 时间。
Run 的摘要包含运行状态；artifact 摘要针对已有 codec 解码后规范化的完整
payload。它不是原始文件字节签名，也不是可信人工签名。

保存时重新读取并校验对象归属、版本和摘要。表单用进程内 CSRF token、
绑定对象的 HMAC 及一小时有效期；仅接受 loopback 的 URL 编码 POST，
检查 Host 和可用的 Origin。每个文本字段最多 2000 字，整个请求最多
64 KiB。服务重启使旧表单失效，重新打开即可填写。

提交 UUID 实现重放幂等；POST 后 303 跳转，刷新只读取。SQLite 单事务追加，
UPDATE / DELETE 触发器拒绝改写。每个对象最多 200 条意见，页面显示最近
100 条；旧版本意见保留且明确标记，不自动套用到当前版本。反馈写入失败
返回错误，不显示成功。页面内容转义，CSP 限制表单提交到本站。

## 授权边界

反馈日志不注入 Admission、Evidence Intake 或可信 Review 端口。
`ProductionDraftAdmission` 保持 `DRAFT_EXECUTION_AUTHORIZATION_REQUIRED`。
本功能没有用户认证、可信签名、正式批准、Gate GREEN 或发布能力。
原 Phase7 / EXPLAIN 文件报告仍只读；当前表单只绑定原生 Run / artifact，
尚未提供报告文件或独立 Intake snapshot 的反馈接口。

## 验证

`tests.test_commercial_feedback` 使用临时 SQLite 和既有离线 fixture，覆盖
真实列表与 Source/Draft 关联、持久化与新 app 实例读取、重复提交、追加
历史、跨 Run 拒绝、错误版本与摘要、Run 状态变化、Host/CSRF/Origin、
非本机 POST、XSS、请求预算、磁盘失败及生产 Gate 不变。
现有 Inspector、History、Evidence Intake、生产执行边界和文章修订测试
作为回归。实际桌面与浏览器验收记录另存本机独立审计目录。

最终上述六个测试模块实际运行 **104 项通过**。未运行全套仓库测试。
VDemo 基线验证显式绑定自身源码，10 个模块 **135 项通过**；阶段一的
Commercial Inspector / Intake / 执行边界验证 **42 项通过**。
早期测试暴露 DraftItem 没有 title、heading 可空及失败报告无文章的显示
问题，已按原契约修正并回归，不放宽旧验证。

桌面两个快捷方式实际双击成功；Commercial 在确认进程归属后冷启动，
VDemo 复用原进程。8003 本机 HTTP 保存开发意见、刷新只读及真实服务
重启后读取通过，意见只有一条；8002 原成功文章仍可读取。
内置预览浏览器表单点击没有发起请求，切换桌面 Edge 时，Windows
自动化因无法可靠确认当前 URL 而停止。因此真实浏览器“点击保存”
**尚未验收**，不能用 HTTP 测试替代这一结论。需用户在桌面浏览器再
完成一次保存、刷新并确认意见可见。

已有原始模型输出、实验 JSON/锁文件/日志与依赖这些归档的实验重放数据
没有批量纳入基线提交。源码和实验报告保存不表示实验通过生产验收；
恢复实验须同时使用独立备份中的原始归档。
