# Commercial Preview UI/UX 验收 — 2026-10-18

## 改版范围

- `web/commercial_demo_ui.py`：只读首页、单项事实核对、独立文章阅读区、中文说明、响应式样式和无持久化的浏览导航。中文证据摘要匹配原引用哈希，不作为业务证据或审核结论。
- `web/commercial_preview.py`：仅在 `read_only=True` 时选择新展示层，本地可写预览仍沿用原路由与展示。
- `web/render_demo.py`：CSP 仅允许精确哈希匹配的浏览脚本；认证、健康检查、写入拒绝、初始化与临时数据库逻辑未改。
- `tests/test_commercial_demo_ui.py`：新增 10 项 UI、引用保留、只读行为及安全策略回归。
- 四个原有 `tests/test_commercial_preview*.py` 和 `tests/fixtures/commercial_preview.json`：从已有演示工作树带入部署快照（仅规范文件末尾空行），保持原断言，提供可重复的中文与业务回归。
- `scripts/verify_commercial_demo_ui.py` / `.cjs`：可选本地浏览器验证，使用临时认证和独立演示数据库。
- `RENDER_DEMO.md`：记录界面行为、验证方式及手动部署步骤。

未修改 core、workflows、storage、adapters、演示夹具、业务 Gate 或生产授权逻辑；未新增运行依赖。

## 实际运行结果

| 验证 | 通过 | 失败 |
| --- | ---: | ---: |
| 改动前 Render 认证与隔离基线 | 7 | 0 |
| 改动前原有 Commercial Preview 回归 | 70 | 0 |
| 改动后演示快照全套 unittest discover | 87 | 0 |
| Chromium / 本机 Edge 浏览器断言 | 62 | 0 |

最终单元测试覆盖 70 项原有 Commercial Preview 测试、7 项原有 Render 测试、10 项新增测试。
命令：`python -m unittest discover -s tests -p 'test_*.py' -v`，从本工作树加载 `src`。
浏览器命令：`python scripts/verify_commercial_demo_ui.py --playwright-module <本机模块路径>`。

浏览器使用 1440×900、390×844、320×844、768×900、720×450 视口。
实际验证首页入口、5 项连续切换、首尾边界、非零滚动位置保持、键盘和标签页导航、
折叠原文、无嵌套滚动区、无横向溢出、禁用 JS 后的完整阅读回退及无脚本/CSP 错误。
已检查桌面和手机的首页、核对页、文章页六张截图，保存在被 Git 忽略的
`.data/ui-verification/`。

测试期间 UI 没有外部请求或写入请求；浏览前后 SQLite 文件哈希一致，核对记录为空，
执行确认为空，writer 调用为 0，`production_authorized=false`。服务关闭后临时数据目录删除。
服务端覆盖所有现有写入路由、未知路由及 POST/PUT/PATCH/DELETE/OPTIONS/TRACE 拒绝；
未认证业务请求仍被拒绝，`/healthz` 仍可公开读取。

中途出现过两类验证问题，均已修复并重跑：新增测试解析器把缺失属性也当作匹配，
以及浏览器验证子进程缺少 Windows 浏览器安装目录环境变量。没有放宽安全断言。
依赖存在 Starlette/httpx 弃用提示；本轮未升级依赖。

## Git 和数据边界

原 `render-free-demo` 工作树有未提交内容，且本地分支基于开发历史；本轮未改动它。
本轮使用从远程 `origin/render-free-demo` 的 `aeeafb9` 建立的独立隔离工作树，
不引入开发分支历史，不合并回默认分支。公开仓库默认分支为 `main`。

提交前检查演示分支可达历史、文件清单、差异、忽略规则和凭据特征。
扫描提示的固定字符串均属于已有 mock WordPress、模拟响应脱敏测试或 URL 拒绝测试；
没有真实凭据、环境文件、数据库、客户材料或运行日志进入提交。

## 限制与未执行项目

- 当前真实演示种子没有生成后的文章正文，新界面如实显示“尚无文章正文”。已有草稿的正文和段落引用保留通过合成结果单元测试验证，没有调用模型来补造正文。
- 只运行该独立部署快照的全部测试；没有运行原开发工作区的更大测试集。
- 没有使用生产数据、真实 DeepSeek 或 WordPress，也没有执行公网部署或登录后的公网验收。
- Render Auto Deploy 关闭。推送后需要在现有服务执行 **Manual Deploy → Deploy latest commit**，部署成功后再做公网验收。
