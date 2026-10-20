# 整篇 Draft 数字边界误判：离线诊断与最小修复

日期：2026-10-10（Asia/Shanghai）。冻结文章原样重放已通过原生 Parser、Validator/Finalizer、序列化、SQLite 重开和原生 Markdown 导出。**专业质量仍 NOT_APPROVED，独立人工签核 NOT_SIGNED，生产 NO-GO，PostgreSQL BLOCKED。** 本轮真实请求、WordPress 写入均为零。

## 1. 读取对象和精确复现

原始目录为 `.data/seo-article-experiment-20261010-final/`，本次结果在其 `live-attempt/`。读取了冻结原生输入、`raw-response.json`、`model-output.txt`、`fact-citations.json`、`native-validator.json`、`native-failure-detail.json`、`quality-review.json`、`quality-report.md`，并检查实际 core、Parser、证据构建和 Finalizer 源码。

输入 bundle SHA-256：`b87e169204fd31e36ab196d45becbc55bbfe21cc18ab2ff448e9773953d7c198`。

正文 SHA-256：`9776fb2b6e9788f0d6198f4bce4ebb59d19bb5b348619b3098d6bc33ad08d179`。

响应 SHA-256：`3477e0951a4f645e9a6bb19a87f9cbe09864182b8e074fcfcc527b860b2b3e0f`。

离线执行前后逐文件核验输入 manifest 和历史结果 manifest，响应中提取的正文等于冻结 `model-output.txt`，13 条正文和 P/S refs 与历史引用表逐项一致。原始目录全部文件保持不变。

修改前在原源码上复现：Parser PASS，Finalizer 返回 `NUMERIC_NOT_GROUNDED`。原生 observer 定位到 `draft.sections[1].blocks[1].claims[1].text`，即 Q11；3 个表达式中 1 个匹配、2 个不匹配，裸数字计数为 0。

## 2. 根因与完整路径

`_parse_specification` → `finalize_draft_item` → NEW_RESOURCE 每节 `_finalize_blocks` → `_finalize_claim` → `_validate_claim_evidence` → `_validate_numeric_grounding` → `extract_numeric_expressions` → `_numeric_expression_is_present`。

P/S 存在性和 change scope 先验证；Q11 是 `OBSERVED_PRODUCT_FACT`，有 P1/S1，数值依据只来自所引用的 P1，不用 S1 替代第一方事实。`_evidence_text` 汇总标题、正文和结构化内容；P1 正文虽截断，结构化内容仍保留三组完整事实。双方使用现有 NFKC、casefold 和空白折叠，未出现证据丢失或归一化失败。

真正的问题是 token 的开始、结束和类型识别：旧数字扫描只从数字起始，`DEMO-CNC-1` 只取得 `1`；尾部规则允许任意英文字母，随后吞入 `was`。数字主体又允许终止逗号，日期后继续吞入 `and`。严格全文匹配正确地拒绝了错误提取出来的字符串。

| Q11 内容 | 修改前提取 | 修改后提取 |
| --- | --- | --- |
| `DEMO-CNC-1 was` | `1 was`，不匹配 | `demo-cnc-1`，匹配 |
| `DEMO-2026 for` | `2026 for`，碰巧匹配 | `demo-2026`，匹配 |
| `2027-01-01, and` | `2027-01-01, and`，不匹配 | `2027-01-01`，匹配 |

同源问题也影响 Q2 的协议尾号 `1 at` 和 Q8 的 `2 protocol`；新规则校验完整 `demo-spindle-1`、`demo-test-2`。旧逻辑还漏识别 X7 等字母起始型号，新回归覆盖正确和篡改型号。

## 3. 最小修改及事实保护

唯一生产源码修改是 `core/content_draft.py` 的数字提取和精确 token 匹配边界：

- 数字字母混合编号作为完整 token 识别，继续做证据精确匹配，不按品牌或证书名称特判。
- `YYYY-MM-DD` / `YYYY/MM/DD` 日期在 token 结束后停止；末尾句读逗号、句号不进入数值表达式，也不跨句读吞普通单词。
- 匹配两侧的连字符、斜杠相邻数字字母不能用于借用较长编号或日期的子串。

原有 NFKC/casefold、数字与单位间距、裸数字拒绝、数值/单位精确匹配、P/S scope、claim type、Draft budget、Evidence/Gate/执行授权保持。没有数字 claim 豁免、宽泛白名单、Prompt 修改、品牌硬编码或业务 schema 扩展。裸数字即使出现在 P 中也继续拒绝；源中 110 bar / 0.5 bar 不能支持 10 bar / 5 bar，10 mm 不能支持 10 m。

保护范围仍是现有词法 grounding：不会验证证书权威性、日历有效性或无数字事实的语义；没有扩展单位词典或公差正负号语义归一化。S-only 一般背景保留既有规则，不能据此证明第一方参数。专业审核必须独立进行。

## 4. 冻结响应重放结果

完全不改模型正文。Q2、Q8、Q11 共 9 个新提取表达式全部在引用的 P1 中匹配。原生 input 检查、Parser、Validator/Finalizer 全通过；保留两节、5 blocks、13 claims、287 词和 `requires_human_review=true`。

