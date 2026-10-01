# foreign-trade-geo-agent

面向 B2B 外贸独立站的固定 SEO/GEO 工作流。当前 CLI 可以生成可追踪的内容规划，并在人工明确选择一个 `D#` 后创建 WordPress 草稿。

## 本地运行

需要 Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

`plan` 只需要：

```dotenv
DEEPSEEK_API_KEY=
TAVILY_API_KEY=
```

运行规划：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent plan `
  --site https://manufacturer.example `
  --question "What content should this industrial pump manufacturer create?" `
  --language en
```

默认历史数据库是 `.data/history.sqlite3`；可用 `--db <path>` 覆盖。成功输出为简短 JSON，其中包含 `run_id`、各 artifact ID、`content_draft_artifact_id`，以及可供人工选择的 `D1`、`D2` 等草稿标识。例如：

```json
{
  "run_id": "11111111-1111-4111-8111-111111111111",
  "status": "succeeded",
  "content_draft_artifact_id": "22222222-2222-4222-8222-222222222222",
  "requires_human_review": true,
  "drafts": [
    {"draft_id": "D1", "type": "SECTION_DRAFT", "title": "Selection guide"}
  ]
}
```

## 人工批准并交付

在 `.env` 中配置：

```dotenv
WORDPRESS_USERNAME=
WORDPRESS_APPLICATION_PASSWORD=
```

然后把规划输出中的 `run_id`、`content_draft_artifact_id` 和选定的 `D#` 传给 `deliver`：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent deliver `
  --run-id 11111111-1111-4111-8111-111111111111 `
  --artifact-id 22222222-2222-4222-8222-222222222222 `
  --draft-id D1 `
  --site https://customer.example
```

交付输出示例：

```json
{
  "selected_draft_id": "D1",
  "delivery_status": "success",
  "attempt_id": "44444444-4444-4444-8444-444444444444",
  "attempt_outcome": "success",
  "remote_post_id": 41,
  "remote_link": "https://customer.example/?p=41",
  "reconciliation_required": false
}
```

**交付只会创建 WordPress Draft，不会发布文章。** `UNKNOWN`，以及被既有 `PENDING`/`UNKNOWN` 尝试阻止的交付，都需要人工核对 WordPress 和历史记录；CLI 不会自动重试。

退出码：`0` 表示规划成功、交付成功，或已存在匹配的成功交付；`1` 表示正常工作流失败或明确交付失败；`2` 表示 CLI、配置或请求校验错误；`3` 表示需要人工 reconciliation。
