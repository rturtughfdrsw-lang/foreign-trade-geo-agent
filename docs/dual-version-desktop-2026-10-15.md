# SEO Agent 双版本与桌面入口实施报告

日期：2026-10-15（Asia/Shanghai）。状态：**DUAL_VERSION_DESKTOP_SETUP_COMPLETE**。

## A / B：两个实际工作目录和 Git 开发线

| 版本 | 工作目录 | 本地分支 |
|---|---|---|
| SEO Agent - VDemo | `C:/Users/31969/.codex/worktrees/mvp-demo/foreign-trade-geo-agent` | `codex/seo-vdemo` |
| SEO Agent - Commercial Dev | `E:/Codex程序/foreign-trade-geo-agent` | `codex/seo-commercial-dev` |

两条分支均从原 `e78cebd50363a9b3a515d8195fbe54fb346edc06` 非破坏性绑定；VDemo 原来为 detached HEAD，Commercial 原分支 `feat/live-site-analysis` 仍保留。没有复制整个仓库、合并功能、commit、push、reset、clean、强制 checkout 或改写历史。各树原有未提交文件保留。**创建分支不等于提交源码；现有成果和本轮代码仍有大量未提交文件。** 逐树状态见备份 inventory.json / inventory-final.json。

## C：两个真实 Windows 桌面快捷方式

桌面位置由 `[Environment]::GetFolderPath('Desktop')` 查询，实际为 `C:/Users/31969/Desktop`。

- `C:/Users/31969/Desktop/SEO Agent - VDemo.lnk` → mvp-demo/start_mvp.ps1，工作目录为 mvp-demo。
- `C:/Users/31969/Desktop/SEO Agent - Commercial Dev.lnk` → 原主目录/start_commercial.ps1，工作目录为原主目录。

原 `Foreign Trade GEO Agent MVP.lnk` 已先备份，再原地规范命名为 VDemo；没有保留重复旧入口或删除其他桌面文件。两条入口均使用 Windows PowerShell 执行相应脚本。

## D / E：入口功能、端口、环境及数据隔离

| 项目 | VDemo | Commercial Dev |
|---|---|---|
| 地址 | `http://127.0.0.1:8002/` | `http://127.0.0.1:8003/` |
| 功能 | 真实 HTTPS 输入、既有 Crawl / SEO / Opportunities / 英文选题、逐次确认的新 Draft、已有文章查看 | 只读开发状态、已保存 Run / Artifact / Source、当前 Intake、Phase7 / EXPLAIN / 审核历史 |
| 主 SQLite | `C:/Users/31969/.codex/worktrees/mvp-demo/foreign-trade-geo-agent/.data/phase8-mvp/history.sqlite3`，本版本读写 | `E:/Codex程序/foreign-trade-geo-agent/.data/seo-mvp/candidate/history.sqlite3`，仅只读 |
| 其他已有数据 | 不读取 Commercial 数据 | 只读原主目录 `.data/seo-mvp/interactive-intake.sqlite3`、`.data/live-ui/history.sqlite3` 和明确列出的历史报告 |
| PID / 日志 / 临时目录 | mvp-demo 的 `.data/desktop-launcher/`、其 `tmp/` | 原主目录的 `.data/commercial-desktop/`、其 `tmp/` |
| 命名互斥锁 | `Local\SEOAgent-VDemo-8002` | `Local\SEOAgent-Commercial-8003` |
| 模型 / 生产权限 | `live_model_enabled=true` 且 `paid_confirmation_required=true`；未经审核的演示文章 | `live_model_enabled=false`；Production Admission 保持拒绝 |

共用已核对的 Python 3.12 解释器及依赖：`E:/Codex程序/foreign-trade-geo-agent/.venv/Scripts/python.exe`。进程使用 `-I -B`，由各自包装脚本显式前置自己的 src；实例状态校验实际 app 源文件、工作树、数据库、配置、监听 PID、父子关系、创建时间、exe 和命令行。仅绑定 127.0.0.1，关闭代理头信任，不修改 Host/CSRF 保护。

两个启动脚本对现有实例先核对归属，匹配才只打开浏览器；未知端口占用会拒绝接管。停止通过已核对进程句柄进行，不按端口批量杀进程。Windows WMI 的微秒创建时间与进程句柄 100ns 时间已正确对齐；状态请求使用有界、无代理的 UTF-8 解码，中文路径回归已通过。

