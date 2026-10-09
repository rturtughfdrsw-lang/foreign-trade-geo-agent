# Evidence Sufficiency：待授权审核 brief

> 本文保留为前轮 v1 记录。本轮正式逐项审核入口为 [项目所有者审核包 v2](evidence-sufficiency-owner-review-package-2026-10-08.md)，包含新的受阻 Planning specification、P-only 条件方案、冻结输入消费设计和独立商业场景。旧 binding 不认证新候选；本文历史状态不代表新包已签核。

日期：2026-10-08（Asia/Shanghai）。候选 `T-P3-EQUIPMENT-BRIEF-CANDIDATE-v1`。**NOT_REVIEWED；STOP。** 这是一份供授权人员作出决定的材料，不是签核记录、执行许可或成功验收。

## 请审核的具体任务

根据 NovaCNC 受控演示站的 solutions 页，解释准备设备 brief 的六组输入及每组输入所服务的决策/规划。答案仅归因于该演示页，并明确虚构品牌限制；六项全部必答，不要求字数、来源数、数字或额外技术词。题目和六项范围详见[候选证据矩阵](evidence-sufficiency-candidate-matrix-2026-10-08.md)。

原任务、统计主题的 C3 和全量 Plan 仍保留。这份有限任务是新提案，不能签为“原统计指南充分”。原网页已经包含六种关系，若产品目标要求新增知识或完整选机指导，现材料不足；请拒绝增量价值或深度范围，而不是为了允许生成接受缩小的任务。

## 可核验材料与绑定

- [完整 SITE_CONTENT 原 payload](../.data/evidence-sufficiency-candidate-20261008/snapshots/site_content.json)：P3 原字段、上下文、所有截断状态；O1–O6 span 见矩阵。
- [完整原 Plan](../.data/evidence-sufficiency-candidate-20261008/snapshots/change_plan.json)及[原 Opportunity](../.data/evidence-sufficiency-candidate-20261008/snapshots/content_opportunity.json)：核对 C3/R2 的统计错配和 C2 停用能力；这些模型结果不证明事实。
- [受控源码快照](../.data/evidence-sufficiency-candidate-20261008/snapshots/solutions.astro)及[虚构品牌声明](../.data/evidence-sufficiency-candidate-20261008/snapshots/DemoDisclosure.astro)：逐字对应及出处限制。源码没有可信署名或工程资格证明，历史部署 commit 也未绑定。
- [coverage.json](../.data/evidence-sufficiency-candidate-20261008/coverage.json)、[binding.json](../.data/evidence-sufficiency-candidate-20261008/binding.json)、[manifest.json](../.data/evidence-sufficiency-candidate-20261008/manifest.json)：精确引用、版本和状态。
- [审核记录空模板](../.data/evidence-sufficiency-candidate-20261008/review-record.template.json)：所有身份、权限、时间、有效期均为空；每项和整体均 NOT_REVIEWED。填写模板不等于身份认证。

当前 binding：`ca257cf2375ed536b993fe314fc16e1a303895e0a28e5f269f6adc97c61b8539`。该值绑定的是**离线提案**；正式 Opportunity/Plan 建立后必须重新生成绑定，授权审核须针对那个确切版本。

## 审核人须分别确认

| 维度 | 要作出的明确决定 | 当前状态 |
|---|---|---|
| 身份与权限 | 谁被项目所有者授权审核事实来源、支持和任务范围；授权从哪条独立可信记录来；材料使用许可是什么 | 未提供；整理者和 LLM 不能自行取得授权 |
| 来源真实性 | 保存 P3/源码是否适合作为受控站点“所述内容”的来源；是否接受只归因的范围；若作为工程建议，谁验证技术事实 | 原文存在已核验；权威性/许可未确认 |
| 单项 claim 支持 | 对照全文，分别判断 O1–O6 的输入集合与用途关系；范围、强度和条件是否一致，是否需补证 | 六项 NOT_REVIEWED |
| 任务覆盖 | 是否接受该新问题、六项义务和排除范围；是否需要原因、操作方法、模型适配等额外义务 | 未批准，不能由整理者省略困难义务 |
| Plan 一致性 | 批准新的匹配 Opportunity/Plan，解决直接 P-only 支持和合法 S context 的契约问题；不会继续统计标题或 comparison | 尚无正式匹配 Plan |
| 内容价值 | 已有页面有相同信息，拟新增内容是否有明确用途/增量；应该 ADD、EXPAND，还是不应新增 | 未确认 |
| 版本与时效 | 全部 digest、路径、span、语言；新正式包绑定；审核时间、有效期和触发重审的变化 | 当前仅提案绑定；签核时间/有效期为空 |
| 保存与接入 | 真实审核记录在进程结束后仍可追溯；runtime 从可信操作者通道选取；禁止从 P/S/模型正文加载批准 | 未建立可信接入路径 |

