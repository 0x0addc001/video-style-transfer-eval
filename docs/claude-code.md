# Claude Code Setup

## Requirements

- Git
- Python 3.12 or newer recommended
- Python packages from `requirements.txt`
- A CJK font with TrueType outlines for Chinese PDF reports

## Install at user scope

Clone the repository directly into Claude Code's user skills directory.

macOS or Linux:

```bash
mkdir -p "$HOME/.claude/skills"
git clone https://github.com/0x0addc001/video-style-transfer-eval.git \
  "$HOME/.claude/skills/video-style-transfer-eval"
```

Windows PowerShell:

```powershell
$skillParent = Join-Path $env:USERPROFILE '.claude\skills'
New-Item -ItemType Directory -Force -Path $skillParent | Out-Null
git clone https://github.com/0x0addc001/video-style-transfer-eval.git `
  (Join-Path $skillParent 'video-style-transfer-eval')
```

Install the Python dependencies:

```bash
cd "$HOME/.claude/skills/video-style-transfer-eval"
python -m pip install -r requirements.txt
```

## Install for one project

Run this from the project directory:

```bash
mkdir -p .claude/skills
git clone https://github.com/0x0addc001/video-style-transfer-eval.git \
  .claude/skills/video-style-transfer-eval
python -m pip install -r .claude/skills/video-style-transfer-eval/requirements.txt
```

Project-level installation keeps the skill scoped to that repository.

## Use

Mention the skill by name in a Claude Code request:

```text
Use the video-style-transfer-eval skill to compare these video outputs,
review the results, and produce the Markdown, HTML, PDF, and LaTeX reports.
```

Claude Code can also discover the skill from its name and description and
activate it automatically for a matching evaluation request.

The workflow, commands, and output contract are defined in
`.claude/skills/video-style-transfer-eval/SKILL.md`.

## Update

For user-scope installation:

```bash
cd "$HOME/.claude/skills/video-style-transfer-eval"
git pull --ff-only
python -m pip install -r requirements.txt
```
