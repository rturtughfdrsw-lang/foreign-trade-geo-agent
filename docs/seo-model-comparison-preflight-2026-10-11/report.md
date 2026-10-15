# Flash / V4 Pro 单次文章质量对照：离线准备

结论：**READY，限“冻结请求与离线预检完成，等待新的单次真实调用授权”。** 现有 Web / 生产 adapter 仍是 Flash 固定配置；没有上线模型切换，没有实现或启动 live runner，没有签发许可，没有取得 Pro 文章。本轮尚不能选出最终文章生成模型。

## API 与现有实现兼容性

准确 model ID 是 **`deepseek-v4-pro`**；当前官方标示版本 DeepSeek-V4-Pro-0813。使用 `POST https://api.deepseek.com/chat/completions`，文本 system/user messages、temperature=0、thinking.type=disabled、max_tokens=3000 均受支持。没有接口约束迫使改变其他参数。官方支持 JSON Output，但历史 Flash 请求未传 response_format，本实验也不增加。详见 [官方接口与计费记录](official-api-notes.md) 及其中的官方链接。

实现核对结果：

- `adapters/deepseek_content_draft.py` 的 `DeepSeekContentDraftWriter.model` 和 `content_draft_request_payload()` 固定 Flash；仅改实例 model 属性不会可靠地改请求。因此不能宣称生产 adapter 已提供可配置的 Pro 支持。
- 同一 adapter 的 `_extract_text()` 能提取 Pro 的标准 Chat Completions 响应形状，原生领域模型与 ContentDraftWorkflow 可以接受 Pro 模型元数据。离线 Mock 用历史 Flash 原文验证了这一点；它不是 Pro 生成结果或质量证据。
- `adapters/retained_deepseek.py:receive_candidate()` 对返回 model 严格要求 deepseek-flash，`web/experiment.py` 也固定 Flash。现有 arm-live / serve-live 流程不能直接用于本包，不能全局改 model 常量或删掉 envelope 检查来“兼容”。
- 本包只冻结模型选择差异；未来获授权后使用隔离的单次操作路径，复用 OneShotTransport 的精确请求 / 一次限制、现有有界保留和原生校验原则，严格检查 Pro 返回 model 与唯一 choice。真实执行路径如需实现，应先完成其离线校验，再消费新授权；不得放宽生产 Gate / Validator / E-only 契约。本轮不建设该 live 执行器。

这一区别不会改变发给模型的输入。它限制的是“现有 Web 可以直接切换”的说法；本次请求级实验可以继续准备和授权，生产模型切换仍需另行工作。

## Flash 基准与一致性

原始来源为 [2026-10-11 Flash 验收报告](../seo-web-deepseek-live-2026-10-11/report.md) 和 `../seo-web-deepseek-preflight-2026-10-10/frozen/`。本包 baseline 目录保留原始请求、响应、模型文本、正文、验收报告 / JSON、冻结 native input、snapshot 与旧 bundle；不复制余额响应、凭据、许可账本或历史数据库。

Flash 基准可公平复用，**没有重新生成 Flash**。核对请求 / 响应 / 模型文本摘要与历史记录一致；响应 content 逐字节等于 model-output.txt。旧冻结包摘要为 `f573be4c0cf539984c9ba1c4cdf13856fdf3a02fc3c4adcfa0737ffd27bf99c0`。

| 项目 | Flash | V4 Pro 冻结输入 |
| --- | --- | --- |
| model | deepseek-flash | deepseek-v4-pro（唯一变化） |
| messages / Prompt / Plan / P/S/E | 原始完整 bytes | 完全相同 |
| temperature / thinking / max_tokens | 0 / disabled / 3000 | 相同 |
| response_format / tools / stream / reasoning_effort | 均未显式传入 | 相同 |
| task / Plan / E / revision | 1 / 2 / 2 / 3 | 相同 |
| 输入 snapshot 摘要 | 8fa01547bce62864ccc4cdf77bd0c4c88de453d40ec9dfd368d2c02efd02aeea | 相同 |
| 超时 / 请求上限 / 响应上限 | 60 秒 / 16,000 bytes / 65,536 bytes | 未来执行保持相同 |
| 自动重试 / 修复请求 | 0 / 0 | 必须相同 |

当前代码重建的 Flash 请求仍与历史请求逐字节一致，原生 Flash 回放通过。相较旧 bundle，仅四个历史文件发生变化：mvp_application.py、mvp_routes.py、mvp.css、mvp.html；没有请求 builder、草稿 workflow、Validator 或 E 规则变化。它们是此前的 Web / WordPress 工作区变化，本轮未编辑；不影响冻结 messages 和双方原生校验。当前代码摘要和依赖版本另行冻结在 manifest 中，不声称已核验依赖二进制摘要。

保留原始 native input 的 reviewed_at，不续期、不改变证据版本或审核身份。离线原生 replay 不代表历史证据已重新获人类批准，也不产生 live 权限。

