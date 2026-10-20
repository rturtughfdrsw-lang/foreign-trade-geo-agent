param(
    [ValidateRange(1024, 65535)][int]$Port = 8003,
    [switch]$Stop,
    [switch]$NoBrowser
)
# Compatibility entry on the Commercial branch stays within this working tree.
$ErrorActionPreference = 'Stop'
$canonical = Join-Path $PSScriptRoot 'start_commercial.ps1'
if (-not (Test-Path -LiteralPath $canonical -PathType Leaf)) {
    throw 'Commercial Dev launcher is missing; no other worktree was started.'
}
& $canonical -Port $Port -Stop:$Stop -NoBrowser:$NoBrowser
exit $LASTEXITCODE
