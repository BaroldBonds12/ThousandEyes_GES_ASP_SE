# ThousandEyes Questionnaire Automator — Session Handoff

> Reference this file at the start of any new session in this project folder.

---

## What This App Does

A fully local macOS application (no API keys, no cloud) that:
1. Accepts Excel, CSV, Word, PDF, and plain-text questionnaire files
2. Automatically answers questions using **only** `docs.thousandeyes.com` content
3. Writes answers back into the original file format
4. Includes a first-run installer wizard (Ollama + llama3.2 setup)

---

## Tech Stack

| Layer | Choice |
|---|---|
| GUI | `customtkinter` (dark theme, ThousandEyes brand palette) |
| Local LLM | Ollama HTTP API (`localhost:11434`) — default model `llama3.2` |
| File parsing | `openpyxl`, `pandas`, `python-docx`, `pdfplumber` |
| Web search | `ddgs` + `BeautifulSoup` scraping `docs.thousandeyes.com` |
| Mascot | `Vizzy` — drawn with PIL on top of ThousandEyes eye logo |
| Bundling | PyInstaller → `.app` bundle, distributed as `.zip` |

---

## File Map

```
te-questionnaire-app/
├── launcher.py          # Entry point — runs installer OR main app
├── main.py              # Main application window (CTk, ~1200 lines)
├── installer.py         # First-run wizard (CTk, ~1353 lines)
├── src/
│   ├── file_parser.py   # Parse Excel/CSV/Word/PDF/text → structured dict
│   ├── question_extractor.py  # Extract questions/requirements from parsed data
│   ├── llm_engine.py    # Ollama API + answer() + answer_rfp() methods
│   ├── processor.py     # Pipeline orchestrator (feedback → cache → prefetch → LLM)
│   ├── cache.py         # On-disk answer cache (~/.te_qa_cache/, 7-day TTL)
│   ├── feedback.py      # Permanent user-correction store (~/.te_qa_feedback.json) ← NEW
│   ├── file_writer.py   # Write answers back into original format
│   ├── te_search.py     # Search + scrape docs.thousandeyes.com (thread-safe)
│   └── vizzy.py         # Vizzy mascot renderer (PIL, 7 expressions incl. blink)
├── assets/
│   └── eye_logo.png     # ThousandEyes logo — Vizzy's body
├── build_mac.sh         # Build script → dist/TE Questionnaire Automator.app
├── te_qa.spec           # PyInstaller spec
├── requirements.txt     # Runtime deps
└── build_requirements.txt  # Build-time deps (pyinstaller)
```

---

## Architecture: The Pipeline

```
User uploads file
      │
      ▼
file_parser.parse()          # returns typed dict with workbook/doc/lines/etc.
      │
      ├─ detects rfp_matrix? → True  (Excel RFP evaluation matrix)
      └─ detects rfp_word?   → True  (Word numbered-section RFP)
      │
      ▼
question_extractor.extract()
      │
      ├─ Normal files     → look for cells/lines ending in "?" or Q:/Question: prefix
      ├─ Excel RFP matrix → each Col-C description row = 1 requirement
      └─ Word RFP         → each List Paragraph bullet under 3.1.X header = 1 requirement
      │
      ▼ stamp q["_cache_key"] and q["_original_answer"] = None on every question
      │
      ▼
processor.process()
      │
      ├─ Step 3a: feedback check (FeedbackStore — HIGHEST PRIORITY)
      │     fuzzy match (≥0.80) against ~/.te_qa_feedback.json
      │     hit? → q["_feedback"] = True, populate answer + _original_answer instantly
      │
      ├─ Step 3b: cache check (AnswerCache — skip _feedback items)
      │     sha256(model + question) → hit? q["_cached"] = True, populate answer
      │
      ├─ Step 4: parallel context prefetch (ThreadPoolExecutor, up to 4 workers)
      │     RFP mode:     group by category → 1 fetch per unique category
      │     Regular mode: 1 fetch per question, up to 4 concurrent
      │
      ├─ Step 5: LLM inference (sequential, CPU-bound)
      │     rfp_requirement=True  → llm_engine.answer_rfp() → JSON result
      │     normal question       → llm_engine.answer()    → free-text answer
      │     → set q["_original_answer"] = answer (for Review panel Reset)
      │     → persist each result to AnswerCache
      │
      ▼
file_writer.write()
      ├─ Excel RFP matrix → fill X/x in cols E–J (feature categories) in-place
      ├─ Word RFP         → generate new vendor-response .docx (Yes/No + doc links)
      ├─ Excel (normal)   → fill answer column, green/amber highlighting
      ├─ CSV              → fill/add Answer + Source columns
      ├─ Word (normal)    → append "ThousandEyes Answers" section
      ├─ PDF              → produce new .docx with Q&A pairs
      └─ Text             → insert "→ Answer:" lines after each question
```

