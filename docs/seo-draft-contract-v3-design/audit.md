# Phase 0 — v2 audit (2026-10-12)

审计先于代码修改完成。本轮只新增隔离离线模块、测试和本目录产物；现有生产文件、v2、Gate、Validator 和历史实验全部保留原字节。用户明确要求的新增 core 文件不接入 runtime 或生产调用链。

## 实现位置

| 层 | 位置与行为 |
|---|---|
| Explanation parser | `scripts/prepare_seo_draft_v2_flash_preflight.py:parse_experiment_response` 严格解码 candidate/explanations；原生 `_parse_specification` 解析 candidate，再构造 v2 标注。失败映射为 `PREFLIGHT_RESPONSE_INVALID`。 |
| Sidecar validation | `core/draft_explanation_contract.py:ExplanationAnnotation` 检查 20/12/20 词、总 60–160 词；`validate_explanations` 检查 hashes、claim/section、selected refs、正文及固定边界/行动位置。`storage/draft_selection_contract.py` 提供严格 v2 codec。 |
| Prompt injection | `scripts/prepare_seo_draft_v2_flash_preflight.py:SYSTEM/build_request` 注入专用离线 v2 提示和 selected-only 材料；不是生产 DeepSeek adapter 的升级。 |
| Writer projection | `workflows/draft_contract_v2.py:build_offline_writer_material` 保留规划上下文、只投影 selected facts；`assert_writer_boundary` 检查等值及未选证据泄漏。 |
| Offline inspection | `workflows/draft_contract_v2.py:inspect_offline_candidate` 保留原生证据检查、routing、budget、reservation，最多进入 `PENDING_SEMANTIC_REVIEW`。 |

## 实际产物

读取 `docs/seo-draft-v2-flash-quality-live-2026-10-12/` 的 `article-reading-view.md`、`model-output.json`、`parser-diagnostics.json`、`candidate-validation.json`、`report.md`，并核对冻结 parser/prompt 实现。explanation annotations 位于模型 envelope 的 explanations 数组及 parser diagnostics，并无独立 annotations 文件。

HTTP 200/stop 不代表内容合格。原实验 parser FAIL，最早原因 `EXPLANATION_PART_DEPTH`，Validator/Finalizer 均 NOT_RUN。CL6 分段 40/7/7 词；全部六条边界/行动均压缩，CL6/CL11 总词数不足。最后 sidecar 指向 CL33 CTA，实际 interpretation 为 CL32。每章一个 interpretation，selection 要求两个。S4 CL21 写 `different coupon counts`，证据实际均为三个 coupons，区别是连续性及程序约定，不是数量不同。

## A/B/C/D 归因

| 分类 | 结论与证据边界 |
|---|---|
| A Contract failure | 输出违反 v2 分段深度、总长度、标注绑定和解释 reservation。词数代理能拦截压缩，但不能证明采购因果机制，存在填充诱因；这不证明 v2 内部矛盾。 |
| B Prompt failure | 提示已说 WHY/采购目的，也明确词数/编号，模型未遵循；大量并列格式要求和固定 limitation/action 容易形成复述式输出。v3 应让证据→决策变化→适用边界→责任/材料/下一步决定成为显式关系。单样本不能证明提示改法的因果效果。 |
| C Model reasoning failure | CL21 的数量比较有可复核的证据矛盾；S3 对小样本/排除装卸的决策影响不足，验证步骤通常未明确责任/交付物。是该次输出问题，不推断模型能力上限，也不换模型。 |
| D Validator 问题 | 未建立误判：实际 Validator 未运行。首个拒绝发生在 parser 构造标注时。不能把结构通过当作语义正确，也不能为旧失败放宽生产验证。 |

## v3 设计约束

保留 buyer_implication / non_applicability / verification_action；新增证据引用和有向关系、决策对象、边界认知状态、验证责任与材料。词语只能生成诊断或保守拒绝，不能赋予 PASS。PASS 仅指可追踪、可复核的结构完整，人工仍须判断因果、相关性及未测试是否被错误写成失败。任意自由文本的真实语义不能由离线确定性检查完全证明。

后续先记录现有文件 hash，再新增 v3；若任何原有文件字节变化立即停止并报告。无 API、WordPress、部署、commit/push。