每项请记录 `SUPPORTED / PARTIAL / TOPIC_ONLY / UNSUPPORTED / NOT_REVIEWED` 及理由。SUPPORTED 必须是授权人的语义判断，不得由“span 找到了”自动填入。整体 verdict 只有在所有必答项经确认、来源用途获允许、任务和正式 Plan 绑定一致时才可能 sufficient。剩余未审应记录 pending/not_reviewed；明确缺失应记录 insufficient，二者不能混淆。

## 可以直接采用的拒绝理由

| 理由码（设计标签，非生产枚举） | 适用情形 |
|---|---|
| REVIEW_AUTHORITY_MISSING | 无可信审核者身份/授权；只有人名、JSON 布尔、模型自评或网页自称 reviewed |
| SOURCE_USE_NOT_AUTHORIZED | 来源使用权或受控资料使用范围未确认 |
| SOURCE_SCOPE_UNVERIFIED | 希望输出权威工程建议或厂家事实，而材料只有演示站陈述 |
| REQUIRED_ANSWER_UNSUPPORTED | 任一认可必答项没有直接支持，或原文只有主题/概括 |
| TASK_DEPTH_NOT_MET | 实际需要原因/步骤/判断标准，六句列举不足；不得删义务求放行 |
| PLAN_TASK_MISMATCH | 仍绑定历史统计指南、错误 R2、不同 task/Plan/change/point |
| PLAN_NOT_CURRENTLY_EXECUTABLE | 全量 Plan 含停用 comparison，或新提案尚未通过原安全/availability 契约 |
| DECORATIVE_SOURCE_ONLY | 把历史 S2 强行当作六项支持，或把其 Verified 文本升级为认证 |
| NO_CONTENT_INCREMENT | 拟新增仅复制已有六句，未满足认可的商业内容目标 |
| REVIEW_STALE | 证据、任务、义务、正式 Plan、语言变动或认可的有效期已过 |
| SNAPSHOT_OR_SPAN_MISMATCH | digest、字段、ref、span 与所审核版本不一致 |

## 最小补充路径

若授权人认可“受控演示页归因”的有限任务，六句原文已经保全，无需再次联网：先确认资料使用、任务范围和增量价值；创建离线匹配的正式 Opportunity/Plan，并妥善处理合法 context 的角色；重绑，再逐项审核和签核。原 S2 不能补作六项直接支持。这个分支适合受控离线验收，不能证明真实工业网站的工程事实或商业 SEO 效果。

若目标是实际买家可采用的技术指南，最小补证是由获授权的厂家/技术专家提供一份注明版本、适用范围、条件和来源的短材料，逐项覆盖已经认可的问题（可以一份完整文档，无来源数下限）；补充内容必须进入未来实际 bounded input，并重新匹配 Plan、绑定和审核。不要以再调用 LLM 产生解释来补事实。

若保持旧 C3 的行业统计指南，需真实可核验的统计来源、指标定义、时间/地域/方法与使用权限，且重新批准统计任务范围。本轮没有这些事实；一般设备 brief 不能填这个缺口。若保持薄证据 chemical compatibility 任务，则需对应材料/介质/工况适用条件及如何判断的直接资料；本候选不补该任务。

## 四种状态与决策

| 状态 | 本轮 |
|---|---|
| 候选材料已整理 | 是；有精确 span、完整原文/Plan 快照、来源限制及待审矩阵 |
| 可信人工审核已完成 | 否；reviewer/authority/time/expiry 均空，全部 NOT_REVIEWED |
| Gate 实现完成 | 否；本轮未修改实现或正式测试 |
| 真实 Draft 质量通过 | 否；没有新 Draft，旧薄证据 Draft 仍 NO-GO |

**STOP：不得据此进入 GREEN 实现或真实 Draft 质量验收。** 本 brief 供授权人拒绝、要求补证或确认未来正式绑定包；任何 sufficiency 审核都不自动授权收费 LLM、WordPress 创建或发布。
