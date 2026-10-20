# Minimal Writer Flash 离线预检与请求冻结

日期：2026-10-13（Asia/Shanghai）。最终状态：**MINIMAL_WIRE_REAL_PREFLIGHT_READY**。
READY 仅表示离线预检与请求冻结完成，不表示真实模型遵循、商业文章质量、生产接入或调用授权。
本轮真实 DeepSeek / 其他生产 API / WordPress 调用 **0**。没有部署、commit/push。
本包没有 live executor，不会自动请求 DeepSeek；全部授权标志为 false。

## 1. 历史 PACKAGE_FILE_SET

修复前精确重现指定单项测试：**1 test / 0 failures / 1 error / exit 1**，
错误为 `ValueError: PACKAGE_FILE_SET`。旧冻结目录根包含原六文件及
`real-v3-experiment-2026-10-13/`；严格 helper 正确地拒绝第七项。

最小修改仅在 `tests/test_seo_draft_v3_request_freeze.py`：正例使用
`shutil.copyfile` 将原冻结六文件的实际字节复制到独立 TemporaryDirectory，再调用原
`verify_package`。没有从 builder 生成替代正例，也没有修改 helper、历史响应或 manifest。
增加“包内额外目录必须以 PACKAGE_FILE_SET 拒绝”和“同级结果目录允许”两项负/边界测试。
未 skip、xfail、删除测试或放宽原断言。修复后该模块 **15 / 0 failures / 0 errors / 0 skipped / exit 0**。

旧目录因历史布局仍不能直接作为严格六文件包通过；这是保留的正确拒绝行为。
独立六文件副本的原始 request/config/manifest/hash 与确定性来源全部相符，未发现更深的冻结字节缺陷。

## 2. 复用输入与单项证据路由修正

保留原 CNC TEST-only Snapshot、Selection Artifact、Plan、25 个 selected facts、
12 个手工 TEST ONLY 子问题/目标，Schema 和 deterministic assembler 都未修改。
原 Manifest 的 `TEST_ONLY_MANUALLY_AUTHORED` 和 `SYNTHETIC-MINIMAL-TEST-AUTHOR` 原样继承，
不是客户批准。原生输入读取原历史 `frozen-v1/native-input.json`，与 Minimal artifact 的完整 domain 数据逐字段相等。
Snapshot 读取原 v2 preflight 的 evidence bundle，原生解码后与输入 customer_evidence 完全相等。

审查发现 `S4-E2` 的原允许 refs `E4.F01, E3.F05` 没有明示“outer width”测量范围。
同章已 selected 的 **E3.F07** 明确说明 outer width、bore position 和 surface finish 的未评估范围。
只在本次新 `slot-manifest.json` 增加该 ref；原 manifest 保存为 `original-slot-manifest.json`，
所有子问题、目标、预算、顺序和其他允许 refs 不变。该变更有 `source-integrity.json` 明确记录，
没有选择新事实、重新设计事实或更改原证据/Selection/Plan。

一次离线读取探查发现旧 Minimal artifact 的 datetime 使用 `+00:00`，原生存储 codec 要求 `Z`，
直接解码旧 artifact 被拒绝（探查进程 exit 1，非 unittest 回归）。本轮改用已经存在的原生历史输入，
并核对完整 domain 序列化等价；没有改动存储 codec、旧 artifact 或原生 Parser，也没有放宽日期规则。

| 领域绑定 | SHA256 |
|---|---|
| 原 Snapshot 绑定（非 bundle 文件 hash） | `a26579024bfd100c92199e5fb2af8714247b48a2514a803aedddde8cdc438430` |
| 原 Selection | `237fb0ac0f5c3d5f88872405868ef080f9ec989138ad1cd9402831c58a1012be` |
| 原 Plan（含 P/S/brief/context） | `2bdef501ae0eb3e3afb9f232c924bcf81ae3327fa9911b6514f32f1e89105084` |
| 原 Evidence | `e38bb8cc65ee824a25696e99012546147ae691c5f438977d8952381331c52500` |
| 新 Slot Manifest | `dcaf7e23cf987da3ee5e5616d7bc2fe74af4343bbe597755175ce748460d84e2` |