在新隔离目录 `.data/numeric-grounding-fix-20261010/after/` 创建仅供重放的 SQLite 和原生候选 artifact，验证编码/解码等值、新 reader 重开等值、原生 Review Markdown 导出、WordPress attempts=0。预览醒目标记 `OFFLINE REPLAY ONLY / QUALITY NOT_APPROVED / production NO-GO`。没有创建正式商业 Draft，也没有修改历史质量结论或签核状态。

历史 live 入口的代码 hash 保护未改。修改后当前 core hash 与历史 bundle 不一致是预期现象；离线重放只验证历史文件完整性并显式使用新验证器，不能作为重用旧生成授权的依据。未改 bundle、未重新冻结或执行生成。

重放脚本：`.data/numeric-grounding-fix-20261010/offline_replay.py`。它只读固定归档，输出目录必须不存在，没有网络 transport 或 live 模式。示例（每次使用新的输出目录）：

```powershell
.\.venv\Scripts\python.exe .data/numeric-grounding-fix-20261010/offline_replay.py .data/numeric-grounding-fix-20261010/replay-new
```

修改前后完整诊断分别在 `before/replay.json` 和 `after/replay.json`。

## 5. 回归验证

新增 `tests/test_content_draft_numeric_boundaries.py`，配套 `tests/fixtures/content_draft_numeric_article/` 保存四个逐字复制的合成原生输入/模型正文及 provenance 说明；不复制 raw envelope 或凭据。

覆盖原始两处误判、正确编号/日期、型号、Unicode/大小写归一化、标点、单位间距、百分比/分数/公差、篡改数值/单位/日期/编号、较长 token 子串、裸数字、P/S 引用完整性与原样整文回放。现有 section、table、internal link、structure-only、new resource 和 numeric diagnostic 测试保留。

先写回归再改源码：首次 9 项测试得到 8 个失败（含 subTest），准确暴露冻结文章拒绝、错吞词、型号漏检和日期子串问题；不是环境异常。修改后相关 6 模块共 91 tests、5.561s、OK、exit 0。之后新增归一化和斜杠相邻负例，最终新增模块单跑 10 tests、0.009s、OK、exit 0。

最终完整 suite：**1648 tests、279.482s、OK、exit 0，零测试失败**。`git diff --check` exit 0；新增文件空白检查、fixture 原始字节相等检查通过。日志中的 asyncio slow-task 提示及 launcher 用例模拟的端口冲突消息不属于测试失败。没有执行 live/integration scripts、P1 或 PostgreSQL 验收。

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_content_draft_numeric_boundaries tests.test_content_draft_numeric_contract tests.test_content_draft_core tests.test_content_draft_numeric_diagnostic tests.test_content_draft_workflow tests.test_seo_article_experiment -v
.\.venv\Scripts\python.exe -m unittest tests.test_content_draft_numeric_boundaries -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

本轮完整日志、命令和摘要见 `.data/numeric-grounding-fix-20261010/` 及 [verification JSON](seo-article-numeric-grounding-fix-2026-10-10-verification.json)。不把此前历史套件成绩作为本轮结果。

## 6. 本轮文件与 MVP 剩余缺口

本轮修改 `src/foreign_trade_geo_agent/core/content_draft.py`，新增上述测试、fixture、本报告及 verification JSON；诊断、日志和隔离重放产物在 ignored `.data/numeric-grounding-fix-20261010/`。开始时已有的文章分节等未提交修改保留，没有覆盖其他用户文件。

后续尚缺：

1. **E-only 最小闭环**：原生 provider-independent E 证据/逐项引用和覆盖校验；让仅客户 E 有事实、P/S 没有的文章可在明确隔离范围内演示。当前 Intake 只支持单个 EXPAND_SECTION、EXPLAIN，尚未覆盖 CREATE_NEW_RESOURCE；还需要真实来源/适用性审核、当前版本绑定和独立全文质量审核。下一项为此任务，本轮不实施。
2. **前端**：已有分析、Plan 和只读 Draft Review，但客户补证、缺口/待审/冲突状态、证据逐项核查、可信人审和全文质量决定尚未形成完整交互闭环；不能把 JSON/CLI 演示当作完成前端。
3. **WordPress 草稿交付**：已有 create-only、draft-only adapter/workflow 和演示交付页面，Live composition 没有交付边界；需先有正式批准的当前文章、具体目标站和单独写入授权。整篇 HTML 当前只渲染平铺 blocks，尚未消费 `ordered_headings` / `section_block_counts`，需要后续保留节标题的适配与验收。继续保留 UNKNOWN/PENDING 禁盲重试及写后核验。

P1 全局一次性消费的历史问题未处理，PostgreSQL 仍 BLOCKED；本轮没有运行其 live 验收或以 SQLite 重放替代生产条件。文章的近源改写、解释深度、标准核查动作缺失和 S1 截断等历史质量问题仍存在。通过机器契约不能解除它们。

没有调用真实模型/客户站点、WordPress 写入、部署、提交、推送、合并、企业知识库或 PostgreSQL 扩展。完成本轮诊断、修复和回归后停止。
