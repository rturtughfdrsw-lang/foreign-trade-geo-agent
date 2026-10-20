# TEST-only 真实 Web → DeepSeek 单次实验验收

结论：**真实调用和 Web 生成、校验、持久化、展示、导出链路通过；文章商业质量需要修改，未获人工批准。** 本次实验服务已关闭，不继续请求或修改文章。

## 授权、时间与冻结核对

本次仅使用用户明确授权的包 `f573be4c0cf539984c9ba1c4cdf13856fdf3a02fc3c4adcfa0737ffd27bf99c0`，许可 `WEB-TEST-F573BE4C-ONCE`。截止时间为 **2026-10-11 00:30:00+08:00**。此前 10 月 10 日停止记录继续保留，本报告记录本次实际执行。

| 事件 | 北京时间（2026-10-11） |
| --- | --- |
| 首次可信 UTC 时钟查询换算 | 00:15:26 |
| 冻结包、任务和环境核对 | 00:16:29.669 |
| 唯一余额查询完成 | 00:17:10.308 |
| arm-live 前再次查询时钟 | 00:17:52 |
| Web POST 持久化消费许可 | 00:18:32.799083 |
| 消费后保存 started.json | 00:18:32.875897 |
| 原生 SQLite run 完成 | 00:18:35.745532 |

签发距确切截止约 12 分钟，满足签发时起不超过一小时；请求和完成均早于截止。没有延长、更新、重发或重置许可。

156 个源码、模板和资源摘要与冻结清单完全相同；清单 SHA-256 为 `1f66a0bbc3375192dae267ec7f634b231d41a4d0343aad9ea72f20317f15f09f`。冻结输入与报告旁副本逐字节一致；当前 Intake 摘要为 `8fa01547bce62864ccc4cdf77bd0c4c88de453d40ec9dfd368d2c02efd02aeea`，task 1 / Plan 2 / E 2 / revision 3。原生输入复核通过，重新构造请求逐字节一致。TEST-only freshness 复核遵循已有代码，没有改变请求、证据或权限。

请求 SHA-256 为 `8ed4e1fa85f01505193d899879e1399154a9f913398a34edbef355d949a35734`，11,412 bytes。模型 deepseek-flash，temperature 0，thinking disabled，max_tokens 3000，60 秒超时、transport retries=0、follow_redirects=false、trust_env=false。请求和响应大小限额仍为 16,000 / 65,536 bytes。

运行环境已记录：Python 3.12.10、httpx 0.28.1、FastAPI 0.142.2、Starlette 1.7.0、Uvicorn 0.54.0，使用项目既有 `.venv`。冻结清单覆盖运行源码、模板、资源与输入，并未包含依赖二进制摘要；不宣称对依赖二进制完成历史逐字节核验。本次未安装或升级依赖。

## 本次真实调用

| 项目 | 实际结果 |
| --- | --- |
| 余额查询 | 1 次，HTTP 200，账户可用，CNY ≥ ¥1 预留条件通过 |
| DeepSeek 生成请求 | 1 次，由实际浏览器按钮提交 `/mvp/generate` 触发 |
| HTTP / finish_reason | 200 / stop |
| 输入 / 输出 / 总 Token | 2486 / 611 / 3097 |
| 缓存命中 / 未命中输入 Token | 1280 / 1206 |
| 原始响应 | 完整留存，2926 bytes，无截断 |
| 响应 SHA-256 | `61bc38bbb43ca6d7a09e46d31720b067b19de9ca43b2c2bd5a6098382e0b5fa3` |
| 模型文本 SHA-256 | `e90eaa40499c7bc6e0e6f40d21e9eada10c9ea13cfafea5eb6e182e4ff349201` |
| 自动重试 / 模型修复请求 | 0 / 0 |

