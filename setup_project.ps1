param(
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Get-PythonCommand {
    $candidates = @("python", "py")
    foreach ($candidate in $candidates) {
        try {
            & $candidate --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
        }
    }
    throw "Python 3.10+ is required. Install Python and make sure 'python' or 'py' is on PATH."
}

$python = Get-PythonCommand
$venvPath = Join-Path $PSScriptRoot ".venv"

if ($RecreateVenv -and (Test-Path -LiteralPath $venvPath)) {
    Remove-Item -LiteralPath $venvPath -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPath)) {
    & $python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment."
    }
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment python not found: $venvPython"
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip."
}

& $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install requirements."
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Interpreter: $venvPython"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1) Open this folder in VS Code"
Write-Host "2) Start Codex from the project root"
Write-Host "3) Use .\\new_video_session.ps1 and .\\run_align.ps1 for subtitle work"
