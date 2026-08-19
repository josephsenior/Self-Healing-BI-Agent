param(
    [Parameter(Mandatory = $true)]
    [long]$OpenedAfterUnixMs,

    [Parameter(Mandatory = $true)]
    [string]$VerificationTable,

    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$openedAfter = [DateTimeOffset]::FromUnixTimeMilliseconds($OpenedAfterUnixMs).LocalDateTime
$port = $null
$serverPid = $null

function Find-ListeningPort([int]$processId) {
    foreach ($line in (& netstat.exe -ano -p TCP)) {
        if ($line -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$') {
            if ([int]$matches[2] -eq $processId) {
                return [int]$matches[1]
            }
        }
    }
    return $null
}

while ([DateTime]::UtcNow -lt $deadline -and -not $port) {
    $servers = @(Get-Process msmdsrv -ErrorAction SilentlyContinue |
        Sort-Object StartTime -Descending)
    $recent = @($servers | Where-Object { $_.StartTime -ge $openedAfter.AddSeconds(-5) })
    $candidates = if ($recent.Count -gt 0) { $recent } else { $servers | Select-Object -First 1 }
    foreach ($server in $candidates) {
        $candidatePort = Find-ListeningPort $server.Id
        if ($candidatePort) {
            $port = $candidatePort
            $serverPid = $server.Id
            break
        }
    }
    if (-not $port) { Start-Sleep -Milliseconds 500 }
}

if (-not $port) {
    throw "Power BI's local Analysis Services endpoint did not become available."
}

$adomdCandidates = @(
    "$env:ProgramFiles\Microsoft Office\root\Office16\ADDINS\Microsoft Power Query for Excel Integrated\bin\Microsoft.PowerBI.AdomdClient.dll",
    "$env:ProgramFiles\Microsoft Office\root\vfs\ProgramFilesCommonX64\Microsoft Shared\Office16\DataModel\Microsoft.Excel.AdomdClient.dll"
)
$adomdPath = $adomdCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $adomdPath) {
    throw 'No installed Microsoft ADOMD client was found; cannot process the local model.'
}

[void][Reflection.Assembly]::LoadFrom($adomdPath)
$connection = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection "Data Source=localhost:$port;"
try {
    $catalog = $null
    $catalogDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $catalogDeadline -and -not $catalog) {
        try {
            if ($connection.State -ne [System.Data.ConnectionState]::Open) {
                $connection.Open()
            }
            $catalogs = $connection.GetSchemaDataSet('DBSCHEMA_CATALOGS', $null)
            if ($catalogs.Tables.Count -gt 0 -and $catalogs.Tables[0].Rows.Count -gt 0) {
                $catalog = [string]$catalogs.Tables[0].Rows[0].CATALOG_NAME
            }
        }
        catch {
            $connection.Close()
        }
        if (-not $catalog) { Start-Sleep -Milliseconds 500 }
    }
    if (-not $catalog) {
        throw 'The local Power BI model catalog did not become available.'
    }

    $refreshDeadline = [DateTime]::UtcNow.AddSeconds(30)
    $refreshed = $false
    while ([DateTime]::UtcNow -lt $refreshDeadline -and -not $refreshed) {
        try {
            $refresh = $connection.CreateCommand()
            $refresh.CommandText = (@{
                refresh = @{
                    type = 'full'
                    objects = @(@{ database = $catalog })
                }
            } | ConvertTo-Json -Depth 5 -Compress)
            [void]$refresh.ExecuteNonQuery()
            $refreshed = $true
        }
        catch {
            Start-Sleep -Milliseconds 1000
        }
    }

    $verifyDeadline = [DateTime]::UtcNow.AddSeconds(30)
    $rowCount = $null
    $escapedTable = $VerificationTable.Replace("'", "''")
    while ([DateTime]::UtcNow -lt $verifyDeadline -and $null -eq $rowCount) {
        try {
            $verify = $connection.CreateCommand()
            $verify.CommandText = "EVALUATE ROW(`"Rows`", COUNTROWS('$escapedTable'))"
            $reader = $verify.ExecuteReader()
            try {
                if ($reader.Read() -and -not $reader.IsDBNull(0)) {
                    $rowCount = [long]$reader.GetValue(0)
                }
            }
            finally {
                $reader.Close()
            }
        }
        catch {
            Start-Sleep -Milliseconds 1000
        }
    }

    if ($null -eq $rowCount) {
        throw "The '$VerificationTable' table remained unprocessed after refresh."
    }

    [pscustomobject]@{
        processed = $true
        server_pid = $serverPid
        port = $port
        catalog = $catalog
        verification_table = $VerificationTable
        row_count = $rowCount
    } | ConvertTo-Json -Compress
}
finally {
    $connection.Close()
}
