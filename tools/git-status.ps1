[CmdletBinding()]
param(
    [switch]$Fetch
)

$ErrorActionPreference = 'Stop'

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $output = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }
    return $output
}

$repoRoot = (Invoke-Git rev-parse --show-toplevel | Select-Object -First 1).Trim()
Set-Location -LiteralPath $repoRoot

if ($Fetch) {
    Write-Host 'Fetching remote references...'
    Invoke-Git fetch --prune | Out-Host
}

$branch = (Invoke-Git branch --show-current | Select-Object -First 1).Trim()
if (-not $branch) {
    $branch = '(detached HEAD)'
}

$head = (Invoke-Git log -1 --format='%h %s' | Select-Object -First 1).Trim()
$upstream = & git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>$null

Write-Host ''
Write-Host 'Repository:' $repoRoot
Write-Host 'Branch:    ' $branch
Write-Host 'HEAD:      ' $head

if ($LASTEXITCODE -eq 0 -and $upstream) {
    $upstream = ($upstream | Select-Object -First 1).Trim()
    $counts = (Invoke-Git rev-list --left-right --count "HEAD...$upstream" | Select-Object -First 1) -split '\s+'
    Write-Host 'Upstream:  ' $upstream
    Write-Host 'Ahead:     ' $counts[0]
    Write-Host 'Behind:    ' $counts[1]
}
else {
    Write-Host 'Upstream:   (not configured)'
}

Write-Host ''
Write-Host 'Working tree:'
$status = Invoke-Git status --short
if ($status) {
    $status | Out-Host
}
else {
    Write-Host '  clean'
}

Write-Host ''
Write-Host 'Recent commits:'
Invoke-Git log --oneline --decorate --graph -10 | Out-Host
