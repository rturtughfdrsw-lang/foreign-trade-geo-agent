# 修复版 DeepSeek Flash 真实请求预检交付

最终目录：`docs/seo-flash-request-preflight-2026-10-12/final-v2/`。
详细 A–I 报告：[冻结预检报告](final-v2/preflight-report.md)；[逐项官方核实](final-v2/official-verification.json)；[最终核验](final-verification.json)。

本轮只新增本目录资料/离线核验脚本；生产源码、测试源码、README 和既有未提交内容未修改。1992 个已有文件（含 1645 个历史 docs 文件）逐文件检查不变。0 DeepSeek/余额/WordPress 请求，0 LIVE permit；无部署、Git 写操作或 PostgreSQL 变更。

| 项目 | 结果 |
|---|---|
| A 官方配置 | Flash = V4.1-Flash；1M context，393216 最大输出；16384、json_object、temperature0/non-thinking 和 thinking.disabled 均兼容 |
| B 请求一致性 | 与 Prompt 修复 final-v2 逐字节相同；E Candidate；7资料/43facts/6章，task/Plan/brief 完整绑定，无旧 P/S 冲突 |
| C Token | System 7775，User 22847，输入30622chars/bytes，wire32544bytes；约7744历史校准/9187官方比例；保守场景65536输入+16384输出=81920，十进制1M规划余量918080；非精确上界 |
| D 费用 | 峰值全cache-miss保守场景 USD0.0393216；拟议USD0.05，尚未授权且无服务端费用硬限额 |
| E 安全 | 现有受控入口绑定hash/源码/snapshot/固定endpoint/精确bytes；持久化单次claim，60秒、零重试/fallback，256KiB读取；待审不准入Draft；禁止WordPress |
| F 测试 | 52定向 +5案例预检通过；最终包5项再次复验通过；未重跑1887全量；首次最终核验辅助脚本字段错误保留并修正，非生产或单元测试失败 |
| G 冻结 | 49产物、174代码hash全部核验；SQLite待审原文重开一致；没有批准任何解释 |
| H 剩余条件 | 精确V4.1 tokenizer/server framing仍UNVERIFIED，需所有者明确接受估算风险，并另行授权；现有compose须注入精确FactsOnlyReviewer，裸serve-live仍阻断 |
| I 判定 | OFFLINE READY；REAL PREFLIGHT CONDITIONAL READY；ESTIMATED_TOKEN_FEASIBILITY=true；真实遵循/质量未测；PRODUCTION_NO_GO=true |

Request SHA256：`8fd2b8834c9aa50f4ebaeba6229b4a9b01b59d033effa8637cce5ed223428431`

交付 bundle SHA256（artifact-sha256.json 的 SHA256）：`e797983c2d20d63b6f57491c377142a57aa05886f58bd8b7abdc27447adb094a`

原生执行 bundle SHA256（执行许可绑定，不能与交付摘要混用）：`e114a55bd2e55c80a3f8b869f9e00d90acdefb4da376837515bb28e75ab4ca01`

未来精确授权范围：上述交付与执行bundle及request；`https://api.deepseek.com/chat/completions` 一次 `deepseek-flash` 英文SYNTHETIC六章文章实验；temperature=0、thinking.disabled、json_object、max_tokens=16384；60秒，0重试/0fallback；拟议USD0.05，接受token/费用估算风险、超时仍可能计费、实际模型质量未知。只允许待审结果；不含WordPress、发布、其他模型或重试。未来许可提案10分钟；本轮未签发。

准备期至2026-10-13 10:50:36+0800；执行前重验当前公开参数/价格、所有哈希、Evidence/Plan/范围及TEST复核。任何变更或超期应重新冻结并另行授权。若所有者要求严格token/费用上界，继续BLOCKED，最小额外依据为当前服务端计数规则匹配的可信tokenizer，而非继续扩建本地计数工具。

第一份frozen-v1和错误核验工具保留，仅final-v2为最终交付。新请求本身未变，因而request摘要不变；新的交付manifest包含官方核实、预算、安全及新离线证据，摘要独立变化。等待所有者另行授权并明确接受估算风险；本轮停止。
