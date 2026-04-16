param(
    [Parameter(Mandatory = $true)]
    [string]$SourceSrt,

    [Parameter(Mandatory = $true)]
    [string]$SessionName
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath $SourceSrt)) {
    throw "Source SRT was not found: $SourceSrt"
}

$sessionPath = Join-Path $PSScriptRoot $SessionName
if (-not (Test-Path -LiteralPath $sessionPath)) {
    New-Item -ItemType Directory -Path $sessionPath | Out-Null
}

$destSrt = Join-Path $sessionPath "en.srt"
$destTranscript = Join-Path $sessionPath "ko_gemini_transcript.txt"

Copy-Item -LiteralPath $SourceSrt -Destination $destSrt -Force

if (-not (Test-Path -LiteralPath $destTranscript)) {
    @"
[0:00:00] [마크 리치] 여기에 Gemini 한국어 원고를 붙여 넣으세요.
"@ | Set-Content -LiteralPath $destTranscript -Encoding UTF8
}

Write-Host "Session ready:" -ForegroundColor Green
Write-Host "  Folder: $sessionPath"
Write-Host "  Source: $destSrt"
Write-Host "  Transcript template: $destTranscript"
