# Windows 单项目可信签核：owner 部署步骤与验收边界

本轮结论：**Windows 平台具备必要机制，但当前部署 NO-GO**。以下是 owner 本人执行的系统准备步骤，Agent 没有执行账户、ACL、生产 key、时间配置或服务变更。准备完成也不代表软件已经部署：生产 CNG authenticator、认证 registry host 和受保护 composition 尚不存在。真实 O1–O6 继续 NOT_REVIEWED，正式 Draft 不能执行。

## 1. 2026-10-08 历史实测环境与暂停点

下面的平台事实来自上一轮只读调查，不是当前部署验收。2026-10-09 续作的实际复核、测试和差异另见 `evidence-review-windows-resume-report-2026-10-09.md`；不得把历史账户/时钟状态当作实时授权。

- 当前 SID `S-1-5-21-3323324173-3147371586-2667959577-1001` 同时是仓库 owner 和 Agent 进程身份；是本地 Administrators 的直接成员，当前 UAC token 未提升。不能把“token 非管理员”当成独立受限身份。
- 仓库及其上级继承了 Authenticated Users Modify。不能从此处加载可信验证代码、签名配置、Python依赖或注册授权。只给私钥加 ACL 而继续运行可修改的验证代码仍不成立。
- E: 是 NTFS。账户/ACL 管理工具可用；PowerShell 7.6.5、64 位、CNG/RSACng/RSA-PSS 类型可用。这是机制可用性，不是实际签名/key custody/hardware attestation 验证。
- `C:\ProgramData\ForeignTradeEvidenceReview` 不存在。没有已登记独立 reviewer/Agent SID、固定公钥、受保护权限/撤销源或服务。
- W32Time Running，但当前状态为 Leap 3 未同步、stratum 0、Local CMOS Clock、没有成功同步时间。不修改时钟或联系时间服务器；生产有效期验核 NO-GO。
- 现有 CodexSandboxOffline/Online 是工具账户，不是 owner 审核身份；不尝试登录、取凭据或擅自赋予业务权限。

只读复核命令：

```powershell
& 'E:\Codex程序\foreign-trade-geo-agent\scripts\inspect_evidence_review_windows.ps1'
```

脚本只列事实并始终返回 `NO_GO_UNVERIFIED_TRUST_ROOT`；不能用其 JSON、候选目录参数或环境变量打开 Gate。ACL 列表不是 effective-access 测试；缺权限/缺目录时只报告不可用，绝不批准。

脚本兼容 Windows PowerShell 5.1 与 PowerShell 7，仅查询本地账户、ACL、卷类型和 `w32tm /query /status`。不存在、不可读、非目录、reparse point 分别报告；账户查询失败时管理员直接成员状态是 `null`，不能解释为受限用户。UNC/网络盘参数拒绝，不查询远端。中间路径的 reparse points、间接特权组及有效权限仍须 owner 检查。输出含本机路径、账户名/SID和本地时间源等管理信息，只在本机保存；不含密码、私钥、token或原始异常。

本机 5.1 的执行策略会阻止 `-File`，可能也阻止模块自动加载。不要修改执行策略或加入 `-ExecutionPolicy Bypass`。owner 审阅源码且本地策略允许交互执行时，可用以下只读调用；若组织策略也禁止脚本块执行，应停止并由系统管理员走审查/签名流程，不绕过 AppLocker/WDAC/GPO。

```powershell
$inventoryPath = 'E:\Codex程序\foreign-trade-geo-agent\scripts\inspect_evidence_review_windows.ps1'
& ([scriptblock]::Create([IO.File]::ReadAllText($inventoryPath))) `
    -Repository 'E:\Codex程序\foreign-trade-geo-agent' `
    -CandidateTrustRoot 'C:\ProgramData\ForeignTradeEvidenceReview'
```

## 2. 部署模型选择

采用**两个专用标准用户**：`FTEReviewOwner`（人类审核者及 registry host），`FTEAgent`（Agent 验证客户端）。现有管理员账户只负责引导、安装可信代码和固定验证锚；以后不能用此账户运行 Agent。一个人仍是唯一业务管理员，不建设多租户权限系统。

第一版 registry host 可由 owner 在专用审核账户交互启动，在该会话中提供本地命名管道；host退出或不可用时拒绝。锁屏通常不会自动停止进程或命名管道，不能把锁屏当成撤销。无需先安装 Windows 服务或保存服务密码。如果以后需要自动服务，另行由 owner 审核服务身份、Log on as a service 和恢复策略；不能用 SYSTEM 为方便而扩大权限。

