param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'start-local-api.ps1')
$composeFiles = @('--env-file', $envPath, '-f', (Join-Path $PSScriptRoot 'docker-compose.dev.yml'), '-f', (Join-Path $PSScriptRoot 'docker-compose.play.yml'))
& $pythonPath (Join-Path $PSScriptRoot 'check_resources.py') --env-file $envPath -f (Join-Path $PSScriptRoot 'docker-compose.dev.yml') -f (Join-Path $PSScriptRoot 'docker-compose.play.yml')
if ($LASTEXITCODE -ne 0) { throw 'Resource layout invalid; adjust LOCAL_* CPU settings or Docker CPU/RAM allocation first.' }
& docker compose @composeFiles up -d --build --wait minio registry
if ($LASTEXITCODE -ne 0) { throw 'Storage/registry startup failed.' }
if (-not $SkipBuild) {
    & docker build -f (Join-Path $repoPath 'engine/Dockerfile.bot') -t ottv2-python:local $repoPath
    if ($LASTEXITCODE -ne 0) { throw 'Python bot image build failed.' }
    & docker build -f (Join-Path $repoPath 'runner/Dockerfile.engine') -t ottv2-worker:local $repoPath
    if ($LASTEXITCODE -ne 0) { throw 'Worker image build failed.' }
}
& docker tag ottv2-python:local 127.0.0.1:5000/ottv2-python:local
if ($LASTEXITCODE -ne 0) { throw 'Bot image tag failed.' }
& docker push 127.0.0.1:5000/ottv2-python:local
if ($LASTEXITCODE -ne 0) { throw 'Local registry push failed.' }
$imageInfo = (& docker image inspect 127.0.0.1:5000/ottv2-python:local | ConvertFrom-Json)[0]
$env:RUNNER_IMAGE_PYTHON = @($imageInfo.RepoDigests | Where-Object { $_ -like '127.0.0.1:5000/ottv2-python@sha256:*' })[0]
if (-not $env:RUNNER_IMAGE_PYTHON) { throw 'Missing immutable Python image digest.' }
Push-Location $backendPath
try {
    & $pythonPath -m app.cli ensure-bucket
    if ($LASTEXITCODE -ne 0) { throw 'Bucket creation failed.' }
} finally { Pop-Location }
& docker compose @composeFiles up -d build-worker match-worker match-scrimmage
if ($LASTEXITCODE -ne 0) { throw 'Worker startup failed.' }

$schedulerPidPath = Join-Path $PSScriptRoot '.local-scheduler.pid'
$schedulerExists = $false
if (Test-Path -LiteralPath $schedulerPidPath) {
    $savedPid = [int](Get-Content -LiteralPath $schedulerPidPath)
    $savedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    $schedulerExists = $savedProcess -and $savedProcess.CommandLine -match 'app.cli scheduler' -and $savedProcess.ExecutablePath -eq $pythonPath
}
if (-not $schedulerExists) {
    $scheduler = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'app.cli', 'scheduler') -WorkingDirectory $backendPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot '.local-scheduler.log') -RedirectStandardError (Join-Path $PSScriptRoot '.local-scheduler.error.log') -PassThru
    $scheduler.Id | Set-Content -LiteralPath $schedulerPidPath
}
Write-Host 'Python build/match services are running with the real OTTv2 engine.'
Write-Host 'Create the two-team demonstration: backend\.venv\Scripts\python.exe infra\demo_match.py'
