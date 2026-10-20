# 单项目/单管理员签核：最小部署设计与本轮计划

## 事实及授权边界

已读AGENTS、上轮报告、owner-obligations及实际代码。当前 CLI/Web/runtime 不引用 evidence preflight；代码只有显式Python调用、tests-only synthetic HMAC signer、严格loader及默认拒绝。现有HistoryStore不是签核身份源。审核对象仍为 task `T-P3-SIX-RELATIONS-ATTRIBUTED-EXCERPT-v2`、task/Plan/evidence版本 `(2,2,1)`、六义务七span、frozen-target `146cd906b1fce15a21a6f26f50224e09182a1d0b7ed934df1e7ccba826972c1d`、DraftInput `a24428cbc575527b09d59897422fdabe6038c13b206878ddc4cce0a93256b7e2`；O1–O6全部NOT_REVIEWED。

Windows只读检查：进程账户是仓库所有者，当前token的IsAdministrator=false；仓库无已配置独立reviewer/trust root或签核注册源。venv没有cryptography/win32crypt/win32security/fido2。不据此断言本机没有TPM/硬件密钥，也不枚举/使用用户既有私钥。没有创建账户、密钥、Windows服务或修改ACL。当前token不是管理员，不意味着同账户owner与Agent已隔离。

## 最小信任模型

选择单管理员独立审核账户/小型本地审核服务，Agent用另一个受限账户。管理员由项目所有者在Windows交互登录中建立，Agent不得代为选择owner身份。审核密钥和当前注册状态由独立账户持有；代码/配置/验证端信任锚同样应位于Agent无权修改的目录。可以在独立账户下使用current-user DPAPI保护软件私钥：只有在账户确实隔离时才构成保护，不防本地管理员/SYSTEM、同审核账户恶意进程或被劫持的审核程序。不以隐藏路径、仓库JSON、.env或普通SQLite flag充当权限。

认证实现复用 EvidenceReviewAuthenticator；必须用真实签名验证，绑定固定审核者及单项目/具体task/purpose权限，并验证当前key/grant撤销。生产实现尚未存在，不能用test HMAC实现替代。审核服务需认证本地IPC连接身份，并证明当前注册状态响应来自该服务；客户端与服务约定fresh challenge及可信时钟。challenge回显本身不是认证，受认证transport/签名response和独立信任锚才是认证依据。

每个签核有不可复用review_id、注册revision、完整record/proof/frozen目标摘要、审核者/project/task/version/purpose、注册时间/expiry及撤销时间。批准/撤销/替代只由owner审核服务写入受保护状态。每次preflight重新查询当前状态；服务不可用、身份/权限根不明、过期、撤销或摘要不符均拒绝。注册服务禁止回滚revision、复用ID或恢复已撤销ID；替代创建新ID并使旧ID撤销。代码不缓存注册授权。

本轮生产身份根止于设计及前置条件，只实现无授权能力的凭据缓存和注册验核消费边界。业务HistoryStore/schema/旧codec/Draft API不改；无CLI/Web signer、bootstrap密钥、自动批准或实际review注册操作。

## 持久化与重放规则

单独SQLite receipt store保存完整canonical frozen-target、原始signed review bytes和detached proof，append-only、有界、无approved/revoked权限字段。它是可篡改缓存，不能成为信任锚。每次读取重新核对字节/完整冻结目标，再经原loader验证签名身份/时间/全部义务，再查当前可信注册源。编辑JSON/DB或重算全部缓存digest，不能改变包外注册源及签名。缓存严格校验固定schema和trigger定义、限定查询集合及每连接100,000 SQLite VM steps；写入在BEGIN IMMEDIATE事务内验schema并INSERT，防并发替换trigger。资源护栏不提供审批授权。

数据库删除/篡改/替换/恢复旧备份最多导致拒绝或仍显示原合法记录；不能解除包外撤销。服务当前允许的同一记录、同一目标重复只读preflight是幂等检查，允许；已撤销/替代/过期的旧批准、旧注册响应nonce、跨task/purpose或同ID不同bytes都拒绝。此时没有writer、副作用或一次性Draft消费，不虚构“一次性token”语义。