方案比较：同账户 DPAPI/HMAC 不提供审核隔离，拒绝采用；独立账户 + native CNG 非对称签名是本机最小方案；独立设备/硬件 key 更适合抵御同机管理员或磁盘回滚，但增加部署成本。此处的本机方案明确不承诺抵御管理员/SYSTEM。

## 3. owner 系统准备：提升的管理员 PowerShell 7

**风险：创建新本地账户和受保护目录改变系统状态。owner 先备份、确认名称和路径，再亲自执行。不要把下面内容作为 Agent 获得修改系统权限的授权。**账户名是新部署建议，不是已创建事实；名称或目录已存在时停止，人工检查，不删除、接管或覆盖。

```powershell
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw '系统准备步骤要求 64 位 PowerShell 7；不要在 Windows PowerShell 5.1 中执行。'
}
if (-not [Environment]::Is64BitProcess) { throw '要求 64 位 PowerShell。' }
$reviewName = 'FTEReviewOwner'
$agentName = 'FTEAgent'
$reviewRoot = 'C:\ProgramData\ForeignTradeEvidenceReview'
$bootstrapIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$bootstrapPrincipal = [Security.Principal.WindowsPrincipal]::new($bootstrapIdentity)
if (-not $bootstrapPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请由 owner 在提升的管理员 PowerShell 中执行。'
}
if ((Get-LocalUser -Name $reviewName -ErrorAction SilentlyContinue) -or
    (Get-LocalUser -Name $agentName -ErrorAction SilentlyContinue) -or
    (Test-Path -LiteralPath $reviewRoot)) { throw '已有名称或路径；停止并人工检查。' }

# 两次分别输入独立强密码；不使用明文参数、/savecred、日志或环境变量。
$reviewPassword = Read-Host '专用审核账户密码' -AsSecureString
$agentPassword = Read-Host '专用 Agent 账户密码' -AsSecureString
$reviewUser = New-LocalUser -Name $reviewName -Password $reviewPassword -Description 'Human evidence reviewer'
$agentUser = New-LocalUser -Name $agentName -Password $agentPassword -Description 'Restricted evidence verification client'
$usersName = ([Security.Principal.SecurityIdentifier]::new('S-1-5-32-545').Translate(
    [Security.Principal.NTAccount]).Value -split '\\')[-1]
$existingUserSids = @(Get-LocalGroupMember -Group $usersName | ForEach-Object { $_.SID.Value })
foreach ($standardUser in @($reviewUser,$agentUser)) {
    if ($standardUser.SID.Value -notin $existingUserSids) {
        Add-LocalGroupMember -Group $usersName -Member $standardUser -ErrorAction Stop
    }
}
# 不加 Administrators、Backup Operators 等特权组；实际登录后再验证 token/组/privileges。
Remove-Variable reviewPassword,agentPassword
$reviewSid = $reviewUser.SID.Value
$agentSid = $agentUser.SID.Value
if ($reviewSid -eq $agentSid -or $reviewSid -eq $bootstrapIdentity.User.Value -or
    $agentSid -eq $bootstrapIdentity.User.Value) { throw '身份未隔离。' }

# 仅新目录。不要对仓库、用户 profile 或任何现有目录递归重写 ACL。
function New-ReviewDirectory([string]$Path, [string]$WriterSID) {
    if (Test-Path -LiteralPath $Path) { throw '路径已存在；停止。' }
    # 不用-Force；并发出现或创建失败必须终止，不能接着给已有目录Set-Acl。
    $createdDirectory = New-Item -ItemType Directory -Path $Path -ErrorAction Stop
    if (-not $createdDirectory.PSIsContainer -or
        ($createdDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw '未确认新建普通目录；停止。'
    }
    $security = [Security.AccessControl.DirectorySecurity]::new()
    $security.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    $security.SetAccessRuleProtection($true,$false)
    $inherit = [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
    $propagate = [Security.AccessControl.PropagationFlags]::None
    $allow = [Security.AccessControl.AccessControlType]::Allow
    foreach ($adminSid in @('S-1-5-18','S-1-5-32-544')) {
        $security.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($adminSid),
            [Security.AccessControl.FileSystemRights]::FullControl,$inherit,$propagate,$allow))
    }
    foreach ($readerSid in @($reviewSid,$agentSid)) {
        if ($WriterSID -and $readerSid -ne $WriterSID) { continue }
        $rights = if ($WriterSID -eq $readerSid) { [Security.AccessControl.FileSystemRights]::Modify }
                  else { [Security.AccessControl.FileSystemRights]::ReadAndExecute }
        $security.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($readerSid),$rights,$inherit,$propagate,$allow))
    }
    Set-Acl -LiteralPath $Path -AclObject $security -ErrorAction Stop
    if (-not (Get-Acl -LiteralPath $Path).AreAccessRulesProtected) { throw 'ACL继承未禁用。' }
}
New-ReviewDirectory $reviewRoot ''
New-ReviewDirectory (Join-Path $reviewRoot 'Verifier') ''
New-ReviewDirectory (Join-Path $reviewRoot 'Anchor') ''
New-ReviewDirectory (Join-Path $reviewRoot 'AuthorityState') $reviewSid
```

