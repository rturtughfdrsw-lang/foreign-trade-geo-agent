# Read-only deployment inventory. This is NOT a trust verifier or approval tool.
# No account/ACL/key/service/time changes; no private-key or credential reads.
[CmdletBinding()]
param(
    [string]$Repository = (Split-Path -Parent $PSScriptRoot),
    [string]$CandidateTrustRoot = 'C:\ProgramData\ForeignTradeEvidenceReview'
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Windows deployment inventory requires Windows.'
}

function Get-DirectoryFacts([string]$Path) {
    try {
        # Reject UNC, device/provider and mapped-network paths before directory I/O.
        if ($Path -notmatch '^[A-Za-z]:[\\/]') {
            return @{ Path=$Path; State='NON_LOCAL_PATH_REJECTED' }
        }
        $fullPath = [IO.Path]::GetFullPath($Path)
        $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($fullPath))
        if ($drive.DriveType -eq [IO.DriveType]::Network) {
            return @{ Path=$Path; State='NON_LOCAL_PATH_REJECTED' }
        }
        $fileSystem = @{ State='UNAVAILABLE'; Root=$drive.Name; DriveType=$drive.DriveType.ToString() }
        if ($drive.IsReady) {
            $fileSystem = @{ State='AVAILABLE'; Root=$drive.Name; DriveType=$drive.DriveType.ToString()
                             Format=$drive.DriveFormat }
        }
        $item = Get-Item -LiteralPath $Path -Force
        if (-not $item.PSIsContainer) { return @{ Path=$Path; State='NOT_DIRECTORY' } }
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            return @{ Path=$item.FullName; State='REPARSE_POINT_UNVERIFIED'; FileSystem=$fileSystem }
        }
        # Desktop's module auto-loading may be blocked by execution policy;
        # this .NET Framework read uses the same filesystem ACL without changing policy.
        $acl = if ($PSVersionTable.PSEdition -eq 'Desktop') {
            [IO.Directory]::GetAccessControl($item.FullName)
        } else { Get-Acl -LiteralPath $Path }
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]) | ForEach-Object {
            @{
                SID=$_.IdentityReference.Value; Type=$_.AccessControlType.ToString()
                Rights=$_.FileSystemRights.ToString(); Inherited=$_.IsInherited
                InheritanceFlags=$_.InheritanceFlags.ToString(); PropagationFlags=$_.PropagationFlags.ToString()
            }
        })
        return @{
            Path=$item.FullName; State='PRESENT'; OwnerSID=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
            InheritanceDisabled=$acl.AreAccessRulesProtected; Attributes=$item.Attributes.ToString(); Rules=$rules
            FileSystem=$fileSystem
        }
    } catch [System.Management.Automation.ItemNotFoundException] {
        return @{ Path=$Path; State='MISSING' }
    } catch { return @{ Path=$Path; State='UNAVAILABLE' } }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
try {
    $sid = $identity.User.Value
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $tokenAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $groups = @($identity.Groups | ForEach-Object { $_.Value })
    $localAccounts = @()
    $adminMembers = @()
    $directAdminMember = $null
    $accountQueryState = 'AVAILABLE'
    try {
        $localAccounts = @(Get-LocalUser | Select-Object Name,Enabled,@{n='SID';e={$_.SID.Value}})
        $adminName = ([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544').Translate(
            [Security.Principal.NTAccount]).Value -split '\\')[-1]
        $adminMembers = @(Get-LocalGroupMember -Group $adminName | ForEach-Object {
            @{ Name=$_.Name; SID=$_.SID.Value; ObjectClass=$_.ObjectClass }
        })
        $directAdminMember = (@($adminMembers | Where-Object SID -eq $sid).Count -gt 0)
    } catch { $accountQueryState = 'UNAVAILABLE' }
    $timeService = Get-Service -Name W32Time -ErrorAction SilentlyContinue
    # Capture only local w32tm status; querying does not resync/contact a server.
    $timeQueryState = 'UNAVAILABLE'
    $timeStatus = $null
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = Join-Path ([Environment]::GetFolderPath('System')) 'w32tm.exe'
    # Fixed literal arguments also work on Windows PowerShell 5.1/.NET Framework.
    $start.Arguments='/query /status'
    $start.UseShellExecute=$false; $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true; $start.RedirectStandardError=$true
    $start.StandardOutputEncoding=[Text.Encoding]::GetEncoding([Globalization.CultureInfo]::InstalledUICulture.TextInfo.OEMCodePage)
    $process = [Diagnostics.Process]::new(); $process.StartInfo=$start
    try {
        if ($process.Start()) {
            $stdout=$process.StandardOutput.ReadToEndAsync()
            $stderr=$process.StandardError.ReadToEndAsync()
            if ($process.WaitForExit(5000)) {
                $timeQueryState=if ($process.ExitCode -eq 0) { 'AVAILABLE' } else { 'QUERY_FAILED' }
                $timeStatus=$stdout.GetAwaiter().GetResult()
                $null=$stderr.GetAwaiter().GetResult()
            } else { $process.Kill(); $timeQueryState='TIMEOUT' }
        }
    } catch { $timeQueryState='UNAVAILABLE' } finally { $process.Dispose() }

    [ordered]@{
        SchemaVersion=1; Kind='READ_ONLY_INVENTORY_NOT_AUTHORIZATION'
        CollectedAtUTC=[DateTimeOffset]::UtcNow.ToString('o')
        ProductionGate='NO_GO_UNVERIFIED_TRUST_ROOT'
        Identity=@{
            Name=$identity.Name; SID=$sid; TokenIsAdministrator=$tokenAdmin
            TokenGroupSIDs=$groups; LocalAccountQueryState=$accountQueryState
            LocalAccounts=$localAccounts; Administrators=$adminMembers
            AccountIsDirectAdministratorMember=$directAdminMember
        }
        Runtime=@{
            PowerShell=$PSVersionTable.PSVersion.ToString(); Is64Bit=[Environment]::Is64BitProcess
            CngKeyTypeAvailable=([Security.Cryptography.CngKey] -ne $null)
            RsaCngTypeAvailable=([Security.Cryptography.RSACng] -ne $null)
            PssPaddingAvailable=([Security.Cryptography.RSASignaturePadding]::Pss -ne $null)
            PersistentKeysCreated=0
        }
        Directories=@(
            (Get-DirectoryFacts $Repository)
            (Get-DirectoryFacts (Split-Path -Parent $Repository))
            (Get-DirectoryFacts $CandidateTrustRoot)
            (Get-DirectoryFacts (Split-Path -Parent $CandidateTrustRoot))
        )
        Time=@{ ServiceStatus=if ($timeService) { $timeService.Status.ToString() } else { 'MISSING' }
                QueryState=$timeQueryState; LocalStatus=$timeStatus; TrustedTimeEstablished=$false }
        Limitations=@(
            'Directory ACL inventory is not an effective-access or adversarial isolation test.'
            'Intermediate reparse points and indirect/domain privileged groups need owner inspection.'
            'CNG type availability is not key custody, hardware attestation or identity enrollment.'
            'Local account existence does not authenticate an owner or enroll a reviewer.'
            'No signer, authenticated registry service, protected verifier or production approval is established.'
            'Inventory JSON and paths never confer authorization; production remains fail-closed.'
        )
    } | ConvertTo-Json -Depth 9
} finally { $identity.Dispose() }
