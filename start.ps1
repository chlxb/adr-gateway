param([string]$Python = "$PSScriptRoot/.venv/Scripts/python.exe")
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -m adr_gateway
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