执行只到目录准备。失败后不要自动删除/补跑整段：部分创建状态先由 owner 核验。创建目录到设置 ACL 有短暂引导窗口；引导期间停止所有客户端、不能放密钥/授权，验收前确认没有意外子对象。新目录的成功创建与Set-Acl之间不是对抗并发进程的原子操作；本机不受信任进程必须退出/隔离，否则不要执行此引导。管理员/SYSTEM在威胁边界之外。后续每个代码/anchor/state 子对象必须核验继承与 owner；不允许 reparse points、额外 Users/Authenticated Users/Everyone 写权限或 Agent WriteDac/WriteOwner/DeleteChild，包括父目录的删除/替换权限。账户密码政策、交互登录限制由 owner 决定，不在此自动修改。

| 对象 | Administrators/SYSTEM | 审核账户 | Agent |
| --- | --- | --- | --- |
| Verifier：受保护程序、Python/.NET runtime、依赖 | 安装/维护 | RX | RX |
| Anchor：固定公钥、SID及scope登记、协议版本 | 安装/更新 | RX | RX |
| AuthorityState：grant/key lifecycle、撤销、audit、revision/time | 维护/恢复 | Modify（受审核host控制） | 无读取/写入权限 |
| 审核账户 current-user CNG 私钥 | Windows特权能力仍存在 | Sign；禁止export | 不可打开/签署/读取文件 |
| 原仓库/receipt cache/inbox | 不作为信任根 | 不信任其权限字段 | 可修改；每次完整验核 |

## 4. owner 登录专用审核账户：key 与锚准备

必须以实际 OS 登录验证 `whoami /user` 得到新审核 SID，`whoami /groups`/`whoami /priv` 无管理员和更改系统时间等能力。用 Windows 切换用户，或 `runas /user:<本机名>\FTEReviewOwner pwsh.exe` 交互输入密码；不得 `/savecred`。不要在当前 Agent 进程中模拟 reviewer 字符串。

拟用固定协议 **RSA-3072 / SHA-256 / PSS**，Windows Microsoft Software Key Storage Provider 的 current-user named CNG key、`CngExportPolicies.None`、仅 Signing。下面是 owner 手工生成生产 key 的步骤说明，本轮没有执行，尚没有生产 authenticator 消费这些 key。**当前停止在账户/目录准备：生产 key 步骤须等 host/client 和专用 TEST 身份验收完成后再由 owner 执行。**此段仅适用 64 位 PowerShell 7（SPKI、HashData、ToHexString API 不适用于 5.1），不提供生产签核。

```powershell
# 仅实际专用审核账户会话。替换为上一步人工核对的完整SID，不从待审核包获取。
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7 -or
    -not [Environment]::Is64BitProcess) { throw 'key 准备要求 64 位 PowerShell 7。' }
$expectedReviewerSid = '<owner人工登记的新审核SID>'
if ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne $expectedReviewerSid) { throw '错误身份。' }
$keyName = 'FTE-Evidence-Review-v1'
$keyProvider = [Security.Cryptography.CngProvider]::MicrosoftSoftwareKeyStorageProvider
if ([Security.Cryptography.CngKey]::Exists($keyName,$keyProvider)) { throw 'key已存在，禁止覆盖。' }
$keyParameters = [Security.Cryptography.CngKeyCreationParameters]::new()
$keyParameters.Provider = $keyProvider
$keyParameters.ExportPolicy = [Security.Cryptography.CngExportPolicies]::None
$keyParameters.KeyUsage = [Security.Cryptography.CngKeyUsages]::Signing
$keyParameters.Parameters.Add([Security.Cryptography.CngProperty]::new(
    'Length',[BitConverter]::GetBytes(3072),[Security.Cryptography.CngPropertyOptions]::None))
$reviewKey = [Security.Cryptography.CngKey]::Create([Security.Cryptography.CngAlgorithm]::Rsa,$keyName,$keyParameters)
$publicRsa = [Security.Cryptography.RSACng]::new($reviewKey)
try {
    $spki = $publicRsa.ExportSubjectPublicKeyInfo() # 仅public；不导出私钥、不签署O1–O6。
    $publicFingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($spki)).ToLowerInvariant()
    # 公钥只在owner确认的导出位置新建，禁止覆盖；由管理员独立核对fingerprint后登记锚。
    $publicExport = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'fte-review-public-v1.spki'
    $stream = [IO.File]::Open($publicExport,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.Write($spki) } finally { $stream.Dispose() }
    $publicFingerprint
} finally { $publicRsa.Dispose(); $reviewKey.Dispose() }
```

