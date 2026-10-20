# 独立 synthetic 客户补充资料示例

这些文件由实际本地 Intake workflow 生成，使用临时 SQLite、虚构出口包装客户和显式 synthetic 人工 fixture 判断。没有真实签核、身份凭据、执行授权或网络调用。

- [初始请求（可读）](initial-request.md) / [JSON](initial-request.json)：载荷、密封材料和认证三项缺失事实，版本 task=1 / Plan=1 / evidence=1。
- [客户只补载荷事实的提交](partial-submission.json)：绑定初始完整快照 digest；不包含 actor/time，后者来自集成应用的 CustomerContext。
- [剩余请求（可读）](remaining-request.md) / [JSON](remaining-request.json)：提交使旧绑定失效；原生 Plan 重新校验和绑定、synthetic 人工明确确认 F1 后，剩 F2/F3，版本 task=1 / Plan=2 / evidence=2。

生产使用不能把 fixture reviewer 替换成自动肯定的 stub。完整材料未经当前可信人工语义判断仍拒绝；判断通过也只获得后续审核候选资格。客户源材料不会被自动升级成 P/S 或 Draft 输入。

可复验：[测试](../../tests/test_evidence_intake.py)，命令 `python -m unittest tests.test_evidence_intake -v`。测试不依赖本样例文件中的固定 digest；digest 是绑定值，不是签名或权限。
