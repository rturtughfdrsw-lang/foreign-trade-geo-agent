# 双人协作指南

先阅读 `AGENTS.md`，了解架构、SEO MVP 范围和真实接口的授权边界。

## 首次准备（Windows / PowerShell）

安装 Git 和 Python 3.12，接受仓库协作邀请后执行：

```powershell
git clone https://github.com/rturtughfdrsw-lang/foreign-trade-geo-agent.git
cd foreign-trade-geo-agent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[demo]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

如果正在验收尚未合并的 PR，先在 PR 页面确认其分支名，再用 `git switch --track origin/<分支名>` 切换到该分支。默认克隆得到的是 `main`，不包含尚未合并的功能。

离线 Commercial Preview 使用合成页面和 fake writer，不需要 API key：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent.commercial_preview_runtime
```

在浏览器访问 `http://127.0.0.1:8017/`。本地数据保存在 `.data/`，每个人独立保存。其他入口和产品限制见 `README.md`。

## 每个任务的工作流程

1. 在 GitHub Issue 中写明目标、负责人、验收条件和预计修改的模块。开始前确认双方不会同时修改相同文件。
2. 保存当前工作后同步主分支，并为一个任务建一个分支：

   ```powershell
   git switch main
   git pull --ff-only origin main
   git switch -c codex/your-task-name
   ```

3. 开发时运行相关 unittest；跨模块修改在交付前运行完整测试。遇到已有失败，记录实际结果，不删除断言或跳过有效测试。
4. 检查 diff，并明确列出要提交的文件：

   ```powershell
   git diff
   git status --short
   git add path/to/changed-file.py path/to/test_file.py
   git diff --cached
   git commit -m "fix: describe the concrete change"
   git push -u origin HEAD
   ```

5. 向 `main` 提 Pull Request，说明行为变化和实际测试结果。由另一人审核，通过后再合并。出现冲突先沟通，不覆盖对方工作，不强制推送。

## 分工与审核

- 每项任务只有一名负责人，另一人负责审核；具体人选在 Issue 中明确。
- core 契约、数据库 schema、凭据处理和 WordPress 交付变更，需要双方确认影响。
- `src/`、测试和必要的脱敏文档纳入版本管理；`.venv/`、`.env`、数据库和运行产物留在各自电脑。
- `docs/` 中的实验记录和验收资料逐项审核后再提交，不批量添加。原始响应、客户资料和截图可能含敏感内容。
- API key 各自配置，不通过 Git 或 Issue/PR 分享。共享配置只提交占位符到 `.env.example`。
- 本地离线测试通过不代表真实接口已验收。真实网站抓取、付费模型调用和 WordPress 创建草稿都需要针对具体动作的明确授权。

## 自动检查

GitHub Actions 在 PR 和向 `main` 推送时使用 Windows、Python 3.12 创建 `.venv`、安装 `.[demo]` 并运行完整 unittest。CI 不配置业务 API 密钥，不运行 `scripts/verify_*.py` 等 live 验证。合并前检查 CI 结果；分支保护需要仓库管理员另外配置。

部分离线回归测试会读取 `docs/` 下的历史样本。这些已纳入版本管理的样本必须保留原始字节；`.gitattributes` 为其禁用换行转换。冻结包测试在临时目录中构建 TEST-only 样本，不重写历史实验 manifest，也不授权真实调用。
