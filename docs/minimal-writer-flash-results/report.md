# DeepSeek Flash Minimal Writer：首次真实 TEST-only 实验

日期：2026-10-13，Asia/Shanghai。实际唯一请求时间：15:47:01–15:47:13。

**TECHNICAL：FAIL**  
**CONTENT：FAIL**（AI 辅助评审对“可作为本项目商业 SEO 文章使用”的判定；不是独立人工验收）

真实 Flash 能生成有采购意义、总体可读的英文解释；本次不能成为合法 Native Candidate，
且部分事实边界被扩大。因此它提供了继续小范围离线改进的价值证据，尚不支持生产 Writer 接入。
本轮实际 DeepSeek 请求 **1**；无重试、修复、换模型、重新冻结、WordPress、数据库写入、部署或 Git 写操作。

## A. 冻结包与授权条件

| 核验 | 实际结果 |
|---|---|
| Request SHA256 | `3578587e2e55a941710aafb1eb8e5fc2b616697d3682753590adc385618540d4`，发送前/后均一致 |
| Manifest SHA256 | `ec19fb23760d34b3af17f9bad66cc70c6860de8a422f7cbd111f7ad3649541dd`，发送前/后均一致 |
| 严格文件集合、输入与源码绑定 | 原20文件包、17个manifest文件条目、6个源输入、97个源码绑定全部通过原verify_package |
| 内容范围 | 原25个selected facts、12个TEST-only槽位、原Schema、原Prompt与参数；没有混入fake wire、synthetic答案或历史输出 |
| 凭据 | 仅确认存在；未打印或保存密钥/Authorization Header；响应敏感内容扫描通过 |
| 防重复 | 准备前结果目录不存在；发送前无既有attempt/response/model output；独占持久化attempt-started.json先于联网，授权已消耗 |
| 工作区 | 使用当前Local：大量冻结输入/源码尚未提交，Git HEAD不足以复现；未创建Worktree或复制/重新冻结输入 |

执行前读过原preflight报告、success criteria、冻结构建/验证脚本、既有one-shot transport及
历史v2/v3失败记录。复用原`verify_package`、selected-only边界核验与旧历史基线检查；
没有覆盖旧验证日志。历史基线2824项仍只包含原先许可的3项变化，没有新漂移。
本轮建立发送前独立基线，发送后 **2858/2858文件不变，0 changed**，
包括生产源码、旧冻结包、所有Git可见历史响应和原有未提交文件，证据见integrity-after.json。

新增最小入口为scripts/run_minimal_writer_flash_once.py，复用现有
OneShotTransport、receive_candidate、save_bytes和本地凭据读取工具。
没有改生产Writer/Parser/Validator/Evidence Gate或冻结脚本。
offline dry-run使用MockTransport，16,508个实际body字节与冻结request逐字节一致，
并验证第二次发送被拒绝。真实请求只在明确命令下执行一次，发生异常也不重试。

## B. 唯一真实请求与成本

| 项目 | 结果 |
|---|---|
| Endpoint | https://api.deepseek.com/chat/completions |
| 配置 | deepseek-flash / temperature=0 / thinking disabled / json_object / max_tokens=16384 |
| 传输限制 | timeout60秒；retries0；fallback=false；repair=false；redirects=false |
| HTTP / finish_reason | **200 / stop**；完整响应，无超时或断线 |
| 请求耗时 | **11.615890秒** |
| 实际请求次数 | **1** |
| usage | prompt **3606**，completion **1975**，total **5581**；cache hit **0**，cache miss **3606** |
| 原始响应 | response-body.bin，**10,248字节**；response-http-headers.bin保留客户端可取得的HTTP状态行及原始header数据，无敏感header遗漏 |
| 响应SHA256 | `ad83f9b1a3792e07c8fa4ce1710b206015f355ffa36346dfeb61dd0ae6de12bc` |
| 模型content SHA256 | `ba5154d8ef357f3b8c2dcb992913be82c9daa48c411282a4284dec332b60cf93` |

