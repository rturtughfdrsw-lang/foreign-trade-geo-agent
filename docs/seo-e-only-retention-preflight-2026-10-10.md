# E-only 响应留存修复与独立重新预检（2026-10-10）

**READY：仅表示离线实验入口预检通过。真实生成请求、余额查询、真实 Token 消耗、WordPress 写入均为 0。新冻结包没有执行授权，完成后停止。**

根因是共享入口在保存任何结果前先检查 HTTP 状态、解析 JSON 和执行原生 Validator，usage 又在 Validator 后提取。异常分支只能保存 diagnostics，故错误响应、被拒正文及 usage 丢失。

仅修改两个独立实验脚本：共享入口先持久化 HTTP body 原始字节并 fsync，再解析 envelope/提取 usage 与 finish_reason，原样保存 model-output。原生 Parser/Validator 拒绝时另存 rejected-candidate，不修正文、不放松校验。补充失败阶段、JSON 行列/偏移、claim 数量/预算、E 引用字段及原生数值诊断。JSON 诊断采用临时文件、fsync 和原子替换。

输出先独占预留、收紧本机 ACL；拒绝历史目录覆盖。live 仍为每个冻结目录一次固定 live-attempt 预留，禁止重新消费同一预留；Mock 每次使用新的 UUID。任何持久化失败均为 INCOMPLETE，删除本次有效 Draft 导出并移除 artifact/run 成功标识，不重试。完全无法写盘时，返回值与 started.json 的未完成状态供审查，不伪造落盘成功。

秘密扫描发生在 JSON parser 之前，只在内存扫描字节/转义文本，不改变原文。检测到鉴权/Key/Cookie 时明确 WITHHELD_SECRET，不保存或输出秘密，不以删改后的正文冒充原始响应。请求增加 Accept-Encoding: identity；若仍收到压缩正文，明确 WITHHELD_UNINSPECTABLE / ENCODED_RESPONSE_REFUSED。未保存任何请求或响应 header。

实际文件样例均来自 MockTransport，文章为手写 fixture，usage 为模拟数值，不代表真实模型能力或账单。完整文件大小、SHA-256、诊断和返回值见 [留存矩阵](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/preflight-result.json)。

| 场景 | 状态 / 类别 | 请求次数 | 留存 |
|---|---|---:|---|
| valid | SUCCESS | 1 | article-preview.md, content-draft.json, diagnostics.json, execution-review.json, history.sqlite3, model-output.txt, quality-review.json, response-body.bin, started.json |
| http_invalid_json | FAILED / PROVIDER_JSON_FORMAT | 1 | diagnostics.json, response-body.bin, started.json |
| draft_invalid_json | FAILED / JSON_FORMAT | 1 | diagnostics.json, model-output.txt, rejected-candidate.txt, response-body.bin, started.json |
| validator_reject | FAILED / NEW_RESOURCE_INVALID | 1 | diagnostics.json, model-output.txt, rejected-candidate.txt, response-body.bin, started.json |
| invalid_e | FAILED / UNKNOWN_CUSTOMER_REFERENCE | 1 | diagnostics.json, model-output.txt, rejected-candidate.txt, response-body.bin, started.json |
| claim_budget | FAILED / CLAIM_BUDGET | 1 | diagnostics.json, model-output.txt, rejected-candidate.txt, response-body.bin, started.json |
| numeric_reject | FAILED / NUMERIC_NOT_GROUNDED | 1 | diagnostics.json, model-output.txt, rejected-candidate.txt, response-body.bin, started.json |
| truncated | FAILED / OUTPUT_INCOMPLETE | 1 | diagnostics.json, model-output.txt, response-body.bin, started.json |
| http_error | FAILED / PROVIDER_HTTP_FAILURE | 1 | diagnostics.json, response-body.bin, started.json |
| timeout | FAILED / REQUEST_TIMEOUT | 1 | diagnostics.json, started.json |
| disconnect | FAILED / REQUEST_DISCONNECTED | 1 | diagnostics.json, started.json |
| partial_disconnect | FAILED / REQUEST_DISCONNECTED | 1 | diagnostics.json, response-body.bin, started.json |
| body_write_failure | INCOMPLETE / PERSISTENCE_FAILED | 1 | diagnostics.json, started.json |
| diagnostics_write_failure | INCOMPLETE / PERSISTENCE_FAILED | 1 | execution-review.json, model-output.txt, quality-review.json, response-body.bin, started.json |
| existing_directory | REFUSED | 0 | sentinel.txt |

正常响应实例：[diagnostics](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09/mock-83cc46052f594c498d104ea5b8b8569e/diagnostics.json)；[原始响应](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09/mock-83cc46052f594c498d104ea5b8b8569e/response-body.bin)。

数值拒绝实例：[diagnostics](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09/mock-29d27c8c85bb4355a26ad7c967c66c57/diagnostics.json)；[原样 rejected candidate](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09/mock-29d27c8c85bb4355a26ad7c967c66c57/rejected-candidate.txt)。

15 种留存结果已另行从磁盘重读，文件大小/哈希一致；被拒候选再次通过同一原生 Validator，仍得到原失败类别。超时/断连无响应时，http_status、finish_reason、usage 为 null；部分断流只保存已收字节，标记 PARTIAL_RESPONSE。已有目录拒绝覆盖的请求数为 0。见 [独立重读核验](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/offline-reread-verification.json)。

新独立冻结目录：[冻结目录](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09)。

