# DeepSeek VisibilityMonitor PoC

- 测试日期：2026-09-18
- Provider：DeepSeek
- Model：deepseek-flash
- Target：Flowserve
- 执行方式：3 个 prompt × 1 个 provider，串行执行

## Prompts

1. Name several major global industrial valve manufacturers.
2. Which companies are well known for industrial flow control and valve products?
3. Recommend established suppliers of valves and flow-control equipment for industrial B2B buyers.

## Result

| Metric | Value |
| --- | ---: |
| Total attempts | 3 |
| Successful | 3 |
| Failed | 0 |
| Mentioned | 3 |
| Mention rate | 1.0 |

`DeepSeekVisibilityProvider` → `VisibilityMonitor` → `VisibilityReport` 链路验证成功。完整模型回答未记录在本文档中，以保持 PoC 记录简洁。

## Scope

本次结果只是技术 PoC。

当前 DeepSeek 请求没有启用联网搜索或外部检索，因此该指标表示模型自身知识中的 brand recall / mention visibility。

它不代表实时搜索结果、citation visibility、SEO 排名，也不能解释为 Flowserve 的“GEO 得分 100%”。
