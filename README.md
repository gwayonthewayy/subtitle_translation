# Subtitle Workflow

This repo is set up so you can open it on another Windows PC in VS Code, start Codex, and keep working with the same subtitle flow.

## What this project does

- Aligns a coarse Korean transcript to an English `.srt`
- Preserves subtitle timing from the original English file
- Adds speaker labels such as `마크미너비니`, `마크리치`, `브랜든`, `밥와이스먼`
- Supports separate translation workflows through `run_subs.ps1`

## Core files

- `tools/align_korean_transcript.py` - aligns Korean transcript text to source SRT timing
- `tools/subs_translate.py` - translation pipeline for Google, DeepL, Gemini, local model
- `run_align.ps1` - simple wrapper to generate `ko.srt` from transcript + English SRT
- `new_video_session.ps1` - creates a new working folder for a video
- `run_subs.ps1` - translate directly from English SRT when needed
- `requirements.txt` - Python dependencies
- `setup_project.ps1` - one-time environment setup

## One-time setup on another PC

### 1. Install prerequisites

- Git
- Python 3.10+
- VS Code
- Codex in VS Code or Codex CLI

### 2. Clone the repo

```powershell
git clone <YOUR_REPO_URL>
cd <YOUR_REPO_FOLDER>
```

### 3. Create the virtual environment and install packages

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_project.ps1
```

## Daily workflow

### A. Create a new video work folder

```powershell
powershell -ExecutionPolicy Bypass -File .\new_video_session.ps1 `
  -SourceSrt "C:\path\to\source.srt" `
  -SessionName "video7_2025_01_20_qa"
```

This creates:

- `video7_2025_01_20_qa\en.srt`
- `video7_2025_01_20_qa\ko_gemini_transcript.txt`

### B. Paste the Gemini Korean transcript

Open `video7_2025_01_20_qa\ko_gemini_transcript.txt` and paste the Korean transcript in this format:

```text
[0:00:02] [마크 리치] 첫 문장...
[0:00:08] 다음 문장...
```

### C. Generate the aligned Korean SRT

```powershell
powershell -ExecutionPolicy Bypass -File .\run_align.ps1 `
  -SourceSrt .\video7_2025_01_20_qa\en.srt `
  -Transcript .\video7_2025_01_20_qa\ko_gemini_transcript.txt `
  -OutputSrt .\video7_2025_01_20_qa\ko.srt `
  -VideoTitle "Q&A Session Mark Ritchie & Brandon Hedgepath"
```

Result:

- `video7_2025_01_20_qa\ko.srt`

## Direct translation workflow

If you want to translate from the English SRT directly instead of using a pasted Gemini transcript:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_subs.ps1 `
  -InputSrt .\en.srt `
  -OutputSrt .\ko.srt `
  -Engine google
```

Examples:

- `-Engine google`
- `-Engine deepl -DeepLApiKey "YOUR_KEY"`
- `-Engine gemini -GeminiApiKey "YOUR_KEY"`

## Recommended Codex prompt on another PC

Once the repo is open in VS Code and Codex is running at the project root, you can use a prompt like:

```text
새 영상 작업해줘.
원문 srt는 C:\...\video7...\en.srt
Gemini 원고는 video7...\ko_gemini_transcript.txt
이전과 동일한 방식으로 정렬해서 ko.srt 만들어줘.
```

## Git workflow

Because Git is not installed in this current machine, the files are prepared but the repository has not been initialized here.

On the machine where Git is installed:

```powershell
git init
git add .
git commit -m "Set up subtitle workflow"
git branch -M main
git remote add origin <YOUR_REPO_URL>
git push -u origin main
```

## Notes

- The repo is configured for Windows + PowerShell.
- `.vscode/settings.json` points VS Code to `.venv`.
- `.gitignore` excludes large unrelated local artifacts and virtual environment files.
- If speaker inference ever looks off, the explicit bracketed speaker in `ko_gemini_transcript.txt` wins, so keep those speaker tags in the transcript when possible.
