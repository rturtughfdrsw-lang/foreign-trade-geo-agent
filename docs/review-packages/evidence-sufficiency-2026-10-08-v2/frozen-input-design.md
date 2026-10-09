# 同一审核冻结输入的端到端消费（设计，未实现）

目标：消费审核时冻结的同一 task、合法 Plan 与 bounded evidence，不重跑 crawl/search/research/Opportunity/Plan 替换输入。当前没有合法且批准的匹配 Plan，本附件不是可执行 resume。

## 可复用接口与缺口

`EndToEndWorkflow.run(EndToEndRunRequest)` 每次新 run，从 crawl 经 Research/Opportunity/Plan，立即构造 ContentDraftInput 调 DraftWorkflow。request 只有 site/question/language，没有冻结包或审核 record，`_run_stages` 没有 Planning 后人工暂停；使用这条入口会重新 Planning 而丢失审核绑定。

已有 `HistoryStore.get_artifact/get_run/get_analysis_run_input/list_artifacts`、只读 `SQLiteHistoryReader`、codec 可加载确切 artifact；`ContentDraftInput(site_content, opportunity_report, change_plan_report, target_language)`、`ContentDraftWorkflow.run` 已消费固定对象。Draft safety/all-or-nothing/budgets 和 append/finish 可复用，不需再请求 LLM 规划。

但现有 DraftInput 无 task/义务/reviewer，stable validation 不验证审核，保存 Plan 不代表批准。接口能传对象不代表可信准入已实现。

## 推荐最小流程

增加独立“从审核冻结包生成”用例（概念 `ReviewedDraftRunRequest`，非现存 API），直接复用 Draft workflow 和历史 ports，与现有全链入口明确区分。不用 fake Planning workflow 冒充 resume，也不选完签核 Plan 再跑 `_run_stages`。

1. **合法冻结后再审核。** 后续条件契约实现后，按原 finalizer/availability 产生匹配 Opportunity/Plan，保全实际 bounded input，分配明确 IDs/version 后签核。不需收费 provider 产生确定性候选，但合法校验必须运行；本包批准不继承到新 Plan。
2. **可信选择。** 操作者明确选 bundle ID/digest 和真实 review record；runtime 从受控记录通道取得权限/用途/时效，不从 P/S/provider 解析 approved。归因支持/任务范围与技术专业审核权限分开。
3. **明确加载。** 按 IDs/type/version，不用 latest/P3/C1 单号；核来源 run/site/language、全文/截断状态。通常同一 freeze run；跨 run 组合须冻结前显式 lineage 并整体重验/审核，旧失败/success 都不代批准。
4. **全量 preflight。** codec、原 stable validation 后，再检查全部 EXPLAIN/task/policy/绑定/span/身份/覆盖/verdict/expiry。未审/不足/错绑均 writer=0，不重抓/Planning/repair；未审和已确认不足分类分开。
5. **同一输入生成。** 从核验的 immutable packet/opportunity/plan/language 构造一次 DraftInput，交既有 workflow，brief/context 是独立附加输入。审核答句不变为证据；prompt 若缩减必须确认所需原文仍在实际 material，否则拒绝或新包重审，不能仍称同证据。
6. **独立执行保全。** 新 child run（新的 workflow_name），复制合法上游 payload，保留原来源 IDs/digests 和 bundle/review 链路；成功才 append Draft，失败保留上游/finish FAILED。沿用诊断/budgets，补 brief/digest/义务定位；不存 raw provider response/secret。本轮不写 DB。
7. **生成后审核。** 准入不证明逐句支持/完整任务，独立审归因、六义务、禁止扩展/重复/增量；收费生成或 WordPress draft 另授权，WordPress 独立 create-only/draft-only。

## hash、身份和 lineage

目前无可复用充分性 hash API；本包仅离线绑定。未来 core 纯确定性投影绑定 task/义务、完整所选 operation/language、bounded packet/opportunity/plan、截断/可信约束，不导入 storage 或读 DB。

审核 provenance 同时绑定原 freeze artifact IDs/type/version/digest。新执行 run ID/复制 artifact 新 IDs/时间属于 execution lineage，不替换审核对象的原来源身份；复制 payload 等值，明确从哪份批准包执行。不要把新 IDs 塞回旧审核对象再声称 hash 未变。若设计坚持审核绑定目标执行 IDs，应先分配/保存目标输入再签核，执行不可重分配并沿用旧批准。

原 artifact/run 不改，旧失败不升级 success。优先保持 V1 codec/schema；独立 sidecar/envelope 保存 bundle/review/来源链路，sanitized run 摘要放固定 ID/digest 可定位。process-local RunDiagnosticContext 不够；sidecar 重启后不能读取仍是 blocker，不能用临时属性假称追溯完成。

审批记录引用 binding，不参加自己的输入哈希，避免签字后循环变 hash；record 摘要另在 execution lineage 保存。task/Plan/evidence/language/义务/实际 prompt 必需材料改变、到期或权限撤销则新冻结/重审；有效期由所有者指定，不发明天数。

## 最小改动面与后续验证

runtime 可信 frozen loader/请求选择；workflow 新固定输入执行/保全用例复用 DraftWorkflow；core 纯附加 brief/binding 检查；CLI 明确 frozen selection/现有 diagnostic 分支。旧 request/run 默认不变，不隐式 fallback 或选最新包，不扩展 UI/GEO/WordPress，不重认证历史。

后续 focused 离线验证：crawl/search/Planning spies=0；writer 实收对象/digest 等值；错绑/过期/第二任务不足均 writer=0；child lineage 重启可查/原 payload 不变；失败无 Draft；Plan/语言/截断一字符变化拒绝；历史 decode/review 保持。**本轮未运行这些设计场景，未假造 approved Plan 来证明通过。**
