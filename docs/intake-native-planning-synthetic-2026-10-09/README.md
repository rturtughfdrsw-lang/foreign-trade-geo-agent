# LumenSeal/V7 synthetic 原生规划链路

虚构出口水阀企业，全部身份、产品、认证和人工 verdict 都是 TEST fixture。没有 NovaCNC 历史审批、真实抓取、付费模型、生产签核或 Draft 授权。

1. [初始三项请求](01-initial-request.txt) / [JSON](01-initial-request.json)：流量工况、密封适用性、认证范围。
2. 第一次只提交流量陈述，经原生重规划和明确 synthetic 人工判断后，[保留两项请求](02-remaining-request.txt) / [JSON](02-remaining-request.json)。
3. 第二次提交密封陈述和严格 UTF-8 证书文本：[原生 Planner 收到的精确 material](03-native-planner-material.json)。客户来源位于独立 customer_evidence_intake context，不是 P/S。
4. [逐 claim 人工审核包](03-human-review-candidate.json)：全部材料 UNREVIEWED，当前原生 Plan/evidence binding 一致，draft_authorized=false。
5. [五次版本与 digest](state-transitions.json)：初始→提交→重规划→提交→重规划。旧快照保留，新候选只对应当前版本。

样例由 `tests/test_intake_native_planning.py` 的相同原生工作流和 fixture 生成；来源 locator 是客户声明，不证明页码、权威性或事实语义。
