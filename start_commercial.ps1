param(
    [ValidateRange(1024, 65535)][int]$Port = 8003,
    [switch]$Stop,
    [switch]$NoBrowser,
    [switch]$InspectOnly
)

$ErrorActionPreference = 'Stop'

function Test-ProcessIdentity($Current, $Expected) {
    if ($null -eq $Current -or $null -eq $Expected) { return $false }
    foreach ($field in @('ProcessId', 'ParentProcessId', 'CreationDate', 'ExecutablePath', 'CommandLine')) {
        if ($null -eq $Current.$field -or $null -eq $Expected.$field -or
            [string]$Current.$field -ceq '' -or [string]$Current.$field -cne [string]$Expected.$field) { return $false }
    }
    return $true
}

function Test-ServiceIdentity($Status, $Record) {
    return ($null -ne $Status -and $null -ne $Record -and
        $Status.database -ceq $Record.database -and $Status.project -ceq $Record.project -and
        $Status.source -ceq $Record.source -and -not [string]::IsNullOrEmpty($Record.source) -and
        $Status.instance -ceq $Record.instance -and $Status.pid -eq $Record.server.ProcessId -and
        $Status.live_model_enabled -is [bool] -and $Status.live_model_enabled -eq $Record.live_model_enabled -and
        $Status.paid_confirmation_required -is [bool] -and $Status.paid_confirmation_required -eq $Record.paid_confirmation_required -and
        $Status.profile -ceq $Record.profile -and -not [string]::IsNullOrEmpty($Record.profile) -and
        -not [string]::IsNullOrEmpty($Record.instance))
}