软件 key 非导出不意味着同账户代码不能调用 SignData；隔离依赖实际 OS SID、private key store ACL 和受保护程序。owner 必须在新 Agent 会话验证不能 `CngKey.Open` 此 key、不能取得私钥/读取对应存储；审核账户私钥导出必须失败。无需重写整个 Crypto/Keys 目录 ACL。另用同规则创建 registry-response key，不与 review 签名共用；两把公钥由管理员独立核对并固定在 Anchor。上述 key 步骤若失败留下部分状态，由 owner 人工处理，不能自动重生或覆盖。

固定锚登记包括 reviewer SID（可直接用符合 bounded_id 的 SID 作 reviewer_id）、Agent SID、单项目ID、具体task/purpose允许集、grant有效期、两把SPKI指纹、协议与key版本。锚更新属管理员操作，不能接纳 caller/JSON/env提供的公钥。保护所有父目录和验证程序/依赖加载路径；不依赖可修改仓库代码进行实际授权。

受保护安装须包含 host、client、composition、解释器及全部依赖；不能复制指回本仓库的 editable venv/`.pth` 链接。Python 客户端使用固定绝对解释器路径和隔离加载（`-I`），核对实际 `sys.path`/模块来源，不能从当前目录、用户 site、`PYTHONPATH`或可写插件路径加载验签代码；`-I` 本身不能保护可写的解释器或依赖。此验收当前未完成。

## 5. 尚待实现的最小 host 与客户端契约

这部分是可实施规格，**没有可用部署/启动命令**。不要把目录/key准备等同于生产签核能力。

复用 `EvidenceReviewAuthenticator` 和 `CurrentEvidenceReviewRegistry`，不修改既有字段或历史 codec。review proof 是固定3072位key产生的384字节PSS signature，签名消息为固定domain prefix + 原始record bytes；协议不接受任意algorithm/keyurl。另固定registry domain prefix，阻止签名跨用途复用。完整冻结目标/任务/Plan/证据版本/obligation-span/DraftInput绑定继续由原loader/preflight验核。

- 命名管道只暴露 query-current 给登记 Agent SID；server 对 client 做 Windows token impersonation SID校验，客户端验证server身份，并验固定registry公钥的challenge-bound signed response。核对server SID需要受审查的Windows API实现；仅凭pipe名称/nonce回显不算认证。
- grant/key current state 和 review registration 由保护目录下的host读取；签署/登记/撤销入口仅真实reviewer SID、人工交互确认，不给Agent review signing RPC。Registry key不能代签review record；禁止从query请求注册或复活批准。
- 每次查询返回当前身份权限/key lifecycle及record/proof/frozen摘要、全部task/版本/purpose、有效期、status/revocation、递增revision、serverUTC、32字节challenge；客户端重验签名、exact字段、5秒时效及所有绑定。签名有效的旧响应不能替代当前状态。
- 注册和append-only audit事件在同一事务内持久化，包含actor SID、实际time、action、reason、old/new revision与对象摘要。crash后事件和当前状态不可分叉；ID不复用、撤销不复活；替代必须新ID。把 SQLite trigger/hashchain 当防本机管理员回滚手段是不成立的。
- host保留last-seen UTC、拒绝回拨；clock不可信、注册源不可用、权限不明、撤销/过期均拒绝。每次准入重新查询，不缓存批准。Verifier composition固定生产ports并拒绝synthetic；正式Draft writer仍不接入。

## 6. owner 验收：必须真实跨账户，不能只看测试GREEN

在临时 TEST 专用账户/key/root 中先按同一权限模型验收，不能给 O1–O6 注册 test批准。尚未创建这种测试身份，因此以下 OS验收本轮未执行。