---

## Speed Impact of Latest Optimisations

| Scenario | Before | After |
|---|---|---|
| Re-process same file (cache warm) | 20–25 s/item | ~0 s/item ⚡ |
| 100-req RFP (first run, doc fetch) | ~100 × 8 s = 800 s sequential | ~5 × 8 s = 40 s parallel (5 categories) |
| 10-question regular file (doc fetch) | ~10 × 8 s = 80 s sequential | ~3 × 8 s = 24 s (4 parallel workers) |
| Crash-resume | restart from zero | cache provides free resume |

---

## Key Design Decisions

### User feedback store (`src/feedback.py`)
`FeedbackStore` persists hand-corrected answers permanently to `~/.te_qa_feedback.json`.
- Key: full normalised question text (lowercased + stripped + whitespace-collapsed)
- Fuzzy lookup: `difflib.SequenceMatcher` ratio ≥ 0.80 — handles minor rephrasing
- No TTL — corrections are permanent until explicitly removed via Tools → Clear All Feedback
- Priority: feedback is checked BEFORE the LLM cache in `processor._apply_feedback()`
- `_original_answer` chain: LLM/cache answer → stored in question dict → FeedbackStore on save → enables one-click Reset in Review panel
- RFP items: skipped by `_apply_feedback` (structured editing deferred to future work)

### Review & Edit panel (`main.py` — `AnswerCard`, `_build_review_section`, `_populate_review`)
- Built dynamically after each processing run in `_show_results()`
- One `AnswerCard` per answered question (regular Q&A only; RFP = read-only card with note)
- State machine: VIEW → EDIT → VIEW (badge updates, buttons swap)
- On Save: `FeedbackStore.set()` + `q["answer"]` mutated in-place (flows into file output)
- On Reset: `FeedbackStore.remove()` + reverts `q["answer"]` to `q["_original_answer"]`
- Vizzy callback fires on Save ("Thanks, saved your correction!")
- `App._feedback_store` is a single shared instance (loaded once at startup)

### On-disk answer cache (`src/cache.py`)
`AnswerCache(model)` stores answers as `~/.te_qa_cache/<sha256>.json`.
- Key: `sha256(model + "rfp:" + category + ":" + description)` or `sha256(model + "q:" + question)`
- TTL: 7 days; expired entries silently deleted on first miss
- Thread-safe for concurrent reads; concurrent writes to the same key are idempotent
- Clears via Tools → Clear Answer Cache… in the menu bar
- Provides implicit crash-resume: re-processing a partially-done file skips all cached items

### Parallel context prefetch (`processor.py` Step 4)
`_prefetch_contexts(remaining, is_rfp)` uses `ThreadPoolExecutor(max_workers=4)`.
- **RFP mode**: groups requirements by `category` (typically 5–6 unique values for a 100-item RFP) and issues one `search_and_fetch` per category; context is shared across all requirements in that group.
- **Regular mode**: one fetch per question, up to 4 concurrent.
- `TESearcher._page_cache` is protected by `threading.Lock` to make concurrent access safe.

### Thread-safe UI updates
Both `main.py` and `installer.py` use a `queue.Queue` + `_poll_ui_queue()` pattern
(drains every 40ms on the main thread). Background threads call `self._post_ui(fn)`
instead of `self.after(0, ...)` — the latter silently drops callbacks from threads
in tkinter on macOS.

### Vizzy mascot
`src/vizzy.py` renders Vizzy programmatically using PIL. Expressions:
`idle`, `checking`, `working`, `downloading`, `happy`, `done`, `blink`.
The `blink` expression is used by `VizzyBar` in `main.py` to animate a random
blink every 3–8 seconds. `VizzyBar.speak(text, expression)` updates both the
image and speech bubble atomically.

