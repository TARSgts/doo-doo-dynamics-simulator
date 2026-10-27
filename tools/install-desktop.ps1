param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'setup.ps1') -Python $Python
Push-Location $projectPath
try {
    & .\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --only-binary=:all: --require-hashes -r requirements-desktop-win-py312.lock
    if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency installation failed.' }
    & .\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw 'Desktop application installation failed.' }
    & .\.venv\Scripts\python.exe -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency check failed.' }
    if ($env:CI -ne 'true') { & (Join-Path $PSScriptRoot 'create-shortcuts.ps1') }
    Write-Output 'Installed. Double-click Launch Simulator.cmd or run .venv\Scripts\doo-doo-dynamics.exe.'
} finally {
    Pop-Location
}