function Test-CreationTime([DateTime]$ActualTime, [string]$RecordedString) {
    $recordedTime = [DateTime]::Parse($RecordedString, [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
    $actualTicks = $ActualTime.ToUniversalTime().Ticks
    return (($actualTicks - ($actualTicks % 10)) -eq $recordedTime.Ticks)
}

$projectDirectory = $PSScriptRoot
$python = 'E:\Codex程序\foreign-trade-geo-agent\.venv\Scripts\python.exe'
$database = Join-Path $projectDirectory '.data\seo-mvp\candidate\history.sqlite3'
$serverScript = Join-Path $projectDirectory 'scripts\desktop_commercial.py'
$stateDirectory = Join-Path $projectDirectory '.data\commercial-desktop'
$statePath = Join-Path $stateDirectory "$Port.json"
$url = "http://127.0.0.1:$Port/"

function Get-ProcessRecord([int]$ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    return [pscustomobject]@{
        ProcessId = [int]$process.ProcessId
        ParentProcessId = [int]$process.ParentProcessId
        CreationDate = $process.CreationDate.ToUniversalTime().ToString('o')
        ExecutablePath = $process.ExecutablePath
        CommandLine = $process.CommandLine
    }
}

function Get-MvpListener {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Get-ServiceStatus {
    $response = $null
    try {
        $request = [Net.WebRequest]::Create($url + '_desktop/status')
        $request.Proxy = $null
        $request.Timeout = 2000
        $request.ReadWriteTimeout = 2000
        $request.AllowAutoRedirect = $false
        $response = $request.GetResponse()
        $stream = $response.GetResponseStream()
        $buffer = New-Object byte[] 8193
        $count = 0
        while (($read = $stream.Read($buffer, $count, $buffer.Length - $count)) -gt 0) {
            $count += $read
            if ($count -gt 8192) { throw 'Status response exceeded budget.' }
        }
        $json = [Text.UTF8Encoding]::new($false, $true).GetString($buffer, 0, $count)
        return ($json | ConvertFrom-Json)
    } catch { return $null }
    finally { if ($null -ne $response) { $response.Close() } }
}

function Stop-VerifiedProcess($Expected) {
    if (-not (Test-ProcessIdentity (Get-ProcessRecord $Expected.ProcessId) $Expected)) {
        throw 'Process identity changed; no termination was attempted.'
    }
    # Bind termination to an opened process handle and its creation time, so a
    # PID reused between validation and termination cannot select a new process.
    $handle = Get-Process -Id $Expected.ProcessId -ErrorAction Stop
    $null = $handle.Handle
    # WMI truncates FILETIME to microseconds; Get-Process retains 100 ns ticks.
    if (-not (Test-CreationTime $handle.StartTime $Expected.CreationDate)) {
        throw 'Process creation time changed; nothing was stopped.'
    }
    $handle.Kill()
    $handle.WaitForExit(5000) | Out-Null
}

if ($InspectOnly) { return }

$mutex = [Threading.Mutex]::new($false, "Local\SEOAgent-Commercial-$Port")
$locked = $false
$ownedRoot = $null
$ownedChild = $null
try {
    try { $locked = $mutex.WaitOne(30000) }
    catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Another launch is in progress.' }
    $listener = Get-MvpListener
    $record = $null
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        try { $record = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { throw 'Invalid launcher ownership record; nothing was changed.' }
    }
    if ($null -ne $listener) {
        $status = Get-ServiceStatus
        if ($null -eq $record -or $record.schema -ne 1 -or
            $record.project -cne $projectDirectory -or $record.database -cne $database -or
            $listener.OwningProcess -ne $record.server.ProcessId -or
            -not (Test-ServiceIdentity $status $record) -or
            -not (Test-ProcessIdentity (Get-ProcessRecord $record.root.ProcessId) $record.root) -or
            -not (Test-ProcessIdentity (Get-ProcessRecord $record.server.ProcessId) $record.server)) {
            throw "Port $Port belongs to a service without matching ownership. Nothing was stopped or replaced."
        }
        if ($Stop) {
            Stop-VerifiedProcess $record.server
            if ($record.root.ProcessId -ne $record.server.ProcessId -and
                (Test-ProcessIdentity (Get-ProcessRecord $record.root.ProcessId) $record.root)) {
                Stop-VerifiedProcess $record.root
            }
            Write-Host "V1 stopped: $url"
        } else {
            Write-Host "V1 already running: $url"
            if (-not $NoBrowser) { Start-Process -FilePath $url }
        }
        exit 0
    }
    if ($Stop) { Write-Host 'No listener; nothing was stopped.'; exit 0 }
    foreach ($path in @($python, $database, $serverScript)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required existing file missing: $path" }
    }
    & $python -I -B $serverScript --database $database --check-database
    if ($LASTEXITCODE -ne 0) { throw 'V1 source, Python dependencies or existing database could not be verified.' }
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    $temporaryDirectory = Join-Path $stateDirectory 'tmp'
    New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
    $env:TEMP = $temporaryDirectory
    $env:TMP = $temporaryDirectory
    $instance = [guid]::NewGuid().ToString()
    $stdout = Join-Path $stateDirectory "$Port.stdout.log"
    $stderr = Join-Path $stateDirectory "$Port.stderr.log"
    $arguments = @('-I', '-B', ('"' + $serverScript + '"'), '--database', ('"' + $database + '"'),
        '--port', "$Port", '--instance', $instance)
    $spawned = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectDirectory `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $ownedRoot = Get-ProcessRecord $spawned.Id
    if ($null -eq $ownedRoot) { throw "V1 exited; inspect $stderr" }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $ready = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not (Test-ProcessIdentity (Get-ProcessRecord $spawned.Id) $ownedRoot)) { throw "V1 exited; inspect $stderr" }
        $status = Get-ServiceStatus
        if ($null -ne $status -and $status.instance -ceq $instance) {
            $candidate = Get-ProcessRecord $status.pid
            $listener = Get-MvpListener
            if ($null -eq $candidate -or $null -eq $listener -or $listener.OwningProcess -ne $candidate.ProcessId -or
                ($candidate.ProcessId -ne $spawned.Id -and $candidate.ParentProcessId -ne $spawned.Id) -or
                -not $candidate.CommandLine.Contains($instance) -or -not $candidate.CommandLine.Contains($serverScript)) {
                throw 'The serving process is not the child created by this launcher.'
            }
            $ownedChild = $candidate
            $record = [pscustomobject]@{schema=1; project=$projectDirectory; database=$database;
                source=(Join-Path $projectDirectory 'src\foreign_trade_geo_agent\web\commercial_inspector.py');
                profile='commercial'; live_model_enabled=$false; paid_confirmation_required=$false;
                instance=$instance; root=$ownedRoot; server=$candidate}
            if (-not (Test-ServiceIdentity $status $record)) { throw 'V1 source, database or model permission mismatch.' }
            $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $ready) { throw "V1 did not become ready; inspect $stderr" }
    Write-Host "V1 started: $url"
    Write-Host "Database: $database"
    Write-Host 'Workflow history is read only; local developer feedback is stored separately. Model execution and publication are unavailable.'
    Write-Host 'To stop only this entry: run start_commercial.ps1 -Stop.'
    if (-not $NoBrowser) { Start-Process -FilePath $url }
} catch {
    # Failed launch cleanup is restricted to the exact new process identities.
    if ($null -ne $ownedRoot -and (Test-ProcessIdentity (Get-ProcessRecord $ownedRoot.ProcessId) $ownedRoot)) {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($ownedRoot.ProcessId)"
        foreach ($child in $children) {
            if ($child.CommandLine -and $child.CommandLine.Contains($instance) -and $child.CommandLine.Contains($serverScript)) {
                Stop-VerifiedProcess (Get-ProcessRecord $child.ProcessId)
            }
        }
        if (Test-ProcessIdentity (Get-ProcessRecord $ownedRoot.ProcessId) $ownedRoot) { Stop-VerifiedProcess $ownedRoot }
    }
    Write-Host "V1 launch error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