## 冻结请求与摘要

发送实体为 [request-v4-pro.json](request-v4-pro.json)，UTF-8，**11,413 bytes**。从原始 Flash request.json 精确替换一次 model 值，其余字节不变；文件没有额外尾部换行。

```text
Pro request SHA-256:
991361f0eb58bfeb7fd557374faca7aae0093fd19a8e215586ca4c37593d8abc

Flash request SHA-256:
8ed4e1fa85f01505193d899879e1399154a9f913398a34edbef355d949a35734

Flash response SHA-256:
61bc38bbb43ca6d7a09e46d31720b067b19de9ca43b2c2bd5a6098382e0b5fa3

Flash model text SHA-256:
e90eaa40499c7bc6e0e6f40d21e9eada10c9ea13cfafea5eb6e182e4ff349201
```

[manifest.json](manifest.json) 冻结本目录输入 / 文档 / 离线核验脚本和当前源码摘要，摘要存于 [manifest.sha256](manifest.sha256)。本包摘要与旧 Flash 包摘要是不同绑定，不能拿旧包许可执行 Pro。

## 保守 Token / 费用预算

按 [DeepSeek 官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：Pro 每百万 Token 输入命中 / 未命中 / 输出，空闲 ¥0.15 / ¥4.5 / ¥13.5，高峰 ¥0.30 / ¥9 / ¥27。计费按输入与输出 usage，缓存命中单独计价；不以余额差估算费用。

| 项目 | 数值 |
| --- | ---: |
| Flash 已发生输入 / 输出 / 总 Token | 2486 / 611 / 3097 |
| Flash 已发生输入缓存命中 / 未命中 | 1280 / 1206 |
| Flash 按历史空闲费率的 usage 估算 | ¥0.0036756 |
| Pro 离线保守输入估算 / 输出限制 | 16,000 / 3,000 Token |
| Pro 全未命中空闲预算 | ¥0.1125 |
| Pro 全未命中高峰预算 | **¥0.225** |
| 建议预留 | **¥0.25** |

公式（高峰）：`(16000 × 9 + 3000 × 27) / 1000000 = 0.225 CNY`。输入预算沿用此前保守口径，相比约 11.4 KB 文本和 Flash 2486 实际输入留有大量余量，但并非精确 tokenizer 计算或服务端输入 Token 硬限制。输出 3000 包括 JSON 框架和引用字段，不是 3000 个正文词。Pro 实际输入 / 输出和费用均待真实响应，不能拿 Flash usage 冒充 Pro usage。

若 Pro 恰好消耗与 Flash 相同的 2486 / 611 且全部未命中，空闲估算 ¥0.0194355、高峰 ¥0.038871；这只是尺度参考，不是输出长度或实际费用承诺。建议预留不是账户级消费硬上限；价格变化或服务端 Token 计算差异须单列记录。未来执行前只核对公开价格和授权，不查询余额；价格超出批准预算假设时停止并重新取得授权，不擅自增加预算。

## 共同瓶颈：两节短文是怎么形成的

- **Plan 硬结构**：CREATE_NEW_RESOURCE，只能依次使用 `spindle performance`、`Test conditions and scope` 两个 heading。批准标题为 `NovaCNC machining center buyer guide`，范围比唯一主轴子题宽。只有一个 EXPLAIN 内容点，subject=spindle performance，没有独立深度要求、目标词数、必需采购场景或必需 CTA。
- **证据厚度**：P1 是泛泛工程主题的合成页面；S1 只有 750 字符，标为截断、未验证，末尾停在半句话；E1 是 193 字符的唯一完整合成主轴测试引句。材料不足以展开真实选型阈值、生产性能、认证、工厂能力、成本或产品比较。
- **Prompt 与原生预算**：要求每条陈述简短且词汇有据；最多 8 个块、16 条陈述、每条规范化文本最多 300 字符。事实陈述正文理论上受 4800 字符预算约束（标题 / heading 另计），输出还需容纳结构化 JSON。E1 必须原样复制；背景要求简短改写；CTA 类型被允许，但没有强制生成。
- **并非精确锁死 170 词**：两个 section 不等于两个段落，仍允许多个段落 / 列表。Flash 实际只有 3 块、10 条陈述、611 输出 Token，未达到 8 块 / 16 条 / 3000 Token 上限。浅、复制 S1 和没有 CTA 不能全归因于 Token 不够。

因此本实验同时检查模型能否在已有余量内组织更好的解释和 CTA，以及共同输入的上限。即使 Pro 也未必能用这份材料写成成熟长篇指南；不通过放宽 E 规则、补造事实、替换更长 S、扩 outline 或强加新 CTA Prompt 获得不公平优势。

## 同一评价规则与基准观察

完整冻结规则见 [rubric.md](rubric.md)。三层结论始终分开：原生技术 PASS / FAIL；内容维度 0–4 并附具体陈述依据；可信人类签核独立记为未发生。不给测试结果或 AI 评分加上客户正式批准。

内容维度为客户事实与 E1、数值条件完整性、解释深度、搜索意图、B2B 决策帮助、背景照搬、英语结构、CTA；Token / 成本另列，不用总分掩盖事实错误。E1 的强制逐字引用不计入背景照搬。

Flash 的已知基准：正文含标题 / heading 为 170 词（统一正则见 check_offline.py），10 条陈述；E1→CL3，原句及限制完整，独立 customer_refs=[E1]；CL4/5/6/7/9 共 73 个空白切分词逐字来自 S1；CALL_TO_ACTION 类型为 0。Flash 原生 PASS，内容评价沿用 NEEDS_REVISION，可信人类签核未发生。Pro 全部质量项、Token 与费用保留待测，不用 Mock 文章给 Pro 打分。

## 未来一次真实请求的最小授权范围

以下只是可审阅的范围，**本报告不是授权，也不自动触发调用**。需要用户下一条明确授权，并给出确切北京时间截止；执行窗口不超过签发起一小时，不默认为本轮或历史截止时间。

1. 仅本包 manifest 摘要及上面的 Pro request SHA-256；只向 `https://api.deepseek.com/chat/completions` 发送上述 11,413 bytes 一次 POST，model=deepseek-v4-pro。使用已有本地凭据但不输出或保存凭据 / authorization header。
2. temperature=0、thinking disabled、max_tokens=3000；一次尝试，timeout=60 秒，retries=0、follow_redirects=false、trust_env=false，请求 / 响应 byte 限额及单次范围如上。沿用 60 秒总执行超时与单次网络限制，不增加等待预算以补偿 Pro 可能较慢。
3. 消费新的一次性授权必须先于读取凭据和网络发送；请求失败、超时、连接中断、非 200、截断或校验失败均消耗唯一尝试，不自动重试、修复、续期或查询结果。使用全新本地保留位置与固定信任的单次记录，不回滚 / 复用旧许可。
4. 只在本地安全保留请求、完整或明确标记的部分响应、model text、usage、摘要、失败类别和原生验证报告；先做已有 secret 检查，发现秘密则拒绝持久化，不把改写后的文本叫作原始响应。用同一 frozen native input、同一 Validator / Finalizer、零模型修复，按冻结 rubric 对照 Flash。
5. 同意保守预算估算高峰 ¥0.225，预留 ¥0.25，并理解它不是账户消费硬限额。只使用本次测试合成 P/S/E；不重新生成 Flash、不查余额 / 模型列表、不调用 WordPress、不爬客户站、不创建生产文章、不启动部署或 Git 写操作。

授权可表述为：“授权对本包 manifest SHA-256（以 manifest.sha256 为准）和请求 SHA-256 991361f0eb58bfeb7fd557374faca7aae0093fd19a8e215586ca4c37593d8abc 执行一次 TEST-only V4 Pro 请求，接受上述参数、估算预算和零重试范围，截止北京时间 YYYY-MM-DD HH:MM:SS+08:00。”执行者需把实际 manifest 摘要明确绑定到记录；不把此模板视作用户已发出的指令。

## 本轮验证与边界

离线核验入口：

```powershell
.\.venv\Scripts\python.exe docs/seo-model-comparison-preflight-2026-10-11/check_offline.py
```

核验当前文件摘要、历史包与请求一致性、仅 model 的 byte / JSON 差异、原生 Flash 回放、Pro 形状 Mock 回放、错误 E 数字被原生拒绝、OneShotTransport 拒绝第二次 Mock 请求。Mock 的文字始终为历史 Flash 原文，不做 Pro 效果推断；脚本没有 live 模式，不读取 .env、不发真实 HTTP。

本轮实际运行：`python -m unittest tests.test_deepseek_content_draft_adapter tests.test_deepseek_draft_numeric_prompt tests.test_seo_e_only tests.test_content_draft_word_boundaries -q`，**54 项通过，5.571 秒**。冻结与原生离线核验结果见 [verification.json](verification.json)。本轮没有运行完整回归；用户提供的 1787 项历史结果不算本轮结果。公开文档抓取存在前述超时，后来成功核对；没有为此访问任何账户接口。

本轮仅新增此目录的冻结数据、评价规则、说明与离线核验脚本；未修改生产源码、Gate、P1、PostgreSQL 或原有未提交文件。DeepSeek 生成 0、余额查询 0、WordPress 0、部署 0、commit/push/merge 0。现有生产 / Web 的 Pro 配置支持仍未实现；账户可用性与 Pro 真实输出仍待一次新授权下验证。

公平性限制还包括：历史与未来调用时间不同、model 别名不能锁权重、缓存和分词可能不同、只有一组样本、评价规则制定者已知 Flash 问题、输入全为合成且 S 未验证。故 READY 只针对这次低成本方向性对照，不代表生产模型切换、真实客户文章合格或任何人类批准。
