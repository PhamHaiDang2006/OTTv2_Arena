# Local API + persistent PostgreSQL/Redis. Run from any directory.
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path $PSScriptRoot -Parent
$backendPath = Join-Path $repoPath 'backend'
$pythonPath = Join-Path $backendPath '.venv\Scripts\python.exe'
$envPath = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Install backend dependencies first: uv sync --project backend --frozen'
}

function New-LocalSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $envPath)) {
    # Never overwrite existing settings or rotate credentials on subsequent starts.
    $pgSecret = New-LocalSecret
    $redisSecret = New-LocalSecret
    $storageSecret = New-LocalSecret
    @"
POSTGRES_DB=ottv2
POSTGRES_USER=ottv2
POSTGRES_PASSWORD=$pgSecret
POSTGRES_PORT=5432
REDIS_PASSWORD=$redisSecret
REDIS_PORT=6379
MINIO_ROOT_USER=ottv2-local
MINIO_ROOT_PASSWORD=$storageSecret
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
S3_ACCESS_KEY_ID=ottv2-local
S3_SECRET_ACCESS_KEY=$storageSecret
S3_BUCKET=ottv2
JWT_SECRET=$(New-LocalSecret)
WORKER_API_TOKEN=$(New-LocalSecret)
"@ | Set-Content -LiteralPath $envPath -Encoding UTF8
}

$localSettings = @{}
foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $value = $Matches[2].Trim().Trim('"').Trim("'")
        $localSettings[$Matches[1]] = $value
        [Environment]::SetEnvironmentVariable($Matches[1], $value, 'Process')
    }
}
foreach ($key in @('POSTGRES_PASSWORD', 'REDIS_PASSWORD', 'JWT_SECRET', 'WORKER_API_TOKEN')) {
    if (-not $localSettings[$key]) { throw "Missing $key in infra/.env" }
}

& docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Open Docker Desktop, wait until it is running, then run this script again.' }
& docker compose --env-file $envPath -f (Join-Path $PSScriptRoot 'docker-compose.dev.yml') up -d --wait postgres redis
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL/Redis startup failed; see Docker output above.' }

$pgPort = if ($localSettings['POSTGRES_PORT']) { $localSettings['POSTGRES_PORT'] } else { '5432' }
$redisPort = if ($localSettings['REDIS_PORT']) { $localSettings['REDIS_PORT'] } else { '6379' }
$pgUser = if ($localSettings['POSTGRES_USER']) { $localSettings['POSTGRES_USER'] } else { 'ottv2' }
$pgDb = if ($localSettings['POSTGRES_DB']) { $localSettings['POSTGRES_DB'] } else { 'ottv2' }
$env:DATABASE_URL = 'postgresql+psycopg://{0}:{1}@127.0.0.1:{2}/{3}' -f [uri]::EscapeDataString($pgUser), [uri]::EscapeDataString($localSettings['POSTGRES_PASSWORD']), $pgPort, $pgDb
$env:REDIS_URL = 'redis://:{0}@127.0.0.1:{1}/0' -f [uri]::EscapeDataString($localSettings['REDIS_PASSWORD']), $redisPort
$env:FRONTEND_ORIGINS = 'http://127.0.0.1:5173,http://127.0.0.1:5174,http://localhost:5173,http://localhost:5174'
$env:COOKIE_SECURE = 'false'
$env:S3_ENDPOINT_URL = 'http://127.0.0.1:9000'
$env:S3_PUBLIC_ENDPOINT_URL = 'http://127.0.0.1:9000'
$env:PYTHONUTF8 = '1'

Push-Location $backendPath
try {
    & $pythonPath -m app.cli migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
} finally { Pop-Location }

$healthUrl = 'http://127.0.0.1:8000/api/v1/health'
$current = $null
try { $current = Invoke-RestMethod $healthUrl -TimeoutSec 3 } catch {}
if ($current) {
    if ($current.status -ne 'ok' -or $current.contract_version -ne '1.2.0') {
        throw 'An older or unhealthy API is using port 8000. Stop that API before restarting.'
    }
    Write-Host 'API is already healthy. Open http://127.0.0.1:5173/ and register.'
    return
}
$logPath = Join-Path $PSScriptRoot '.local-api.log'
$errorPath = Join-Path $PSScriptRoot '.local-api.error.log'
$apiProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $backendPath -WindowStyle Hidden -RedirectStandardOutput $logPath -RedirectStandardError $errorPath -PassThru
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ($apiProcess.HasExited) { throw "API exited. See $errorPath" }
    try {
        $health = Invoke-RestMethod $healthUrl -TimeoutSec 2
        if ($health.status -eq 'ok' -and $health.contract_version -eq '1.2.0') {
            $apiProcess.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot '.local-api.pid')
            Write-Host 'API ready. Accounts persist in the Docker development database.'
            Write-Host 'Start web separately: cd web; npm.cmd run dev'
            Write-Host 'Then open http://127.0.0.1:5173/ and register.'
            Write-Host 'Bot build/matches additionally need MinIO, registry, scheduler and runner.'
            return
        }
    } catch {}
    Start-Sleep -Seconds 1
}
throw "API did not become healthy. See $errorPath"
