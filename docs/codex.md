# Codex Setup

## Requirements

- Git
- Python 3.12 or newer recommended
- Python packages from `requirements.txt`
- A CJK font with TrueType outlines for Chinese PDF reports

## Install

Clone the repository directly into the Codex skills directory.

macOS or Linux:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/0x0addc001/video-style-transfer-eval.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/video-style-transfer-eval"
```

Windows PowerShell:

```powershell
$skillParent = Join-Path $env:USERPROFILE '.codex\skills'
New-Item -ItemType Directory -Force -Path $skillParent | Out-Null
git clone https://github.com/0x0addc001/video-style-transfer-eval.git `
  (Join-Path $skillParent 'video-style-transfer-eval')
```

Install the Python dependencies:

```bash
cd "${CODEX_HOME:-$HOME/.codex}/skills/video-style-transfer-eval"
python -m pip install -r requirements.txt
```

## Use

Reference the skill by name in a request:

```text
Use $video-style-transfer-eval to compare these videos, review the outputs, and generate English and Chinese reports.
```

The workflow, commands, and output contract are defined in `SKILL.md`.

## Update

```bash
cd "${CODEX_HOME:-$HOME/.codex}/skills/video-style-transfer-eval"
git pull --ff-only
python -m pip install -r requirements.txt
```
