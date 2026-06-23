"""
Customer Questionnaire Crusher — main application window.

All inference is done locally via Ollama (no API keys, no cloud services).
On first launch the built-in Setup Wizard (src/setup_wizard.py) guides the
user through Ollama installation and model download automatically.
"""

from __future__ import annotations

import datetime
import json
import os
import queue as _queue
import random
import sys
import threading
import traceback
from pathlib import Path
from tkinter import Menu, filedialog, messagebox

import customtkinter as ctk
from src.setup_wizard import SetupWizard, needs_ollama_setup

# ---------------------------------------------------------------------------
# Theme — ThousandEyes brand palette
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Spreadsheet column pixel widths (must sum to ≈ usable width after scroll-bar)
_SC_NUM   = 36    # row-number gutter
_SC_Q     = 200   # Question column
_SC_BADGE = 90    # Support-level badge column (Yes / Partial / N/A)
_SC_A     = 280   # Answer column (editable)
_SC_URL   = 152   # Source URL column (editable)
_SC_SEP   = 1     # vertical separator width

C_BG      = "#12121e"   # deepest navy background
C_SURFACE = "#1a1a2e"   # card / panel surface
C_SURF2   = "#22223a"   # inset / secondary surface
C_BORDER  = "#2e2e50"   # subtle purple-tinted border
C_TEXT    = "#f0f0fa"   # near-white text
C_MUTED   = "#8888bb"   # blue-gray muted text
C_ACCENT  = "#7c6fff"   # primary purple/violet
C_ACCENT2 = "#a78bff"   # lighter purple (hover / highlight)
C_SUCCESS = "#4dd98a"   # vivid green
C_WARN    = "#fbbf24"   # amber
C_CRIT    = "#f87171"   # soft red
C_BLUE    = "#60a5fa"   # secondary blue

SUPPORTED_EXTS = "*.xlsx *.xls *.csv *.docx *.doc *.pdf *.txt"
SETTINGS_PATH  = Path.home() / ".te_qa_settings.json"

# Curated model list — names that Ollama recognises
RECOMMENDED_MODELS = [
    "llama3.2",
    "phi3:mini",
    "llama3.2:3b",
    "llama3.1:8b",
    "mistral",
    "qwen2.5:7b",
]

# ---------------------------------------------------------------------------
# Support-level UI helpers  (used by review spreadsheet rows)
# ---------------------------------------------------------------------------

def _support_badge_config(support_level: str) -> tuple[str, str, str]:
    """
    Return (label_text, bg_hex, fg_hex) for a support-level badge pill.

    Colours stay within the dark-navy palette and are subtle enough not to
    overwhelm the text in adjacent cells.
    """
    if support_level == "yes":
        return "✓  Yes",     "#1e3527", C_SUCCESS   # green pill
    elif support_level == "partial":
        return "⚠  Partial", "#332b10", C_WARN      # amber pill
    elif support_level == "not_applicable":
        return "○  N/A",     "#252535", C_MUTED     # grey pill
    else:
        return "—",          "#1c1c30", C_MUTED     # Q&A / unknown


def _row_bg_for_level(support_level: str | None, alt: bool) -> str:
    """
    Return a row background hex that blends the support-level tint with the
    alternating stripe colour.  The tints are intentionally very subtle so
    the primary readability signal is the badge column, not the row colour.
    """
    if support_level == "yes":
        return "#1b2920" if alt else "#172520"      # faint green wash
    elif support_level == "partial":
        return "#2a2412" if alt else "#262110"      # faint amber wash
    else:
        return C_SURF2 if alt else C_SURFACE        # normal alternating


def _format_file_info(filepath: str) -> dict:
    """
    Extract display metadata from a file path for the upload preview widget.

    Returns a dict with: icon, name, size (formatted string), type (extension).
    """
    path = Path(filepath)
    try:
        raw = path.stat().st_size
        if raw < 1_024:
            size = f"{raw} B"
        elif raw < 1_024 * 1_024:
            size = f"{raw / 1_024:.1f} KB"
        else:
            size = f"{raw / (1_024 * 1_024):.1f} MB"
    except OSError:
        size = "—"

    icon_map = {
        ".docx": "📄", ".doc": "📄",
        ".xlsx": "📊", ".xls": "📊",
        ".pdf":  "📕",
        ".csv":  "📋",
        ".txt":  "📝",
    }
    ext = path.suffix.lower()
    return {
        "icon": icon_map.get(ext, "📎"),
        "name": path.name,
        "size": size,
        "type": ext.upper().lstrip(".") or "FILE",
    }


# Processing stage → (Vizzy expression, status prefix) mapping.
# _status_callback pattern-matches incoming messages against these keywords.
_STAGE_MAP: list[tuple[str, str, str]] = [
    # keyword (lower)     expression      status-bar prefix
    ("parsing",          "checking",     "📂 Parsing"),
    ("extracting",       "checking",     "🔍 Extracting"),
    ("prefetch",         "downloading",  "🌐 Fetching docs"),
    ("fetching",         "downloading",  "🌐 Fetching docs"),
    ("searching",        "downloading",  "🌐 Searching docs"),
    ("answering",        "working",      "🤖 Analyzing"),
    ("llm",              "working",      "🤖 LLM inference"),
    ("analyzing",        "working",      "🤖 Analyzing"),
    ("enriching",        "working",      "🔗 Enriching URLs"),
    ("loading",          "idle",         "⏳ Loading"),
    ("done",             "done",         "✅ Done"),
    ("complete",         "done",         "✅ Complete"),
]


# ---------------------------------------------------------------------------
# Debug logging
# ---------------------------------------------------------------------------

_debug_lines: list[str] = []


def _log(msg: str, level: str = "INFO") -> None:
    ts  = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{level}] {msg}"
    _debug_lines.append(line)
    print(line, flush=True)


def _log_exc(msg: str) -> None:
    _log(msg, "ERROR")
    for ln in traceback.format_exc().splitlines():
        _debug_lines.append(f"          {ln}")
        print(f"          {ln}", flush=True)


class DebugWindow(ctk.CTkToplevel):
    """Floating window that shows the live debug log."""

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("Debug Log — ThousandEyes QA")
        self.geometry("780x480")
        self.configure(fg_color=C_BG)
        self._parent = parent

        toolbar = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0)
        toolbar.pack(fill="x")

        ctk.CTkLabel(toolbar, text="🐛  Debug Log",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_ACCENT).pack(side="left", padx=14, pady=8)

        ctk.CTkButton(toolbar, text="Copy to Clipboard", width=140,
                      fg_color=C_SURF2, border_width=1, border_color=C_BORDER,
                      hover_color=C_SURFACE, text_color=C_TEXT,
                      command=self._copy).pack(side="right", padx=10, pady=6)

        ctk.CTkButton(toolbar, text="Clear", width=70,
                      fg_color=C_SURF2, border_width=1, border_color=C_BORDER,
                      hover_color=C_SURFACE, text_color=C_MUTED,
                      command=self._clear).pack(side="right", pady=6)

        # ── System info row ────────────────────────────────────────────────
        info_frame = ctk.CTkFrame(self, fg_color=C_SURF2, corner_radius=0)
        info_frame.pack(fill="x")
        info = (
            f"Python {sys.version.split()[0]}  │  "
            f"Platform: {sys.platform}  │  "
            f"CWD: {os.getcwd()}"
        )
        ctk.CTkLabel(info_frame, text=info,
                     font=ctk.CTkFont(family="Menlo", size=10),
                     text_color=C_MUTED).pack(anchor="w", padx=12, pady=4)

        # ── Log text box ───────────────────────────────────────────────────
        self._box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=C_SURF2, text_color=C_TEXT,
            border_color=C_BORDER, border_width=1,
            wrap="none",
        )
        self._box.pack(fill="both", expand=True, padx=12, pady=10)

        self._refresh()
        self._poll()

    def _refresh(self) -> None:
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        self._box.insert("1.0", "\n".join(_debug_lines))
        self._box.configure(state="disabled")
        self._box.see("end")

    def _poll(self) -> None:
        self._refresh()
        self.after(600, self._poll)

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append("\n".join(_debug_lines))
        _log("Debug log copied to clipboard.")

    def _clear(self) -> None:
        _debug_lines.clear()
        _log("Debug log cleared.")
        self._refresh()


# ---------------------------------------------------------------------------
# Vizzy widget — mascot + speech bubble
# ---------------------------------------------------------------------------

_VIZZY_IMG_CACHE: dict[str, object] = {}   # expression → ImageTk.PhotoImage