1. 独立审核SID与AgentSID实测不同且非管理员；Agent可以读取Verifier程序和Anchor公钥，但不能修改它们或其父目录；不能读取或修改AuthorityState/私钥，不能用审核private key签署。不能只检查key export失败。
2. 用 unrelated synthetic 六义务七span；专用test reviewer逐项做test决策并PSS签署，测试Agent仅public key验证；再进持久化preflight得到SYNTHETIC_GREEN。synthetic标记来自固定测试环境登记，不由record宣称。
3. Agent调用署名/注册/撤销入口应被OS身份拒绝；另一账户/冒用SID、假公钥、假proof、修改record/frozen/digest、跨task/Plan/evidence/purpose、EXPLAIN复用都拒绝。全部writer=0。
4. 测试key/grant/review分别撤销、过期、恢复旧receipt、重放旧response、服务退出、断电重启；每次重新查询的结果必须拒绝。重启audit/current revision一致；回拨时间应拒绝。
5. 时钟由owner核对实际UTC、W32Time最近成功同步及来源。服务 Running、非零 stratum、普通未认证 NTP 或一次 `resync` 成功都不单独证明可信时间：须记录受信任域时间链/认证来源或独立核准的校准依据、最大漂移和同步失效期限，过期/不明即拒绝。标准审核/Agent token 不得有 `SeSystemtimePrivilege`。host 持久化 last-seen UTC，验证回拨、停机后陈旧时钟及重启恢复；不把本地持久化时间当作防全盘回滚根。若需配置时间源，属于系统/网络操作，owner另行执行；本轮没有自动resync。测试全部通过才讨论生产部署；仍不批准真实材料。

管理员/SYSTEM、同审核账户恶意代码、受保护程序供应链和全盘/authority-state回滚在本机模型外。要抵御这些威胁需独立设备/硬件、外部单调日志或其它额外可信根。明确接受边界后才能部署，不把服务自己的revision或本地hashchain说成防全盘回滚。

## 7. 失败恢复与停止规则

- 账户/目录准备部分失败：退出部署流程，保留实际创建清单和 SID/ACL 本地记录；owner 在独立会话核验已建对象及父目录。不要重跑整段、接管已有名称、自动放宽 ACL 或自动删除对象。无密钥/授权前可由 owner 决定修复或废弃。
- key 生成或公钥导出部分失败：现有 named key 不覆盖、不自动轮换，owner 核对是否已生成、是否有正确 fingerprint；不明确即停用签核，后续由 owner 登记新版本并撤销旧版本。非导出私钥无法靠普通文件备份恢复；丢失后换 key/锚并重新审核，不复活旧批准。
- host/clock/锚不可用或疑似篡改：停止准入，保留已有 receipt 不改写，不启用 fallback authority。从核准安装介质重建受保护程序并复核锚；恢复状态前核对独立备份/审计检查点、撤销集合、revision 和 last-seen UTC。没有足够依据证明状态未回滚时，恢复后仍 NO-GO，由 owner 建立新信任版本并重新审核。
- 重启/恢复验收先用 TEST 对象证明旧撤销不能复活、旧 response/receipt 不能重放、服务离线拒绝，全部 writer=0。恢复业务不等于批准 O1–O6；正式人工审核和商业输出验收各自独立。

## 8. Git安全检查点（2026-10-08 历史记录）

开始时实际224项：79 modified、144 untracked、1 deleted（`tests/test_history_migration_v1_to_v2.py`）。上轮最初216项是79 modified +136 untracked +1 deleted；上轮8个新增文件解释了差额。没有 staged项；不要恢复删除或清理未跟踪review packages。

本轮已保存355个现存非忽略文件字节摘要、完整status分类、branch/HEAD到忽略目录 `.data/evidence-review-windows-feasibility-20261008/baseline.json`，末尾重新逐字节比较。摘要不是可恢复备份。系统部署前由owner将已人工检查无secret的355文件、tracked binary diff及完整status清单复制到独立离线恢复位置，记录原删除清单和hash manifest，实际演练恢复到另一个目录。`.env`和私钥不得进入Git/报告或普通代码归档；若需备份凭据，owner另行加密保管。此处仅提出备份方案，Agent没有生成可能含secret的完整patch/archive，没有stage/reset/stash/commit/push。

建议先完成跨账户/ACL准备的人工检查点，再交付“准备已完成”的实际SID、ACL验收和clock状态（不含密码/私钥）。后续开发才可在这些条件上实现并测试production host/adapter；现在真实签核与商业Draft仍NO-GO。
