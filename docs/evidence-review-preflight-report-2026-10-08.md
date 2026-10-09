# P-only Evidence Sufficiency：A–G 完成报告

## A 当前事实与 Git 状态

读取根 AGENTS.md、README.md、excerpt-v2 README，以及实际 Planning/Draft/inspection/storage/codec/冻结材料与测试。分支 `feat/live-site-analysis`，HEAD `fedcb3b7a8ffb3e3480c9807d5831ddd89dfc148`。开始时202条 Git status，包含大量已有修改和删除的 `tests/test_history_migration_v1_to_v2.py`；没有恢复或清理这些变更。以 `.data/evidence-review-20261008/baseline.json` 冻结333个当时存在的版本控制/非 ignored 文件摘要；核对全部未变。本轮仅新增文件，无 commit、push、stage、外部网站、付费 LLM、WordPress 或正式 Draft 操作。

旧 excerpt-v2 verifier 重新通过：原生 Opportunity/Plan 重放成功、6义务/7 spans/705字符、旧包完整性与5类V1 codec roundtrip成立；默认 Draft 为 FIELD_CONTRACT / INVALID_INPUT，writer=0；O1–O6 NOT_REVIEWED。额外发现旧 coverage 顶层仍为 v1/1，而六行任务和 task/scope 为 v2/2；旧 verifier 未核验顶层。原字节保留，新 lineage 明确记录更正。

## B 信任边界及威胁模型

已有 review 仅 inspection，deliver 用户动作不赋予证据支持审批；SQLite append-only 本身不认证身份。复用现有 scope、upstream validator、Planning prompt/catalog/finalizer和V1 codec，不引入第二套Planning规则。

严格 loader 在解释签核前，用包外注入的 authenticator 认证原始 record bytes 与 detached proof；identity/grants/key lifecycle/revocation 由该受信任边界返回，不从JSON读权限。再检查身份匹配、project/task/purpose权限、当前有效期、签核与全部reason、版本及冻结 target/DraftInput digest、全部义务和决策。每次重新认证，不缓存授权；重复键、未知字段和超限拒绝，错误消毒。最长签核窗口24小时，且不能越过 authority grant 有效期。

生产 authenticator/身份管理/撤销/受保护保存并不存在：无 loader 配置时拒绝；synthetic默认拒绝。tests中的HMAC使用随机内存key，不提供仓库测试密钥、生产signer、环境变量开关或CLI/Web入口。JSON的APPROVED、runtime_approval_valid、synthetic或重新计算的digest不能证明授权。受信任Python依赖注入/代码/时钟被替换的攻击超出文件包威胁模型；将来服务必须由受保护composition提供真实时钟，不能接受客户端控制的now或信任根。

该preflight没有writer或Draft许可，也不证明来源陈述为工程事实或最终文章完成度。核心模型仅依赖core；workflow经core port调用loader，未依赖adapter/storage。

## C 新增文件及原因

- `src/foreign_trade_geo_agent/core/evidence_sufficiency.py`：有界task/obligation/principal/port/result，完整span覆盖与原生Plan重验。
- `src/foreign_trade_geo_agent/adapters/evidence_review.py`：严格authenticated loader、独立frozen-target codec、既有DraftInput codec digest。
- `src/foreign_trade_geo_agent/workflows/evidence_sufficiency.py`：默认拒绝的独立离线preflight，每次认证与冻结绑定。
- `tests/evidence_review_fixtures.py`、`tests/test_evidence_sufficiency_preflight.py`：真正字节认证的synthetic fixture与正负例。
- `docs/evidence-review-preflight-design-2026-10-08.md`、本报告及新 `docs/review-packages/evidence-sufficiency-2026-10-08-trusted-preflight/`：设计、可重建人工材料、unsigned模板、明确lineage与验证结果。

原SQLite schema、artifact payload version/codec、既有公开API和Draft prompt/workflow均未改。新增frozen-target是独立schema v1容器，内部仍用已有artifact V1；不是迁移，也不能使旧程序获得授权。普通P/S、EXPLAIN、comparison、GEO、WordPress create-only/draft-only语义保持。

## D 人工审核包及待签核事项

入口：[新审核包](review-packages/evidence-sufficiency-2026-10-08-trusted-preflight/README.md)；[逐项义务](review-packages/evidence-sufficiency-2026-10-08-trusted-preflight/owner-obligations.md)；[unsigned模板](review-packages/evidence-sufficiency-2026-10-08-trusted-preflight/review-record.UNSIGNED.template.json)。材料包括精确原文、前后文、P3 URL/heading、原artifact与Draft serializer preview locator、原本地源码locator、Unicode spans、完整义务/7点覆盖、R1→C1、task/Plan/evidence版本和虚构声明。