### ETA estimation
`processor.py` emits an `eta_cb` payload (`"ETA:<time>|<count> requirements"`)
after question extraction if estimated time > 60s. `main.py` intercepts this
and has Vizzy warn the user before LLM work starts.
Baselines: 20s/requirement (RFP), 25s/question (regular).

### RFP Excel detection
`file_parser._detect_rfp_matrix()` scans row 1 for a cell containing
`"ThousandEyes"` with 2+ feature-category labels to its right. Column mapping
is dynamic — works for any future RFP that follows this pattern.
Feature columns (synthetics / device layer / traffic insights / cloud insights /
endpoint) are detected from the actual header row, not hardcoded.

### RFP Word detection
`file_parser._detect_word_rfp()` looks for paragraphs matching `^\d+\.\d+\.\d+\s+`
followed by `List Paragraph` bullets. Requires 2+ qualifying sections.

### LLM prompts
- **Regular questions** (`answer()`): strict RAG prompt, returns `CANNOT ANSWER:` if
  docs don't support the claim.
- **RFP requirements** (`answer_rfp()`): structured JSON prompt asking for
  `{supported, feature_categories, explanation}`. Three fallback strategies handle
  models that don't return clean JSON.

### macOS Ollama installation
`installer.py` uses `osascript "do shell script ... with administrator privileges"`
to get a native macOS password dialog instead of broken `sudo` in a non-terminal.

---

## Known Bugs / Limitations

| Issue | Status | Notes |
|---|---|---|
| `List Number` style missing in some .docx | Fixed | `file_writer._add_qa_block` checks style exists before applying |
| `self.after(0, ...)` from threads silently dropped | Fixed | Replaced with `_post_ui` queue pattern everywhere |
| LLM inference ~20–25s per item | By design | Local-only constraint; ETA warning added |
| 119-req Word RFP ≈ 40+ minutes (first run) | By design | Cache + category batching cuts subsequent runs to seconds |

---

## Potential Next Improvements

1. ~~**Parallel LLM calls**~~ — doc fetching is now parallel; LLM stays sequential (CPU-bound)
2. ~~**Progress persistence / resume**~~ — on-disk cache provides implicit resume for free
3. **Confidence score display** — surface the LLM's certainty alongside Yes/No
4. **Export to PDF** — render the Word response doc as PDF before saving
5. **Custom model system prompt** — let user edit the system prompt from the UI
6. ~~**Batch context fetching**~~ — done: RFP groups by category, regular questions parallel-fetched
7. ~~**Results caching**~~ — done: `src/cache.py` + SHA-256 keyed on-disk cache
8. **Excel RFP: add explanation column** — currently only X marks; write LLM explanation nearby
9. **Installer: auto-detect and offer model upgrades** if a newer llama3.x is available
10. **Windows support** — `_start_ollama` and admin install already have Windows branches
11. **Cache TTL setting** — expose TTL (currently 7 days) as a user preference
12. **RFP structured editing** — `AnswerCard` for RFP items: Supported toggle + category checkboxes + explanation text (currently read-only with a note)
13. ~~**Feedback mechanism**~~ — done: `src/feedback.py` + Review panel with AnswerCard, fuzzy matching, Reset

---

## Build & Run

```bash
# Developer run (no build needed)
cd te-questionnaire-app
bash run.sh

# Build macOS distributable
bash build_mac.sh
# → dist/TE Questionnaire Automator.app
# → dist/TE_QA_Automator_mac.zip
```

**Python requirement:** 3.12 (managed by `uv`, bundled Tcl/Tk 9.0)

---

## Session Transcripts

| Session | Key work |
|---|---|
| [Initial build](a86b595d-a65a-4914-85c4-244394de3690) | Full app scaffold — GUI, installer, parser, LLM engine, file writer, Vizzy |
| [Cache + parallel fetch](a86b595d-a65a-4914-85c4-244394de3690) | `src/cache.py`, parallel doc prefetch, RFP category batching, Tools menu |
| [Feedback mechanism](a86b595d-a65a-4914-85c4-244394de3690) | `src/feedback.py`, Review panel, AnswerCard, fuzzy matching, processor priority chain |
