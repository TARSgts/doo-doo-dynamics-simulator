param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path $PSScriptRoot -Parent
$pythonVersion = & $Python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne '3.12') { throw 'Use a working Python 3.12 x64 installation with -Python <path>.' }
Push-Location $projectPath
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the project environment.' }
    }
    & .\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --only-binary=:all: --require-hashes -r requirements-win-py312.lock
    if ($LASTEXITCODE -ne 0) { throw 'Dependency verification or installation failed.' }
    & .\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    $solverFolder = Join-Path $projectPath '.tools\calculix'
    $solverPath = Join-Path $solverFolder 'calculix_2.23_4win\ccx_static.exe'
    if (-not (Test-Path -LiteralPath $solverPath)) {
        New-Item -ItemType Directory -Force -Path (Join-Path $projectPath '.tools') | Out-Null
        $archivePath = Join-Path $projectPath '.tools\calculix_2.23_4win.zip'
        Invoke-WebRequest 'https://www.dhondt.de/calculix_2.23_4win.zip' -OutFile $archivePath
        $expectedHash = '87FC4E1721DF37370EC67D0A244BB14F9BF804B0A95DF49E2AE7369D30EC72E8'
        if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $expectedHash) {
            throw 'CalculiX download changed; inspect the upstream release before updating the recorded hash.'
        }
        if (Test-Path -LiteralPath $solverFolder) { throw 'Incomplete CalculiX folder exists; inspect it before retrying.' }
        Expand-Archive -LiteralPath $archivePath -DestinationPath $solverFolder
    }
    & .\.venv\Scripts\open-sim.exe doctor
    if ($LASTEXITCODE -ne 0) { throw 'Simulation dependencies are not ready.' }
} finally {
    Pop-Location
}
