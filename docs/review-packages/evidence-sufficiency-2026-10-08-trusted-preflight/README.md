# 真实六项材料：待人工签核包

全部 O1–O6 / D01–D07 均 NOT_REVIEWED，unsigned；真实 Gate NO-GO。旧的有限离线用途授权不等于本完整任务签核。D08 商业验收仍待另行真实审核。

- [逐项核验材料](owner-obligations.md)：六项原文、上下文、精确 locator/spans、七个 content points、义务覆盖及 Plan 绑定。
- [冻结目标](frozen-target.json)：独立 task v2、Plan candidate v2、证据快照 v1、完整原生 DraftInput，及额外绑定的归属/虚构语境/输出范围。
- [未签核模板](review-record.UNSIGNED.template.json)：没有 reviewer、时间或 proof；编辑此文件不能取得权限。
- [lineage](lineage.json)：旧 coverage 顶层 v1 的显式更正记录，原包字节保持。

frozen-target SHA-256：`146cd906b1fce15a21a6f26f50224e09182a1d0b7ed934df1e7ccba826972c1d`；DraftInput：`a24428cbc575527b09d59897422fdabe6038c13b206878ddc4cce0a93256b7e2`。

人工需逐项确认 SOURCE_USE（仅原有项目离线用途）、TASK_AND_DEPTH（完整逐字六项任务）、OFFLINE_PLACEMENT（测试展示，非商业改版）、P_ONLY_CANDIDATE（仅本 R1/C1）、FROZEN_CONSUMPTION（将来必须消费同一冻结对象，本轮未写作）、REVIEW_AUTHORITY（真实身份与任务权限）、VALIDITY_AND_STORAGE（最长24小时、撤销和可信保存），并填写六项 verdict/reason。商业 D08 不属于这份离线授权，也没有被排除后默认为批准。

可信来源尚缺：受保护身份/权限/密钥与撤销服务、可信签核存储及 append-only lineage。生产运行没有 authenticator，默认拒绝。只有 tests 中的随机内存 HMAC synthetic fixture 可取得 SYNTHETIC_GREEN；它与真实 NovaCNC 六项签核分开。

preflight 没有 writer，结果不构成 Draft/CMS capability。原生 Draft builder/workflow 仍拒绝 P-only 输入。没有生成正式 Draft，没有外部调用或签名。