发送前已读取[官方当前计价](https://api-docs.deepseek.com/quick_start/pricing/)：
Flash峰值input cache miss USD0.30/M、cache hit USD0.006/M、output USD1.20/M，非峰值减半。
以65,536输入reserve（远高于本次约16KB英文请求）及16,384完整输出额度、全部cache miss和峰值费率
保守规划为 **USD0.0393216 < 授权USD0.05**。这是合理保守估算，不是假称精确tokenizer硬上界。

按返回usage与峰值费率计算：
`3606 × 0.30 / 1,000,000 + 1975 × 1.20 / 1,000,000 = USD0.0034518`。
请求发生于周二07:47 UTC，位于官方峰值时段；这是usage推算费用，未检查独立账单。
即使适用额外优惠也只会低于本处峰值估算。官方核验记录及预算见official-pricing.json，
完整cache usage见usage-full.json，费用明细见cost-record.json。

官方[thinking参数](https://api-docs.deepseek.com/guides/thinking_mode/)及
[JSON模式](https://api-docs.deepseek.com/guides/json_mode/)与本次冻结配置对应；没有改参数。

## C. 自动技术验证

| 层 | 结果 | 依据 |
|---|---|---|
| HTTP与完整接收 | PASS | 200、stop、完整保存；不等于内容验证通过 |
| 严格JSON | PASS | 单个对象，无重复键/非有限数；顶层恰为request_id与slots |
| request_id与槽位覆盖 | PASS | 与冻结Manifest绑定；12/12唯一已知槽位，无缺少/重复/未知slot |
| status/字段名 | PASS | 全部answered，0拒答；每个字段集合准确，无额外或权限字段 |
| premise_refs范围 | PASS | 每槽实际refs均属于本槽allowlist；这不证明语义相关 |
| boundary/action | PASS | 12/12精确回显原限制与动作 |
| Wire字段长度 | **FAIL** | **10/12 buyer_implication超300字符**，首次S1-E1为305；原codec返回MW_ANSWER_FIELDS |
| Native Candidate组装 | NOT_RUN | 原workflow在Wire拒绝后返回空candidate/sidecar；未截短或补写 |
| Native Parser | NOT_RUN | 没有合法Wire可交给assembler，未构造替代candidate绕过入口 |
| Native Validator | NOT_RUN | 未到达此层，不能宣称通过或正式返回数值错误 |

正式原始失败结果在native-experiment-result.json：Minimal Wire FAIL，Native Parser/Validator NOT_RUN，
errors=[MW_ANSWER_FIELDS]。reception.json的reception_success只指HTTP/供应商响应接收；
其中failure_stage=native_validation为复用接收helper的阶段标签，该callback仅留存接收结果，
不代表运行过真正的Native Validator。实际验证由未改动run_minimal_experiment执行并在Wire层拒绝。

为避免首个失败遮蔽其他问题，对**每个原始槽位**独立调用当前codec并检查现有范围/精确回显/预算，
记录全部长度。assumptions均≤300，boundary/action均≤150，组合长度均≤1200；没有出现额外独立Wire范围错误。
长度详情和逐槽技术结果见technical-validation.json。

另作**独立数值诊断，不是正式Native Validator结果**：使用原numeric extractor及grounding predicate，
按既有“数量句必须为实际引用原句”条件检查原始模型字段，发现 **8个槽位**含非原句数量表达。
S6-E1将原`60 days`写为`60-day`，原grounding predicate也返回NUMERIC_NOT_GROUNDED。
其他数量即使能在引用中找到，也没有按原句保留完整条件，不能因ref合法就认定数值语义安全。
没有修复后重跑或让这些诊断替代完整Validator；首个正式拒绝始终是MW_ANSWER_FIELDS。

## D. 逐槽内容质量：AI辅助审读

本表是本助手对真实输出和允许原句的非盲化评审，不是第二模型或真人独立验收。
“有价值”与“满足冻结契约/商业可用”分别判断。原始字段与允许事实逐项对照见slot-reading-view.md。

| 槽位 | implication字符数 | 独立采购价值与事实判断 | AI内容结论/编辑需求 |
|---|---:|---|---|
| S1-E1 | **305** | 以夹具超出小机型台宽/拟议静载解释排除，并保留大机型非认证边界；有具体因果。数量被重写而非保持完整原句。 | NEEDS_EDIT：采购方向有用；需简短定性重写和数值条件复核。 |
| S1-E2 | **374** | 将名义行程与工具访问/动态载荷分开，目标独立；但称NCX10载荷是“the only load screen available”。全文也有NCX7载荷事实，不能从该槽局部可见范围推出全局没有其他记录。 | **FAIL**：存在过强的排他表述，需重写并限定观察范围；650kg数量句也不符合契约。 |
| S2-E1 | 298 | 明确空载额定不能决定实际切削，建议代表性有载试验，不按rpm排名；可见假设与边界一致。 | NEEDS_HUMAN_REVIEW：本轮较好片段；“hold up”较口语，试验/记录责任仍待约定。 |
| S2-E2 | **315** | 铭牌配置与实测扭矩区别清楚，回答不同于上一槽；结尾重用loaded trial/torque，与固定动作叠加。 | NEEDS_EDIT：因果基本成立，需定性压缩、去重复及数值改写检查。 |
| S3-E1 | **331** | 材料/图纸/夹具特定试验不能外推其他应用，方向有据；不同应用和新试验可行性被明示为假设。 | NEEDS_EDIT：自然可读，但重复事实较多且超限；材料code触发现有数量句约束，不代表该code本身捏造。 |
| S3-E2 | **302** | 完整节拍与台架mean cycle区别有用；然而断言trial timings omitted loading **and tool-change steps**。本槽E4.F04/F05只明示排除loading，没有证明工具更换被排除。 | **FAIL**：新增无证据的试验边界；把它放进assumptions不能使历史试验事实成立。需保留未知，而非替试验记录补条件。 |
| S4-E1 | **382** | 将观测、不确定度、拟议准则与处置规则区分，没有复现历史v2“different coupon counts”错误。 | NEEDS_EDIT：推理方向好，但数值重述、冗长；不能凭这些数值自动判定合格。 |
| S4-E2 | 287 | 外宽记录不能代表孔位/表面等关键特征，有E3.F07直接支持。 | NEEDS_EDIT：原文“on three drawing A coupons”漏掉**per machine**限定，易读成总计三件；“only measured feature”需限定为所给方法记录。没有虚构新数值，但文本数量也需人审。 |
| S5-E1 | **340** | 询价输入先定义、supplier review再约定criteria，采购顺序有意义；未把review称已完成。 | NEEDS_EDIT：主要是清晰的事实复述加建议；超限，需减掉重复RFQ列表，突出决策后果。 |
| S5-E2 | **427** | buyer批图、supplier记录、双方处置/更正后复测/放行与E6.F05一致，比泛化“双方确认”更有责任信息。 | NEEDS_EDIT：本轮有价值的责任链，但长句密集；可用作编辑素材，不能自动当作已同意协议。 |
| S6-E1 | **482** | 将选件、配置、交付/基础培训关联起来，有采购意义；提“60-day dispatch”丢失after deposit and signed configuration起算条件，且days→day违反原数值绑定。 | **FAIL**：日程条件表达不完整；需定性重写、恢复起算/国际transit范围并压缩。 |
| S6-E2 | **436** | 正确区分initial response与restoration、保修与排除项，整体边界谨慎；没有承诺无限覆盖。 | NEEDS_EDIT：字段严重超限且大部分为原条款改写；原句“proposal promises”与pending signed terms存在语气张力，需改为拟议措辞并精简。 |

12个槽位总体分别处理筛选、访问/载荷、切削试验、铭牌/扭矩、新应用、节拍、测量决策、关键特征、
RFQ输入、处置责任、配置交付/培训、售后范围，未退化为12份完全相同的模板。
但多段仍为“事实摘要+Purchasing should...”加共同限制语/动作，解释深度与验证产物尚不均匀。
引用ID全部有效，不能掩盖S1-E2的排他推断和S3-E2的新增试验条件。

### 代表性的真实英文

较好：S2-E1，因果、目标和边界清楚：

> Both spindle ratings come from unloaded bench tests at controlled temperature, so they cannot settle whether either machine will hold up under actual cutting. The purchasing decision should be a representative loaded trial with torque records, not a ranking based on the higher unloaded rpm figure.

有价值的责任信息：S5-E2原文包含：

> the buyer approving the test drawing, the supplier recording setup and measurements, and both parties agreeing disposition and re-test after correction before shipment release

无充分依据的试验边界：S3-E2 assumptions原文：

> The buyer's production cycle includes loading and tool-change steps that the trial timings omitted, and those steps materially affect the comparison.

问题不在buyer可能需要工具更换，而在把原记录未说明的“tool-change omitted”作为既定试验性质。

过强的范围判断：S1-E2原文：

> the NCX10 proposed 650 kg centered static load is the only load screen available

过度重复：S2-E1/E2逐字重复如下boundary/action，implication中又重复loaded trial/torque：

> Loaded cutting capability remains unassessed. Request a representative loaded trial and torque records.

这两句的重复来自冻结契约要求，不应全部归因于模型。六组boundary/action各出现两次；
将来合法组装时末章CTA还会再出现同一commercial terms动作。英文总体语法可读，没有历史v3的
明显机械语法错误，但缺少全篇过渡和读者叙事；本次没有生成通过验证的完整文章，不能冒称已商业可用。

## E. 商业可用性与人工工作量

**CONTENT：FAIL**是对当前输出可直接作为此MVP商业文章使用的否定；不是对模型长期能力的结论。
存在有用采购推理与自然英文片段，但10个解释需重写至现有字段上限，8个槽位需按数量句合同重新处理，
至少S1-E2、S3-E2、S6-E1有实质边界问题；还有重复、条件限定、责任/验证产物和文章连贯性编辑。
这些编辑类别相互重叠，不相加为独立错误总数。

它可能减少“采购解释初稿”的起草工作，尚未证明能减少端到端事实审核与编辑成本。
**真人编辑分钟数：未测；独立人工内容验收：未执行；人工批准：无。**
不以AI自评假定编辑更快，也不把这份非合格Wire拼接成“最终英文SEO文章”。
实际真人仍须复核所有因果/未知条件、每台样本数、日程起算条件、条款承诺强度、责任分配，
并记录逐槽轻改/重写/不可用及全篇编辑时间，才能回答人工成本是否可接受。

## F. 失败根因与最小后续改进建议

| 类别 | 本次证据 | 边界 |
|---|---|---|
| 模型指令遵循 | 明示300字符上限，10段超限；明示qualitative reasoning，8槽有重组数量句 | 单样本不能认定模型能力上限，也不能证明下一次成功 |
| Prompt/Wire表达 | 1200组合预算与300单字段并存，模型可能把较大的槽预算当正文目标；多事实槽更容易长句；精确echo强制重复 | 合同可满足，离线正例已证明；本次没有发现矛盾合同或放宽理由 |
| 证据/可见范围 | S3-E2没有工具更换是否计入原试验的证据；S1-E2局部allowlist不能证明全局缺少小机型载荷记录 | 应保留未知/限定范围，不补造证据；不是事实bank重设计的许可 |
| 实现 | one-shot、冻结字节、响应留存和fail-closed Wire按设计工作；未发现导致本次失败的实现缺陷 | Native Validator尚未运行，不能归因为其误判 |

最小建议仅供下一任务决策，本轮不实施：

1. 先人工确认上述原文问题及采购价值，测编辑工作量。
2. 如另获离线改进授权，优先使Prompt更突出“每个implication≤300、仅定性、只回答本槽决定”，
   并强调“未说明”不能写成“已排除/不存在”；保持现有Validator，不自动截断或删除语义。
3. 固定回显导致的重复，应作为单独产品编辑取舍讨论；不在本次真实结果上修改合同。
4. 任何将来Prompt/Wire变更都需新版本冻结与新的真实请求授权；不复用已消耗的一次许可。

## G. MVP下一步建议与本轮验证范围

建议继续保留Minimal Writer这条最小研究路线，因为它确实输出了多个独立且有证据基础的采购决定；
**暂缓生产Writer接入**。下一步优先是一次离线编辑/Prompt诊断任务与真人审阅，而不是扩大Provider架构、
重构证据系统或立即换模型。进入MVP下一阶段的门槛应同时包含合法Native候选和可接受的人审成本。

本轮实际运行：

- 发送前冻结/源码/历史完整性核验，PASS；dry-run字节/第二次发送阻断，PASS。
- `python -m unittest tests.test_minimal_writer_flash_once tests.test_minimal_writer_flash_preflight tests.test_minimal_writer_wire -v`：
  **89 tests，0 failures/errors/skipped，8.459秒，exit0**，包含11项新增runner安全测试。
  这些测试在结果目录创建之前完成，均为mock/offline；不证明真实输出通过。
- 唯一真实请求：HTTP200/stop，实际次数1；原输出run_minimal_experiment返回FAIL，未修复。
- 离线逐槽诊断、响应/content字节对应、usage费用与2858项完整性核验，exit0。
- 本轮未跑完整suite，不沿用上一轮2123项全绿冒充本轮运行。现有preflight测试中“未来结果目录未创建”
  断言属于发送前状态，本轮保留它和全部旧测试文件，不为结果目录已经生成而修改历史断言。

新增文件：scripts/run_minimal_writer_flash_once.py、scripts/analyze_minimal_writer_flash_result.py、
tests/test_minimal_writer_flash_once.py及本结果目录。生产、冻结和既有文件未改。
全部生成与网络活动已停止，授权已消耗，不自动发起下一轮实验。
