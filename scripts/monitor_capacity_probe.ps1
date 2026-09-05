param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$PrivateRoot,
    [Parameter(Mandatory = $true)][string]$PublicRoot
)

# This monitor intentionally observes filenames and process metadata only.  It
# never reads bundle rows, prompts, API cache entries, or Test50 identities.
while ($true) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $seedDirs = @(Get-ChildItem -LiteralPath $PrivateRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^seed_\d+$' } | ForEach-Object { $_.Name })
    $completed = @(Get-ChildItem -LiteralPath $PublicRoot -Recurse -Filter result.json -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Directory.Name })
    $payload = [ordered]@{
        stage = 'capacity_probe'
        observed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        process_id = $ProcessId
        process_status = if ($null -eq $process) { 'finished' } else { 'running' }
        cpu_seconds = if ($null -eq $process) { $null } else { [math]::Round($process.CPU, 2) }
        private_seed_directories = @($seedDirs | Sort-Object)
        completed_public_seed_directories = @($completed | Sort-Object)
        test_access = 'not_observed; monitor has no bundle reader'
    }
    New-Item -ItemType Directory -Force -Path $PublicRoot | Out-Null
    $target = Join-Path $PublicRoot 'monitor.json'
    [System.IO.File]::WriteAllText(
        $target,
        (($payload | ConvertTo-Json -Depth 3) + "`n"),
        (New-Object System.Text.UTF8Encoding($false))
    )
    if ($null -eq $process) { break }
    Start-Sleep -Seconds 30
}
