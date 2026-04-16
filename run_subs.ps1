param(
    [string]$InputSrt = "en.srt",
    [string]$OutputSrt = "ko.srt",
    [string]$Engine = "google",
    [string]$Model = "facebook/nllb-200-distilled-600M",
    [string]$GeminiModel = "gemini-2.5-flash",
    [string]$GeminiApiKey = "",
    [string]$DeepLApiKey = "",
    [int]$BatchSize = 12
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath $InputSrt)) {
    throw "Input SRT was not found: $InputSrt"
}

if ($GeminiApiKey) {
    $env:GEMINI_API_KEY = $GeminiApiKey
}
if ($DeepLApiKey) {
    $env:DEEPL_API_KEY = $DeepLApiKey
}

python -m pip install --quiet srt deep-translator deepl torch transformers sentencepiece openai | Out-Null
python .\tools\subs_translate.py $InputSrt -o $OutputSrt --engine $Engine --model $Model --gemini-model $GeminiModel --batch-size $BatchSize
if ($LASTEXITCODE -ne 0) {
    throw "Subtitle translation failed."
}

Write-Host "Done: $OutputSrt"
