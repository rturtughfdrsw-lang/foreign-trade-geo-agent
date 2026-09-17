# MVP Architecture

## 目标与边界

本项目面向 B2B 外贸独立站，目标是把网站诊断、AI 可见度数据、优化建议、内容规划、文章草稿和历史结果连接为可追踪的自动化流程。

本阶段仅定义架构边界，不实现业务逻辑、第三方调用、数据库或 Web API。

## 架构原则

- 第一版采用固定 Workflow：按照预先定义的步骤执行，不使用会自主决定下一步的自由 Agent。
- 核心业务逻辑只依赖项目内部的统一数据结构和抽象接口。
- 所有第三方能力必须通过 Adapter 隔离；核心层和工作流不能直接依赖某个第三方项目或 SDK。
- 第三方实现应可替换：替换诊断工具、AI 可见度数据源、内容生成服务或 WordPress 客户端时，不改变核心流程语义。
- 先保持最小化；FastAPI、Pydantic、PostgreSQL 与具体 LLM/SEO 工具仅在后续已验证的需求下引入。
- WordPress 第一版只能创建 Draft，禁止自动 Publish。

## 目录职责

- `core/`：后续放置稳定的领域模型、统一数据结构与接口定义。
- `workflows/`：后续放置固定工作流的步骤编排和状态流转。
- `adapters/`：后续放置第三方工具与服务的适配实现。
- `storage/`：后续放置历史结果的持久化抽象与实现。

## 固定数据流

```text
站点 URL
  -> 网站数据获取
  -> GEO/SEO 诊断 Adapter
  -> AI visibility / brand mention / competitor Adapter
  -> 统一数据结构（core）
  -> 固定 Workflow：优化建议与 content plan
  -> 企业真实资料驱动的文章生成
  -> WordPress Adapter：仅保存 Draft
  -> 历史结果存储（storage）
```

在第一版中，Workflow 负责以确定顺序协调这些步骤；每个 Adapter 只负责将外部能力的输入与输出转换到内部约定。

## 初步组件策略

第一版优先研究以下组件，并在评估通过后才考虑接入：

- `geo-optimizer-skill`：网站 GEO/技术诊断。
- `Elmo`：AI visibility、brand mention、competitor 与历史监测。

第一版暂不集成 Voyage GEO、GEORank、GEOFlow，除非后续技术审计证明它们具备不可替代价值。
