# TEST-only 真实 Web 实验：执行前停止记录

核对时间：2026-10-10 23:41:53（北京时间）。本记录是本次授权的执行前检查，不是此前 Mock 或 CLI 实验结果。

状态：BLOCKED_BEFORE_LIVE。余额查询 0，文章生成请求 0；没有启动 LIVE 服务、签发或消费许可，没有读取密钥、调用 WordPress 或进行 Git 历史操作。

## 阻断依据

用户指定截止时间为 2026-10-11 20:00:00+08:00。预检报告要求截止时间“必须取用户给出的确切截止时间”，同时“签发时起不超过一小时”。`scripts/web_deepseek_experiment.py` 的 arm-live 分支实际执行该约束，失败原因码为 `EXPIRY_MUST_BE_WITHIN_ONE_HOUR`。当前时间距指定截止约 20 小时，不符合签发条件；没有尝试签发，也没有修改启动器、冻结文件或请求。

已在聊天中请求用户明确将截止时间收紧为 2026-10-11 00:30:00+08:00，其余范围保持不变；在得到明确答复前不执行依赖动作。本记录不构成许可。

## 已完成核对

- bundle SHA-256：f573be4c0cf539984c9ba1c4cdf13856fdf3a02fc3c4adcfa0737ffd27bf99c0。
- 请求 SHA-256：8ed4e1fa85f01505193d899879e1399154a9f913398a34edbef355d949a35734；11,412 bytes；重新构造逐字节相同。
- 156 个源码/模板/资源摘要完全相同；清单 SHA-256：1f66a0bbc3375192dae267ec7f634b231d41a4d0343aad9ea72f20317f15f09f。
- 原生输入、快照和报告旁冻结副本一致；当前 snapshot digest 一致；TEST-only 结构复核刷新 freshness 后原生输入校验通过，未改变冻结请求。
- 模型 deepseek-flash，temperature 0，thinking disabled，max_tokens 3000；60 秒、1 请求、0 自动重试。
- task 1 / Plan 2 / E 2 / revision 3。
- 固定 LIVE 账本尚不存在；这是未签发状态，没有创建或替换既有账本。运行目录 generation 不存在。

## 费用依据

已只读查询官方公开价格页：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ 。Flash 空闲时段未命中输入为 ¥1/百万 Token、输出 ¥4/百万；高峰分别为 ¥2、¥8。沿用预检的输入 16,000 Token 预算假设及输出 3,000 上限，估计空闲 ¥0.028、高峰 ¥0.056。没有做 tokenizer 精确计数，估计不是账单。¥1 为预留余额检查标准，未实现账户侧消费硬限制。

官方余额接口文档 https://api-docs.deepseek.com/api/get-user-balance/ 确认 GET /user/balance 可只读返回账户状态；本次未调用该账户接口。

## 本次验收状态

| 项 | 本次实际结果 |
| --- | --- |
| 余额查询 / 生成请求 | 0 / 0 |
| Token usage / finish_reason / 生成 HTTP 响应 | 无；未发请求 |
| 真实浏览器生成链 | 未执行 |
| 原生 Draft Validator / Finalizer | 未执行；仅输入结构核对通过 |
| 新文章 SQLite / Markdown / Web | 均未生成；本报告不算文章 Markdown |
| 完整英文文章及 E1 引用质量 | 无本次候选，无法评价 |
| 一次性许可签发 / 消费 | 均未发生 |
| 重复点击 / 重启实际验收 | 未执行；不得把既有 Mock 测试算为本次验证 |
| 人工质量审批 | 未进行，非 APPROVED |

E1 核对基准为 NCX7、7200 rpm continuous、NOVA-TEST-7、20 C、unloaded bench、仅 NCX7、不构成切削负载或生产保证；没有候选可核对，不能推定模型会正确引用。

## WordPress 草稿交付剩余阻断

生产仍 NO-GO，PostgreSQL 仍 BLOCKED。当前实验只对合成客户开放；真实客户身份、证据与人工语义签核及生产授权链未满足。生产 Draft admission / Writer 的拒绝边界保持。P1 已知 journal 更换/回滚问题未解决，独立本地 TEST 账本不是生产抗回滚方案。还缺真实 Draft 成功及整篇人工质量审核、生产持久化/许可问题解决，以及另行明确的 WordPress create-only / draft-only 授权与交付验证。不得由本次 TEST 实验升级生产权限。

## 变更与验证

仅新增本目录 `preexecution-verification.json` 与本报告；没有修改业务源码、冻结请求或用户已有未提交修改。本次没有运行单元测试或完整回归，未引用历史 1771 项测试作为本次运行结果。一次性离线核对脚本初次因误读 snapshot.task_version 属性中止，改为 customer_evidence.task_version 后上述核对完成；两次均没有网络生成或余额查询。