新 frozen-target SHA-256：`146cd906b1fce15a21a6f26f50224e09182a1d0b7ed934df1e7ccba826972c1d`。实际DraftInput保持 `a24428cbc575527b09d59897422fdabe6038c13b206878ddc4cce0a93256b7e2`。target还绑定归属、虚构context、逐字及禁止扩展约束；不宣称writer已消费它。

O1–O6全部NOT_REVIEWED，无reviewer、reviewed_at、expires_at、proof代填。D01–D07仅列出待判断项，其合同是离线任务：source use、完整任务深度、离线placement、P-only候选、同冻结对象消费条件、身份权限、保存及有效期。D08真实独立B2B商业验收另外处理，未批准且不能从离线签核继承。现有有限用途授权保留，不自动升级为完整任务或对外授权。

## E 正负例测试及 writer 计数

TDD初始12 FAIL（缺少preflight）；初版11 PASS/1 ERROR，原因是6点EXPLAIN对象先被既有Plan构造校验拒绝。改用可构造的4点负例后真正到达Gate并拒绝，未修改生产边界。最终13项新测试通过（0.151s）。新包回归补充来自独立只读审查的一项test gap；审查无critical/important findings。

正例使用与NovaCNC无关的synthetic物流文本、6项义务/7 spans/一个operation、随机内存HMAC身份/权限和完整人工判断fixture，得到SYNTHETIC_GREEN。preflight不持有writer；随后实际调用native Draft workflow仍INVALID_INPUT，NoWriter.calls=0。

负例包括NOT_REVIEWED/部分/缺项/重复/reason缺失/未签核决策、过期/未来/naive/倒置时间、身份/项目/任务权限不足及撤销、task/Plan/evidence错绑、EXPLAIN历史授权复用、input语言/证据/问题/context变化、伪造proof、JSON权限标志、duplicate keys、畸形/超限输入、非法EXPLAIN/COMPARE Plan、错误span/statement及覆盖缺失。各拒绝路径均断言native Draft INVALID_INPUT和writer=0。真实旧包与新包保持NOT_REVIEWED并拒绝。

最终针对性命令（357 tests，10.675s，exit0）：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_evidence_sufficiency_preflight tests.test_first_party_excerpt_capacity tests.test_first_party_planning tests.test_change_plan_core tests.test_change_plan_workflow tests.test_change_plan_material_availability tests.test_content_opportunity_workflow tests.test_comparison_admission tests.test_content_draft_core tests.test_content_draft_workflow tests.test_deepseek_change_plan_adapter tests.test_deepseek_content_opportunity_adapter tests.test_history_serialization -v
```

日志：`.data/evidence-review-20261008/targeted-final.log`。旧包 `verify_materials.py` 本轮两次运行均通过；新包 target validation、canonical roundtrip、版本(2,2,1)、两个digest及unsigned拒绝已实际检查。

## F 完整回归结果

首轮（补充新包回归前）1406 tests，220.456s，exit0。最终版本完整回归 **1407 tests，217.031s，OK，exit0**；无失败或错误。包含新增13项及既有1394项，结果已实际观察。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

最终日志：`.data/evidence-review-20261008/full-final.log`。日志中的launcher/port8000文字及asyncio慢任务诊断属于既有测试输出，不把它们当作外部站点访问或新的业务签核。

## G 下一步与 GO/NO-GO

| 对象 | 结论 | 含义 |
|---|---|---|
| synthetic P-only离线测试 | GO / SYNTHETIC_GREEN | 受控fixture能通过新preflight；不批准真实O1–O6，不放行native Draft |
| 真实六项材料审核 | NO-GO / NOT_REVIEWED | 尚缺逐项真实判断、身份及具体任务权限和可信签核来源；默认Gate拒绝 |
| 本候选商业Content Draft准入 | NO-GO | 缺商业D08验收、生产身份/撤销/签核保存、同冻结输入消费接口及逐字/全部义务输出校验 |

先由项目所有者逐项核验材料，再选择真实reviewer身份、受保护密钥/权限管理员、撤销与最长24小时有效期政策、受保护append-only review lineage和可信时钟。真正接入后，审核记录才能成为可信输入。之后另行设计与授权Draft消费边界、重启消费和输出覆盖验证；不以已有unit tests GREEN替代这些前置条件。本轮完成安全离线实现、人工材料与缺口分析，生产审核/商业Draft闭环未完成。
