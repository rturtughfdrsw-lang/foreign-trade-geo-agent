# 六项完整摘录：原生 Planning 候选 v2

本轮解除摘录容量阻塞，**六项完整原文已通过两个生产 Planning workflow**。注入的离线 writer 选择真实候选 ID，Opportunity 与 Plan 分别经过原生 parser、validator、finalizer 返回 SUCCESS；不是手填 SUCCESS。O1–O6 全部 **NOT_REVIEWED**。没有实现 Gate，没有 Gate GREEN，没有生成文章。

任务保留 v1 的问题、六义务、语言和输出约束，仅升为独立摘录任务版本 2：`T-P3-SIX-RELATIONS-ATTRIBUTED-EXCERPT-v2`。原 `T-P3-EQUIPMENT-BRIEF-CANDIDATE-v2` EXPLAIN 任务及其原审核包不变，也未被本候选替代。

## 容量定位与选择

先读 AGENTS.md、`docs/first-party-planning-implementation-2026-10-08.md` 和 excerpt-v1 的失败记录，再执行其原只读校验：在修改前确实重现 O1 125 字符、六/七片段 scope 拒绝，原 EXPLAIN Opportunity 返回 SOURCE_REFERENCE_REQUIRED。既有工作树大量未提交修改保留。

| 层级 | 原契约与校验位置 | 本轮 |
|---|---|---|
| 每条摘录 | `core/first_party_planning.py` 的 `MAX_FIRST_PARTY_EXCERPT_CHARS=120` 与 `FirstPartyExcerpt.__post_init__` | 不变 |
| 每个内容点 | `core/change_plan.py` 的 `MAX_CONTENT_POINT_SUBJECT_CHARS=120`；ContentPointCandidate / ContentPoint 构造、`_validate_phrase` / `_validate_content_points`、provider candidate 解析 | 不变 |
| 摘录任务 scope | `FirstPartyPlanningScope.__post_init__` 原先硬编码 1–5 条，整个显式任务一个 P / observed heading | 1–10 个精确片段 |
| 单个 operation | `MAX_CONTENT_POINTS_PER_OPERATION=5`；workflow `_parse_content_points`、core `_validate_content_points`、ChangeOperation / NewResourceSpec 结构校验 | 仅显式 P-only EXPAND parser/finalizer 可到 10；其存储形状要求单 P、exact heading、无 S/A、DESCRIBE/SUMMARIZE；其他仍为 5 |
| 单个 Opportunity | 原最多 2 operations；候选最多 12，全局 48 | 不变；P-only 完整任务固定仅 1 operation，不能用两项重复扩大到 20 点 |
| 全 Plan | 原最多 4 Opportunities / 8 operations | 不变；本例严格一个 R / 一个 C |

120 是**规划 subject/候选片段的资源与规范化文本边界**，不是事实支持度或整句长度标准。它限制模型可选择字段的体积，与候选数、JSON 输出和最终输入 envelope 一起形成资源上界；不能单独删掉它而声称完整能力可用。实际 `_is_bounded_text` 还要求单行、规范空白，精确摘录不能 trim 或改写以迎合它。

现有 P-only finalizer 要求 `content_points.subject == scope.quotes` 按序等值，且每点 P origin、locator、完整 packet、task_id 一致。**多片段合并成一个内容点不属于已有合法契约**；六义务也不要求刚好六点，一个完整原句可以映射为多个连续片段。但原 scope 5 与 operation 5 均会挡住无损七片段。合并六句、加无贡献 S、制造额外 Change 都不能解决。因此选择方案二：局部有界扩容，不改变 120。

通用依据：沿用已有每 Opportunity 的 `2 × 5 × 120 = 1,200` subject 字符预算，将其集中到一个真实逐字摘录 operation；最多十片段，不随客户、样本或义务数变化。通用测试另用不同网站的十项物流摘录，以及两处完整 structured section 的十项 Unicode 片段填满 1,200 字符，并验证十一片段拒绝。它仍受字段/packet/provider 总预算限制，不保证任何长文都可容纳。

O1 在原字段 `[172,297)` 无损拆为 `[172,236)` 与 `[236,297)`，长度 64 与 61；断点在 `features` 后、逗号前。**连接两个片段无插入、无删除即完整 125 字符原句**，不是缩写或两个独立解释型论断。O2–O6 各一片段，长度 114/117/111/118/120；七片段共 705 字符。六项完整 sentence 的支持审核对象仍保留在 coverage，不能以某片段成功代替整项支持。

