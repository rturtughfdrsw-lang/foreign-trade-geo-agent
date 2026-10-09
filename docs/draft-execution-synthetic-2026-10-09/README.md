# BellHarbor/F9：独立 synthetic 执行边界验收

全部公司、域名、产品、事实和 actor 都是虚构 TEST 数据。Fetcher/Search/Writer 使用本地 fixtures；Crawl、Packet、Audit、Research、Opportunity、Change Planning、Intake、SQLite 和 Draft boundary 使用当前原生实现。没有客户身份接入、真实签核、商业 Draft、网络或 WordPress 操作。

- `01-initial-request.json` / `.txt`：原任务要求解释过滤精度、壳体适用性；原 P/S 仅有主题词，输出具体单位、工况、材料、方法和限制缺口。
- `02-native-planner-material.json` / `02-customer-request.json`：第一次仅补精度资料；同一任务保留，F1 等人审，F2 仍明确缺资料。
- `03-native-planner-material.json` / `03-customer-request.json`：第二次补壳体资料；客户材料单独作为不可信 context 进入同一个原生 Planner，保留 EXPLAIN 和原 P/S/A。
- `04-human-review-candidate.json`：完整来源与逐义务材料；F1/F2 都是 UNREVIEWED，待可信人工语义审核，`draft_authorized=false`。
- `05-versions-and-denials.json`：五个不同 snapshot digest，revision=1→5、evidence=1→3、Plan=1→3；十次旧/当前输入与旧/当前 digest 组合均拒绝，writer=0。

新证据不自动赋予旧请求资格；即使旧 Plan 文案与新 Plan 相同，新 digest 也不是 Draft permission。客户文本中出现全部主题词不证明 EXPLAIN 的事实、工况适用性或因果解释得到支持。完整负例及真实 CLI/Live POST 验收位于 `tests/test_draft_execution_boundary.py`；撤销/过期/伪造签核与后生成二次验证继续由既有 P-only TEST 测试覆盖。

样例可用 ignored 本地生成脚本 `.data/draft-entry-20261009/synthetic.py` 复核；脚本复用验收测试 fixtures，不属于生产入口。