独立服务状态的完整回滚、同管理员权限绕过、系统时钟回拨仍是残余风险。MVP最小做法是Agent无写权、管理员登录受控、服务保留单调revision及last-seen UTC并拒绝回拨、独立备份核对；若还要抵御本地管理员或完整磁盘快照回滚，需要外部设备/硬件或独立追加日志锚，不能用本库hash chain自证。此次不实现或宣称这些根已成立。

## 实现步骤（复用现有preflight）

1. 新core模块声明bounded receipt、VerifiedReviewRegistration、receipt reader/current registry/persisted loader ports；不新增多租户模型。
2. 新storage模块实现独立SQLite receipt create/append/read；create拒绝覆盖已有文件，reader不迁移/写入，拒绝误用History DB。无signer、权限管理或bootstrap。
3. 新adapter实现持久化loader：完整冻结目标一致、现有AuthenticatedEvidenceReviewLoader、fresh registry查询及所有绑定/生命周期验核。新workflow包装原preflight，时钟由受信任composition提供，调用者只传target/review_id；缺任何依赖则拒绝。
4. 先写tests观察RED；使用原synthetic signer和仅tests内的当前注册源，临时SQLite验证重启/持久化、DB/JSON篡改、重放/撤销/过期、身份/跨task/版本/span/Input变更、来源失联与native writer=0。保留原13项正负例。
5. 运行相关unittest及完整discover，核对所有既有文件字节与Git状态。完整结果另记本轮报告；不commit/push。

## owner真实签核的可执行部署验收清单（尚未执行）

1. owner确认独立审核Windows账户或独立设备，Agent保持受限账户；以OS登录建立owner身份。配置目录/私钥/注册DB仅审核账户可写，Agent无法读取私钥、修改信任锚或执行signer；检查实际ACL和跨账户拒绝行为。
2. 独立审核环境安装/选定经过审查的签名实现（不自行设计密码算法）。owner人工生成签名key，将固定public key指纹和owner身份在受保护验证配置中登记；独立核对指纹，不从待审核包或自动生成的JSON提取授权。明确key/grant有效期与撤销恢复流程。
3. 实现认证本地IPC的Authenticator+Registry服务及仅owner可用签核工具。用synthetic对象先做署名/验证、缓存篡改、旧备份撤销重放、断电/服务停止和重启时钟测试。真实项目保持NOT_REVIEWED，验收通过才启用。
4. owner逐项打开原owner-obligations.md，对O1核验两个连续span无损重组，对O2–O6核验单span、原文/归属/locator/上下文与禁止扩展。每项手工输入自己的verdict/reason，任何NOT_REVIEWED/REJECTED都不能seal；不能提供自动填APPROVED或通用全部批准快捷动作。
5. owner逐项确认SOURCE_USE、TASK_AND_DEPTH、OFFLINE_PLACEMENT、P_ONLY_CANDIDATE、FROZEN_CONSUMPTION条件、REVIEW_AUTHORITY、VALIDITY_AND_STORAGE。冻结对象/版本/digest必须与上述审核对象一致。D08商业验收另外进行，不继承本离线签核。
6. owner工具展示完整最终记录，交互确认后才签名；记录reviewer ID、实际UTC审核时间、最多24h expiry、独立review ID，注册不可变record/proof/frozen摘要。把不含私钥的receipt导入本缓存，启动受保护preflight读端。此处的signer/service尚未实现，没有可用“签署命令”；不得编辑模板后声称已签。
7. 撤销由owner工具追加带实际actor/time/reason的审计事件并改变服务当前状态；此前receipt不改写，下一次preflight立即拒绝。key/grant撤销同样拒绝。未来重新审核必须使用新ID、新revision与完整新签名，不能恢复旧批准。

身份/服务/ACL/trust root部署未完成前，真实签核NO-GO；本轮可验收结果仅为synthetic持久化闭环和安全设计。正式Draft writer始终关闭。
