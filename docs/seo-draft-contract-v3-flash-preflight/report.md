# SEO Draft Contract v3 Flash 冻结请求包

最终状态：**REAL_V3_REQUEST_FROZEN**。

本轮仅补齐冻结请求包。包内执行状态仍为 `FROZEN_NOT_AUTHORIZED`，`network_allowed=false`、`live_authorized=false`、`semantic_approved=false`、`production_authorized=false`。真实 DeepSeek / 其他生产 API / WordPress 调用均为 **0**。等待新的真实实验授权，不沿用上一轮授权自动执行。

## 之前为何 BLOCKED，如何补齐

上一轮 OFFLINE_V3_INTEGRATION_READY 只保存了离线 prompt material、projection、Selection 与 synthetic 校验产物，没有 provider request body、request hash 和真实请求参数配置，因此在请求前停止。历史 REAL_V3_EXPERIMENT_BLOCKED 报告及所有 v2/v3 结果原样保留。

本轮读取原始冻结材料并核对其既有 manifest；不调用 fixture producer，不重新生成 Prompt、Projection、Selection、Evidence 或 Plan。新增操作只有供应商 JSON envelope 的确定性序列化、新实验配置和哈希清单。

`request.json` 的 system message 是已有 prompt 的 `instructions` 原文；user message 是整个 `prompt-v3-material.json` 原始 UTF-8 文件内容。后者已包含完整 Writer Projection，其对象与独立 `writer-projection.json` 一致，且 selected facts 逐节与冻结 Selection 对应。没有另行追加 Evidence、审计文件、测试文件或历史输出。

已有 Prompt 的 OFFLINE_ONLY / synthetic 表述、hash_creator 和 contract version 字符串均保留，未为了真实调用更改任何指令。新配置用 `contract_version=v3` 表示本次版本，同时以 `explanation_contract_version` 记录原内容的 `seo-draft-explanation-v3-offline`。这次冻结不证明真实模型会遵循这些内容。

## 六个新增包文件

| 文件 | 内容 |
|---|---|
| request.json | 确定性 provider body，31,739 bytes |
| experiment-config.json | 模型、传输参数、输入绑定、禁止网络及授权标志 |
| manifest.json | 10 项文件的 filename / sha256 / size，按 filename 排序 |
| manifest.sha256 | manifest.json 的文件字节 SHA256 |
| request-body.sha256 | request.json 的文件字节 SHA256 |
| report.md | 本报告，含核验、测试结果和失败历史；不是模型输入 |

manifest 的 filename 以**仓库根目录**为基准，不依赖机器绝对路径。10 项包括：本包 request.json、experiment-config.json、request-body.sha256，以及既有 integration 目录的 artifact-sha256.json、verification.json、selection-artifact.json、synthetic-input.json、writer-projection.json、prompt-v3-material.json、experiment-config.json。

旧 synthetic-input 只用于本地解码、Plan/Evidence/Snapshot 绑定与泄漏检查；旧 manifest、verification、Selection reasons 和旧 config 只用于本地核验，均未作为文件或完整对象发送。请求中只有既有 Prompt 原文及其内嵌 Projection。外部引用文件必须与包一同保留，不能只移动本目录便视为完整实验输入。

manifest 不包含自己的 hash，也不包含 manifest.sha256（避免循环）及 report.md（报告不是输入）；manifest.sha256 提供单独锚点。本包根目录只允许这六个文件。另新增指定测试模块 `tests/test_seo_draft_v3_request_freeze.py`，其中的离线 helpers 用于组装及核验，没有新增生产入口或执行网络的函数。

## 模型与冻结绑定

| 参数 | 冻结值 |
|---|---|
| model | deepseek-flash |
| temperature | 0 |
| thinking | disabled；provider body 为 {type:disabled} |
| response_format | json_object；provider body 为 {type:json_object} |
| max_tokens | 16384 |
| timeout | 60 秒，只在 config 中；不是 provider JSON 字段 |
| retries / fallback / repair / redirects | 0 / false / false / false |

| Hash 范围 | SHA256 |
|---|---|
| 新 request.json 原始字节 | `d9bd075042613882b47dad0d2e56b7a1bb5aabdffda7b1f9abfbf12dac70a7ae` |
| 新 manifest.json 原始字节 | `589c090c0bff0d1e38f7615eb2b61b4ad568e36a723a172227e000f3f9d834f5` |
| Selection 领域绑定 | `237fb0ac0f5c3d5f88872405868ef080f9ec989138ad1cd9402831c58a1012be` |
| Snapshot 既有绑定 | `a26579024bfd100c92199e5fb2af8714247b48a2514a803aedddde8cdc438430` |
| Plan 重算领域绑定 | `2bdef501ae0eb3e3afb9f232c924bcf81ae3327fa9911b6514f32f1e89105084` |
| 原 Prompt 文件字节 / config.prompt_hash | `d5d06d66a202395847ecd98471cf54cadb00fee8dbd388538f077b33724e2a14` |
| 原 Writer Projection 文件字节 | `bacb0dc7de828d0d40f6fbbc0def3200720f2e47c7b7899452bf804de41ed1ab` |
| 原 integration artifact manifest 字节 | `ccafe59f3044a432f2a36a9ba856c16366b5cbff8eccd235adfa428738cf08ec` |

