# 本轮核验范围与重跑

本包验证是材料完整性/保全及现有契约探针，不是人工充分性审核、Gate 测试或商业质量结果。

实际准备命令（仓库根目录，隔离脚本不在正式 tests 中）：

```powershell
.\.venv\Scripts\python.exe -B .data/evidence-sufficiency-owner-review-20261008/build_package.py
```

结果：exit=0，九份原快照复制到非 ignored 审核目录，P-only Opportunity 的现有 pure validator 返回 `SOURCE_REFERENCE_REQUIRED`。从历史合法 Planning prompt 核对 P3 已有 H1 locator 和页标题 ContentPoint；不是新 Plan/availability 成功。没有构造新 SUCCESS report、finalizer 调用、provider/writer/WordPress 调用。准备脚本拒绝覆盖已有 baseline/版本，不应重复执行以更新快照。

最终验证命令：

```powershell
.\.venv\Scripts\python.exe -B docs/review-packages/evidence-sufficiency-2026-10-08-v2/verify_materials.py
.\.venv\Scripts\python.exe -B .data/evidence-sufficiency-owner-review-20261008/verify_preservation.py
git diff --check -- docs/evidence-sufficiency-review-brief-2026-10-08.md
```

`verify_materials.py` 是独立标准库离线脚本，校验文件/binding digest、五类旧 artifact identity、十三 spans、空模板及本包链接。它不认证身份，不派生 SUPPORTED，也不调用生产 workflow/网络。本包的 `verification.json` 保存实际结果；缺失或 digest 不符应停止阅读为确定版本，不能自行修 hash 继承批准。

`verify_preservation.py` 在 ignored 目录，使用准备时 baseline 检查既有 tracked/untracked 文件的内容/缺失状态（仅旧 brief 的显式 v2 导航允许修改）、58 个既有 SQLite 文件、完整旧候选目录。新非 ignored 文件仅本次审核 docs/离线材料；不会初始化 store/migrate DB。结果在 ignored 目录保存，并逐字复制为本包 preservation.json 便于阅读；baseline 在 `.data/evidence-sufficiency-owner-review-20261008/`。独立 verify_materials 只检查该保全记录完整性，不宣称已在另一机器重查原工作树/DB。核验不覆盖所有其他 ignored 文件。

另执行过一次相同 pure validator 的内联 Python 探针，结果相同，exit=0。一次读取不存在独立 task-proposal.json 和 Windows 不支持的 rg 路径 glob 报检索错误，随后改为读取 binding/task 与目录 `-g`；一次文档补丁因同路径 Delete/Add 被拒绝，无文件修改，后改为新增 v2 入口并给旧 brief 添加导航。这些不是测试失败或 Gate 结果。

材料验证首次执行 exit=1：链接检查在脚本尚未生成自身 `verification.json` 时要求它已存在。修正验证器顺序：其他链接先查，结果写入后再核对全部链接；未改证据、validator 或审核状态。修正后按同一命令重新核验；最终结果以实际生成的 verification.json 为准，首次失败保留于本说明，不报告为一次全过。

正式 unittest、full discovery、前轮 RED/live harness 本轮均未运行；不复用前轮通过数作本轮成绩。不重新遍历数据库做审计、不访问公网/收费 API、WordPress、其他源码工作树，不 commit/push。保全/材料检查通过仍为 NOT_REVIEWED/NOT_IMPLEMENTED/NOT_PASSED。