## 3. 12 个槽位的可行性与质量风险

下列为离线作者审查判断；“可行”只表示支持有条件的采购推理或明确拒答，不表示已有适配/接受结论。
程序文本去重不等于语义独立证明。问题和目标未重新编写，未用模板填充增加槽位数。

| 槽位 | 独立决定与允许证据 | 支持范围及剩余风险 |
|---|---|---|
| S1-E1 | 夹具排除/候选筛选；E5.F01, E2.F03 | 明示小机型宽度/载荷超限，大机型仅候选。不能据此认证完整夹具适配。 |
| S1-E2 | 名义行程与访问空间、静载分别审查；E2.F01, E2.F05, E2.F07 | 两组行程均要求单独 clearance 检查，大机型载荷限 centered/static。没有工具路径、朝向、动态载荷记录，不能确认可达。 |
| S2-E1 | 确定有载试验需求；E1.F01, E3.F03 | 两组空载 bench 额定条件不足以评切削。不能比较真实切削优势或伪造试验结果。 |
| S2-E2 | 确认铭牌配置与扭矩证据；E3.F01, E3.F02 | 铭牌功率明确不证明切削功率/扭矩曲线。与前槽分别处理转速试验与电机证据；英文易退化成同一提醒。 |
| S3-E1 | 新零件的材料/几何试验范围；E4.F01, E4.F08 | drawing A/6061-T6/fixture A 有明确边界，其他应用需代表性试验。不能认定其他材料不适用或已适用。 |
| S3-E2 | 采购节拍的 loading 边界；E4.F04, E4.F05 | 两个小样本 cycle 均排除 loading，无一般 throughput 优势。不要引用该槽未授权的工具更换条款或补造完整节拍。 |
| S4-E1 | 测量决策规则与处置；E3.F05, E3.F07, E6.F03 | 观测、uncertainty 和 proposed criterion 可支持先协商规则，不能自动判断合格、量产能力或推导新数值。 |
| S4-E2 | 确定额外关键特征记录；E4.F01, E3.F05, **E3.F07** | 新增同章已选 E3.F07 后明确外宽以外孔位/表面未评估。采购者实际关键特征仍未知；不要将未测等同不合格。 |
| S5-E1 | RFQ 输入先决条件；E6.F01 | drawing revision/material/tolerance/fixture/tools/cycle/utilities 是拟议询价输入。应说明 supplier review，不能称双方标准已批准。 |
| S5-E2 | 更正、复测、放行责任；E6.F04, E6.F05 | buyer 批图、supplier 记录、both parties agree disposition/re-test 有明确来源。与 S4 测量规则不同，处理执行/责任；不能声称已签协议或已验收。 |
| S6-E1 | 配置选项对发运/培训范围的影响；E2.F09, E5.F05, E7.F01, E7.F03 | 配置需对照、options 可能影响日程、培训及 onsite/advanced 范围待约定。不能补报价、国际到货日或选件适用结论。 |
| S6-E2 | 支持响应/恢复及保修范围；E7.F04, E7.F05 | 初始响应不承诺恢复，保修有诊断与排除项。与前槽不同，处理售后责任，不能升级为无条件覆盖或 SLA。 |

每个解释槽预算 **1200 字符**；implication、assumptions 各非空且 ≤300，
boundary/action 各非空且 ≤150 并须精确回显，四段以三个空格连接的实际长度受槽预算。
当前即使四字段取上限也 ≤903；长度为上限，没有最低凑字数。
premise_refs 必须是该槽 allowed refs 的非空唯一子集，最多20；引用“允许”不证明实际相关。
拒答仅含 slot_id/status/missing_information（≤300），不计完成、不组装候选、不补写。

全篇 6 章，25 个唯一 selected facts、26 次章节分配；25 direct + 12 explanation + 1 CTA =
**38 claims / 13 blocks**，低于原生 48 claims / 24 blocks。
各章实际 claims 为 7/6/6/5/5/9，分别不超过 Selection 的 8/7/7/7/6/10。
E4.F01 在两章使用，仅直接展示一次。局部 synthetic 验证只证明这些输入存在合法 Native candidate 组装，
没有把 fake wire 当作真实模型遵循或商业质量证据。