重新只读查阅了 [DeepSeek 官方价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。当前空闲时段每百万 Token 输入命中 ¥0.02、未命中 ¥1、输出 ¥4。16,000 输入与 3,000 输出的原保守预算估计为 ¥0.028；按实际 usage 计算约 ¥0.0036756。均为费用估计，**不是账户账单或消费硬上限**；没有进行第二次余额查询或用余额差推算费用。余额文档的本次公开网页读取超时，账户接口本身一次调用成功；没有重试账户请求。

## Web、SQLite、Markdown 与一次性许可

既有 arm-live 只签发固定服务端账本许可，serve-live 只启动本地服务。因 8011 已有其他监听，本次使用空闲的 8021，不停止或更改原服务。浏览器页面核对包摘要、版本、截止和参数后，点击“生成文章（TEST-only · 单次真实调用）”。实际页面经历 RUNNING → SUCCEEDED；服务日志确认仅一次生成 POST，返回 303 后 GET 状态页。

原始结果保存在 `.data/web-deepseek-ready-20261010/generation/f573be4c0cf539984c9ba1c4cdf13856fdf3a02fc3c4adcfa0737ffd27bf99c0/`。包含 request.json、started.json、response-body.bin、model-output.txt、result.json、history.sqlite3。响应、请求、模型文本的摘要已重新核验；本报告目录保留相应文件副本、完整正文、浏览器截图、页面文本和核验 JSON。原始响应和模型输出没有改写。

- SQLite `integrity_check=ok`，run 状态 succeeded，完成时间在截止前；原生 Draft Validator / Finalizer 与既有 Review 均通过。
- Run：`3425b49c-74e2-46aa-a800-27c2b76ed8e7`；Draft artifact：`2559b26b-844b-454a-bd24-ff8d42f0c017`。
- Web 读取本次 LIVE 原生 Draft，确认与当前任务、证据及冻结版本一致，状态仍为 PENDING_REVIEW / v0。
- 实际点击 Web Markdown 下载；[article.md](article.md) 与服务端 Markdown 序列化及 SQLite 原生正文一致。[article-body.md](article-body.md) 单独保留完整正文。
- 许可固定账本中 claimed 时间早于 started 文件时间；现有代码在 SQLite synchronous=FULL / BEGIN IMMEDIATE / commit 成功后，才创建执行目录、异步任务、读取凭据和创建真实 transport。这是代码顺序审计及持久化时间证据，未新增抓包或网络前探针。
- 对同一许可再次调用既有 `claim`，实际拒绝 `PERMIT_EXPIRED_OR_CONSUMED`；账本行完全不变，没有执行第二次网络请求。
- 关闭本次服务器，再用同一包、同一许可启动新进程；浏览器仍显示 SUCCEEDED、请求数 1、生成按钮禁用。没有重签许可，也没有执行重复 HTTP POST。
- 重启验收结束后关闭本次 8021 服务，确认端口无监听。原固定许可账本保留原地，没有复制、删除、恢复或回滚。

有效浏览器证据为 [browser-success.png](browser-success.png)、[browser-article.png](browser-article.png) 和 [browser-restarted.png](browser-restarted.png)。额外 viewport 截图 browser-proof.png 因滚动位置呈空白，未用作验收证据。

## E1 引用与文章质量

文章保留批准标题和两个 outline heading，共 10 条陈述、3 个内容块。完整正文按英文词边界模式计数为 170 词，按空白切分为 176 项（含标题及列表标记）。没有把 Token 数当作正文词数。

E1 唯一映射为 **E1 → CL3**，证据 v2，要求 F1，`local:novacnc/E1/utf8-text`，字符区间 `[46, 239]`。完整原文逐字一致：

> SYNTHETIC ONLY: NovaCNC NCX7 spindle rated 7200 rpm continuously under NOVA-TEST-7 protocol at 20 C on an unloaded bench; applies only to NCX7 and is not a cutting-load or production guarantee.

NCX7、7200 rpm continuously、NOVA-TEST-7、20 C、unloaded bench、仅适用于 NCX7，以及不构成 cutting-load / production guarantee 均保留；该陈述只带 customer_refs=[E1]，P/S refs 为空。未发现新增产品数值、认证、负载保证或将 E 事实冒充 P/S 的情况。

**商业文章质量评估：NEEDS_REVISION。** 英文可读，有开场、测试范围说明和买家检查问题，但仍是短说明，缺少成熟买家指南所需的解释深度。CL4、CL5、CL6、CL7、CL9 共 73 个空白切分词逐字沿用 S1，未充分改写为连贯解释。结尾是描述这些要点用途的元话语，没有 CALL_TO_ACTION 类型陈述或明确询盘动作。原生校验未拦截这些编辑质量问题，因此不能将 SUCCESS 等同为商业成稿合格。

S1 原本即被标记为截断、未验证外部材料，P/S/E 均为合成演示证据。这里是 AI 对全文的验收评估，**不是人类语义签核**；没有保存“本地审核完成”、改写正文或启动第二轮生成。未验证真实客户应用、SEO 排名或转化效果。

## 验证、变更与边界

本次实际运行 `python -m unittest tests.test_web_deepseek_experiment tests.test_web_generation tests.test_web_mvp tests.test_web_article_review -q`：**45 项通过，54.804 秒**。出现已有 Starlette/httpx deprecation warning，无测试失败。本次未运行完整回归，未把历史 1771 项结果算作本次执行。`git diff --check` 退出 0，存在既有 LF/CRLF 提示。

只新增本验收目录、实际运行结果和固定 TEST-only 许可记录；保留此前阻断记录及所有用户已有未提交修改，没有修改业务源码或冻结包。正式机器可读核验见 [acceptance-verification.json](acceptance-verification.json)，执行前、余额及许可证据分别独立保存。

WordPress 写入 0，生成 SQLite 的 wordpress_draft_attempts 行数 0；部署 0，Git 写操作 0。生产 Gate、P1、PostgreSQL 未修改，生产仍未授权。固定本地 TEST 账本仍依赖本机操作员与文件系统信任，不能抵抗恶意管理员删除/回滚账本，不能视为修复生产 P1 抗回滚问题。

本次实验已结束；不自动重试、不延长截止、不转为生产或 WordPress 授权。