class VizzyBar(ctk.CTkFrame):
    """
    Horizontal bar housing the Vizzy mascot and a speech bubble.

    Call speak(text, expression) to update both simultaneously.
    Vizzy blinks automatically every 3-8 seconds.
    """

    VIZZY_SIZE = 64   # compact — was 100

    # Default greeting messages keyed by app state
    MESSAGES: dict[str, tuple[str, str]] = {
        "startup":     ("idle",     "Hi! I'm Vizzy. Select a file and click Process to get started."),
        "ollama_ok":   ("happy",    "Ollama is running! Select your file below and hit Process."),
        "ollama_down": ("checking", "Ollama isn't running — click 'Start Ollama' to wake it up!"),
        "starting":    ("checking", "Starting Ollama… give me a moment to wake it up. ☕"),
        "processing":  ("working",  "Analyzing your file and searching ThousandEyes docs. This may take a few minutes…"),
        "done":        ("done",     "All done! Review your answers and save the file. 🎉"),
        "error":       ("idle",     "Hmm, something went wrong. Open the Debug Log for details."),
        "no_file":     ("idle",     "Pick a file first — I accept Excel, CSV, Word, PDF, and plain text!"),
    }

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, fg_color=C_SURFACE, corner_radius=0, **kwargs)
        self._expression = "idle"
        self._blink_job: str | None = None
        self._photo = None

        # ── Main content row: mascot + bubble ─────────────────────────────
        content_row = ctk.CTkFrame(self, fg_color="transparent")
        content_row.pack(fill="x")

        self._img_lbl = ctk.CTkLabel(content_row, text="", width=self.VIZZY_SIZE)
        self._img_lbl.pack(side="left", padx=(14, 0), pady=6)

        # ── Speech bubble ─────────────────────────────────────────────────
        bubble = ctk.CTkFrame(
            content_row,
            fg_color=C_SURF2, corner_radius=14,
            border_width=1, border_color=C_BORDER,
        )
        bubble.pack(side="left", padx=12, pady=6, fill="x", expand=True)

        # Thin left accent stripe inside bubble
        ctk.CTkFrame(bubble, width=3, fg_color=C_ACCENT, corner_radius=2).pack(
            side="left", fill="y", padx=(0, 0), pady=6
        )

        bubble_text = ctk.CTkFrame(bubble, fg_color="transparent")
        bubble_text.pack(side="left", fill="x", expand=True)

        self._bubble_lbl = ctk.CTkLabel(
            bubble_text, text="",
            wraplength=560, justify="left",
            font=ctk.CTkFont(size=12), text_color=C_TEXT,
            anchor="w",
        )
        self._bubble_lbl.pack(padx=12, pady=(6, 1), anchor="w")

        # Subtle status sub-label inside the bubble
        self._status_lbl = ctk.CTkLabel(
            bubble_text, text="",
            font=ctk.CTkFont(size=10), text_color=C_MUTED,
            anchor="w",
        )
        self._status_lbl.pack(padx=12, pady=(0, 5), anchor="w")

        # ── Progress bar — slim strip ──────────────────────────────────────
        self._progress_bar = ctk.CTkProgressBar(
            self, fg_color=C_SURF2, progress_color=C_ACCENT,
            height=4, corner_radius=2,
        )
        self._progress_bar.pack(fill="x", padx=0)
        self._progress_bar.set(0)

        # Initial render
        self._render("idle")
        expr, msg = self.MESSAGES["startup"]
        self._bubble_lbl.configure(text=msg)
        self._schedule_blink()

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def progress_bar(self) -> ctk.CTkProgressBar:
        return self._progress_bar

    @property
    def status_lbl(self) -> ctk.CTkLabel:
        return self._status_lbl

    def speak(self, text: str, expression: str = "idle") -> None:
        """Update the speech bubble and Vizzy's expression."""
        self._expression = expression
        self._render(expression)
        self._bubble_lbl.configure(text=text)

    def speak_key(self, key: str) -> None:
        """Convenience: speak using a pre-defined MESSAGES key."""
        expr, msg = self.MESSAGES.get(key, ("idle", ""))
        self.speak(msg, expr)

    # ── Rendering ─────────────────────────────────────────────────────────

    def _render(self, expression: str) -> None:
        from PIL import ImageTk
        from src.vizzy import create_vizzy

        key = f"{expression}:{self.VIZZY_SIZE}"
        if key not in _VIZZY_IMG_CACHE:
            img = create_vizzy(expression=expression, size=self.VIZZY_SIZE)
            _VIZZY_IMG_CACHE[key] = ImageTk.PhotoImage(img)

        self._photo = _VIZZY_IMG_CACHE[key]
        self._img_lbl.configure(image=self._photo)

    # ── Blink animation ───────────────────────────────────────────────────

    def _schedule_blink(self) -> None:
        delay = random.randint(3_000, 8_000)
        self._blink_job = self.after(delay, self._blink)

    def _blink(self) -> None:
        self._render("blink")
        self.after(130, self._blink_restore)

    def _blink_restore(self) -> None:
        self._render(self._expression)
        self._schedule_blink()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _load_settings() -> dict:
    try:
        if SETTINGS_PATH.exists():
            return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        pass
    return {"model": "llama3.2"}


def _save_settings(s: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(s))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Answer card — one editable Q&A block in the Review panel
# ---------------------------------------------------------------------------

class CollapsibleCard(ctk.CTkFrame):
    """
    A themed card with a ▾/▸ toggle button that shows/hides its body.

    Usage
    -----
    card = CollapsibleCard(parent, "🤖  AI ENGINE")
    card.pack(fill="x", pady=(0, 12))       # or let __init__ do it via auto_pack
    some_widget = ctk.CTkLabel(card.body, text="hello")
    some_widget.pack(...)
    card.collapse()   # programmatic collapse
    card.expand()
    """

    def __init__(self, parent, title: str, *, open: bool = True) -> None:
        super().__init__(
            parent,
            fg_color=C_SURFACE,
            border_width=1,
            border_color=C_BORDER,
            corner_radius=16,
        )
        self._is_open = open

        # ── Header row (always visible) ──────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 0))

        ctk.CTkLabel(
            hdr, text=title,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C_ACCENT2, anchor="w",
        ).pack(side="left", fill="x", expand=True)

        self._toggle_btn = ctk.CTkButton(
            hdr,
            text="▾" if open else "▸",
            width=28, height=22,
            fg_color="transparent",
            hover_color=C_SURF2,
            text_color=C_ACCENT,
            font=ctk.CTkFont(size=14),
            command=self.toggle,
        )
        self._toggle_btn.pack(side="right")

        # Thin divider under header
        ctk.CTkFrame(self, height=1, fg_color=C_BORDER).pack(
            fill="x", padx=16, pady=(8, 0)
        )

        # ── Body and collapsed spacer — mutually visible ─────────────────
        self._body    = ctk.CTkFrame(self, fg_color="transparent")
        self._spacer  = ctk.CTkFrame(self, height=8, fg_color="transparent")
        if open:
            self._body.pack(fill="x")
        else:
            self._spacer.pack()

    @property
    def body(self) -> ctk.CTkFrame:
        return self._body

    def toggle(self) -> None:
        if self._is_open:
            self.collapse()
        else:
            self.expand()

    def collapse(self) -> None:
        if not self._is_open:
            return
        self._body.pack_forget()
        self._spacer.pack()
        self._toggle_btn.configure(text="▸")
        self._is_open = False

    def expand(self) -> None:
        if self._is_open:
            return
        self._spacer.pack_forget()
        self._body.pack(fill="x")
        self._toggle_btn.configure(text="▾")
        self._is_open = True