哈希范围不混用：Snapshot 是冻结输入内的既有 snapshot 绑定，不是将 Evidence bundle 的文件 hash 冒充原 snapshot hash。通过原 codec 解码，调用既有 validate_selection 验证 snapshot 绑定、重算 Plan/Evidence digest，并验证原 Selection Artifact 的 intrinsic digest。

## 冻结前检查

- 原 integration 清单 **57/57** 文件字节一致；OFFLINE_V3_INTEGRATION_READY 状态核实。
- 重复组装和输入字典顺序变化后，request、request hash、manifest、manifest hash 均逐字节相同。没有时间戳或随机值参与生成。
- Prompt 的 user content 恢复为 UTF-8 后与原文件逐字节相等，Writer Projection 嵌入关系一致；没有调用 projection builder 重新产生输入。
- 对解码后的全部文本扫描未选 fact refs、未选完整 quotes、完整 source content 和 selection reasons；逐章 selected facts 对照 source/quote/version/location/requirements，全部通过。
- 任意附加文本、审计/测试/历史输出对象即使未命中泄漏扫描，也会被原 Prompt 字节相等和完整包哈希校验拒绝。
- config 的四个授权/网络标志要求严格 boolean false，true、1、字符串和缺失值均拒绝。缺失参数、文件变更、输入 hash 不符、旧 anchor 下重写 manifest 均拒绝；没有自动重算并接受、修复或重新封存的验证路径。
- 请求 system/user/envelope 的字符和 UTF-8 大小符合现有输入上限。未进行 tokenizer 或模型探测请求。

## 实际测试与失败历史

| 运行 | tests | failures | errors | skipped | exit code | 耗时秒 |
|---|---:|---:|---:|---:|---:|---:|
| new-initial | 13 | 0 | 1 | 0 | 1 | 1.359 |
| new-final | 13 | 0 | 0 | 0 | 0 | 0.984 |
| related-final | 139 | 0 | 0 | 0 | 0 | 11.453 |
| full-final | 2034 | 0 | 0 | 0 | 0 | 453.859 |

首次 new-initial 在实际冻结目录尚未创建时执行，13 项中 12 项通过，`test_frozen_real_package_matches_deterministic_sources` 因目录不存在触发 `FileNotFoundError / WinError 3`。这次确实失败；随后按本次授权首次创建六文件包，再运行全部 13 项通过。没有改生产实现或弱化断言，也没有在发现旧材料不一致后重新冻结；旧材料始终一致。

新增测试覆盖 request/manifest 确定性、原 prompt 字节保留、manifest 条目及尺寸、逐文件 hash 不符、旧可信锚点下伪造 manifest、源材料修改、未选 refs/quote 泄漏、章节错路由、selection reasons/私有 artifact 泄漏、任意附加正文、非法授权标志、缺失 config/参数、重复 JSON key，以及实际冻结包复验。

相关测试运行 8 个模块：test_draft_contract_v3_experiment、test_draft_explanation_contract_v3、test_draft_selection_contract、test_draft_contract_v2、test_draft_explanation_contract、test_seo_draft_v2_flash_preflight、test_draft_prompt_contract、test_flash_draft_replay。

实际使用 `.venv/Scripts/python.exe -B <scratch>/run_tests.py <label> [modules...]`：new-initial/new-final 传入 tests.test_seo_draft_v3_request_freeze；related-final 传入上述 8 模块；full-final 不传模块，执行标准库 `unittest` 的 `discover(tests, pattern="test_*.py", top_level_dir=repository_root)`，verbosity=2。完整回归包含新增 13 项，没有 skip。全套 unittest 内部计时 452.868 秒；表中 453.859 秒包括发现测试和 runner 开销。

Runner 与日志位于仓库外临时目录 `C:/Users/31969/AppData/Local/Temp/seo-v3-freeze-cfr9yyu9/`，文件为 run_tests.py、各 label 的 .log/.json 及网络日志；为遵守六文件包范围，没有向包中追加脚本或日志。本报告嵌入持久统计及失败历史，临时日志不是冻结输入。

Runner 复用已有 `docs/seo-draft-v2-flash-experiment-preflight/network_guard/sitecustomize.py`，通过 PYTHONPATH 让 Python 子进程继承外网 guard。新增测试 strict 禁止全部网络，网络事件 0；相关测试 loopback 事件 1；完整回归 loopback 事件 1,955。四次运行外网阻断尝试均为 0，真实 API 调用 0。Starlette/httpx 弃用提示、asyncio debug、CLI 预期拒绝和启动器 mock 输出未造成 unittest failure/error。


## 保留与限制

执行前记录 2,680 个既有 non-ignored 文件；完整回归后逐字节 SHA256 核对 changed_files=[]。新增文件集合精确为本目录六个文件和指定测试模块，unexpected_new_files=[]。原有 tracked/untracked 用户改动全部保留。最终 request/config/manifest 和原 integration 57 项清单再核验通过；报告更新不改变任何实验输入 hash。

本轮无生产代码、Parser、Validator、Selection Contract、Explanation Contract v3、Prompt 或 Evidence 修改；无 Git commit/push、WordPress、部署。网络 guard 仅用于测试进程，现有测试中的 mocks、本地服务和 loopback 不计为真实 API。

本包是可核验的冻结输入，不是已执行实验，也不是语义批准或生产授权。真实响应、usage、latency、费用及 v2/v3 模型质量比较尚未产生。将来只有另获明确授权，且再次验证本报告给出的可信 manifest/request hash 与全部输入一致后，才可进入独立真实实验。本轮已停止。