固定 boundary/action 在每章两个解释中重复，末章 CTA 还会重复同一动作，这是当前合同约束。
同章目标虽不同，真实模型仍可能写成泛化免责声明。保守数值规则、精确英文回显和 60 秒 timeout
可能导致拒绝/截断；不重试、不自动修复。证据没有分配的责任必须待协商，Python 不补责任。

## 4. 冻结字节、参数、预算

- **request SHA256：`3578587e2e55a941710aafb1eb8e5fc2b616697d3682753590adc385618540d4`**
- **manifest SHA256：`ec19fb23760d34b3af17f9bad66cc70c6860de8a422f7cbd111f7ad3649541dd`**
- request.json **16,508 UTF-8 bytes**；system/user 内容合计15,455字符/字节。
- POST `https://api.deepseek.com/chat/completions`；model=deepseek-flash，temperature=0，
  thinking={type:disabled}，response_format={type:json_object}，max_tokens=16384。
- timeout=60秒、retries=0、fallback=false、repair=false、redirects=false；timeout仅属传输 config，
  不是 provider JSON 字段。没有 credentials 或授权 header 留存。
- 输入估计 **3,864–7,728 tokens**，方法为内容字符数/4至/2；chat framing 未精算，未调用 tokenizer/API，
  不冒充精确值或上界。输出上限16,384 tokens。
- 只使用已有本地**历史费率场景**：cache-miss input USD0.3/M、output USD1.2/M。
  若输出达到上限，上述估计输入的场景成本约 USD **0.0208200–0.0219792**；
  65,536 input + 16,384 output 的保守规划场景为 USD **0.0393216**，建议另授权预算 USD **0.05**。
  不代表当前费率、账单或硬费用上界；本轮没有网络核价，也没有证明模型别名当前可用。

冻结包为根目录严格 **20 个文件**，manifest 绑定17个文件；排除自身、manifest.sha256 与报告，避免循环。
source-integrity.json 绑定6个原始输入路径/文件 bytes/hash/size、97个 Python源码 hash 及领域摘要。
本地完整输入含原证据/审计元数据，仅用于核验；模型请求只有明确 selected-only 的 material 和无答案 Schema。
system/user 两份文本与 request messages 精确逐字节对应，request 可由冻结输入确定性重建。
来源、代码、Schema、Prompt、Plan、Selection、Snapshot 或槽 Manifest 漂移，旧包核验失败。
报告不是模型输入，不可替代外部可信 manifest anchor。

本轮工具只读 allowlist 中的六个数据源，不加载 tests fixture、fake wire、synthetic candidate 或历史失败输出。
测试内才读取 fake wire 以验证组装；29项新测试中对原假答案 implication/assumptions 的请求缺席和
工具实际读取路径都有断言。selected-only 投影严格相等校验，同时扫描未选 ref/quote、完整 source、audit reason。
source-integrity 的源码与本报告均不发送给模型。

