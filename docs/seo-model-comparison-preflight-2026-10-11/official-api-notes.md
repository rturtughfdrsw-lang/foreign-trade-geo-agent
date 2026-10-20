# DeepSeek 官方接口核对

查阅日期：2026-10-11（Asia/Shanghai）。只读取公开文档，没有请求模型、模型列表、账户余额或其他账户 API。

- [官方模型与人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：model ID 为 `deepseek-v4-pro`，当前标示版本 DeepSeek-V4-Pro-0813；Flash 当前为 `deepseek-flash` / DeepSeek-V4.1-Flash。两者均支持文本、非思考 / 思考、JSON Output。Pro 无图像输入能力，本次只有文本，不受影响。
- [官方 Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：`POST https://api.deepseek.com/chat/completions`，允许上述 model ID、system/user messages、thinking.type=disabled、temperature=0 及 max_tokens=3000。上限允许 1–393216，不必调整本实验参数。
- [官方思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)：默认启用思考，因此显式保留 disabled；非思考模式的 temperature 有效。没有增加 reasoning_effort、工具、流式输出或 response_format。历史请求仅通过 Prompt 要求 JSON，Pro 也保持同样方式，不借 JSON mode 改变比较条件。
- [官方 Token 用量](https://api-docs.deepseek.com/quick_start/token_usage/)：不同模型分词可能不同，以响应 usage 为准；离线字符估算不等于实际计费 Token。

人民币 / 每百万 Token，按当前中文官方页记录：

| 模型 / 时段 | 输入命中 | 输入未命中 | 输出 |
| --- | ---: | ---: | ---: |
| Flash 空闲 | 0.02 | 1 | 4 |
| Flash 高峰 | 0.04 | 2 | 8 |
| V4 Pro 空闲 | 0.15 | 4.5 | 13.5 |
| V4 Pro 高峰 | 0.30 | 9 | 27 |

高峰是北京时间周一至周五（排除中国法定节假日）09:00–12:00、14:00–18:00；其余时间及周末为空闲。以实际执行时官方费率为准；本包采用高峰和全未命中作为保守预算，不依赖执行日为空闲，也不做外汇换算。价格可调整，估算不是账单 / 硬限额。

文档读取说明：标准中文价格 URL 数次返回抓取超时，最终通过同一官方路径的搜索结果查询参数成功读取全文；规范来源仍是上面的无参数官方链接。英文价格与 Chat Completions 页也成功读取。成功读取的中文价格 URL 为：

<https://api-docs.deepseek.com/zh-cn/quick_start/pricing/?nb_mt=p&nb_ti=kwd-2297875758714&nbt=nb%3Aadwords%3Ag%3A22371110801%3A175662281183%3A741266097534&r=0>

这些是公开文档证据；未验证当前账户的 Pro entitlement、可用余额、服务延迟或真实响应。model ID 是服务别名，不能用它锁定永久不变的权重；需记录未来响应的 model、created、system_fingerprint（如有），服务端版本变化会限制实验公平性。
