# 单篇真实 DeepSeek 文章实验：离线预检

2026-10-10，Asia/Shanghai。**READY 仅指冻结材料和隔离实验入口已完成离线预检，等待明确的单次请求授权。真实 DeepSeek 请求数为 0，真实文章质量 NOT_TESTED。** 本轮没有读取 `.env`、访问客户站点、调用 WordPress、发布、部署、提交、推送、合并或操作 PostgreSQL。没有修改生产 Gate、P1 路径或任何 `src/` 文件，开始时的未提交修改保留。

## 复用与隔离

已核查 `seo-article-mvp-2026-10-10.md`、既有文章预览、原生 Draft prompt/schema/parser/finalizer、review/codec/SQLite，以及此前受控请求脚本。RouteDock 参考来自 `C:/Users/31969/.codex/worktrees/explain-offline-diagnosis/foreign-trade-geo-agent/scripts/test_explain_model.py` 和 `explain_second_preflight.py`；只读参考其精确请求绑定、16,000-byte 请求护栏、65,536-byte 响应护栏、60 秒超时和独占 attempt 机制，**没有引入其 TEST-only E 证据桥或授权**。另核查当前 ignored `.data/seo-draft-acceptance-20261008/accept_deepseek.py` 的旧单请求机制；当前生产 adapter 的非 MockTransport 拒绝仍保留。

新入口 `scripts/prepare_seo_article_experiment.py` 默认只准备离线包，不加载凭据。用既有 `ArticleFetcher/ArticleSearch/LocalResearch/ArticleOpportunity/ArticlePlan` 合成 ports，经当前生产 planning 生成合法单个 C1 `CREATE_NEW_RESOURCE`，到 `INTAKE_EXECUTION_BLOCKED` 停止，production writer=0。没有调用 `build_isolated_test_planning_workflow`，没有提交 TEST reviewer verdict，也没有客户 E→P/S 重标。

独立实验直接复用 `_parse_specification` 和 `finalize_draft_item`，保留所有原生字段、数值、引用、claim 分类、宣传限制、节边界及预算校验。刻意不运行原生 workflow 的修复循环；失败直接停止，绝无第二次模型请求。这个脚本不被生产 runtime/CLI 导入，不能给生产 Draft 签发权限。通过后仅追加到实验自己的 SQLite，使用原生只读 review 重开与导出 Markdown。

## 最终冻结包与请求配置

唯一拟授权目录为 `.data/seo-article-experiment-20261010-final/`。更早的 `.data/seo-article-experiment-20261010/` 是准备迭代，**不属于本次拟授权范围**。两个目录均没有 `live-attempt`。不得覆写冻结文件；变更输入、Prompt 或依赖源码后须重新预检、冻结并重新授权。

| 配置 | 实际值 |
| --- | --- |
| 项目 / 任务 | SYNTHETIC-NOVACNC / SYNTHETIC-NOVACNC-ARTICLE-001 |
| 输出 | 一篇英文 `NEW_RESOURCE_DRAFT`，NovaCNC machining center buyer guide |
| Endpoint | POST https://api.deepseek.com/chat/completions |
| 模型 | deepseek-flash |
| thinking / temperature | disabled / 0 |
| 输出上限 | 3000 tokens，没有提高 |
| 超时 | HTTP 各阶段最多 60 秒；整个请求、流式读取和验证另设 60 秒总期限 |
| 请求体 | 14,776 UTF-8 bytes，护栏 16,000 bytes |
| 响应 | 流式解码后最多 65,536 bytes；原生正文另限 16,000 chars / 32,768 bytes |
| 网络行为 | 最多一次；AsyncHTTPTransport(retries=0)；不跟随重定向；trust_env=False |
| 原生文章预算 | 原两节 outline；全篇最多 8 blocks / 16 claims；每 paragraph 最多 4 claims、每 claim 300 chars；每节最多 4 paragraph blocks，其他原生预算同样保留 |
| 失败行为 | HTTP/超时/截断/非法 JSON/原生校验失败/绑定改变/过期均停止；不修复、不重发、不导出失败候选 |
| 费用边界 | 一次请求及上述输入/输出上限；没有账户侧硬金额限额，不声称价格或实际费用已验证 |

冻结摘要：

```text
request.json SHA-256:
a464cb595ecefc13a154dbdf9dbde0aea1e3be233b574f1bf987f7d34c2cc73d
bundle.json SHA-256（授权绑定）:
b87e169204fd31e36ab196d45becbc55bbfe21cc18ab2ff448e9773953d7c198
system-prompt.txt SHA-256:
ab54131053ce764ef078d602c3bf1067dc17d044d9a95f794d969faa4bacfb22
user-material.json SHA-256:
f5fb911fe1fd0a0fc56c473f72dd3125c014a07c16e94d747051ee8d43e5bc08
```

`request.json` 是将实际发送的精确 body bytes，不含认证 headers/cookies。`native-material.json` 保留未追加实验说明的原生材料；另保存完整 `site-content.json`、`opportunities.json`、`change-plan.json`、system、user material 和质量清单。`bundle.json` 记录每个文件及现有源码/fixture/环境加载器的 SHA-256；调用前后重新检查。认证只在未来授权后从 ignored `.env` 读取，不冻结 secret。任何 provider error body、raw envelope、headers、异常原文均不落盘；已知 key 回显和典型 secret 标记在解析/保存前拒绝。

独立输出为同目录下 `mock-<uuid>/` 和未来唯一的 `live-attempt/`；真实调用前独占创建 `live-attempt/started.json`，即使凭据缺失、失败、超时或进程崩溃也不自动重发。标记绑定 bundle/request digest 与授权截止时间。CLI digest/expiry 参数只是绑定检查，不能替代聊天中的真人授权，更不是生产许可。