原主目录 `start_mvp.ps1` 现在仅为本目录 Commercial Dev 启动器的兼容别名，不再跨目录启动 VDemo。

关闭浏览器不会结束后台服务。需要停止时使用：

```powershell
# 只停止 VDemo
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\31969\.codex\worktrees\mvp-demo\foreign-trade-geo-agent\start_mvp.ps1" -Stop

# 只停止 Commercial Dev
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Codex程序\foreign-trade-geo-agent\start_commercial.ps1" -Stop
```

## F：成功历史文章

已实际通过 8002 读取：Run `36f32eda-b8cd-4944-9234-39987e6df526`，Draft `2b236340-3166-4dce-bc8e-4c2c02ca45e1`，SUCCEEDED / NEEDS_REVIEW。

[查看原成功文章](http://127.0.0.1:8002/runs/36f32eda-b8cd-4944-9234-39987e6df526/drafts/O-content-h2-present?draft_id=2b236340-3166-4dce-bc8e-4c2c02ca45e1)

页面完整 Markdown 逐字符等于原 SQLite 值。刷新、重复查看、服务重启后仍可读取，未产生新模型调用。已识别的原运行数据库及 16 个相关运行文件在全部验收后 SHA256 保持不变。

## G：VDemo 新文章能力及逐次付费确认

**已实现并离线验收；本轮没有新的真实 DeepSeek 请求。** 桌面入口的实际运行状态已确认模型启用、逐次确认策略启用、现有本地凭据已配置。没有探测 API 账号或验证新的真实计费请求。

在新 Run 的英文选题卡上，用户必须勾选确认将该选题及采样网页资料发送给 DeepSeek，并执行本次付费请求。复选框默认未勾选；POST 仅接受精确确认值，服务层也重新检查确认。GET、启动程序、浏览或刷新均不会生成文章。

既有默认 `build_mvp_application(... allow_live_drafts=False)` 保持关闭；只有 VDemo 桌面组合启用 `allow_live_drafts=True` 与服务层 `require_paid_confirmation=True`。没有修改 Commercial 或生产 Admission。

原单任务、来源 digest、唯一 Draft 预留、120 秒 adapter / 150 秒 workflow 超时、3000 输出 token、128 KiB 响应及 64 KiB 输入预算保持不变。模型 adapter 不自动重试、redirect 或 fallback。重复提交返回已有记录，成功/失败/中断记录不会再次扣费；FAILED 的新重试仍需原独立 scoped authorization，本次复选框不能解锁它。

密钥只在 VDemo 进程内按需读取现有配置：进程环境优先，再读取 mvp-demo/.env，最后读取原主目录/.env 中的 DEEPSEEK_API_KEY；不会输出或持久化其值。Commercial 不加载模型凭据。尚未实现新的旧失败稿重试授权界面。

## H：Commercial Dev 可人工检查的真实内容

- `/history`：原合成 MVP / Live 保存 Run；`/runs/...` 和 `/artifacts/...` 通过既有只读 reader / codec 查看受支持记录与 Evidence / Source。
- `/intake`：原合成开发会话的当前 Evidence Intake snapshot、checks、证据和版本绑定。实际数据可读，没有创建或迁移数据库。
- `/reports`：白名单历史材料，包括 Evidence 原文、绑定、Phase7-A.1 preflight、A.6 live failure、Claim Audit replay、Editorial / Human Review、Phase6 manifest 和 EXPLAIN 最新报告。
- 首页显示实际 `DRAFT_EXECUTION_AUTHORIZATION_REQUIRED`，没有伪造可信稿件、审核通过或人类批准。

此入口不执行审核或改写；人工审核提交界面标记 NOT_IMPLEMENTED，缺失、不支持或超预算记录标记 NOT_AVAILABLE。历史报告不是本轮重新验证，也不是生产批准。旧主目录已有 Web 入口含补证、生成及 WordPress 路由和初始化写入，因此本次新增独立只读 inspector，没有重构 Trust Layer 或暴露那些写入路由。

## I：Phase7 实际位置及保全

- 原主目录：Evidence Intake / Sufficiency / Production Admission 及版本绑定；`docs/real-llm-draft-phase7a2/` 至 `phase7a6/`；`docs/draft-claim-audit-phase7b/`。
- `C:/Users/31969/.codex/worktrees/phase6-e2e/foreign-trade-geo-agent`：Phase2–6 冻结基线、Evidence-001–004、manifest、TEST ONLY Evidence-bound Draft Admission、Editorial / Human / Revision Review。
- `explain-model-preflight`、`explain-offline-diagnosis`、`p1-postgresql-consumption`：各自不同的 EXPLAIN 和可信消费实验及源代码，均未自动合并。
- `19dc`、`f7f2`、`d81b` 等树：早期 Editorial / Human Review 原型；其余 Decision Record / Writer / Validator 材料也已逐树保留。

对实施前全部 10,969 个快照原文件逐文件比较；只有本轮明确改动的启动器及 VDemo 文件改变，**Phase7 / EXPLAIN 原文件无变化、无缺失**。A.5/A.6 真实实验仍为 Layer3 阻断，Claim Audit 为有限规则；生产 Gate 默认拒绝，不声称 Trust Layer 通过生产级验收。

## J：独立本地备份及恢复

`E:/CodexBackups/foreign-trade-geo-agent/2026-10-15-dual-version`

实施前检查全部 17 个登记工作树并建立逐树 `snapshots/`，保存源码、测试、文档、未提交文件、非敏感实验材料、HEAD、Git 状态和 tracked diff。原快照 10,969 文件。`runtime-snapshots/` 另外保存 VDemo 原 SQLite 及已识别的 Commercial 合成状态（16 文件），SQLite integrity_check 均为 ok。

`final-overlay/` 保存本轮最终修改/新增文件；`desktop-final/` 保存两个最终快捷方式；`inventory-final.json` 保存最终分支和未提交状态。`all-files-manifest.json` / `all-integrity.json` 保存最终全备份 SHA256 及校验结果；`verify_backup.py` 可独立只读校验，不依赖原工作树。

没有复制 `.env*`、API Key、个人凭据或未知数据库。已识别 SQLite 才单独备份，原数据库未覆盖或替换。恢复时先校验，再按各树原 HEAD 分别恢复 snapshots 并叠加相应 final-overlay；不要把多树快照整体混合或覆盖正在使用的库。旧 live consumed 标记和失败证据必须保留；不得重新运行历史 live sender 或复用旧授权。详细旧阶段地图另见备份 previous-recovery-reference.md。

## 实际验收及 K：剩余工作

**已完成并实际验证：**

- 两条实际 `.lnk` 的冷启动、复用、停止和重启；Explorer 中实际双击两条桌面入口均打开浏览器，未创建重复服务。
- 8002 / 8003 同时可访问；各自源码、数据库、PID、状态、互斥锁、日志和临时目录独立。
- 关闭 VDemo 不影响 Commercial 的 PID / 页面；关闭 Commercial 不影响 VDemo，随后均通过各自 `.lnk` 重启。
- VDemo 首页、原 Crawl/SEO/Opportunity、原成功文章、刷新及 Host/CSRF 403 拒绝。
- Commercial 历史、Intake、Admission、Claim Audit / Review / EXPLAIN 页面；所有 POST 写入路由不存在，测试返回 405。
- 原运行数据 hash 不变；Phase7 原文件完整；两个 Git HEAD 不变，无 commit/push。

旧 8002 进程并非未知服务：此次只读核实 PID 7136 / 父 PID 8680 的工作目录都是 mvp-demo，其创建时间、exe、命令行及监听关系与上一轮记录完全相同。只迁移了这组已识别的旧 VDemo 进程；没有终止未知服务。证据见 verified-legacy-migration.json。

离线验证：VDemo **119 tests PASS**，Commercial / 原 Gate、Intake、runtime、Draft workflow **64 tests PASS**；没有运行全仓库套件。完整命令和日志在备份的 vdemo-final-tests.log / commercial-final-tests.log。新功能的初次 red 失败、测试 fixture / 错误模块名造成的调用失败及中文路径启动失败均有记录，修正后最终复核通过；没有放宽生产 Gate 或旧有效断言求通过。

**已完成但本轮未实发验收：** 用户确认后真实 DeepSeek 新稿的 API / 账号 / 计费结果；按本轮限制只用 MockTransport 验证单次完整模型链路。真实 Crawl 功能沿用已有实现，本轮读取原 Crawl 记录并做离线回归，没有新抓取。

**尚未实现且不属于本轮交付：** Commercial 的人工审核提交、可信审核身份和生产授权、Phase7 生产接入与生产级商业质量验收。旧失败稿的新授权 UI 也未新增。

**本轮阻断：无。** 两个服务保持运行，停止本轮开发，等待下一步安排。真实 LLM 请求 0，WordPress 调用 0，公网部署 0。
