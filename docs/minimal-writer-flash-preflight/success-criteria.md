# Minimal Writer Flash 首次真实实验：独立评价标准

本包仅为 TEST ONLY 离线预检，不包含模型答案，不授予真实调用或客户审批。
必须先以外部记录的 manifest/request SHA256 重建核验，输入漂移则停止。
未来结果目录为同级 `docs/minimal-writer-flash-results/`，不得放入本包。

## 技术评价（单独记录每项 PASS / FAIL / NOT_RUN）

1. 留存原始 HTTP response、原始 model output、finish_reason、usage、耗时、调用数和错误；禁止输出凭据。HTTP/超时/截断/非 stop 结束均不得视为完成；不重试、不 fallback、不修复。
2. JSON 为单个严格对象；拒绝 Markdown、重复键、NaN、额外或权限字段。
3. 当前 Minimal Wire codec 校验 request_id、12 个 explanation slot 的唯一完整覆盖、逐字段类型/长度、每槽 premise_refs 范围、精确 boundary/action、总预算和拒答。
4. 任意 insufficient_evidence 必须保留 missing_information，候选不完整且不得补写。可记录为安全拒答；不是技术完成 PASS。
5. 由现有 deterministic assembler 组装 25 direct facts + 12 explanations + 1 CTA，38 claims / 13 blocks；不得用填充文字凑数。Python 仅连接模型提供的四段文字，不增加语义。
6. 必须调用原 Native Parser 与 Candidate Validator，原样保留引用、数值条件、章节覆盖、重复、CTA 和其他拒绝结果。没有 finalizer、Evidence Gate 注入、v2/v3 fallback 或宽松重放。
7. 原句/版本/位置/source hash、实际 premise、slot→claim、正文/sidecar hash 可重建，修改后必须拒绝；所有人审与生产授权保持 false/PENDING。

## 内容评价（独立于技术结果）

逐槽对照允许引用的原句，逐项记录 PASS / FAIL / NEEDS_EDIT 及原文证据：

- 是否形成独立采购决定，12 个目标是否真正互补，而不是同一提醒换写。
- 每个实际 premise 是否参与推理，因果是否成立，是否混淆 nominal / loaded、static / dynamic、coupon / production、proposal / commitment。
- 英文是否自然，implication/assumption 是否清楚；精确回显的限制语及动作造成多少重复。
- 是否明确未知条件和推理适用范围；是否把未知适配升级成已验证结论。
- 谁提供输入、谁记录试验、谁同意处置是否有依据；证据未分配责任时应说明待约定，不能伪造责任。
- 每槽重复、跨章重复、泛化免责声明及无信息密度模板数量。
- 人工编辑工作量：逐槽编辑处数、轻改/重写/不可用、全篇实际编辑分钟；由审阅者实测，不由 Python 推定。

技术 PASS 不代表商业文章质量 PASS。商业评价必须单独给出结论与理由；结构、hash、全部槽位填满均不能代替人工语义审查。

## 停止边界与下一次授权

本轮真实 API 调用为 0。没有 live executor；本包不会自动请求 DeepSeek。
下一次须明确授权：对外部记录的本包 request SHA256/manifest SHA256，向
`https://api.deepseek.com/chat/completions` 发送且仅发送一次 TEST ONLY 请求，
deepseek-flash / temperature=0 / thinking disabled / json_object / max_tokens=16384，
timeout=60 秒，retries=0，fallback=false，预算上限建议 USD 0.05（须另行确认当前费率可满足），
原始结果留存在独立同级目录，并允许本地原生解析验证及人工内容评审。
若用户同时授权执行前官方别名、参数、价格的只读核验，应核验后再执行；不满足冻结条件则停止，不能改参数、换模型或自动重冻。
授权一次实验不表示批准生产 Writer、客户证据、WordPress 或任何发布。
