# ThousandEyes Questionnaire Automator

Automatically answers questions found in Excel, CSV, Word, PDF, or plain text files
using exclusively **ThousandEyes documentation** (`docs.thousandeyes.com` and `thousandeyes.com`).

- **100 % local** — no data leaves your machine
- **No API keys** — powered by free, open-source AI models via [Ollama](https://ollama.com)
- **Cross-platform** — macOS and Windows

---

## Quick Start (from source)

```bash
# 1. Clone / download the repo
cd te-questionnaire-app

# 2. First-time setup (installs Python deps)
./setup.sh          # macOS / Linux
# or: run.bat        # Windows (double-click or cmd)

# 3. Launch (runs installer wizard on first run, then main app)
./run.sh            # macOS / Linux
# or: run.bat        # Windows
```

The installer wizard will guide you through:
1. System requirements check
2. Installing Ollama (the local AI runtime)
3. Downloading an AI model (~2–5 GB, one time)

---

## Building a Distributable (send to others)

Recipients **do not need Python** — the bundled app is self-contained.

### macOS `.dmg` / `.zip`

```bash
# Run this on a Mac
./build_mac.sh
# Output: dist/TE_QA_Automator_mac.zip  (or .dmg)
```

### Windows `.exe` / `.zip`

```bat
REM Run this on a Windows PC
build_windows.bat
REM Output: dist\TE_QA_Automator_win.zip
```

Send the zip/dmg to your recipient. When they run the app for the first time,
the built-in wizard installs Ollama and downloads a model automatically.

---

## Supported File Formats

| Format | Questions detected | Answers written |
|--------|-------------------|-----------------|
| Excel (`.xlsx`) | Cells ending with `?` or under a `Question` column | Adjacent / `Answer` column, green highlight |
| CSV (`.csv`) | Same as Excel | New `Answer` + `Answer Source` column |
| Word (`.docx`) | Paragraphs ending with `?` | Appended `Answers` section |
| PDF (`.pdf`) | Lines ending with `?` | New `.docx` output file |
| Text (`.txt`) | Lines ending with `?` | `→ Answer:` lines inserted inline |

---

## AI Models Available

| Model | Size | RAM needed | Notes |
|-------|------|-----------|-------|
| **phi3:mini** *(recommended)* | 2.3 GB | 8 GB | Fast, excellent quality |
| llama3.2 | 2.0 GB | 8 GB | Meta's Llama 3.2 3B |
| llama3.1:8b | 4.7 GB | 16 GB | Highest quality |
| mistral | 4.1 GB | 16 GB | Strong instruction following |

Switch models anytime in the app's model dropdown.

---

## How answers are sourced

1. Each question is searched on `docs.thousandeyes.com` and `thousandeyes.com`
   using DuckDuckGo (no API key required)
2. The top matching pages are fetched and their text extracted
3. The local AI model is given the question + page excerpts and instructed
   to answer **only** from that content
4. If no relevant content is found, the question is flagged as unanswerable

---

## Project Structure

```
te-questionnaire-app/
├── launcher.py          # Entry point — installer on first run, app on subsequent runs
├── installer.py         # Multi-step installation wizard GUI
├── main.py              # Main application GUI
├── requirements.txt     # Runtime Python dependencies
├── build_requirements.txt  # PyInstaller (build only)
├── te_qa.spec           # PyInstaller build spec
├── build_mac.sh         # Build macOS distributable
├── build_windows.bat    # Build Windows distributable
├── run.sh               # Run from source (macOS/Linux)
├── run.bat              # Run from source (Windows)
└── src/
    ├── file_parser.py       # Parse input files
    ├── question_extractor.py # Detect questions
    ├── te_search.py          # Search ThousandEyes docs
    ├── llm_engine.py         # Ollama LLM integration
    ├── file_writer.py        # Write answers to output files
    └── processor.py          # Orchestrate the pipeline
```

---

## Requirements

- macOS 12+ or Windows 10/11 (64-bit)
- 8 GB RAM minimum (16 GB recommended for larger models)
- ~10 GB free disk space (for the AI model)
- Internet connection for the initial model download only