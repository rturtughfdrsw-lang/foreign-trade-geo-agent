# 本地 SEO MVP Web 交付记录 · 2026-10-10

实现采用现有 FastAPI + Jinja + 本地静态资源及 loopback 启动入口。
没有新建前后端框架、修改抓取/审计/规划/Draft 核心算法或接入生产服务。

## 启动与入口

在项目根目录：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[demo]"
# 首次准备；目录必须不存在。已准备时跳过，避免覆盖任务。
.\.venv\Scripts\python.exe -m scripts.prepare_web_mvp
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent.web
```

访问 <http://127.0.0.1:8000/mvp>。本轮已实际准备并启动此地址。
原有首页 `/` 增加工作台链接，既有 Demo / Live API 保留。
准备步骤完全离线：复用 `demo_seo_e_only.prepare`，原生生成、保存并重新读取
Crawl 派生 Packet、Audit、Opportunity、Plan 及独立的合成候选。

如需从空白任务重复演示，请使用新的输出目录及现有应用工厂参数：

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_web_mvp --output-dir .data/seo-mvp-fresh
.\.venv\Scripts\python.exe -c "import uvicorn; from foreign_trade_geo_agent.web.app import create_app; uvicorn.run(create_app(mvp_dir='.data/seo-mvp-fresh'), host='127.0.0.1', port=8000)"
```

先停止占用同一端口的服务。已有目录不覆盖；没有 UI 清空或删除历史操作。

## 可操作流程

1. 在分析页选择 NovaCNC，查看保存的 1 页页面证据、15 项审计观察、1 项机会及 C1 文章任务。
   页面数据从原生 History SQLite 读取，网址查询不会创建 run 或发起抓取。
2. 进入资料补充，初始为 `WAITING_FOR_EVIDENCE`。F1 明确要求主轴型号、参数、测试条件和限制。
3. 点击“填入合成 E1 示例”，或粘贴 UTF-8 文本/用 `.txt` 文件填入文本框。
   点击保存后真实追加原生 Intake revision，状态为 `RECHECK_REQUIRED`。
4. 点击“重新核对”，调用原有 PlanningEvidenceWorkflow 和 RetainedIntakePlanWriter；
   绑定新的原生规划版本，状态为 `WAITING_FOR_HUMAN_REVIEW`。没有语义 reviewer、人工签核或执行授权。
5. 刷新或重启，已保存任务、文本、版本和状态恢复。补交资料追加 E2/E3，保留被替代记录。
6. 文章页读取独立候选：完整标题、2 节正文、13 条陈述、P1/S1/E1 引用和 E1 原文。
   主轴参数陈述 CL3 只有 E1，没有 P/S 参数支持。质量与人工审核均为 `UNREVIEWED`。
7. 点击导出，浏览器下载 `novacnc-synthetic-unreviewed.md`；内容由原生 renderer 生成。

交互 journal 与候选 journal 严格分离。候选为准备命令预先生成的手写合成 writer 产物；
其 TEST reviewer 仅属于离线 fixture，不被 Web 服务实例化，也不产生生产执行权限。
页面只比较当前文本与候选原文是否一致，不声称任务版本、审核或执行权限一致。
改动客户文本后显示不匹配，仍查看原冻结 E1，绝不将其重标为当前生成结果。

## 验收记录

实际使用 Codex 浏览器操作本地服务，桌面 1440×1000、移动视口 390×844。

| 验收点 | 结果 |
| --- | --- |
| 浏览器打开三页 | 已实际打开，HTTP 200 |
| 分析及任务来自后端保存结果 | 原生 HistoryReader + 原生 presenter；没有替代业务报告 |
| 保存资料改变状态 | 待资料 → 待 recheck，Intake revision / evidence version 真实增加 |
| recheck 状态 | 待人工审核，规划版本真实增加，执行仍未授权 |
| 刷新及服务重启恢复 | 浏览器刷新已验证；停止/重新启动服务后读取旧任务已验证 |
| E-only 正文映射 | 2 个节标题、完整正文、CL3 → E1、冻结原文及字符区间可见 |
| Markdown 下载 | 实际点击下载，与当前原生 renderer UTF-8 字节一致 |
| 不可批准的 Draft | 执行按钮禁用；MVP approve/deliver 路由不存在 |
| 生产 Gate / P1 / WordPress | 本轮没有修改；没有真实模型、站点或 WordPress 操作 |
| 移动布局 | 三页布局实查，DOM 内容宽度 = 可用视口宽度，无横向溢出 |
| UTF-8 文件读取 | 实际选择合成 `.txt` 后正文正确填入；无效字节显示失败，保留原有文本 |
| 未保存 URL | 实际输入未授权的 `.example` URL，仅显示无保存结果，没有抓取 |