## 所有相关边界仍在

- scope 构造仍要求确切 page/heading、完整选择字段、Unicode 半开 span 与原文等值；不从 provider JSON 或 artifact 加载 scope 权限。Opportunity workflow 仍只接受一个 P-only R、无 S/A、原观察 heading；默认 SOURCE_REFERENCE_REQUIRED 保留。
- `build_change_plan_prompt` 使用完整精确片段替换候选池；最终候选裁剪会触发 availability 关闭和 provider material 拒绝。finalizer 仍要求完整按序匹配所有 scope 片段及允许 intent。workflow 验证全部后才暴露报告，漏项/重排/伪引用/重复/双 operation 都不产生部分成功。
- 候选的原 8/evidence、12/opportunity、48/global 常规生成预算不变。显式 scope 最多十片段，仍低于每 R 12/global 48，直接精确候选分支不借常规句子摘要或裁剪推导义务。
- SITE_CONTENT 原 body 每页 600、section 1,200、structured 每页 3,500、全站 11,000、序列化 16,000 字符 / 32 KiB；字段、页数与截断校验均保留。P3 body 截断，选择的 structured text 完整。实际输入上界仍由 `validate_change_plan_input` 复核，不能只靠 scope 构造。
- Opportunity 原 site 16,000/32 KiB、S packet 4,000/12 KiB、user 26,000/56 KiB、system 6,000/12 KiB、envelope 36,000/76 KiB、raw output 12,000/24 KiB 保留；adapter 1,500 output tokens、workflow 默认单次 40s / 总 45s、最多两次 writer attempt 也未修改。
- Plan 原 user 26,000/56 KiB（裁剪另预留 512 字符/1,024 bytes）、system 8,000/16 KiB、envelope 52,000/56 KiB、raw output 10,000/20 KiB、1,800 output tokens、120s 总 timeout、最多两次 writer attempt 均保留。条件 system 说明改为遵守 first_party_planning 的 S/点数例外，仍在原 8,000 字符预算内。
- Draft 输入仍没有 scope 字段。`stable_content_draft_input_error` 按默认 Planning 重验并拒绝本候选；`build_content_draft_prompt`、Draft workflow 和 adapter 的检查未放宽。Draft 原 user 26,000/56 KiB、system 8,000/16 KiB、envelope 36,000/76 KiB、raw 16,000/32 KiB、3,000 output tokens、最多 8 drafts/provider calls、8 blocks、4 paragraphs、6 bullet items/list、300 chars/claim、16 claims/draft 保留。六个完整原句均小于 claim 上限，但没有据此调用或批准 Draft。

## 改动与兼容性

本轮生产改动仅 `core/first_party_planning.py`、`core/change_plan.py`、`workflows/change_plan.py`、`adapters/deepseek_change_plan.py`；新增 `tests/test_first_party_excerpt_capacity.py` 七项正式测试及本冻结目录。常规 P/S、ADD_SECTION、NewResource、comparison 不扩容；EXPLAIN/COMPARE 仍拒绝。

没有改变 SQLite schema、codec、payload version、公开函数签名或 artifact 字段。存储的每个 ContentPoint 仍是 120 字符以内的 literal subject，scope/spans 仍为单独技术输入，不在 artifact 中赋予授权。旧五类 V1 artifact decode→encode JSON 等值；原 comparison 仍拒绝。新七点 artifact 需要当前容量实现读取，**不声称旧程序能前向读取新值域**；历史 artifact 本身、默认解释与审核状态未变。

原 EXPLAIN Opportunity 实测仍 SOURCE_REFERENCE_REQUIRED；把原 EXPLAIN Plan specification 放入本合法 scope 的当前 finalizer 实测 EVIDENCE_USE_NOT_ALLOWED。原 v2、excerpt-v1 及 p-only 补充包共 46 个既有文件全部字节不变。excerpt-v1 verifier 记录的是旧容量失败实验；本轮只在改动前运行其旧 probe，改动后做字节保全，不将旧容量断言冒充当前能力验证。

## 新冻结对象与 Draft 可见性

入口：[task.json](task.json)、[coverage.json](coverage.json)、[planning-scope.json](planning-scope.json)、[content_opportunity.json](content_opportunity.json)、[change_plan.json](change_plan.json)、[binding.json](binding.json)。SOURCE_REFERENCE_REQUIRED 已在限定合法任务的原生完整 Planning 链解除，availability 仅 EXPAND_SECTION，R1→C1，page_refs=P3、source_refs/audit_refs 空。原 packet、本地 solutions.astro、虚构说明源码与来源 provenance 都保全，无网站访问。

