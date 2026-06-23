"""
Question Extractor — identifies question cells/lines/paragraphs within
the parsed file structure and returns a uniform list of question dicts.

Each question dict has at minimum:
    question    : str   — the raw question text
    answer      : None  — filled by the LLM engine later
    source_type : str   — "excel" | "csv" | "word" | "pdf" | "text"

Additional keys depend on source_type and are used by file_writer.py
to put the answer back in the right place.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate a cell/line is a question
_QUESTION_RE = re.compile(
    r"""
    .+\?$                       # anything ending with ?
    | ^(?:Q|Question|Q\d+)\s*[:\-\.]\s*.+    # Q: / Question: / Q1:
    | ^\d+[\.\)]\s+.{10,}\?$   # numbered list ending with ?
    | ^[a-zA-Z][\.\)]\s+.{10,}\?$  # lettered list ending with ?
    """,
    re.VERBOSE | re.IGNORECASE,
)

_MIN_QUESTION_LENGTH = 8  # ignore very short tokens even if they end with ?


def _is_question(text: str) -> bool:
    if not text:
        return False
    text = text.strip()
    if len(text) < _MIN_QUESTION_LENGTH:
        return False
    return bool(_QUESTION_RE.match(text))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(parsed: dict[str, Any]) -> list[dict]:
    file_type = parsed["type"]
    handlers = {
        "excel": _extract_excel,
        "csv": _extract_csv,
        "word": _extract_word,
        "pdf": _extract_pdf,
        "text": _extract_text,
    }
    return handlers.get(file_type, lambda _: [])(parsed)


# ---------------------------------------------------------------------------
# Per-type extractors
# ---------------------------------------------------------------------------

def _extract_excel(parsed: dict) -> list[dict]:
    # Delegate to the RFP matrix extractor when the format is detected
    if parsed.get("rfp_matrix"):
        return _extract_excel_rfp(parsed)

    questions: list[dict] = []

    for sheet_name, rows in parsed["sheets"].items():
        if not rows:
            continue

        # Detect header row for "Question / Answer" layout
        question_col: int | None = None
        answer_col: int | None = None
        header_row = rows[0]
        for cell in header_row:
            val = str(cell.get("value") or "").strip().lower()
            if val in ("question", "questions", "q"):
                question_col = cell["col"]
            elif val in ("answer", "answers", "a", "response"):
                answer_col = cell["col"]

        if question_col is not None:
            # Structured layout — iterate data rows
            for row in rows[1:]:
                q_cell = next((c for c in row if c["col"] == question_col), None)
                if q_cell and q_cell.get("value"):
                    questions.append({
                        "question": str(q_cell["value"]).strip(),
                        "source_type": "excel",
                        "sheet": sheet_name,
                        "row": q_cell["row"],
                        "col": q_cell["col"],
                        "answer_col": answer_col if answer_col else question_col + 1,
                        "answer": None,
                        "reason": None,
                        "source_url": None,
                    })
        else:
            # Free-form scan — look for question-shaped cells
            for row in rows:
                for cell in row:
                    val = cell.get("value")
                    if val and _is_question(str(val)):
                        questions.append({
                            "question": str(val).strip(),
                            "source_type": "excel",
                            "sheet": sheet_name,
                            "row": cell["row"],
                            "col": cell["col"],
                            "answer_col": cell["col"] + 1,
                            "answer": None,
                            "reason": None,
                            "source_url": None,
                        })

    return questions


def _extract_excel_rfp(parsed: dict) -> list[dict]:
    """
    Extract requirements from an RFP evaluation-matrix spreadsheet.

    Each row that has a non-empty description (col C) becomes one requirement.
    We track section (col A, sparse) and category (col B, can repeat) as
    context that's passed to the LLM alongside the requirement text.
    """
    rfp_cols   = parsed["rfp_cols"]
    sect_col   = rfp_cols["section_col"]
    cat_col    = rfp_cols["category_col"]
    desc_col   = rfp_cols["description_col"]
    support_col = rfp_cols["support_col"]
    feature_cols = rfp_cols["feature_cols"]

    wb  = parsed["workbook"]
    ws  = wb.active

    requirements: list[dict] = []
    current_section  = ""
    current_category = ""

    for row_num in range(1, ws.max_row + 1):
        sect_val = ws.cell(row_num, sect_col).value
        cat_val  = ws.cell(row_num, cat_col).value
        desc_val = ws.cell(row_num, desc_col).value

        # Track running section / category context
        if sect_val and str(sect_val).strip():
            current_section = str(sect_val).strip()
        if cat_val and str(cat_val).strip():
            current_category = str(cat_val).strip()

        if not desc_val or not str(desc_val).strip():
            continue

        description = str(desc_val).strip()

        # Skip very short or header-like cells
        if len(description) < 6:
            continue

        # Build a display label for the results panel
        label_parts = []
        if current_section:
            label_parts.append(current_section)
        if current_category and current_category != current_section:
            label_parts.append(current_category)
        label = " › ".join(label_parts)

        requirements.append({
            # Human-readable question text shown in the results panel
            "question": f"[{label}] {description}" if label else description,
            # Fields used by the LLM
            "rfp_requirement": True,
            "section":     current_section,
            "category":    current_category,
            "description": description,
            # Spreadsheet location (for writing back)
            "source_type":   "excel",
            "row":           row_num,
            "support_col":   support_col,
            "feature_cols":  feature_cols,
            # Filled by processor
            "answer":      None,
            "rfp_result":  None,
            "reason":      None,
            "source_url":  None,
        })

    return requirements


def _extract_csv(parsed: dict) -> list[dict]:
    questions: list[dict] = []
    df = parsed["dataframe"]

    q_col: str | None = None
    a_col: str | None = None
    for col in df.columns:
        cl = col.strip().lower()
        if cl in ("question", "questions", "q"):
            q_col = col
        elif cl in ("answer", "answers", "a", "response"):
            a_col = col

    if q_col:
        for idx, row in df.iterrows():
            val = str(row[q_col]).strip()
            if val and val != "nan":
                questions.append({
                    "question": val,
                    "source_type": "csv",
                    "row_index": idx,
                    "q_col": q_col,
                    "a_col": a_col,
                    "answer": None,
                    "reason": None,
                    "source_url": None,
                })
    else:
        # Free-form scan
        for col in df.columns:
            if _is_question(col):
                questions.append({
                    "question": col.strip(),
                    "source_type": "csv",
                    "row_index": -1,
                    "q_col": col,
                    "a_col": None,
                    "answer": None,
                    "reason": None,
                    "source_url": None,
                })
        for col in df.columns:
            for idx, row in df.iterrows():
                val = str(row[col]).strip()
                if val and val != "nan" and _is_question(val):
                    questions.append({
                        "question": val,
                        "source_type": "csv",
                        "row_index": idx,
                        "q_col": col,
                        "a_col": None,
                        "answer": None,
                        "reason": None,
                        "source_url": None,
                    })

    return questions


def _extract_word(parsed: dict) -> list[dict]:
    # Delegate to the RFP extractor when the numbered-section format is detected
    if parsed.get("rfp_word"):
        return _extract_word_rfp(parsed)

    questions: list[dict] = []

    for para in parsed["paragraphs"]:
        text = para.get("text", "").strip()
        if _is_question(text):
            questions.append({
                "question": text,
                "source_type": "word",
                "para_index": para["index"],
                "answer": None,
                "reason": None,
                "source_url": None,
            })

    for t_idx, table in enumerate(parsed.get("tables", [])):
        for row in table:
            for cell in row:
                text = cell.get("text", "").strip()
                if _is_question(text):
                    questions.append({
                        "question": text,
                        "source_type": "word",
                        "table_index": t_idx,
                        "table_row": cell["row"],
                        "table_col": cell["col"],
                        "answer": None,
                        "reason": None,
                        "source_url": None,
                    })

    return questions


def _extract_word_rfp(parsed: dict) -> list[dict]:
    """
    Extract each bulleted requirement from a numbered-section Word RFP.

    Every bullet becomes an 'rfp_requirement' dict compatible with the
    existing processor/LLM/writer pipeline.  The section header is used
    as the 'section' field so the LLM has full context.
    """
    requirements: list[dict] = []

    for section in parsed["rfp_sections"]:
        header  = section["header"]   # e.g. "3.1.1 Solution"
        bullets = section["bullets"]  # [{idx, text}, …]

        for b in bullets:
            description = b["text"].strip()
            if len(description) < 4:
                continue

            requirements.append({
                # Display label in results panel
                "question": f"[{header}] {description}",
                # RFP fields consumed by processor + LLM
                "rfp_requirement": True,
                "rfp_format":      "word",
                "section":         header,
                "category":        header,   # same as section for Word RFP
                "description":     description,
                # Location metadata (for reference; writer uses rfp_sections)
                "source_type":     "word",
                "para_index":      b["idx"],
                # Filled by processor
                "answer":          None,
                "rfp_result":      None,
                "reason":          None,
                "source_url":      None,
            })

    return requirements


def _extract_pdf(parsed: dict) -> list[dict]:
    questions: list[dict] = []

    for page_data in parsed["pages"]:
        for line in page_data["text"].splitlines():
            line = line.strip()
            if _is_question(line):
                questions.append({
                    "question": line,
                    "source_type": "pdf",
                    "page": page_data["page"],
                    "answer": None,
                    "reason": None,
                    "source_url": None,
                })

    return questions


def _extract_text(parsed: dict) -> list[dict]:
    questions: list[dict] = []

    for i, line in enumerate(parsed["lines"]):
        line = line.strip()
        if _is_question(line):
            questions.append({
                "question": line,
                "source_type": "text",
                "line_index": i,
                "answer": None,
                "reason": None,
                "source_url": None,
            })

    return questions