- 新 bundle SHA-256：`106eaa38e82a2802c267a876fad93e81b83171cb458e7a8be80966b1a46042f7`
- 上一轮 bundle SHA-256：`7f164ee4773b9f35ae39137bdafd4f737503d2124e0aea912e41fd20e50b6a2c`
- 请求 SHA-256：`53a77560a5446b7d5e15699aa7f060112b7ae4dfe82f3e2d98ad9195edf1ed6b`（12,002 UTF-8 bytes，逐字节未变）
- System Prompt SHA-256：`3f353b81a72db31854895b43dcabb5b1d6551268c8d3d9108d8ca1e9f07bb5f1`
- User material SHA-256：`7728205dc3824b6d5189cd89976ef96ac3a004553ac8937eb7783ad072760b7d`
- [仅冻结输入的 ZIP](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-inputs.zip) SHA-256：`4db792f5f667bc66581ccd750463e3358c42436342026fafd086d35179732a59`（不包含任何响应/失败正文）

精确差异：14 个冻结输入文件的内容及摘要全部相同；117 个源码摘要中只有以下两个变化，其余 115 个相同。没有重建证据 ID、改写 Prompt、调整输入或改动旧包 preflight 状态。当前 READY 结论写在独立报告中。

| 源码 | 旧 SHA-256 | 新 SHA-256 |
|---|---|---|
| scripts/prepare_seo_article_experiment.py | `1c3ba903fcb1840a2eb5e6e52f0c9802a81b60920988c0472ea651b0569d211a` | `f62832b42f1c958a9bd16247ce397c615417b8b249217565bef7cc05704adf9e` |
| scripts/prepare_seo_e_only_experiment.py | `77a684213aab1123891194965d95095568c758b3b7115024ea2e0f2e9d91497c` | `8bee99a9684b37835fb7da4a3d7e7ea418c3efbaaaad1e41516d7dab9eb139ea` |

完整源码差异：[code-diff.patch](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/code-diff.patch)。382 个历史报告、旧冻结结果和 src 文件哈希未变化。新增/调整测试：test_seo_e_only_retention.py、test_seo_e_only_experiment.py、test_seo_article_experiment.py；生产 core、adapters、workflows、Gate、P1、PostgreSQL 均未修改。

实际测试记录（所有失败日志保留，当前无未解决失败）：

| 日志 | 测试数 | 结果 | 退出码 |
|---|---:|---|---:|
| [red-tests.log](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/red-tests.log) | 16 | FAILED (failures=4, errors=12) | 1 |
| [green-tests-1.log](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/green-tests-1.log) | 16 | FAILED (failures=2) | 1 |
| [focused-1.log](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/focused-1.log) | 51 | OK | 0 |
| [red-edge-tests.log](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/red-edge-tests.log) | 23 | FAILED (failures=3) | 1 |
| [focused-final.log](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/focused-final.log) | 96 | OK | 0 |
| [red-parser-order.log](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/red-parser-order.log) | 1 | FAILED (failures=1) | 1 |
| [focused-final-2.log](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/focused-final-2.log) | 97 | OK | 0 |
| [full-final.log](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/full-final.log) | 1721 | OK | 0 |

初次 Red 用例证明原入口缺少留存；首轮修复后的两条失败是新测试误写了原生类别（实际为 NEW_RESOURCE_INVALID / UNKNOWN_CUSTOMER_REFERENCE），已纠正测试预期。边界 Red 用例证明需要清理成功后诊断写入失败的 Draft、拒绝无法检查的压缩响应，并在无正文时独立提取 finish_reason；parser 顺序 Red 用例证明秘密扫描不能调用 JSON parser。上述缺陷均已修复，最终针对性 97 项、完整 1721 项通过，退出码均为 0。

完整回归命令：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`。执行时 PYTHONPATH 加载本地外部 socket 禁止保护，允许 asyncio/TestClient 必需的 loopback；PYTHONUTF8=1。未调用 opt-in live 检查脚本。仍有既有 Starlette/httpx deprecation warning，未改依赖。

独立预检脚本首次退出 1，原因是把 asyncio loopback socketpair 一并拦截，生成 transport 未调用；第二次退出 1，原因是把每次新 TEST 审核的 reviewed_at 时间戳当作不变量，只有一次 Mock 请求。最终修正为保留版本/内容/来源比较、规范化审核时间，15 场景通过，退出 0。三个日志均保留，所有目录均独立，旧结果未覆盖。

真实请求配置与原预检一致：POST https://api.deepseek.com/chat/completions；deepseek-flash；thinking disabled；temperature 0；最多 1 请求；max_tokens 3000；60 秒请求/总生成等待上限；不自动重试、不跟随重定向、trust_env false；输入上限 16,000 bytes、响应上限 65,536 bytes、原生正文上限 16,000 chars / 32,768 bytes；8 blocks、16 claims、每 claim 300 chars。E1 独有事实不进入 P/S，证据与 Plan 版本均为 2，执行前后仍用临时副本重新 TEST 审核，未授予正式人工批准。

本轮实际预算使用：真实请求 0、余额查询 0、真实输入/输出/合计 Token 0。Mock usage 的 2400/800/3200 仅用于证明失败时仍可保留 usage。输入字节预算不等于精确输入 Token 数；未声称账户侧金额封顶，也未联网验证模型可用性、余额、价格或实际文章质量。

Windows ACL 实测：实验根目录、最终冻结目录、attempt 目录禁用继承，仅当前账户 FullControl；body 文件仅继承 attempt 的同一账户权限。Git 忽略 .data，原始响应仅在本地受限目录；ZIP 仅含冻结输入。见 [ACL 核验](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/acl-verification.json)。

**结论：READY（离线预检）。真实模型质量仍为 NOT_TESTED，生产仍 NO-GO；未部署、commit、push、merge。此前单次授权不延续到新摘要，必须等待对该新包的明确授权及带时区有效期，不能自动执行。**
