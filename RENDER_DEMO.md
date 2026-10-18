# Render 免费只读演示

这是当前 Commercial Preview 的最小部署快照。只包含运行入口所需的 Python
源码依赖、虚构 Aster 测试资料和部署测试；不携带开发历史、客户文档或本地数据库。
原仓库的开发分支和未提交修改保持原状。不要把这个独立历史分支合并回开发分支。

## 服务配置

- 类型：Web Service；Runtime：Python 3；Instance Type：Free（$0/月）。
- 分支：`render-free-demo`；Python 版本由 `.python-version` 固定为 3.12 系列。
- Build Command：`pip install '.[demo]'`
- Start Command：使用 `render.yaml` 中的完整 `startCommand`。
- Health Check Path：`/healthz`；Auto-Deploy：Off。
- 不添加磁盘、数据库、付费实例或其他资源。

在 Render 环境变量中设置 `DEMO_USERNAME` 和 `DEMO_PASSWORD`。
用户名为 3–64 位字母、数字、下划线、点或短横线。密码用密码管理器生成，
24–128 位 ASCII 可打印字符，不含空格。不要把密码贴入代码、聊天、URL 或日志。
Render 自动提供 `RENDER_EXTERNAL_HOSTNAME`。不要添加 DeepSeek、WordPress
或正式数据库的环境变量。密码缺失或不符合要求时启动失败。

## 安全和数据

浏览器使用 HTTP Basic 登录；除不含业务信息的 `/healthz` 外全部路径需要认证。
业务流量要求 HTTPS；错误认证有全局限流。所有写入方法在路由前返回 403，
所有表单禁用。没有生成、抓取真实网站、审核提交、反馈、执行确认或发布入口可用。
`production_authorized=false`。这里不提供用户独立账户、细粒度权限或生产用途。

每个进程启动都在系统临时目录建立新的 SQLite，只加载虚构夹具。
不读取 `.env`，不接受数据库路径参数，不连接正式数据。
重启、休眠、重新部署会丢失临时数据并重新加载夹具；不保证永久保存。
应用访问日志关闭；异常响应不包含原始异常文本。

## $0 的账户前提

Free 实例本身是 $0，但 Render 的带宽和构建分钟超额可能产生费用。
为严格保持 $0，请使用没有绑定支付方式的免费工作区，并确认没有付费资源；
免费额度耗尽时应暂停服务或构建，不购买额外额度。不要为此服务添加支付方式。
创建前在 Billing 中核对账户状态，不能只凭 Free 实例标签承诺账户永不收费。
参见 https://render.com/docs/free 。

## 本地验证

安装后执行 `python -m unittest tests.test_render_demo -v`。
部署后验证 HTTPS `/healthz` 为 200，未登录 `/` 与 `/status` 为 401，
登录后首页和演示任务为中文，只读标识清晰；只对演示服务验证 POST 返回 403。
本文件是部署配置说明，不代表远程服务已经创建或公网检查已经通过。