未来结果固定为同级 **docs/minimal-writer-flash-results/**，当前未创建。
验证日志放在独立同级 **docs/minimal-writer-flash-preflight-verification/**，不会污染冻结包。

## 5. 测试与完整性

所有回归通过同一个外部 socket/DNS guard 运行，loopback 仅供本地 unit fixtures。
`scripts/verify_minimal_writer_flash_offline.py historical-fix|new|related|full|integrity` 为复现入口，
详细日志与机器统计在同级 verification 目录，退出码是实际进程结果。

| 实际验证 | tests | failures | errors | skipped | exit |
|---|---:|---:|---:|---:|---:|
| 修复前指定单测重现 | 1 | 0 | 1 | 0 | 1 |
| 历史 freeze 模块（修复后） | 15 | 0 | 0 | 0 | 0 |
| 新增 Minimal Flash preflight | 29 | 0 | 0 | 0 | 0 |
| 相关回归（含新增） | 248 | 0 | 0 | 0 | 0 |
| 完整 discover | 2123 | 0 | 0 | 0 | 0 |

完整回归耗时 **471.094 秒**，没有 expected failures 或 unexpected successes。
historical-fix/new/related/full 四次运行的外部网络阻断尝试均 **0**、真实 API 调用均 **0**。
完整运行启动时出现现有 FastAPI/Starlette TestClient 的 httpx 弃用提醒；它不是测试失败，本轮未改依赖。

最终基线核对：**2824 个基线文件，2821 unchanged，3 changed，0 missing，0 unexpected changes，exit 0**。
基线包含了本轮刚新建的两个脚本，因此3项变化为这两个新脚本的开发及已授权的旧freeze测试修改；
原有2822个文件中只有该测试变化，其余2821个文件全部逐字节保持，包括生产源码、旧冻结包、
全部Git可见历史真实响应、manifest与未提交文件。没有以git diff遗漏未跟踪历史文件。
凭据、虚拟环境、缓存和本地数据库不纳入读取基线；本轮没有读取/修改凭据或运行数据。
证据见同级 verification 的 baseline.json、integrity.json、各 *-tests.json/log 与 final-verification.json。

新测试验证确定性 bytes/hash、Selection/Snapshot/Plan/Manifest漂移拒绝、全部绑定文件篡改、
额外字段/权限/未选refs/未知slot/包内额外目录拒绝、原锚点拒绝重封manifest、代码漂移拒绝，
以及模型语义的逐字同源、拒答不补写、真实原生Parser/Validator调用及原始数值错误保留。
技术检查不包含通用自然语言事实/因果证明；语义伪装仍是人工审查风险。

历史 v2 原始输出仍 REJECTED，初次真实 v3 仍 `V3_EXPERIMENT_ENVELOPE_FIELDS`，
最新真实 v3 仍 `V3_CLAIM_BINDING`；没有更改 CL、正文、字段、hash 或修复历史失败输出。
原生 Parser/Candidate Validator 未绕过；不调用 finalizer、不注入 approved interpretations，
不调用 v2/v3 fallback，也未接入 Evidence Gate、数据库或生产Writer。

## 6. 下一次真实实验授权

需要用户明确授权：对以上**固定 request SHA256 和 manifest SHA256**，向指定 DeepSeek Chat
Completions endpoint **只发送一次 TEST ONLY 请求**，保持冻结参数、timeout60秒、retries0、
fallback=false，明确预算上限（建议USD0.05，当前费率须确认可满足），留存原始响应/usage/耗时/错误
到独立同级结果目录，然后只做本地 Native Parser/Validator 与人工内容评价。
如需执行前官方当前别名/参数/价格的只读核验，也应在该授权中明确；不满足冻结条件即停止，
不能换模型、改参数或自行重冻。本轮没有预占或继承任何历史真实实验许可。

评价严格分为两部分，完整标准见 success-criteria.md：
**技术**评 JSON/Wire/Slot coverage/Native Parser/Validator/引用与数值绑定；
**内容**评独立采购决定、因果、自然英文、未知条件、验证责任、重复程度、人工实际编辑工作量。
**技术 PASS 不代表商业文章质量 PASS**，编辑工作量须由审阅者实测。

## 7. 与生产 Writer 接入仍有的阻断

尚无真实 Minimal Wire 模型遵循结果、可靠性或商业文章质量证据；只有 TEST-only 采购子问题/目标，
没有客户批准来源或可信审批绑定。真实运行还缺冻结请求的受控 transport/usage留存、
实时 Evidence Gate/snapshot freshness 接入、持久化及人审生命周期适配、客户语义与商业验收。
当前 Candidate inspection 的 PASS 仍是待审 candidate，不是可直接入库/交付的 DraftItem。
以上均不在本轮接入；一次模型实验授权不能替代生产 Writer 或 WordPress 权限。

## 8. 本轮文件范围

仅修改既有 `tests/test_seo_draft_v3_request_freeze.py` 的正例隔离与新增严格边界测试。
新增 `tests/test_minimal_writer_flash_preflight.py`、
`scripts/prepare_minimal_writer_flash_preflight.py`、`scripts/verify_minimal_writer_flash_offline.py`、
`docs/minimal-writer-flash-preflight/` 冻结包及同级 verification 证据。
没有编辑生产 Writer、Parser、Validator、Evidence Gate、runtime、数据库或WordPress代码。