这些是离线 writer 经生产流程生成并以现有 V1 codec 冻结的**真实规划报告**；不声称模型产出，也不伪造生产 HistoryStore artifact IDs/run。未写生产 SQLite。`prepare_candidate.py` 拒绝覆盖已有候选；`verify_materials.py` 只读校验摘要、来源/spans、完整覆盖、原生重放、task binding、历史 roundtrip 和 Draft 拒绝，不是 Gate/可信 loader。

[draft-input.json](draft-input.json) 保存实际构造的 ContentDraftInput 三项 payload 与 language；[draft-visible-material.json](draft-visible-material.json) 是当前生产 `ContentDraftPrompt.material_json` 对该输入与 C1/P3 的**准入前 serializer 预览**。它并非 `build_content_draft_prompt` 准入成功：原生 builder 返回 FIELD_CONTRACT，原生 Draft workflow INVALID_INPUT，writer=0。未绕过该限制发送请求。

六句原文完整存在于实际预览 `pages[0].structured_content[0].text` 的对应 spans，每个内容点 required_page_refs=P3；无 S。material 5,699 字符/bytes，按生产 request payload 计算的未发送 envelope 12,382 字符/bytes，均在现有预算内。[draft-visible-input.json](draft-visible-input.json) 绑定 input、material、system、envelope digest 并记录上述限制。生产 serializer 没有任务的虚构语境输出义务或义务审核状态字段，故这些仍需可信冻结消费/审核契约确保；本轮不新增 Draft/Gate 接口。**不能把预览完整性称为 D05 已批准或未来 writer 已消费同输入。**

冻结 binding canonical SHA-256：`5d4f659e7da8858e2016ef4ec2397c019912d18f020393860d17e30988a74b17`。绑定冻结文件及生产政策代码摘要；README 与完成验证摘要不属于执行对象/授权。

## 本轮真实验证与尚待签核

完整记录见 [verification.json](verification.json)，日志保存在 ignored `.data/excerpt-capacity-20261008/`。

| 验证 | 实测结果 |
|---|---|
| TDD 首轮七项模块中的初始六项测试 | RED：6 errors，原 scope 最多五条阻塞 |
| 初版实现迭代 | RED：精确片段边缘空白、源 CRLF 读取、测试误设已为 true 的 packet flag、对 builder 裁剪返回值的预期，以及 1,200 chars 放入 600-char body 的 fixture 均修正；不放宽生产原边界 |
| 最终相关十个 unittest 模块 | GREEN：305 tests，8.769s，exit 0 |
| 最终完整 unittest discover | GREEN：1394 tests，235.320s，exit 0 |
| 冻结校验与完整原生重放 | PASS；六义务完整，精确来源/spans，旧包/五类 artifact 保全 |
| 实际 Draft 原生准入 | FIELD_CONTRACT / INVALID_INPUT，writer=0；维持关闭 |

相关命令：`.\.venv\Scripts\python.exe -m unittest tests.test_first_party_excerpt_capacity tests.test_first_party_planning tests.test_change_plan_core tests.test_change_plan_workflow tests.test_change_plan_material_availability tests.test_content_opportunity_workflow tests.test_comparison_admission tests.test_deepseek_change_plan_adapter tests.test_deepseek_content_opportunity_adapter tests.test_history_serialization -v`。

完整命令：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`。全量日志的 demo launcher/port 输出是既有测试输出，最终 unittest 为 OK，不是启动真实网站。

只读冻结校验：`.\.venv\Scripts\python.exe docs/review-packages/evidence-sufficiency-2026-10-08-excerpt-v2/verify_materials.py`。

**工程容量测试 GREEN 不等于 Gate GREEN。** O1–O6 支持判断均待真实审核；D02 完整任务/深度、D03 增量/placement、D04 本新 Plan/P-only 业务候选、D05 同冻结输入消费、D06 审核身份/权限、D07 保存/有效期、D08 真实独立 B2B 商业验收都未获完整签核。D01 历史有限用途转录继承，不扩展对外权利，也不升级整个项目签核。没有审核者/时间/签名代填。可信 review loader、append-only 冻结 lineage/重启消费、Gate preflight 仍未实现，另行工作后才能讨论 Gate 准入。

付费 LLM、WordPress、外部网站操作均为零；无 commit/push。
