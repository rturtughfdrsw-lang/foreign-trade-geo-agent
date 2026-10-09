# P-only 可信审核 preflight：设计与执行计划

范围：独立离线 ATTRIBUTED_EXCERPT，完整原文、来源归属、虚构演示声明；不认可工程事实、SEO 成效、商业 placement、EXPLAIN/comparison 或 CMS 操作。真实 O1–O6 不自动审批，不生成 Draft，不访问网络，不 commit/push。

## 已核对的链路与复用

冻结 SITE_CONTENT → 显式 FirstPartyPlanningScope（任务、P、heading、完整字段和精确 Unicode spans）→ 原生 Opportunity validator → ChangePlanInput → prompt/catalog → Plan finalizer → V1 codec → ContentDraftInput。默认 Draft 按无 scope 的 ChangePlanInput 重验，返回 FIELD_CONTRACT，writer=0。此次新增 preflight 用同一 upstream validator 和 finalizer重建 C1，并比较完整 operation，避免平行实现 Planning 规则。

`ContentDraftReviewWorkflow`、reporting/CLI review 仅 inspection；WordPress deliver 的用户动作只授权 create-only/draft-only；SQLite append-only 约束不认证 reviewer。都不能作为 sufficiency 签核来源。没有已配置的审核身份服务、信任根、签核存储或撤销服务。

旧冻结 coverage 顶层为 excerpt-v1/version 1；六行义务为 excerpt-v2/version 2。旧 verifier 只检查行级绑定，遗漏顶层差异。保留旧包字节，新审核包显式更正 lineage；不得把旧包直接当作有效签核记录。

## 设计与威胁模型

选择新增独立离线 preflight，保持 native Draft 拒绝。直接把 JSON 的 APPROVED/digest 当权限会被本地篡改；将 review 字段加到现有 artifact 会改变历史语义。两者不采用。

新增 core bounded 任务/义务/身份契约，adapters 的严格 review loader，以及 workflow preflight。loader 每次经注入的 EvidenceReviewAuthenticator 验证原始 record bytes 和 detached proof，再接受其返回的身份及权限。权限来源必须在审核包外，不能从 record 自声明；默认无 authenticator 则拒绝。冻结 digest 仅用作签名绑定的完整性标识，不能证明权限。所有实际 input 用既有 V1 codec 序列化，冻结对象同时包含任务问题、版本、使用限制、归属、scope、义务分组及完整 DraftInput。

外部 authenticator 必须验证签名/认证来源、当前 identity/key、撤销、项目与任务权限及时间。它是受信任 composition boundary；任意代码执行或替换该依赖不在包级攻击防护范围内。生产 adapter 尚不存在。只在 tests 内实现随机内存密钥的 HMAC authenticator 和 synthetic grant；没有仓库测试密钥、生产 signer、环境变量开关或 CLI/Web 放行入口。synthetic 身份由 authority 提供，不能由 JSON 改成生产身份；默认 preflight 拒绝 synthetic，测试显式离线模式仅返回 SYNTHETIC_GREEN。非 synthetic 的可信审核最多返回 OFFLINE_REVIEW_GREEN，仍无 native Draft 放行能力。

拒绝无审核、部分/缺失/重复义务、reason 缺失、非 APPROVED、未知字段/重复 JSON key、伪造/错误 proof、无 identity、身份不符、权限不符、时间过期/未来/naive、不符 task/Plan/evidence 版本、input 或 scope 变更、错误 P/locator、EXPLAIN/comparison、S/A 混入。离线 preflight 不持有 writer；默认 Draft workflow 的 writer=0 另作真实验证。审核不是 writer 许可，更不是 output 支持度检查。

## 最小实现与验证步骤

1. 生成新的逐项人工材料、待签核模板及正确版本的冻结 target；保留旧包和工作区所有既有文件摘要。
2. 先写行为测试，观察缺少 preflight 的 RED；实现 core 验证、严格 loader、默认拒绝 workflow。测试独立 synthetic 物流素材，不签核真实 O1–O6。
3. 验证真实冻结材料在默认 Gate 与 native Draft 都拒绝；synthetic 正例完整通过，负例全部拒绝且 writer=0；覆盖重新加载、codec/history 兼容性。
4. 运行针对性 unittest 与完整 discover；记录实际输出及失败。核对旧文件摘要、最终 diff 与信任边界。

执行记录：12 项初始测试在缺少 preflight 时全部 FAIL；初版 11 PASS/1 ERROR，根因为六点 Plan 的既有结构校验在 EXPLAIN 负例构造时已拒绝。调整为四点测试对象，实际到达新 Gate 后拒绝；未放宽生产边界。随后12项通过。最终补充新审核包直接消费/拒绝测试，并将 synthetic fixture 调整为六义务/七片段；13 项新测试及357项相关测试通过。完整最终回归结果另见完成报告。

`requesting-code-review` 技能要求的独立只读审查：无 critical/important findings；一个新包直接回归测试的缺口已补充。审查者独立检查新包 target/codec/digest/版本、NOT_REVIEWED 和默认拒绝。生产身份/签名/撤销、可信时钟、append-only review storage 因未存在而未评为生产就绪；这些缺口的裁定是继续 NO-GO。此次技能的 commit、额外审批或通用流程不适用于用户明确禁止 commit、要求直接完成已授权离线工作的范围。

## 生产前置条件与 GO 条件

项目所有者完成 D01–D07 的具体离线任务签核及 O1–O6 支持判断；D08 商业验收另外处理，不能由本离线授权继承。必须另行选择可认证 reviewer 的服务/受保护密钥、权限管理员、撤销/过期政策、受保护 append-only review lineage、可信时钟及重启消费规则。签核系统须保存人工判断而非代替人工判断。之后才讨论另行授权的 Draft 消费接口及输出逐字/全部覆盖校验；本轮不接入该入口。