浏览器导出 SHA-256：`9f135563290578dac9eb0ee22e2a0c65618c56dedf1239d4f6e49eb5208eb85a`。
原准备脚本在 Windows 写出的 `.md` 可能采用 CRLF；HTTP 使用原生 renderer 的 LF UTF-8。
正文、引用及审核说明一致；对比通过读取文本统一换行，下载对 renderer 则逐字节一致。

截图：

- [分析页（桌面）](seo-web-mvp-acceptance-2026-10-10/01-analysis-desktop.jpg)
- [待补资料](seo-web-mvp-acceptance-2026-10-10/02-evidence-waiting.jpg)
- [保存后待核对](seo-web-mvp-acceptance-2026-10-10/03-evidence-recheck-required.jpg)
- [待人工审核与版本历史](seo-web-mvp-acceptance-2026-10-10/04-evidence-human-review.jpg)
- [完整文章与证据（桌面）](seo-web-mvp-acceptance-2026-10-10/05-article-desktop.jpg)
- [文章页（移动）](seo-web-mvp-acceptance-2026-10-10/06-article-mobile.jpg)
- [文章总览](seo-web-mvp-acceptance-2026-10-10/07-article-overview.jpg)
- [资料页（移动）](seo-web-mvp-acceptance-2026-10-10/08-evidence-mobile.jpg)
- [分析页（移动）](seo-web-mvp-acceptance-2026-10-10/09-analysis-mobile.jpg)

本轮浏览器最初复现了 textarea CRLF 与冻结 LF 原文比较问题。现已在 Web 文本入口
明确统一 LF，按保存后的 UTF-8 内容计算哈希，并通过测试及浏览器复验。
验收工作区保留了修复前 E1 与修复后 E2，当前规划/证据版本均为 v3，修订为 5；
原冻结候选仍引用其独立的 E1/v2。这是两条不同历史，页面明确区分。

## 测试与复核

新增 `tests.test_web_mvp`：9 项通过。覆盖真实版本状态、重开存储恢复、过期提交、
原生导出、XSS 转义、无批准入口、空/损坏包、候选缺失不阻断资料补充、
CRLF、16,000 中文字符、坏 UTF-8、超大 chunked 表单、非 ASCII CSRF、
非本地主机拒绝及候选 History 文件不被修改。

测试过程曾观察到预期 RED（模块缺失、浏览器换行、输入大小边界、候选耦合），
并修复了模板 `request` 上下文冲突及校验令牌异常。以上问题均已回归 GREEN。
独立代码复核指出的两项 P2（中文 URL 编码大小、非 ASCII token）已修复并回归。

最终完整回归 **1686 项通过（446.480 秒，exit 0）**。见 [完整回归摘要](seo-web-mvp-acceptance-2026-10-10/full-suite-summary.txt) 和 [验收数据](seo-web-mvp-acceptance-2026-10-10/verification.json)。
测试环境会出现现有 Starlette/httpx deprecation warning；本轮没有安装替代测试依赖。

## 本轮文件

- 修改 `web/app.py`、`web/templates/start.html`：在既有服务挂载工作台及首页链接。
- 新增 `web/mvp_application.py`、`web/mvp_routes.py`：本地应用 facade、受限表单及导出。
- 新增 `web/templates/mvp.html`、`web/static/mvp.css`、`web/static/mvp.js`：三页响应式 UI。
- 新增 `scripts/prepare_web_mvp.py`：离线准备并分离交互 journal。
- 新增 `tests/test_web_mvp.py`：有意义的边界和集成回归。
- 更新 README；新增计划、本文及截图/验收数据。

上述 `web/` 均位于 `src/foreign_trade_geo_agent/web/`。已有后端未提交改动原样保留。

## 可用与仍不可用

已可用：NovaCNC 保存分析查看、任务缺口、文本补充与版本历史、原生 recheck、刷新恢复、
独立原生候选正文/证据阅读、Markdown 下载、空/错误/加载/待审状态。

本工作台尚不可用：任意客户历史 run 的选择/导入、授权后新站点分析、现场生成生产 Draft、
正式人工语义审核与可信身份签核、Draft 执行批准、WordPress 交付、审核备注。
既有 Live 入口仍独立保留，本轮未执行。没有注册、付费、多租户或团队权限系统。

真正的通用 MVP 闭环仍需：授权站点分析与任务选择接入同一工作区；可信审核身份及当前
证据审核记录；生产 Draft 执行授权与受控真实 writer；真实 Draft 质量验收；
单独授权的 WordPress create-only/draft-only 交付和独立验证。
这些需要下一轮明确决策，不能以本次合成演示的通过替代。

本轮未部署、commit、push、merge，未调用真实 DeepSeek、抓取第三方、写入 WordPress、
修改生产 Gate/P1/PostgreSQL。工作到本地演示验收结束。
