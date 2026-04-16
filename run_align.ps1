param(
    [Parameter(Mandatory = $true)]
    [string]$SourceSrt,

    [Parameter(Mandatory = $true)]
    [string]$Transcript,

    [string]$OutputSrt = "",
    [string]$VideoTitle = ""
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath $SourceSrt)) {
    throw "Source SRT was not found: $SourceSrt"
}

if (-not (Test-Path -LiteralPath $Transcript)) {
    throw "Transcript file was not found: $Transcript"
}

if (-not $OutputSrt) {
    $OutputSrt = Join-Path (Split-Path -Parent $Transcript) "ko.srt"
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

$arguments = @(
    ".\tools\align_korean_transcript.py",
    $Transcript,
    "--source-srt", $SourceSrt,
    "-o", $OutputSrt
)

if ($VideoTitle) {
    $arguments += @("--video-title", $VideoTitle)
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Alignment failed."
}

Write-Host "Done: $OutputSrt" -ForegroundColor Green