## 事实、搜索意图与预算

完整保留三组必需事实及限定，原生 P1 自身含这些事实，不依赖指令 ledger 提供第一方事实：

- 主轴：VMC-DEMO，8000 rpm，连续额定，DEMO-SPINDLE-1，20 C，无切削负载结论。
- 公差：VMC-DEMO 铝测试件，+/-0.02 mm，20 C，DEMO-TEST-2 protocol，不保证其他材料或生产条件。
- 证书：DEMO-CNC-1，Fictional Lab，DEMO-2026，VMC-DEMO，2027-01-01 到期，明确非真实认证。

搜索意图固定为采购询价前理解测试适用性、限定和证书范围，并知道应索取什么证据。保留原生 `spindle performance` / `machining tolerance` 两节，证书内容放在第二节，不额外发明第三节或改变 Plan。实验说明只追加完整义务与写作目标，未改变原生输出 schema，system 实际 7,465 chars，低于 8,000 上限。

本地完整覆盖见证仍是既有手写 fixture：14 claims / 5 blocks，provider specification 3,713 bytes，含全部限定并通过原生 finalizer。它证明当前结构预算可容纳这个短文任务，**不证明模型会遵循、3000 tokens 必然够用、或真实质量合格**；没有使用 provider tokenizer，bytes 不能作为实测 tokens。未发现确定性事实覆盖冲突；若真实输出截断或遗漏必要限定，判失败并报告冲突，不能提高上限或删事实换通过。

P1/S1 本来含有手写说明句，后续必须独立比较模型正文和完整来源；不能把近义词改写或引用齐全认定为原创解释。这次只能验证合成 P/S 整篇生成，不能宣称验证了客户 E-only 生成。

## 独立质量验收及实际离线结果

冻结 `quality-checklist.json`，真实成功输出时复制为独立输出目录的 `quality-review.json`，逐行记录正文/claim 位置、结论及理由。核查原生完整文章、全部事实限定与逐句引用、虚构参数/关系/营销承诺、预设买家问题与搜索意图、段落衔接、解释和采购决策价值、证据复述/重复，以及重读和 Markdown 导出。全部初始 UNREVIEWED，最终整篇是否可用须独立人工结论；不把 schema success 当质量通过。测试还特意证明：删掉部分事实的候选可能仍通过原生机械校验，所以不能省略独立语义审核。

最终本地持久化 Mock 成功输出：

```text
.data/seo-article-experiment-20261010-final/mock-91bc09130e424301bbe2fa98b4ad0ef0/
run_id: 503bdc4a-b360-432d-a015-c88b04c29e37
artifact_id: f8dfe3b8-17f3-460f-927e-0d5c9fb93c39
```

包含 `history.sqlite3`、`content-draft.json`、`model-output.txt`、`article-preview.md`、`quality-review.json` 和净化 `diagnostics.json`。预览醒目标明 **MOCK / hand-written / NOT a real model article**，model_generated=false，quality=UNREVIEWED。另一个 bad_json Mock 目录仅含净化诊断，JSON_FORMAT 后停止，没有候选/数据库/Markdown；两场景分别一条 Mock 请求、真实请求均 0。见 `.data/seo-article-experiment-20261010-checks/final-mock-verification.json`。

新增 24 项 focused tests，含请求字节/配置、单次传输及第二次拒绝、禁 retry/redirect、HTTP/超时/总期限/截断/secret/资源上限失败停止、冻结文件/源码前后改变拒绝、原生引用/数值/宣传/outline/预算校验、重开 SQLite 和只读 CLI Markdown、既有 Gate/真实 adapter 拒绝、TEST permissive admission 也被拒绝、WordPress attempts=0、凭据失败消耗预留及过期前置检查、准备预算冲突不删事实。

最终相关回归：**168 tests / 25.590s / OK，exit=0**，覆盖上述新测试、原文章 demo、DeepSeek Draft adapter/prompt、原生 core/workflow/数值/预算、review 与生产执行边界。命令、日志及最终源码 hashes 见 `seo-article-experiment-preflight-2026-10-10-verification.json`。本轮没有重跑完整 1614 项 suite，不沿用上轮数字作为本轮通过结果。

迭代问题如实保留：首轮 21 项有 1 项失败，实验脚本误用 `SQLiteHistoryReader.list_wordpress_attempts`（reader 无该方法）；改用既有 store 接口后通过，未改生产契约。一次回归日志整理发生 Windows 编码解码失败；测试日志本身为 168 项 OK。随后显式 UTF-8 重跑记录，最终上述结果通过。最后增加 Mock 预览标记后再次运行全部相关 168 项，通过。

## 下一次授权范围（本轮未获授权，已停止）

用户需要明确授权：**仅上述最终目录和 bundle SHA-256、固定 NovaCNC 合成 P/S snapshot、C1 单篇英文文章，使用 `.env` 的 DeepSeek key 向上述 endpoint 发出最多一次 deepseek-flash 请求，3000 output tokens、60 秒、不重试，仅本地候选留存与独立全文质量审核**，并指定一个带时区的授权截止时间。输入、模型、Prompt 或代码摘要改变则这份授权失效；失败/崩溃不自动重发。费用按冻结的一次请求与 token 边界，不将未经验证的金额估计当硬预算。

此授权不涵盖真实客户资料/E-only、其他模型请求、生产 Draft、P1、PostgreSQL、WordPress、发布、部署或 Git 历史操作。明确授权前不运行 `--live`。本轮 READY 后停止。

本轮仅新增两个代码文件：`scripts/prepare_seo_article_experiment.py`、`tests/test_seo_article_experiment.py`；另新增本报告、verification 和 ignored 本地实验/日志。没有改动既有源码或已有文档。