class AnswerCard(ctk.CTkFrame):
    """
    Displays one answered question with view / edit / save / cancel / reset
    controls.  State machine:

        VIEW  ──[Edit]──► EDIT ──[Save]──► VIEW  (badge = ⭐ Corrected)
                               └─[Cancel]─► VIEW  (unchanged)

    RFP requirement cards are always read-only (structured editing deferred).

    Parameters
    ----------
    parent        : parent widget
    question_dict : the ``q`` dict from processor results (mutated in-place on save)
    index         : 1-based card index for the "Q N" label
    feedback_store: shared FeedbackStore instance
    on_correction : optional callback(q, new_answer) fired after Save
    on_reset      : optional callback(q) fired after Reset
    """

    def __init__(
        self,
        parent,
        question_dict: dict,
        index: int,
        feedback_store,
        on_correction=None,
        on_reset=None,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            fg_color=C_SURFACE,
            border_width=1,
            border_color=C_BORDER,
            corner_radius=14,
            **kwargs,
        )
        self._q            = question_dict
        self._idx          = index
        self._feedback     = feedback_store
        self._on_correction = on_correction
        self._on_reset      = on_reset
        self._editing      = False

        # Snapshot the current answer so Cancel / Reset can revert cleanly
        self._current_answer  = question_dict.get("answer") or ""
        self._original_answer = question_dict.get("_original_answer") or self._current_answer
        self._has_feedback    = bool(question_dict.get("_feedback"))
        self._is_rfp          = bool(question_dict.get("rfp_requirement"))
        # Canonical question text — works for both plain Q&A and RFP rows
        self._q_text = (
            question_dict.get("question")
            or question_dict.get("rfp_requirement")
            or ""
        )

        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # ── Header: Q-index label + status badge + action buttons ─────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            hdr,
            text=f"Q{self._idx}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C_ACCENT2,
            width=34,
            anchor="w",
        ).pack(side="left")

        # Pill badge with background
        self._badge = ctk.CTkLabel(
            hdr,
            text=self._badge_text(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C_BG,
            fg_color=self._badge_color(),
            corner_radius=10,
            padx=4,
        )
        self._badge.pack(side="left", padx=(4, 0))

        # Action buttons — Edit/Save/Cancel/Reset available for all cards
        self._save_btn = ctk.CTkButton(
            hdr,
            text="💾  Save",
            width=84,
            height=26,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT2,
            text_color="#fff",
            corner_radius=12,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._do_save,
        )
        self._cancel_btn = ctk.CTkButton(
            hdr,
            text="✕",
            width=32,
            height=26,
            fg_color=C_SURF2,
            border_width=1,
            border_color=C_BORDER,
            hover_color=C_SURFACE,
            text_color=C_MUTED,
            corner_radius=12,
            font=ctk.CTkFont(size=11),
            command=self._do_cancel,
        )
        self._reset_btn = ctk.CTkButton(
            hdr,
            text="↩ Reset",
            width=76,
            height=26,
            fg_color=C_SURF2,
            border_width=1,
            border_color=C_BORDER,
            hover_color=C_SURFACE,
            text_color=C_MUTED,
            corner_radius=12,
            font=ctk.CTkFont(size=11),
            command=self._do_reset,
        )
        self._edit_btn = ctk.CTkButton(
            hdr,
            text="✏️  Edit",
            width=80,
            height=26,
            fg_color=C_SURF2,
            border_width=1,
            border_color=C_ACCENT,
            hover_color=C_SURF2,
            corner_radius=12,
            text_color=C_TEXT,
            font=ctk.CTkFont(size=11),
            command=self._do_edit,
        )
        # Initial button layout: VIEW state
        self._edit_btn.pack(side="right")
        if self._has_feedback:
            self._reset_btn.pack(side="right", padx=(0, 6))

        # ── Question text ─────────────────────────────────────────────
        q_text = self._q_text[:200]
        ctk.CTkLabel(
            self,
            text=q_text,
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            anchor="w",
            wraplength=700,
            justify="left",
        ).pack(fill="x", padx=12, pady=(0, 6))

        # ── Divider ───────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=C_BORDER).pack(
            fill="x", padx=12, pady=(0, 6)
        )

        # ── Answer area (editable for all card types) ─────────────────
        self._answer_box = ctk.CTkTextbox(
            self,
            height=84,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=C_SURF2,
            border_color=C_BORDER,
            border_width=1,
            text_color=C_TEXT,
            wrap="word",
            state="disabled",
        )
        self._answer_box.pack(fill="x", padx=12, pady=(0, 6))
        self._answer_box.configure(state="normal")
        self._answer_box.insert("1.0", self._current_answer)
        self._answer_box.configure(state="disabled")

        # ── Source URL ────────────────────────────────────────────────
        source = self._q.get("source_url")
        if source:
            ctk.CTkLabel(
                self,
                text=f"🔗 {source[:120]}",
                font=ctk.CTkFont(size=10),
                text_color=C_MUTED,
                anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 8))
        else:
            ctk.CTkFrame(self, height=6, fg_color="transparent").pack()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _badge_text(self) -> str:
        if self._has_feedback:
            return "  ⭐  Corrected  "
        if self._q.get("_cached"):
            return "  ⚡  Cached  "
        return "  ●  LLM  "

    def _badge_color(self) -> str:
        if self._has_feedback:
            return C_WARN
        if self._q.get("_cached"):
            return C_ACCENT2
        return C_MUTED

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def _do_edit(self) -> None:
        self._editing = True
        self._answer_box.configure(state="normal", border_color=C_ACCENT)
        # CTkTextbox doesn't override focus_set() — target the inner tk.Text directly
        try:
            self._answer_box._textbox.focus_set()
        except AttributeError:
            self._answer_box.focus_force()
        # Swap to EDIT buttons
        self._edit_btn.pack_forget()
        self._reset_btn.pack_forget()
        self._cancel_btn.pack(side="right", padx=(0, 4))
        self._save_btn.pack(side="right")

    def _do_cancel(self) -> None:
        self._editing = False
        # Restore answer text
        self._answer_box.configure(state="normal")
        self._answer_box.delete("1.0", "end")
        self._answer_box.insert("1.0", self._current_answer)
        self._answer_box.configure(state="disabled", border_color=C_BORDER)
        # Restore VIEW buttons
        self._save_btn.pack_forget()
        self._cancel_btn.pack_forget()
        self._edit_btn.pack(side="right")
        if self._has_feedback:
            self._reset_btn.pack(side="right", padx=(0, 6))

    def _do_save(self) -> None:
        new_answer = self._answer_box.get("1.0", "end").strip()
        if not new_answer:
            return

        question    = self._q_text
        source_url  = self._q.get("source_url")
        original    = self._original_answer

        # Persist to FeedbackStore
        self._feedback.set(
            question,
            new_answer,
            source_url=source_url,
            original_answer=original,
        )

        # Update the question dict in-place so file_writer uses the correction
        self._q["answer"]    = new_answer
        self._q["_feedback"] = True

        # For RFP cards the file-writers read rfp_result (not answer), so we
        # backfill the structured fields from the user's edited text.
        if self._is_rfp and isinstance(self._q.get("rfp_result"), dict):
            rfp = self._q["rfp_result"]
            text_lower = new_answer.lower()
            # Infer supported flag from first-line keywords
            first_line = new_answer.splitlines()[0].lower() if new_answer else ""
            if "not supported" in first_line or "❌" in new_answer.splitlines()[0]:
                rfp["supported"] = False
            elif "supported" in first_line or "✅" in new_answer.splitlines()[0]:
                rfp["supported"] = True
            # Explanation: everything after the "Features:" header line, or
            # the full text if the user wrote free-form prose.
            lines = new_answer.splitlines()
            expl_lines = [l for l in lines[1:] if l.strip()] or [new_answer]
            rfp["explanation"] = " ".join(expl_lines).strip() or new_answer

        # Update internal state
        self._current_answer = new_answer
        self._has_feedback   = True
        self._editing        = False

        # Update answer box to read-only with new text
        self._answer_box.configure(state="normal")
        self._answer_box.delete("1.0", "end")
        self._answer_box.insert("1.0", new_answer)
        self._answer_box.configure(state="disabled", border_color=C_BORDER)

        # Update badge
        self._badge.configure(
            text=self._badge_text(), text_color=C_BG, fg_color=self._badge_color()
        )

        # Restore buttons to VIEW + show Reset
        self._save_btn.pack_forget()
        self._cancel_btn.pack_forget()
        self._edit_btn.pack(side="right")
        self._reset_btn.pack(side="right", padx=(0, 6))

        if self._on_correction:
            self._on_correction(self._q, new_answer)

    def _do_reset(self) -> None:
        question = self._q_text
        self._feedback.remove(question)

        # Revert to original LLM/cached answer
        self._q["answer"]    = self._original_answer
        self._q["_feedback"] = False
        self._has_feedback   = False
        self._current_answer = self._original_answer

        # Update answer box
        self._answer_box.configure(state="normal")
        self._answer_box.delete("1.0", "end")
        self._answer_box.insert("1.0", self._original_answer)
        self._answer_box.configure(state="disabled")

        # Update badge
        self._badge.configure(
            text=self._badge_text(), text_color=C_BG, fg_color=self._badge_color()
        )

        # Hide Reset button
        self._reset_btn.pack_forget()

        if self._on_reset:
            self._on_reset(self._q)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Customer Questionnaire Crusher")
        self.geometry("900x860")
        self.minsize(720, 660)
        self.configure(fg_color=C_BG)

        self._settings = _load_settings()
        self._file: str | None = None
        self._results: dict | None = None
        self._busy = False
        self._debug_win: DebugWindow | None = None

        # Shared FeedbackStore — persists user corrections across the session.
        # Loaded once at startup; AnswerCard writes to it in-place on Save.
        from src.feedback import FeedbackStore
        self._feedback_store = FeedbackStore()

        # Thread-safe UI update queue (background threads post here;
        # _poll_ui_queue drains it on the main thread every 40 ms)
        self._ui_q: _queue.Queue = _queue.Queue()

        _log("App init started")
        _log(f"Python {sys.version.split()[0]} on {sys.platform}")
        _log(f"CWD: {os.getcwd()}")

        self._build_menubar()
        self._build_ui()

        # Start polling the UI queue
        self._poll_ui_queue()

        # Check whether setup is needed; if not, probe Ollama status directly.
        self.after(400, self._maybe_show_setup)

    # -----------------------------------------------------------------------
    # Thread-safe UI queue
    # -----------------------------------------------------------------------

    def _post_ui(self, fn) -> None:
        """Queue a callable to run on the main thread. Safe from any thread."""
        self._ui_q.put(fn)

    def _poll_ui_queue(self) -> None:
        """Drain all pending UI callbacks. Runs only on the main thread."""
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception as exc:
                    _log_exc(f"UI queue callback error: {exc}")
        except _queue.Empty:
            pass
        self.after(40, self._poll_ui_queue)

    # -----------------------------------------------------------------------
    # Menu bar
    # -----------------------------------------------------------------------

    def _build_menubar(self) -> None:
        menubar = Menu(self)
        self.configure(menu=menubar)

        # ── Tools menu ────────────────────────────────────────────────
        tools_menu = Menu(menubar, tearoff=0,
                          bg=C_SURFACE, fg=C_TEXT,
                          activebackground=C_ACCENT, activeforeground=C_BG)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Cache Stats…",
                               command=self._show_cache_stats)
        tools_menu.add_command(label="Clear Answer Cache…",
                               command=self._clear_cache)
        tools_menu.add_separator()
        tools_menu.add_command(label="Feedback Stats…",
                               command=self._show_feedback_stats)
        tools_menu.add_command(label="Clear All Feedback…",
                               command=self._clear_feedback)

        # ── Debug menu ────────────────────────────────────────────────
        debug_menu = Menu(menubar, tearoff=0,
                          bg=C_SURFACE, fg=C_TEXT,
                          activebackground=C_ACCENT, activeforeground=C_BG)
        menubar.add_cascade(label="Debug", menu=debug_menu)
        debug_menu.add_command(label="Open Debug Log…",
                               command=self._open_debug_log)
        debug_menu.add_command(label="Copy Log to Clipboard",
                               command=self._copy_log_to_clipboard)
        debug_menu.add_separator()
        debug_menu.add_command(label="Re-run Setup Wizard…",
                               command=lambda: self._run_setup_wizard(force=True))
        debug_menu.add_separator()
        debug_menu.add_command(label="Check Ollama (verbose)",
                               command=self._verbose_ollama_check)
        debug_menu.add_command(label="Clear Log",
                               command=lambda: (_debug_lines.clear(),
                                                _log("Log cleared.")))

    # -----------------------------------------------------------------------
    # First-run setup wizard
    # -----------------------------------------------------------------------

    def _maybe_show_setup(self) -> None:
        """
        Called once after the main window has finished drawing.
        Shows the setup wizard if Ollama is not installed; otherwise runs the
        normal Ollama status probe.
        """
        if needs_ollama_setup():
            _log("Ollama not detected — showing Setup Wizard.")
            self._run_setup_wizard()
        else:
            self._refresh_ollama_status()

    def _run_setup_wizard(self, force: bool = False) -> None:
        """
        Open the Setup Wizard as a modal dialog.

        Parameters
        ----------
        force:
            If True (e.g. from the Debug menu) the wizard is shown even when
            Ollama is already installed, so the user can change their model or
            repair a broken installation.
        """
        _log(f"Opening Setup Wizard (force={force})")
        wizard = SetupWizard(self, on_complete=self._on_setup_complete)
        self.wait_window(wizard)   # blocks event loop until wizard.destroy()

    def _on_setup_complete(self, model: str) -> None:
        """
        Called by SetupWizard when the user clicks 'Finish Setup' (or closes
        the wizard early with an empty model string).
        Updates the model dropdown and refreshes the Ollama status indicator.
        """
        if model:
            _log(f"Setup complete — selected model: {model}")
            if hasattr(self, "_model_var"):
                self._model_var.set(model)
                # Persist the choice so it survives restarts
                settings = _load_settings()
                settings["model"] = model
                _save_settings(settings)
        else:
            _log("Setup wizard closed early — no model selected.")

        # Refresh Ollama status regardless of whether setup completed
        self.after(400, self._refresh_ollama_status)

    # -----------------------------------------------------------------------
    # Cache actions
    # -----------------------------------------------------------------------

    def _show_cache_stats(self) -> None:
        from src.cache import AnswerCache
        model = self._model_var.get()
        stats = AnswerCache(model=model).stats()
        n     = stats["entries"]
        kb    = stats["size_kb"]
        _log(f"Cache stats: {n} entries, {kb} KB")
        messagebox.showinfo(
            "Answer Cache",
            f"Cached answers: {n} entry/entries\n"
            f"Disk usage:     {kb} KB\n"
            f"Location:       ~/.te_qa_cache/\n"
            f"TTL:            7 days\n\n"
            "Cache stores LLM answers so re-processing the same file\n"
            "(or resuming after a crash) skips expensive AI inference.",
        )

    def _clear_cache(self) -> None:
        if not messagebox.askyesno(
            "Clear Answer Cache",
            "Delete all cached answers?\n\n"
            "This will force every question to be re-answered by the AI\n"
            "the next time a file is processed.\n\n"
            "Proceed?",
        ):
            return
        from src.cache import AnswerCache
        model   = self._model_var.get()
        deleted = AnswerCache(model=model).clear()
        _log(f"Cache cleared: {deleted} files deleted.")
        self._vizzy.speak(
            f"Cache cleared! Deleted {deleted} stored answer{'s' if deleted != 1 else ''}. "
            "Next run will fetch fresh answers from ThousandEyes docs.",
            "happy",
        )
        messagebox.showinfo("Cache Cleared", f"Deleted {deleted} cached answer(s).")

    # -----------------------------------------------------------------------
    # Feedback actions
    # -----------------------------------------------------------------------

    def _show_feedback_stats(self) -> None:
        stats = self._feedback_store.stats()
        n     = stats["entries"]
        path  = stats["path"]
        _log(f"Feedback stats: {n} entries at {path}")
        messagebox.showinfo(
            "Answer Feedback",
            f"Saved corrections: {n} entry/entries\n"
            f"Location:          {path}\n\n"
            "Corrections are permanent (no expiry) and take priority over\n"
            "the AI cache and fresh inference on future runs.\n\n"
            "Fuzzy matching applies corrections to questions that are\n"
            "≥ 80 % similar to a stored one (handles minor rephrasing).",
        )

    def _clear_feedback(self) -> None:
        n = self._feedback_store.stats()["entries"]
        if n == 0:
            messagebox.showinfo("No Feedback", "There are no saved corrections to clear.")
            return
        if not messagebox.askyesno(
            "Clear All Feedback",
            f"Permanently delete all {n} saved correction{'s' if n != 1 else ''}?\n\n"
            "This cannot be undone — the AI will re-evaluate those questions\n"
            "from scratch on the next run.\n\n"
            "Proceed?",
        ):
            return
        deleted = self._feedback_store.clear()
        _log(f"Feedback cleared: {deleted} corrections deleted.")
        self._vizzy.speak(
            f"Cleared {deleted} saved correction{'s' if deleted != 1 else ''}. "
            "The AI will answer those questions fresh on the next run.",
            "idle",
        )
        messagebox.showinfo(
            "Feedback Cleared",
            f"Deleted {deleted} saved correction(s).",
        )

    def _open_debug_log(self) -> None:
        if self._debug_win and self._debug_win.winfo_exists():
            self._debug_win.lift()
            return
        self._debug_win = DebugWindow(self)

    def _copy_log_to_clipboard(self) -> None:
        self.clipboard_clear()
        self.clipboard_append("\n".join(_debug_lines))
        _log("Log copied to clipboard.")

    def _verbose_ollama_check(self) -> None:
        _log("=== Verbose Ollama check triggered ===")
        self._open_debug_log()
        threading.Thread(target=self._verbose_ollama_thread, daemon=True).start()

    def _verbose_ollama_thread(self) -> None:
        import shutil, subprocess
        _log(f"shutil.which('ollama') = {shutil.which('ollama')}")
        try:
            r = subprocess.run(["ollama", "list"],
                               capture_output=True, text=True, timeout=10)
            _log(f"ollama list stdout: {r.stdout.strip()}")
            _log(f"ollama list stderr: {r.stderr.strip()}")
            _log(f"ollama list returncode: {r.returncode}")
        except Exception as exc:
            _log_exc(f"ollama list failed: {exc}")
        try:
            import requests
            r2 = requests.get("http://localhost:11434/api/tags", timeout=5)
            _log(f"HTTP /api/tags status: {r2.status_code}")
            _log(f"HTTP /api/tags body: {r2.text[:400]}")
        except Exception as exc:
            _log_exc(f"HTTP check failed: {exc}")

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Vizzy bar — compact strip across the top of the window
        self._vizzy = VizzyBar(self)
        self._vizzy.pack(fill="x")
        # Alias the widgets so all existing code keeps working unchanged
        self._progress_bar = self._vizzy.progress_bar
        self._status_lbl   = self._vizzy.status_lbl

        # Thin divider
        ctk.CTkFrame(self, height=1, fg_color=C_BORDER).pack(fill="x")

        # Plain (non-scrolling) outer frame — only the review section scrolls
        content = ctk.CTkFrame(self, fg_color=C_BG)
        content.pack(fill="both", expand=True, padx=24, pady=(10, 0))

        # AI Engine + File Input side-by-side (process btn lives inside file card)
        card_row = ctk.CTkFrame(content, fg_color="transparent")
        card_row.pack(fill="x", pady=(0, 12))
        self._build_ollama_card(card_row)
        self._build_file_card(card_row)

        self._build_results_card(content)

        # Save pinned to bottom; review fills the remaining space above it
        self._build_save_btn(content)
        self._build_review_section(content)

        # Footer — cache / feedback controls on the left, debug log on the right
        footer = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0)
        footer.pack(fill="x", side="bottom")

        # Right side: debug log
        ctk.CTkButton(
            footer, text="🐛 Debug Log", width=120,
            fg_color="transparent", hover_color=C_SURF2,
            text_color=C_MUTED, font=ctk.CTkFont(size=11),
            command=self._open_debug_log,
        ).pack(side="right", padx=(4, 12), pady=6)

        # Left side: cache and feedback clear buttons
        ctk.CTkButton(
            footer, text="🗑  Clear LLM Cache", width=150,
            fg_color="transparent", hover_color=C_SURF2,
            text_color=C_MUTED, font=ctk.CTkFont(size=11),
            command=self._clear_cache,
        ).pack(side="left", padx=(12, 0), pady=6)

        ctk.CTkButton(
            footer, text="↩  Clear Corrections", width=150,
            fg_color="transparent", hover_color=C_SURF2,
            text_color=C_MUTED, font=ctk.CTkFont(size=11),
            command=self._clear_feedback,
        ).pack(side="left", padx=(4, 0), pady=6)

        # Thin divider between left buttons and right debug log
        ctk.CTkFrame(footer, width=1, fg_color=C_BORDER).pack(
            side="right", fill="y", pady=4, padx=4
        )

    # ---- header ----

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(fill="x", padx=32, pady=20)

        # Title row: accent dot + app name
        title_row = ctk.CTkFrame(inner, fg_color="transparent")
        title_row.pack(anchor="w", fill="x")

        ctk.CTkLabel(
            title_row, text="●",
            font=ctk.CTkFont(size=18), text_color=C_ACCENT,
        ).pack(side="left", padx=(0, 10), pady=(2, 0))

        ctk.CTkLabel(
            title_row, text="Customer Questionnaire Crusher",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=C_TEXT,
        ).pack(side="left")

        ctk.CTkLabel(
            inner,
            text="100 % local AI  •  No API keys  •  Answers sourced only from docs.thousandeyes.com",
            font=ctk.CTkFont(size=12), text_color=C_MUTED,
        ).pack(anchor="w", pady=(4, 0))

        # Thin purple accent line under the header
        ctk.CTkFrame(hdr, height=2, fg_color=C_ACCENT, corner_radius=0).pack(fill="x")

    # ---- Ollama status card ----

    def _build_ollama_card(self, parent) -> None:
        self._ollama_card = CollapsibleCard(parent, "🤖  AI ENGINE  (Ollama — local)")
        self._ollama_card.pack(side="left", fill="both", expand=True, padx=(0, 6))
        card = self._ollama_card.body

        # Status row
        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=16, pady=(4, 0))

        ctk.CTkLabel(status_row, text="Status:", width=70,
                     font=ctk.CTkFont(size=13), text_color=C_TEXT).pack(side="left")

        self._ollama_status_dot = ctk.CTkLabel(
            status_row, text="●", font=ctk.CTkFont(size=14), text_color=C_MUTED
        )
        self._ollama_status_dot.pack(side="left", padx=(4, 6))

        self._ollama_status_lbl = ctk.CTkLabel(
            status_row, text="Checking…",
            font=ctk.CTkFont(size=13), text_color=C_MUTED
        )
        self._ollama_status_lbl.pack(side="left")

        ctk.CTkButton(
            status_row, text="⟳ Refresh", width=90,
            fg_color=C_SURF2, border_width=1, border_color=C_BORDER,
            hover_color=C_SURFACE, text_color=C_ACCENT2,
            corner_radius=10,
            command=self._refresh_ollama_status,
        ).pack(side="right")

        ctk.CTkButton(
            status_row, text="Start Ollama", width=110,
            fg_color=C_SURF2, border_width=1, border_color=C_BORDER,
            hover_color=C_SURFACE, text_color=C_WARN,
            corner_radius=10,
            command=self._start_ollama,
        ).pack(side="right", padx=(0, 8))

        # Model selector row
        model_row = ctk.CTkFrame(card, fg_color="transparent")
        model_row.pack(fill="x", padx=16, pady=(10, 12))

        ctk.CTkLabel(model_row, text="Model:", width=70,
                     font=ctk.CTkFont(size=13), text_color=C_TEXT).pack(side="left")

        self._model_var = ctk.StringVar(
            value=self._settings.get("model", "llama3.2")
        )
        self._model_menu = ctk.CTkOptionMenu(
            model_row,
            values=RECOMMENDED_MODELS,
            variable=self._model_var,
            fg_color=C_SURF2,
            button_color=C_SURF2,
            button_hover_color=C_SURFACE,
            dropdown_fg_color=C_SURF2,
            width=220,
            command=self._on_model_change,
        )
        self._model_menu.pack(side="left", padx=(10, 14))

        self._model_hint = ctk.CTkLabel(
            model_row,
            text="phi3:mini / llama3.2 → fast  |  llama3.1:8b → best quality",
            font=ctk.CTkFont(size=11), text_color=C_MUTED,
        )
        self._model_hint.pack(side="left")

    # ---- File card ----

    def _build_file_card(self, parent) -> None:
        self._file_card = CollapsibleCard(parent, "📁  INPUT FILE")
        self._file_card.pack(side="left", fill="both", expand=True, padx=(6, 0))
        card = self._file_card.body

        self._drop_zone = ctk.CTkFrame(
            card, height=96, fg_color=C_SURF2,
            border_width=2, border_color=C_BORDER, corner_radius=14,
        )
        self._drop_zone.pack(fill="x", padx=16, pady=(8, 12))
        self._drop_zone.pack_propagate(False)

        self._drop_lbl = ctk.CTkLabel(
            self._drop_zone,
            text="Click to select a file\nExcel  ·  CSV  ·  Word  ·  PDF  ·  Plain text",
            font=ctk.CTkFont(size=13), text_color=C_MUTED, justify="center",
        )
        self._drop_lbl.pack(expand=True)

        for w in (self._drop_zone, self._drop_lbl):
            w.bind("<Button-1>", lambda _: self._browse_file())
            w.bind("<Enter>",    lambda _: self._drop_zone.configure(border_color=C_ACCENT))
            w.bind("<Leave>",    lambda _: self._drop_zone.configure(border_color=C_BORDER))

        # Process File button lives inside the File Input card
        self._process_btn = ctk.CTkButton(
            card, text="▶  Process File",
            height=44, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C_ACCENT, hover_color=C_ACCENT2, corner_radius=14,
            command=self._start_processing,
        )
        self._process_btn.pack(fill="x", padx=16, pady=(0, 14))

    # ---- Progress card ----

    def _build_progress_card(self, parent) -> None:
        card = self._card(parent, "⏳  PROGRESS")

        self._status_lbl = ctk.CTkLabel(
            card, text="Ready — select a file and click Process File.",
            font=ctk.CTkFont(size=12), text_color=C_MUTED, anchor="w",
        )
        self._status_lbl.pack(fill="x", padx=16, pady=(4, 6))

        self._progress_bar = ctk.CTkProgressBar(
            card, fg_color=C_SURF2, progress_color=C_ACCENT,
            height=10, corner_radius=5,
        )
        self._progress_bar.pack(fill="x", padx=16, pady=(0, 14))
        self._progress_bar.set(0)

    # ---- Results card ----

    def _build_results_card(self, parent) -> None:
        # Starts collapsed — expands automatically when results are ready
        self._results_card = CollapsibleCard(parent, "📊  RESULTS", open=False)
        self._results_card.pack(fill="x", pady=(0, 12))
        body = self._results_card.body

        self._results_box = ctk.CTkTextbox(
            body, height=120,
            font=ctk.CTkFont(family="Menlo", size=12),
            fg_color=C_SURF2, border_color=C_BORDER, border_width=1,
            text_color=C_TEXT, wrap="word",
        )
        self._results_box.pack(fill="x", padx=16, pady=(4, 14))
        self._results_box.insert("1.0", "No results yet.")
        self._results_box.configure(state="disabled")

    # ---- Save button ----

    def _build_save_btn(self, parent) -> None:
        self._save_btn = ctk.CTkButton(
            parent, text="💾   Save Updated File",
            height=48, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=C_ACCENT, hover_color=C_ACCENT2, corner_radius=14,
            state="disabled", command=self._save_output,
        )
        # side="bottom" so review section fills the space above it
        self._save_btn.pack(side="bottom", fill="x", pady=(8, 16))

    # ---- Review & Edit panel (3-column spreadsheet) ----

    def _build_review_section(self, parent) -> None:
        """
        Sticky-header 3-column spreadsheet view + arrow-button scrolling.
        The header sits ABOVE the CTkScrollableFrame so it never scrolls away.

        Pack order matters: UP arrow → header → (DOWN arrow last-but-side=bottom) → scroll.
        Packing dn_btn with side="bottom" BEFORE the scroll reserves its space;
        _review_scroll(expand=True) then fills everything in between.
        """
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, pady=(0, 16))

        # ── Active filter state ─────────────────────────────────────────
        self._active_filter = "all"

        # ── Filter bar (#4) — compact pill buttons ─────────────────────
        filter_row = ctk.CTkFrame(wrap, fg_color=C_SURF2, corner_radius=8,
                                  border_width=1, border_color=C_BORDER)
        filter_row.pack(side="top", fill="x", pady=(0, 4))

        # Store refs so _apply_filter can toggle active styling
        self._filter_btns: dict[str, ctk.CTkButton] = {}

        for flt_val, flt_lbl in [
            ("all",            "All"),
            ("yes",            "✓ Supported"),
            ("partial",        "⚠ Partial"),
            ("not_applicable", "○ N/A"),
        ]:
            btn = ctk.CTkButton(
                filter_row,
                text=flt_lbl,
                width=100, height=26,
                fg_color=C_ACCENT if flt_val == "all" else "transparent",
                hover_color=C_SURF2,
                border_width=1,
                border_color=C_ACCENT if flt_val == "all" else C_BORDER,
                text_color="#fff" if flt_val == "all" else C_MUTED,
                font=ctk.CTkFont(size=11, weight="bold"),
                corner_radius=6,
                command=lambda v=flt_val: self._apply_filter(v),
            )
            btn.pack(side="left", padx=4, pady=6)
            self._filter_btns[flt_val] = btn

        # Compact inline summary label — right-aligned in the same row (#3)
        self._stats_summary_lbl = ctk.CTkLabel(
            filter_row, text="",
            font=ctk.CTkFont(size=11), text_color=C_MUTED,
            anchor="e",
        )
        self._stats_summary_lbl.pack(side="right", padx=12)

        # ── Scroll arrow — UP (side=top) ───────────────────────────────
        up_btn = ctk.CTkButton(
            wrap, text="▲", height=20,
            fg_color=C_SURF2, hover_color=C_BORDER,
            border_width=1, border_color=C_BORDER,
            text_color=C_ACCENT, font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=8,
            command=lambda: self._review_scroll._parent_canvas.yview_scroll(-3, "units"),
        )
        up_btn.pack(side="top", fill="x")

        # ── Scroll arrow — DOWN (side=bottom, packed BEFORE scroll) ───
        # Pack this first so pack reserves space for it; otherwise
        # expand=True on _review_scroll consumes all remaining room.
        dn_btn = ctk.CTkButton(
            wrap, text="▼", height=20,
            fg_color=C_SURF2, hover_color=C_BORDER,
            border_width=1, border_color=C_BORDER,
            text_color=C_ACCENT, font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=8,
            command=lambda: self._review_scroll._parent_canvas.yview_scroll(3, "units"),
        )
        dn_btn.pack(side="bottom", fill="x")

        # ── Sticky column header (side=top, between arrows and scroll) ─
        # Use a plain tk.Frame with pack_propagate(False) so it stays
        # thin regardless of child widget default sizes.
        import tkinter as _tk
        hdr_frame = _tk.Frame(wrap, bg=C_SURF2, bd=0, height=34)
        hdr_frame.pack(side="top", fill="x")
        hdr_frame.pack_propagate(False)   # lock to height=34

        hdr_font = ctk.CTkFont(size=11, weight="bold")

        def _hdr_lbl(text, w, fg=C_ACCENT2, anchor="w"):
            lbl = _tk.Label(
                hdr_frame, text=text, width=1,  # width in chars; overridden by pack
                bg=C_SURF2, fg=fg, font=("Helvetica", 11, "bold"),
                anchor=anchor, padx=6,
            )
            lbl.pack(side="left", fill="both", ipadx=0)
            return lbl

        def _hdr_sep():
            _tk.Frame(hdr_frame, bg=C_BORDER, width=1).pack(side="left", fill="y")

        # Reserve pixel widths using a sub-frame per column so widths match data rows
        for col_text, col_w, col_fg, col_anch in [
            ("#",          _SC_NUM,   C_MUTED,   "center"),
            ("QUESTION",   _SC_Q,     C_ACCENT2, "w"),
            ("SUPPORT",    _SC_BADGE, C_ACCENT2, "center"),
            ("ANSWER",     _SC_A,     C_ACCENT2, "w"),
            ("SOURCE URL", _SC_URL,   C_ACCENT2, "w"),
        ]:
            _tk.Frame(hdr_frame, bg=C_BORDER, width=1).pack(side="left", fill="y")
            cell = _tk.Frame(hdr_frame, bg=C_SURF2, width=col_w, bd=0)
            cell.pack(side="left", fill="y")
            cell.pack_propagate(False)
            _tk.Label(
                cell, text=col_text, bg=C_SURF2, fg=col_fg,
                font=("Helvetica", 11, "bold"), anchor=col_anch, padx=6,
            ).pack(fill="both", expand=True)

        # ── Scrollable data area (fills all remaining space) ───────────
        self._review_scroll = ctk.CTkScrollableFrame(
            wrap, fg_color="transparent", scrollbar_button_color=C_ACCENT,
        )
        self._review_scroll.pack(side="top", fill="both", expand=True)

        # ── Two-finger / trackpad scroll (macOS-correct) ────────────────
        import platform as _plat
        _is_mac = _plat.system() == "Darwin"

        def _on_scroll(event):
            canvas = self._review_scroll._parent_canvas
            if _is_mac:
                canvas.yview_scroll(-event.delta, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def _bind_scroll(widget):
            widget.bind("<MouseWheel>", _on_scroll, add="+")

        self._review_scroll._parent_canvas.bind("<MouseWheel>", _on_scroll)
        self._review_scroll.bind("<MouseWheel>", _on_scroll, add="+")
        self._bind_scroll_to_widget = _bind_scroll

        # Container for spreadsheet rows
        self._review_container = ctk.CTkFrame(
            self._review_scroll, fg_color="transparent"
        )
        self._review_container.pack(fill="x")
        _bind_scroll(self._review_container)

    # One card per event-loop tick (each AnswerCard ≈12 CTk widgets, ~25 ms)
    # 35 ms yield between cards keeps every freeze < 60 ms (imperceptible)
    _CARD_BATCH = 1
    _CARD_DELAY = 35   # ms between cards

    # ---------------------------------------------------------------------------
    # Spreadsheet review panel
    # ---------------------------------------------------------------------------

    def _populate_review(self, questions: list[dict]) -> None:
        """
        Rebuild the 3-column spreadsheet view from *questions*.
        Rows are created one per event-loop tick so the UI stays responsive.
        """
        # Cancel any in-progress batch from a previous run
        job = getattr(self, "_sheet_batch_job", None)
        if job is not None:
            self.after_cancel(job)
            self._sheet_batch_job = None

        # Tear down previous rows
        for child in self._review_container.winfo_children():
            child.destroy()

        # Storage: list of {"q": dict, "ans_box": CTkTextbox, "url_entry": CTkEntry}
        self._sheet_rows: list[dict] = []

        answered = [q for q in questions if q.get("answer")]
        if not answered:
            # ── Empty state (#9) ──────────────────────────────────────────
            empty = ctk.CTkFrame(self._review_container, fg_color="transparent")
            empty.pack(fill="x", pady=40)

            ctk.CTkLabel(
                empty, text="📋",
                font=ctk.CTkFont(size=52), text_color=C_MUTED,
            ).pack(pady=(0, 10))
            ctk.CTkLabel(
                empty, text="No Results Yet",
                font=ctk.CTkFont(size=18, weight="bold"), text_color=C_TEXT,
            ).pack()
            ctk.CTkLabel(
                empty,
                text="Select a file above and click  ▶ Process File  to see answers here.",
                font=ctk.CTkFont(size=12), text_color=C_MUTED,
            ).pack(pady=(6, 20))

            # Supported-format pills
            fmt_row = ctk.CTkFrame(empty, fg_color=C_SURF2,
                                   corner_radius=10, border_width=1,
                                   border_color=C_BORDER)
            fmt_row.pack(ipadx=14, ipady=12)
            ctk.CTkLabel(
                fmt_row,
                text="SUPPORTED FORMATS",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C_MUTED,
            ).pack(pady=(10, 6))
            pill_row = ctk.CTkFrame(fmt_row, fg_color="transparent")
            pill_row.pack(padx=14, pady=(0, 10))
            for fmt_text in ["📄 Word (.docx)", "📊 Excel (.xlsx)",
                             "📕 PDF", "📋 CSV", "📝 Text"]:
                ctk.CTkLabel(
                    pill_row, text=fmt_text,
                    font=ctk.CTkFont(size=11), text_color=C_TEXT,
                    fg_color=C_SURFACE, corner_radius=6,
                    padx=10, pady=4,
                ).pack(side="left", padx=4)
            return

        # Queue up rows for incremental rendering
        self._sheet_queue: list[tuple[int, dict]] = list(enumerate(answered, 1))
        self._sheet_queue_total: int = len(answered)
        self._sheet_batch_job = self.after(0, self._drain_sheet_queue)

    def _drain_sheet_queue(self) -> None:
        """Build ONE spreadsheet row per event-loop tick; reschedule until done."""
        self._sheet_batch_job = None
        queue = getattr(self, "_sheet_queue", None)
        if not queue:
            return

        idx, q = queue.pop(0)
        alt         = (idx % 2 == 0)
        bind_scroll = getattr(self, "_bind_scroll_to_widget", None)

        # Determine support level for tinting & badge (#1 #2)
        rfp_result    = q.get("rfp_result") or {}
        support_level = rfp_result.get("support_level") if rfp_result else None
        row_bg        = _row_bg_for_level(support_level, alt)

        # ── Thin top-border separator ─────────────────────────────────
        sep_frame = None
        if idx > 1:
            sep_frame = ctk.CTkFrame(
                self._review_container, height=1, fg_color=C_BORDER, corner_radius=0
            )
            sep_frame.pack(fill="x")
            if bind_scroll:
                bind_scroll(sep_frame)

        # ── Row frame ─────────────────────────────────────────────────
        row = ctk.CTkFrame(
            self._review_container, fg_color=row_bg, corner_radius=0
        )
        row.pack(fill="x")
        if bind_scroll:
            bind_scroll(row)

        # ── Row-number gutter ─────────────────────────────────────────
        ctk.CTkLabel(
            row, text=str(idx), width=_SC_NUM, anchor="center",
            font=ctk.CTkFont(size=10), text_color=C_MUTED,
        ).pack(side="left", padx=(4, 0), pady=6)

        ctk.CTkFrame(row, width=_SC_SEP, fg_color=C_BORDER).pack(
            side="left", fill="y", pady=4)

        # ── Question (read-only label, wraps) ─────────────────────────
        q_text = (q.get("question") or q.get("rfp_requirement") or "").strip()
        q_lbl = ctk.CTkLabel(
            row, text=q_text, width=_SC_Q, anchor="nw",
            font=ctk.CTkFont(size=11), text_color=C_TEXT,
            wraplength=_SC_Q - 12, justify="left",
        )
        q_lbl.pack(side="left", padx=(8, 4), pady=6)
        if bind_scroll:
            bind_scroll(q_lbl)

        ctk.CTkFrame(row, width=_SC_SEP, fg_color=C_BORDER).pack(
            side="left", fill="y", pady=4)

        # ── Support-level badge column (#1) ───────────────────────────
        badge_text, badge_bg, badge_fg = _support_badge_config(support_level)
        badge_cell = ctk.CTkFrame(row, width=_SC_BADGE, fg_color="transparent")
        badge_cell.pack(side="left", fill="y", padx=4, pady=6)
        badge_cell.pack_propagate(False)
        ctk.CTkLabel(
            badge_cell,
            text=badge_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=badge_fg,
            fg_color=badge_bg,
            corner_radius=8,
            padx=6, pady=3,
        ).place(relx=0.5, rely=0.5, anchor="center")
        if bind_scroll:
            bind_scroll(badge_cell)

        ctk.CTkFrame(row, width=_SC_SEP, fg_color=C_BORDER).pack(
            side="left", fill="y", pady=4)

        # ── Answer (editable textbox) + expand toggle (#8) ───────────
        _ans_collapsed_h = 56
        _ans_expanded_h  = 144
        ans_box = ctk.CTkTextbox(
            row, width=_SC_A, height=_ans_collapsed_h,
            font=ctk.CTkFont(size=11),
            fg_color=C_SURF2 if alt else C_SURFACE,
            border_width=1, border_color=C_BORDER,
            text_color=C_TEXT, wrap="word",
        )
        ans_box.insert("1.0", q.get("answer") or "")
        ans_box.pack(side="left", padx=4, pady=6)
        if bind_scroll:
            def _scroll_if_no_shift(event, _ans=ans_box):
                if not (event.state & 0x0001):
                    canvas = self._review_scroll._parent_canvas
                    import platform as _p
                    if _p.system() == "Darwin":
                        canvas.yview_scroll(-event.delta, "units")
                    else:
                        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return "break"
            ans_box.bind("<MouseWheel>", _scroll_if_no_shift)

        # Expand/collapse toggle button (#8)
        _expanded = [False]

        def _toggle_expand(_ab=ans_box, _exp=_expanded,
                           _ch=_ans_collapsed_h, _eh=_ans_expanded_h):
            if _exp[0]:
                _ab.configure(height=_ch)
                _exp[0] = False
                expand_btn.configure(text="▾")
            else:
                _ab.configure(height=_eh)
                _exp[0] = True
                expand_btn.configure(text="▴")

        expand_btn = ctk.CTkButton(
            row, text="▾", width=20, height=_ans_collapsed_h,
            fg_color="transparent", hover_color=C_SURF2,
            text_color=C_ACCENT, font=ctk.CTkFont(size=11),
            command=_toggle_expand,
        )
        expand_btn.pack(side="left", pady=6)

        ctk.CTkFrame(row, width=_SC_SEP, fg_color=C_BORDER).pack(
            side="left", fill="y", pady=4)

        # ── Source URL (editable entry) ───────────────────────────────
        url_entry = ctk.CTkEntry(
            row, width=_SC_URL,
            font=ctk.CTkFont(size=10),
            fg_color=C_SURF2 if alt else C_SURFACE,
            border_width=1, border_color=C_BORDER,
            text_color=C_BLUE, placeholder_text="https://…",
        )
        url_entry.insert(0, q.get("source_url") or "")
        url_entry.pack(side="left", padx=(4, 8), pady=6)
        if bind_scroll:
            bind_scroll(url_entry)

        # ── Store row refs for filtering + save-time collection ───────
        self._sheet_rows.append({
            "q":             q,
            "ans_box":       ans_box,
            "url_entry":     url_entry,
            "row_frame":     row,
            "sep_frame":     sep_frame,
            "support_level": support_level or "",
        })

        # ── Reschedule or finish ──────────────────────────────────────
        remaining = len(queue)
        total     = self._sheet_queue_total
        done      = total - remaining

        if remaining:
            if done % 10 == 1:
                self._status_lbl.configure(text=f"Loading… {done}/{total}")
            self._sheet_batch_job = self.after(self._CARD_DELAY, self._drain_sheet_queue)
        else:
            self._status_lbl.configure(
                text=f"Done — {total} answer{'s' if total != 1 else ''} ready to review."
            )

    def _on_feedback_saved(self, q: dict, new_answer: str) -> None:
        """Fired by AnswerCard after a correction is saved."""
        _log(f"Feedback saved: key={q.get('_cache_key', '')[:40]}…")
        self._vizzy.speak(
            "Got it! I've saved your correction. "
            "Next time a similar question comes up, I'll use your answer instead. ⭐",
            "happy",
        )

    def _on_feedback_reset(self, q: dict) -> None:
        """Fired by AnswerCard when a correction is reverted."""
        _log(f"Feedback reset for: {q.get('question', '')[:60]}…")
        self._vizzy.speak(
            "Reverted to the original AI answer.",
            "idle",
        )

    # -----------------------------------------------------------------------
    # Filter (#4)
    # -----------------------------------------------------------------------

    def _apply_filter(self, filter_val: str) -> None:
        """
        Show / hide spreadsheet rows by support level without re-rendering.
        Toggling visibility preserves any unsaved edits the user typed.
        """
        self._active_filter = filter_val

        # Update button styling — active button gets solid accent colour
        _ACTIVE_COLORS = {
            "all":            (C_ACCENT,  "#fff"),
            "yes":            (C_SUCCESS, "#fff"),
            "partial":        (C_WARN,    "#000"),
            "not_applicable": (C_MUTED,   C_BG),
        }
        for val, btn in self._filter_btns.items():
            if val == filter_val:
                fg, tc = _ACTIVE_COLORS.get(val, (C_ACCENT, "#fff"))
                btn.configure(fg_color=fg, text_color=tc, border_color=fg)
            else:
                btn.configure(fg_color="transparent", text_color=C_MUTED,
                               border_color=C_BORDER)

        # Show / hide rows (no widget rebuild — edits are preserved)
        rows = getattr(self, "_sheet_rows", [])
        for entry in rows:
            level   = entry.get("support_level", "")
            visible = filter_val == "all" or level == filter_val

            sep = entry.get("sep_frame")
            row = entry.get("row_frame")
            if row is None:
                continue

            if visible:
                if sep:
                    sep.pack(fill="x")
                row.pack(fill="x")
            else:
                if sep:
                    sep.pack_forget()
                row.pack_forget()

    # -----------------------------------------------------------------------
    # Stats bar (#3)
    # -----------------------------------------------------------------------

    def _update_stats_bar(self, questions: list[dict]) -> None:
        """
        Update the compact inline stats summary (#3) inside the filter bar and
        refresh filter-button labels with live counts.
        """
        total  = len(questions)
        yes_n  = sum(
            1 for q in questions
            if (q.get("rfp_result") or {}).get("support_level") == "yes"
        )
        part_n = sum(
            1 for q in questions
            if (q.get("rfp_result") or {}).get("support_level") == "partial"
        )
        na_n   = sum(
            1 for q in questions
            if (q.get("rfp_result") or {}).get("support_level") == "not_applicable"
        )
        has_rfp = any(q.get("rfp_result") for q in questions)

        if has_rfp:
            summary = (
                f"📋 {total} total  ·  "
                f"✓ {yes_n}  ·  "
                f"⚠ {part_n}  ·  "
                f"○ {na_n}"
            )
        else:
            summary = f"📋 {total} answer{'s' if total != 1 else ''}"

        self._stats_summary_lbl.configure(text=summary)

        # Update filter-button labels with live counts
        label_map = {
            "all":            f"All  ({total})",
            "yes":            f"✓ Supported  ({yes_n})",
            "partial":        f"⚠ Partial  ({part_n})",
            "not_applicable": f"○ N/A  ({na_n})",
        }
        for val, btn in self._filter_btns.items():
            btn.configure(text=label_map.get(val, val))

    # -----------------------------------------------------------------------
    # Card factory
    # -----------------------------------------------------------------------

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent, fg_color=C_SURFACE,
            border_width=1, border_color=C_BORDER, corner_radius=10,
        )
        frame.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(frame, text=title,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED, anchor="w").pack(
            fill="x", padx=16, pady=(12, 6)
        )
        ctk.CTkFrame(frame, height=1, fg_color=C_BORDER).pack(
            fill="x", padx=16, pady=(0, 8)
        )
        return frame

    # -----------------------------------------------------------------------
    # Ollama status
    # -----------------------------------------------------------------------

    def _refresh_ollama_status(self) -> None:
        _log("Refreshing Ollama status…")
        self._ollama_status_lbl.configure(text="Checking…", text_color=C_MUTED)
        self._ollama_status_dot.configure(text_color=C_MUTED)
        threading.Thread(target=self._check_ollama_thread, daemon=True).start()

    def _check_ollama_thread(self) -> None:
        try:
            from src.llm_engine import ollama_is_running, ollama_list_models
            _log("Calling ollama_is_running()…")
            running = ollama_is_running()
            _log(f"ollama_is_running() → {running}")
            models = []
            if running:
                models = ollama_list_models()
                _log(f"ollama_list_models() → {models}")
            self._post_ui(lambda r=running, m=models: self._apply_ollama_status(r, m))
        except Exception as exc:
            _log_exc(f"_check_ollama_thread error: {exc}")
            self._post_ui(lambda: self._apply_ollama_status(False, []))

    def _apply_ollama_status(self, running: bool, models: list[str]) -> None:
        _log(f"_apply_ollama_status(running={running}, models={models})")
        if running:
            self._ollama_status_dot.configure(text_color=C_SUCCESS)
            self._ollama_status_lbl.configure(
                text=f"Running  ({len(models)} model(s) available)",
                text_color=C_SUCCESS,
            )
            all_models = list(dict.fromkeys(models + RECOMMENDED_MODELS))
            self._model_menu.configure(values=all_models)
            current = self._model_var.get()
            if current not in all_models:
                self._model_var.set(all_models[0] if all_models else "llama3.2")
            self._vizzy.speak_key("ollama_ok")
        else:
            self._ollama_status_dot.configure(text_color=C_CRIT)
            self._ollama_status_lbl.configure(
                text="Not running — click 'Start Ollama' or open the Ollama app",
                text_color=C_CRIT,
            )
            self._vizzy.speak_key("ollama_down")

    def _start_ollama(self) -> None:
        import subprocess
        _log("Start Ollama clicked")
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Ollama"])
                _log("Launched Ollama.app via 'open -a Ollama'")
            elif sys.platform == "win32":
                import shutil
                exe = shutil.which("ollama")
                _log(f"shutil.which('ollama') = {exe}")
                if exe:
                    subprocess.Popen([exe, "serve"])
                else:
                    messagebox.showinfo(
                        "Ollama Not Found",
                        "Ollama does not appear to be installed.\n\n"
                        "Please run the installer first, or download from:\n"
                        "https://ollama.com/download",
                    )
                    return
            else:
                _log(f"Unsupported platform for auto-start: {sys.platform}", "WARN")
        except Exception as exc:
            _log_exc(f"Start Ollama error: {exc}")
            messagebox.showerror("Error", str(exc))
            return

        self._status_lbl.configure(text="Starting Ollama…")
        self._vizzy.speak_key("starting")
        # Poll a few times to catch when it's up
        for delay in (3_000, 6_000, 10_000):
            self.after(delay, self._refresh_ollama_status)

    def _on_model_change(self, value: str) -> None:
        _log(f"Model changed to: {value}")
        self._settings["model"] = value
        _save_settings(self._settings)

    # -----------------------------------------------------------------------
    # File selection
    # -----------------------------------------------------------------------

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select questionnaire file",
            filetypes=[
                ("All supported", SUPPORTED_EXTS),
                ("Excel", "*.xlsx *.xls"),
                ("CSV", "*.csv"),
                ("Word", "*.docx *.doc"),
                ("PDF", "*.pdf"),
                ("Text", "*.txt"),
            ],
        )
        if path:
            self._file = path
            _log(f"File selected: {path}")
            self._show_file_preview(path)
            self._vizzy.speak(
                f"Great choice! I'll process '{os.path.basename(path)}' when you're ready.",
                "happy",
            )

    def _show_file_preview(self, path: str) -> None:
        """
        Replace the drop-zone placeholder text with a styled file-preview row (#5).
        Shows file icon, name, size, type badge, and a 'Change' button.
        """
        info = _format_file_info(path)

        # Clear the drop zone children and replace with preview
        for child in self._drop_zone.winfo_children():
            child.destroy()

        self._drop_zone.configure(border_color=C_SUCCESS, height=72)

        preview_row = ctk.CTkFrame(self._drop_zone, fg_color="transparent")
        preview_row.pack(fill="both", expand=True, padx=12)

        # Icon
        ctk.CTkLabel(
            preview_row, text=info["icon"],
            font=ctk.CTkFont(size=28),
        ).pack(side="left", padx=(4, 10), pady=8)

        # Name + meta
        meta = ctk.CTkFrame(preview_row, fg_color="transparent")
        meta.pack(side="left", fill="x", expand=True, pady=4)

        ctk.CTkLabel(
            meta, text=info["name"],
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C_TEXT, anchor="w",
        ).pack(anchor="w")

        badge_row = ctk.CTkFrame(meta, fg_color="transparent")
        badge_row.pack(anchor="w", pady=(2, 0))

        for badge_text, badge_color in [
            (info["type"], C_ACCENT),
            (info["size"], C_MUTED),
        ]:
            ctk.CTkLabel(
                badge_row, text=badge_text,
                font=ctk.CTkFont(size=10),
                text_color=badge_color,
                fg_color=C_SURF2, corner_radius=4, padx=6, pady=1,
            ).pack(side="left", padx=(0, 6))

        # Change-file button
        ctk.CTkButton(
            preview_row, text="✕ Change",
            width=80, height=28,
            fg_color="transparent",
            border_width=1, border_color=C_BORDER,
            hover_color=C_SURF2,
            text_color=C_ACCENT,
            font=ctk.CTkFont(size=11),
            corner_radius=8,
            command=self._change_file,
        ).pack(side="right", padx=(0, 4), pady=8)

    def _change_file(self) -> None:
        """Reset the drop zone to the placeholder state, then open the picker."""
        for child in self._drop_zone.winfo_children():
            child.destroy()
        self._drop_zone.configure(border_color=C_BORDER, height=96)
        self._drop_lbl = ctk.CTkLabel(
            self._drop_zone,
            text="Click to select a file\nExcel  ·  CSV  ·  Word  ·  PDF  ·  Plain text",
            font=ctk.CTkFont(size=13), text_color=C_MUTED, justify="center",
        )
        self._drop_lbl.pack(expand=True)
        for w in (self._drop_zone, self._drop_lbl):
            w.bind("<Button-1>", lambda _: self._browse_file())
            w.bind("<Enter>",    lambda _: self._drop_zone.configure(border_color=C_ACCENT))
            w.bind("<Leave>",    lambda _: self._drop_zone.configure(border_color=C_BORDER))
        self._file = None
        self._browse_file()

    # -----------------------------------------------------------------------
    # Processing
    # -----------------------------------------------------------------------

    def _start_processing(self) -> None:
        if self._busy:
            return
        if not self._file:
            self._vizzy.speak_key("no_file")
            messagebox.showwarning("No File", "Please select a file first.")
            return

        from src.llm_engine import ollama_is_running
        if not ollama_is_running():
            self._vizzy.speak_key("ollama_down")
            messagebox.showwarning(
                "Ollama Not Running",
                "Ollama is not running.\n\n"
                "Click 'Start Ollama' and wait a few seconds, then try again.",
            )
            return

        self._busy = True
        self._process_done = False
        self._results = None
        self._process_btn.configure(state="disabled", text="⏳  Processing…")
        self._save_btn.configure(state="disabled")
        self._progress_bar.set(0)
        self._set_results("Processing…")
        self._vizzy.speak_key("processing")
        # Collapse config + results panels — only Vizzy, review, save remain visible
        self._ollama_card.collapse()
        self._file_card.collapse()
        self._results_card.collapse()
        _log(f"Starting processing: file={self._file}")

        model = self._model_var.get()
        threading.Thread(
            target=self._processing_thread, args=(model,), daemon=True
        ).start()

    def _eta_callback(self, payload: str) -> None:
        """Receive ETA string from processor and show it in Vizzy's bubble."""
        _log(f"ETA received: {payload}")
        # payload format: "ETA:<time_str>|<kind>"
        try:
            _, rest   = payload.split(":", 1)
            time_str, kind = rest.split("|", 1)
        except ValueError:
            time_str, kind = payload, ""

        msg = (
            f"Heads up — I found {kind} to evaluate. "
            f"This will take {time_str}, so feel free to step away! ☕"
        )
        self._post_ui(lambda m=msg: self._vizzy.speak(m, "working"))

    def _processing_thread(self, model: str) -> None:
        try:
            from src.processor import FileProcessor
            _log(f"FileProcessor init: model={model}")
            proc = FileProcessor(
                model=model,
                status_cb=self._status_callback,
                progress_cb=self._progress_callback,
                eta_cb=self._eta_callback,
            )
            _log("FileProcessor.process() starting…")
            self._results = proc.process(self._file)
            _log(f"FileProcessor.process() complete: {len(self._results.get('questions', []))} questions")
            self._post_ui(self._show_results)
        except Exception as exc:
            _log_exc(f"Processing error: {exc}")
            self._post_ui(lambda e=str(exc): self._show_error(e))
        finally:
            self._busy = False
            self._post_ui(lambda: self._process_btn.configure(
                state="normal", text="▶  Process File"
            ))

    def _status_callback(self, msg: str) -> None:
        """
        Called from the processing thread; posts safely to the main thread.

        Drives both the status label and Vizzy's expression (#6 #7) based on
        the content of the incoming message.
        """
        _log(f"[PROC STATUS] {msg}")

        # Pattern-match the message against known stage keywords
        msg_low   = msg.lower()
        expression = "working"   # default
        prefix     = ""
        for keyword, expr, pfx in _STAGE_MAP:
            if keyword in msg_low:
                expression = expr
                prefix     = pfx
                break

        display = f"{prefix}  {msg}" if prefix else msg

        def _update(m=display, e=expression):
            self._status_lbl.configure(text=m)
            # Only change Vizzy expression mid-process (not overriding done/error)
            if not getattr(self, "_process_done", False):
                self._vizzy._expression = e
                self._vizzy._render(e)

        self._post_ui(_update)

    def _progress_callback(self, value: float) -> None:
        """Called from the processing thread; posts safely to main thread."""
        self._post_ui(lambda v=value: self._progress_bar.set(v))

    # -----------------------------------------------------------------------
    # Results display
    # -----------------------------------------------------------------------

    def _set_results(self, text: str) -> None:
        self._results_box.configure(state="normal")
        self._results_box.delete("1.0", "end")
        self._results_box.insert("1.0", text)
        self._results_box.configure(state="disabled")

    def _show_results(self) -> None:
        if not self._results:
            _log("_show_results: no results object", "WARN")
            return
        qs = self._results.get("questions", [])
        _log(f"_show_results: {len(qs)} questions")

        if not qs:
            self._set_results(
                "⚠️  No questions detected.\n\n"
                "Questions are recognised by:\n"
                "  • Any cell/line ending with '?'\n"
                "  • Rows under a 'Question' column header\n"
                "  • Lines starting with  Q: / Question:"
            )
            self._vizzy.speak(
                "I didn't find any questions in that file. "
                "Try a file with cells ending in '?' or a 'Question' column.",
                "checking",
            )
            self._populate_review([])
            return

        answered      = [q for q in qs if q.get("answer")]
        unanswered    = [q for q in qs if not q.get("answer")]
        cache_hits    = self._results.get("cache_hits", 0)
        feedback_hits = self._results.get("feedback_hits", 0)
        _log(
            f"Answered: {len(answered)}  Unanswered: {len(unanswered)}  "
            f"Cache: {cache_hits}  Feedback: {feedback_hits}"
        )

        # ── Summary textbox — stats header + unanswerable list ────────
        # (Individual answered Q&As are shown in the Review panel below.)
        stat_parts: list[str] = [
            f"  ✅  {len(answered)} answered",
            f"  ❌  {len(unanswered)} unanswerable",
        ]
        if feedback_hits:
            stat_parts.append(f"  ⭐  {feedback_hits} correction{'s' if feedback_hits != 1 else ''}")
        if cache_hits:
            stat_parts.append(f"  ⚡  {cache_hits} from cache")

        lines = [
            "─" * 54,
            "   ".join(stat_parts),
            "─" * 54,
        ]

        if answered:
            lines.append("")
            lines.append("↓  Scroll down to review & edit individual answers.")

        if unanswered:
            lines += ["", "UNANSWERABLE", "────────────"]
            for i, q in enumerate(unanswered, 1):
                lines.append(f"\nQ{i}: {_trunc(q['question'], 110)}")
                reason = q.get("reason") or "No relevant ThousandEyes documentation found."
                lines.append(f"  Reason: {_trunc(reason, 200)}")

        self._process_done = True   # stop mid-process Vizzy overrides
        self._set_results("\n".join(lines))
        self._results_card.expand()          # show stats briefly
        self._save_btn.configure(state="normal")

        # Status bar
        note_parts: list[str] = []
        if feedback_hits:
            note_parts.append(f"⭐ {feedback_hits} corrections")
        if cache_hits:
            note_parts.append(f"⚡ {cache_hits} cached")
        note = f"  ({', '.join(note_parts)})" if note_parts else ""
        self._status_lbl.configure(
            text=f"Done — {len(answered)} answered, {len(unanswered)} unanswerable.{note}"
        )
        self._progress_bar.set(1.0)

        # Populate the Review panel with editable cards
        self._populate_review(qs)

        # Update and reveal the stats KPI bar (#3)
        self._update_stats_bar([q for q in qs if q.get("answer")])

        # Collapse the results summary after 2.5 s so review gets full space
        self.after(2500, self._results_card.collapse)

        # Vizzy message
        if answered:
            extras: list[str] = []
            if feedback_hits:
                extras.append(
                    f"{feedback_hits} came from your saved correction{'s' if feedback_hits != 1 else ''} ⭐"
                )
            if cache_hits:
                extras.append(f"{cache_hits} from cache ⚡")
            extra_msg = " — " + ", ".join(extras) + " —" if extras else ""
            self._vizzy.speak(
                f"Found {len(answered)} answer{'s' if len(answered) != 1 else ''}!{extra_msg} "
                "Review and edit below, then click Save. 🎉",
                "done",
            )
        else:
            self._vizzy.speak(
                "I searched the ThousandEyes docs but couldn't find answers "
                "for these questions. They may be outside the ThousandEyes scope.",
                "checking",
            )

    def _show_error(self, msg: str) -> None:
        _log(f"_show_error: {msg}", "ERROR")
        self._set_results(f"❌  Error:\n\n{msg}")
        self._status_lbl.configure(text="Error — see results panel and debug log.")
        self._vizzy.speak_key("error")
        messagebox.showerror("Error", msg)

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------

    def _save_output(self) -> None:
        if not self._results:
            return

        # ── 1. Collect edits from the spreadsheet ─────────────────────────
        self._collect_sheet_edits()

        # ── 2. File-save dialog (always Word / .docx) ─────────────────────
        ipath = Path(self._results["filepath"])

        out = filedialog.asksaveasfilename(
            title="Save answered file as Word document",
            defaultextension=".docx",
            initialfile=f"{ipath.stem}_TE_Response.docx",
            initialdir=str(ipath.parent),
            filetypes=[("Word Document", "*.docx"), ("All files", "*.*")],
        )
        if not out:
            return

        try:
            from src import file_writer
            from src.qa_reference import save_reference, REFERENCE_PATH

            questions = self._results.get("questions", [])

            # ── 3. Write professional Word document ───────────────────────
            _log(f"Saving Word output to: {out}")
            file_writer.write(self._results, out)
            _log("Word save complete.")

            # ── 4. Auto-save companion Excel (Q|Answer|URL) ───────────────
            excel_path = str(Path(out).with_suffix("")) + "_answers.xlsx"
            excel_count = file_writer.write_qa_excel(questions, excel_path)
            _log(f"Companion Excel saved: {excel_path} ({excel_count} rows)")

            # ── 5. Update the persistent QA reference cache ───────────────
            ref_count = save_reference(questions)
            _log(f"QA reference cache updated ({ref_count} rows) → {REFERENCE_PATH}")

            self._vizzy.speak(
                f"Files saved! Word response + Excel summary ready. 🎉",
                "done",
            )
            messagebox.showinfo(
                "Saved",
                f"Word document:\n  {os.path.basename(out)}\n\n"
                f"Excel companion ({excel_count} Q&A rows):\n"
                f"  {os.path.basename(excel_path)}\n\n"
                f"Both saved to:\n  {str(ipath.parent)}",
            )
        except Exception as exc:
            _log_exc(f"Save error: {exc}")
            messagebox.showerror("Save Error", str(exc))

    def _collect_sheet_edits(self) -> None:
        """
        Walk every spreadsheet row, read the current answer and URL from the
        widgets, update the underlying question dict in-place, and push any
        changes to the FeedbackStore so future runs benefit from corrections.
        """
        rows = getattr(self, "_sheet_rows", [])
        if not rows:
            return

        for entry in rows:
            q         = entry["q"]
            ans_box   = entry["ans_box"]
            url_entry = entry["url_entry"]

            new_answer = ans_box.get("1.0", "end-1c").strip()
            new_url    = url_entry.get().strip()

            original_answer = (q.get("_original_answer") or q.get("answer") or "").strip()
            original_url    = (q.get("source_url") or "").strip()

            changed = (new_answer != original_answer) or (new_url != original_url)

            # Always update the question dict so file_writer sees the latest text
            q["answer"] = new_answer
            if new_url:
                q["source_url"] = new_url

            # For RFP questions the file writer reads rfp_result, so backfill it
            if q.get("rfp_result") and isinstance(q["rfp_result"], dict):
                rfp = q["rfp_result"]
                first_line = new_answer.splitlines()[0].lower() if new_answer else ""
                if "not supported" in first_line or "❌" in new_answer.splitlines()[0] if new_answer else False:
                    rfp["supported"] = False
                elif "supported" in first_line or "✅" in (new_answer.splitlines()[0] if new_answer else ""):
                    rfp["supported"] = True
                lines = new_answer.splitlines()
                expl_lines = [l for l in lines[1:] if l.strip()] or [new_answer]
                rfp["explanation"] = " ".join(expl_lines).strip() or new_answer

            # Persist to the FeedbackStore if something changed
            if changed and new_answer:
                q_text = (q.get("question") or q.get("rfp_requirement") or "").strip()
                if q_text:
                    self._feedback_store.set(q_text, new_answer)
                    q["_feedback"] = True
                    _log(f"Feedback stored for: {q_text[:60]}…")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    App().mainloop()
