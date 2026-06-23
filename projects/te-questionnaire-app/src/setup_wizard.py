"""
Setup Wizard — first-run Ollama installation & model download.

This module provides:

  SetupWizard(ctk.CTkToplevel)
      A modal dialog that walks new users through the 5-step setup:
        1. Welcome
        2. System requirements check
        3. Install Ollama AI runtime
        4. Download LLM model
        5. Finish

      It is shown automatically by main.py when Ollama is not detected at
      startup, and can be re-opened any time from the Debug menu.  When the
      user completes setup, the on_complete(model_id) callback is called with
      the selected model name, then the dialog is destroyed.

  needs_ollama_setup() → bool
      Quick check: returns True if Ollama is not found on the system.

Design notes
────────────
• Extends CTkToplevel (not CTk) — lives inside the main app's event loop.
• Colors mirror the main app's dark navy / purple palette for visual cohesion.
• All background work runs in daemon threads; UI updates use a thread-safe
  queue polled every 40 ms on the main thread.
• The DebugWindow helper is self-contained; logs are separate from the main
  app's debug log (by design — setup logs are verbose and mostly noise once
  the app is running).
"""

from __future__ import annotations

import json
import os
import platform
import queue as _queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import customtkinter as ctk
from PIL import ImageTk

# ── Paths (shared with installer.py) ─────────────────────────────────────────

SETUP_FLAG = Path.home() / ".te_qa_installed"
PREFS_FILE = Path.home() / ".te_qa_prefs.json"

# ── Window geometry ───────────────────────────────────────────────────────────

_WIN_W, _WIN_H = 880, 660

# ── Color palette — matches main app's dark navy / purple theme ───────────────

C_BG      = "#12121e"
C_SURFACE = "#1a1a2e"
C_SURF2   = "#22223a"
C_BORDER  = "#2e2e50"
C_TEXT    = "#f0f0fa"
C_MUTED   = "#8888bb"
C_ACCENT  = "#7c6fff"
C_OK      = "#4dd98a"
C_WARN    = "#fbbf24"
C_ERR     = "#f87171"
C_ORANGE  = "#ff6600"

# ── Installer steps ───────────────────────────────────────────────────────────

_STEPS = ["Welcome", "Requirements", "Install AI Runtime", "Download Model", "All Done!"]

_MODELS = [
    {"id": "llama3.2",    "name": "Llama 3.2 3B  (Recommended ⭐)", "size": "2.0 GB", "ram": "8 GB",
     "desc": "Meta's Llama 3.2 — fast, smart, great instruction-following."},
    {"id": "phi3:mini",   "name": "Phi-3 Mini",                      "size": "2.3 GB", "ram": "8 GB",
     "desc": "Microsoft Phi-3 — very fast and surprisingly capable."},
    {"id": "llama3.2:3b", "name": "Llama 3.2 3B (explicit tag)",     "size": "2.0 GB", "ram": "8 GB",
     "desc": "Same as Llama 3.2 with explicit 3b tag."},
    {"id": "llama3.1:8b", "name": "Llama 3.1 8B",                    "size": "4.7 GB", "ram": "16 GB",
     "desc": "Larger model — better answers, needs more RAM."},
    {"id": "mistral",     "name": "Mistral 7B",                      "size": "4.1 GB", "ram": "16 GB",
     "desc": "Strong reasoning, good for complex questions."},
    {"id": "qwen2.5:7b",  "name": "Qwen 2.5 7B",                     "size": "4.4 GB", "ram": "16 GB",
     "desc": "Alibaba's Qwen — excellent at structured tasks."},
]

# ── Vizzy messages for each setup state ───────────────────────────────────────

_VIZZY_MSG: dict[str, tuple[str, str]] = {
    "welcome":        ("happy",       "Hey there! I'm Vizzy! 👋  I'll guide you through setup step-by-step. Click Continue when you're ready!"),
    "req_checking":   ("checking",    "Checking your system{dots}"),
    "req_slow":       ("checking",    "Still checking… some checks can take a few seconds. Almost done!"),
    "req_ok":         ("happy",       "All good! ✅  Your system meets all requirements. Let's keep going!"),
    "req_warn":       ("working",     "A couple of things to note below, but you can still continue. ⚠️"),
    "ollama_check":   ("checking",    "Looking for Ollama{dots}"),
    "ollama_slow":    ("checking",    "Still looking — this can take a moment on first run. Hang tight! 🔍"),
    "ollama_found":   ("happy",       "Ollama is already installed and running! ✅  You're all set for the next step."),
    "ollama_missing": ("working",     "Ollama isn't installed yet — no worries! Click 'Install Ollama' and I'll handle it."),
    "ollama_install": ("working",     "macOS will ask for your administrator password — that's normal! Enter it and I'll handle the rest. ☕"),
    "ollama_running": ("happy",       "Ollama is up and running! 🎉  Time to grab an AI model."),
    "ollama_error":   ("working",     "Something went wrong. Check the message above and try again. (Tip: open the Debug Log for details.)"),
    "model_pick":     ("idle",        "Pick a model from the list. I recommend Llama 3.2 — fast and smart! Click Download when ready."),
    "model_already":  ("happy",       "That model is already downloaded! ✅  Just hit Continue."),
    "model_start":    ("downloading", "Starting the download… grab a snack — this could take a few minutes! 🍕"),
    "model_dl":       ("downloading", "Downloading: {done} / {total}  ({pct}%)  —  almost there!"),
    "model_verify":   ("working",     "Verifying the download… almost done!"),
    "model_done":     ("happy",       "Model downloaded and ready! 🎉  You're all set!"),
    "finish":         ("done",        "You did it! 🚀  Click 'Finish Setup' to start answering questionnaires!"),
}

# ─────────────────────────────────────────────────────────────────────────────
# Public helper
# ─────────────────────────────────────────────────────────────────────────────

def needs_ollama_setup() -> bool:
    """
    Return True if Ollama does not appear to be installed on this machine.

    Checks (in order):
      1. PATH binary  (shutil.which)
      2. Common fixed install paths
      3. macOS Ollama.app bundle
    """
    if shutil.which("ollama"):
        return False
    for candidate in [
        "/usr/local/bin/ollama",
        "/opt/homebrew/bin/ollama",
        str(Path.home() / ".ollama" / "ollama"),
        str(Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
    ]:
        if Path(candidate).exists():
            return False
    if Path("/Applications/Ollama.app").exists():
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# In-wizard debug log
# ─────────────────────────────────────────────────────────────────────────────

_setup_log_lines: List[str] = []
_setup_debug_win_ref: Optional[object] = None


def _log(msg: str, level: str = "INFO") -> None:
    ts   = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{level:<5}] {msg}"
    _setup_log_lines.append(line)
    global _setup_debug_win_ref
    try:
        if _setup_debug_win_ref and _setup_debug_win_ref.winfo_exists():
            _setup_debug_win_ref.append_line(line)
    except Exception:
        pass


def _log_exc(msg: str) -> None:
    _log(msg, "ERROR")
    for ln in traceback.format_exc().splitlines():
        _log(f"    {ln}", "TRACE")


# ─────────────────────────────────────────────────────────────────────────────
# Debug window (self-contained — setup logs are separate from main app logs)
# ─────────────────────────────────────────────────────────────────────────────

class _DebugWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Setup Debug Log")
        self.geometry("780x480")
        self.configure(fg_color=C_BG)
        global _setup_debug_win_ref
        _setup_debug_win_ref = self
        self._q: _queue.Queue = _queue.Queue()
        self.after(60, self._drain)
        bar = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=38)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkButton(bar, text="Clear", width=70,
                      fg_color=C_SURF2, border_width=1, border_color=C_BORDER,
                      text_color=C_MUTED, font=ctk.CTkFont(size=11),
                      command=self._clear).pack(side="left", padx=8, pady=6)
        ctk.CTkButton(bar, text="Copy All", width=80,
                      fg_color=C_SURF2, border_width=1, border_color=C_BORDER,
                      text_color=C_MUTED, font=ctk.CTkFont(size=11),
                      command=self._copy).pack(side="left", padx=(0, 8), pady=6)
        self._auto = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(bar, text="Auto-scroll", variable=self._auto,
                        font=ctk.CTkFont(size=11), text_color=C_MUTED,
                        fg_color=C_ACCENT).pack(side="left", padx=8)
        ctk.CTkLabel(bar, text="🔴 LIVE", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_ERR).pack(side="right", padx=12)
        self._txt = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Courier", size=11),
                                    fg_color=C_SURF2, text_color=C_TEXT, wrap="none")
        self._txt.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        if _setup_log_lines:
            self._txt.configure(state="normal")
            self._txt.insert("1.0", "\n".join(_setup_log_lines) + "\n")
            self._txt.configure(state="disabled")
            self._txt.see("end")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def append_line(self, line: str) -> None:
        self._q.put(line)

    def _drain(self) -> None:
        try:
            while True:
                line = self._q.get_nowait()
                self._txt.configure(state="normal")
                self._txt.insert("end", line + "\n")
                self._txt.configure(state="disabled")
                if self._auto.get():
                    self._txt.see("end")
        except _queue.Empty:
            pass
        try:
            self.after(60, self._drain)
        except Exception:
            pass

    def _clear(self):
        _setup_log_lines.clear()
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.configure(state="disabled")

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append("\n".join(_setup_log_lines))

    def _on_close(self):
        global _setup_debug_win_ref
        _setup_debug_win_ref = None
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Vizzy panel (used inside each setup step)
# ─────────────────────────────────────────────────────────────────────────────

_VIZZY_PIL_CACHE: dict[str, object] = {}


def _get_vizzy_pil(expression: str, size: int):
    key = f"{expression}_{size}"
    if key not in _VIZZY_PIL_CACHE:
        from src.vizzy import create_vizzy
        _VIZZY_PIL_CACHE[key] = create_vizzy(expression=expression, size=size)
    return _VIZZY_PIL_CACHE[key]


class _VizzyPanel(ctk.CTkFrame):
    """Mascot strip — Vizzy on the left, speech bubble on the right."""

    def __init__(self, parent, initial_key: str = "welcome", **kwargs):
        super().__init__(parent,
                         fg_color=C_SURF2,
                         border_width=1,
                         border_color=C_BORDER,
                         corner_radius=12,
                         **kwargs)
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._current_expr: str = ""

        self._img_lbl = ctk.CTkLabel(self, text="")
        self._img_lbl.pack(side="left", padx=(14, 6), pady=10)

        bubble = ctk.CTkFrame(self, fg_color=C_SURFACE,
                               border_width=2, border_color=C_ACCENT,
                               corner_radius=14)
        bubble.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=10)

        self._msg = ctk.CTkLabel(bubble, text="",
                                  font=ctk.CTkFont(size=13), text_color=C_TEXT,
                                  wraplength=420, justify="left")
        self._msg.pack(padx=14, pady=10, anchor="w")

        self.say(initial_key)

    def say(self, key: str, **fmt) -> None:
        expression, tmpl = _VIZZY_MSG.get(key, ("idle", key))
        text = tmpl.format(**fmt) if fmt else tmpl
        self._msg.configure(text=text)
        if expression != self._current_expr:
            self._update_image(expression)

    def _update_image(self, expression: str) -> None:
        try:
            pil_img    = _get_vizzy_pil(expression, 100)
            self._photo = ImageTk.PhotoImage(pil_img)
            self._img_lbl.configure(image=self._photo, text="")
            self._current_expr = expression
        except Exception as exc:
            _log(f"VizzyPanel image error: {exc}", "WARN")
            self._img_lbl.configure(text="👁", font=ctk.CTkFont(size=40), image=None)


# ─────────────────────────────────────────────────────────────────────────────
# SetupWizard — main class
# ─────────────────────────────────────────────────────────────────────────────

class SetupWizard(ctk.CTkToplevel):
    """
    First-run setup wizard.

    Parameters
    ----------
    parent:
        The main App window.  The wizard is transient to it (stays on top)
        and modal (grabs all input until dismissed).
    on_complete:
        Called with the selected model id (str) when the user finishes setup.
        If the user closes the window early, it is called with an empty string.
    """

    def __init__(
        self,
        parent,
        on_complete: Callable[[str], None] = lambda _: None,
    ) -> None:
        super().__init__(parent)
        self._on_complete = on_complete

        self.title("Customer Questionnaire Crusher — Setup")
        self.geometry(f"{_WIN_W}x{_WIN_H}")
        self.resizable(False, False)
        self.configure(fg_color=C_BG)

        # Stay on top of the main window
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self._step_idx   = 0
        self._selected   = _MODELS[0]["id"]
        self._completed  = False

        self._vizzy:     Optional[_VizzyPanel] = None
        self._dots_job:  Optional[str]         = None
        self._dots_n:    int                   = 0
        self._dots_slow: int                   = 0

        self._ui_q: _queue.Queue = _queue.Queue()

        _log(f"SetupWizard opened — Python {sys.version.split()[0]} "
             f"on {sys.platform} ({platform.machine()})")

        self._build_ui()
        self._poll_ui_queue()
        self._show_step(0)

        # If window is closed by the user (✕ button) before finishing
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    # ── Thread-safe UI queue ──────────────────────────────────────────────

    def _post_ui(self, fn: Callable) -> None:
        self._ui_q.put(fn)

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception as exc:
                    _log_exc(f"UI queue callback raised: {exc}")
        except _queue.Empty:
            pass
        try:
            self.after(40, self._poll_ui_queue)
        except Exception:
            pass

    # ── Top-level layout ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Brand bar
        brand = ctk.CTkFrame(self, fg_color=C_SURFACE,
                              border_width=0, corner_radius=0, height=52)
        brand.pack(fill="x")
        brand.pack_propagate(False)
        ctk.CTkLabel(brand, text="●", font=ctk.CTkFont(size=14),
                     text_color=C_ORANGE).pack(side="left", padx=(20, 6))
        ctk.CTkLabel(brand, text="CUSTOMER QUESTIONNAIRE CRUSHER",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C_MUTED).pack(side="left")
        ctk.CTkLabel(brand, text="Setup Wizard",
                     font=ctk.CTkFont(size=12), text_color=C_ACCENT).pack(
                         side="right", padx=20)

        # Body (sidebar + content)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self._sidebar = self._build_sidebar(body)
        self._content = ctk.CTkScrollableFrame(body, fg_color=C_BG, corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        # Bottom nav bar
        bar = ctk.CTkFrame(self, fg_color=C_SURFACE,
                            border_width=0, corner_radius=0, height=62)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._back_btn = ctk.CTkButton(
            bar, text="← Back", width=110,
            fg_color=C_SURF2, border_width=1, border_color=C_BORDER,
            text_color=C_MUTED, command=self._go_back)
        self._back_btn.pack(side="left", padx=20, pady=12)

        self._next_btn = ctk.CTkButton(
            bar, text="Continue →", width=160,
            fg_color=C_ACCENT, text_color="#ffffff",
            command=self._go_next)
        self._next_btn.pack(side="right", padx=20, pady=12)

    def _build_sidebar(self, parent) -> ctk.CTkFrame:
        side = ctk.CTkFrame(parent, fg_color=C_SURFACE, width=200,
                             border_width=0, corner_radius=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        ctk.CTkLabel(side, text="STEPS",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED).pack(anchor="w", padx=20, pady=(20, 8))

        self._step_labels: list[ctk.CTkLabel] = []
        for i, name in enumerate(_STEPS):
            lbl = ctk.CTkLabel(side, text=f"  {i+1}. {name}",
                               font=ctk.CTkFont(size=13),
                               text_color=C_MUTED, anchor="w")
            lbl.pack(fill="x", padx=8, pady=2)
            self._step_labels.append(lbl)

        ctk.CTkButton(side, text="🐛 Debug Log", width=150,
                      fg_color="transparent", border_width=1,
                      border_color=C_BORDER, text_color=C_MUTED,
                      font=ctk.CTkFont(size=11),
                      command=self._open_debug).pack(side="bottom", padx=16, pady=12)
        return side

    def _open_debug(self) -> None:
        global _setup_debug_win_ref
        if _setup_debug_win_ref:
            try:
                if _setup_debug_win_ref.winfo_exists():
                    _setup_debug_win_ref.lift()
                    return
            except Exception:
                pass
        win = _DebugWindow(self)
        win.lift()

    # ── Step navigation ───────────────────────────────────────────────────

    def _show_step(self, idx: int) -> None:
        self._step_idx = idx
        self._stop_dots()
        _log(f"Showing step {idx}: {_STEPS[idx]}")

        for i, lbl in enumerate(self._step_labels):
            if i == idx:
                lbl.configure(text_color=C_ACCENT,
                              font=ctk.CTkFont(size=13, weight="bold"))
            elif i < idx:
                lbl.configure(text_color=C_OK, font=ctk.CTkFont(size=13))
            else:
                lbl.configure(text_color=C_MUTED, font=ctk.CTkFont(size=13))

        for w in self._content.winfo_children():
            w.destroy()
        self._vizzy = None
        self._back_btn.configure(state="normal" if idx > 0 else "disabled")

        [self._step_welcome,
         self._step_requirements,
         self._step_ollama,
         self._step_model,
         self._step_finish][idx]()

    def _go_next(self) -> None:
        if self._step_idx == len(_STEPS) - 1:
            self._finish()
        elif self._step_idx < len(_STEPS) - 1:
            self._show_step(self._step_idx + 1)

    def _go_back(self) -> None:
        if self._step_idx > 0:
            self._show_step(self._step_idx - 1)

    def _on_window_close(self) -> None:
        _log("SetupWizard closed early by user.")
        self._on_complete("")
        self.destroy()

    # ── Shared helpers ────────────────────────────────────────────────────

    def _step_header(self, title: str, subtitle: str) -> None:
        ctk.CTkLabel(self._content, text=title,
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=30, pady=(28, 4))
        ctk.CTkLabel(self._content, text=subtitle,
                     font=ctk.CTkFont(size=13), text_color=C_MUTED,
                     wraplength=610, justify="left").pack(
                         anchor="w", padx=30, pady=(0, 20))

    def _divider(self) -> None:
        ctk.CTkFrame(self._content, fg_color=C_BORDER,
                     height=1, corner_radius=0).pack(fill="x", padx=30, pady=8)

    def _add_vizzy(self, key: str = "welcome") -> _VizzyPanel:
        vz = _VizzyPanel(self._content, initial_key=key)
        vz.pack(fill="x", padx=30, pady=(14, 22))
        self._vizzy = vz
        return vz

    # ── Dots animation ────────────────────────────────────────────────────

    def _start_dots(self, key: str, slow_key: str,
                    slow_after_ticks: int = 14, delay_ms: int = 400) -> None:
        self._stop_dots()
        self._dots_n    = 0
        self._dots_slow = 0
        self._dots_key       = key
        self._dots_slow_key  = slow_key
        self._dots_slow_after = slow_after_ticks

        def _tick():
            if self._vizzy is None:
                return
            n = self._dots_n % 4
            self._vizzy.say(key, dots="." * n)
            self._dots_n    += 1
            self._dots_slow += 1
            if self._dots_slow >= slow_after_ticks:
                if self._vizzy:
                    self._vizzy.say(slow_key)
                return
            self._dots_job = self.after(delay_ms, _tick)

        _tick()

    def _stop_dots(self) -> None:
        if self._dots_job:
            try:
                self.after_cancel(self._dots_job)
            except Exception:
                pass
            self._dots_job = None

    # ─────────────────────────────────────────────────────────────────────
    # Step 0 — Welcome
    # ─────────────────────────────────────────────────────────────────────

    def _step_welcome(self) -> None:
        self._next_btn.configure(text="Continue →", state="normal",
                                  fg_color=C_ACCENT)
        self._step_header(
            "Welcome to Customer Questionnaire Crusher",
            "This wizard will get everything set up so you can automatically "
            "answer ThousandEyes questionnaires using a local AI model — "
            "no internet connection required after setup, no API keys, "
            "and no data leaves your machine.",
        )
        for icon, text in [
            ("📄", "Accepts Excel, CSV, Word, PDF, and plain-text files"),
            ("🔍", "Searches docs.thousandeyes.com for accurate answers"),
            ("🤖", "Runs a local AI model via Ollama (100% private)"),
            ("📝", "Writes answers back into the original file format"),
        ]:
            row = ctk.CTkFrame(self._content, fg_color="transparent")
            row.pack(fill="x", padx=40, pady=3)
            ctk.CTkLabel(row, text=icon,
                         font=ctk.CTkFont(size=18)).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(row, text=text,
                         font=ctk.CTkFont(size=13), text_color=C_TEXT).pack(side="left")
        self._divider()
        ctk.CTkLabel(self._content,
                     text="Setup takes about 5–10 minutes depending on your internet speed.",
                     font=ctk.CTkFont(size=12), text_color=C_MUTED).pack(
                         anchor="w", padx=30, pady=(0, 4))
        self._add_vizzy("welcome")

    # ─────────────────────────────────────────────────────────────────────
    # Step 1 — System requirements
    # ─────────────────────────────────────────────────────────────────────

    def _step_requirements(self) -> None:
        self._next_btn.configure(text="Continue →", state="disabled",
                                  fg_color=C_ACCENT)
        self._step_header(
            "System Requirements",
            "Checking your system to make sure everything is compatible.",
        )
        checks_meta = [
            ("os",      "Operating System", "macOS 12+ or Windows 10+"),
            ("python",  "Python version",   f"{sys.version.split()[0]}"),
            ("disk",    "Free disk space",  "≥ 8 GB recommended"),
            ("memory",  "Memory",           "≥ 8 GB RAM recommended"),
            ("network", "Network",          "Required for first download"),
        ]
        self._req_rows: dict[str, ctk.CTkLabel] = {}
        grid = ctk.CTkFrame(self._content, fg_color=C_SURFACE,
                             border_width=1, border_color=C_BORDER, corner_radius=10)
        grid.pack(fill="x", padx=30)
        for key, label, hint in checks_meta:
            row = ctk.CTkFrame(grid, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=8)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=C_TEXT, width=165, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=hint,
                         font=ctk.CTkFont(size=12), text_color=C_MUTED,
                         width=195, anchor="w").pack(side="left", padx=(0, 20))
            slbl = ctk.CTkLabel(row, text="⏳  Pending…",
                                font=ctk.CTkFont(size=12), text_color=C_MUTED,
                                width=130, anchor="w")
            slbl.pack(side="left")
            self._req_rows[key] = slbl

        self._req_error_lbl = ctk.CTkLabel(
            self._content, text="",
            font=ctk.CTkFont(size=12), text_color=C_ERR,
            wraplength=580, justify="left")
        self._req_error_lbl.pack(anchor="w", padx=30, pady=(6, 0))

        self._add_vizzy("req_checking")
        self._start_dots("req_checking", slow_key="req_slow",
                         slow_after_ticks=16, delay_ms=380)
        threading.Thread(target=self._run_req_checks, daemon=True).start()

    def _run_req_checks(self) -> None:
        time.sleep(0.15)
        results: dict[str, bool] = {}
        details: dict[str, str]  = {}
        errors:  list[str]       = []

        # OS
        try:
            ok = sys.platform in ("darwin", "win32", "linux")
            results["os"] = ok
            details["os"] = f"{sys.platform} / {platform.version()[:60]}"
            _log(f"REQ os: {'OK' if ok else 'FAIL'} — {details['os']}")
        except Exception:
            results["os"] = True

        # Python
        try:
            pv = sys.version_info
            ok = (pv.major, pv.minor) >= (3, 10)
            results["python"] = ok
            details["python"] = f"{pv.major}.{pv.minor}.{pv.micro}"
            _log(f"REQ python: {'OK' if ok else 'FAIL'} — {details['python']}")
            if not ok:
                errors.append(f"Python {details['python']} detected — 3.10+ required.")
        except Exception:
            results["python"] = True

        # Disk
        try:
            stat    = shutil.disk_usage(Path.home())
            free_gb = stat.free / (1024 ** 3)
            ok      = free_gb >= 5.0
            results["disk"] = ok
            details["disk"] = f"{free_gb:.1f} GB free"
            _log(f"REQ disk: {'OK' if ok else 'WARN'} — {details['disk']}")
            if not ok:
                errors.append(f"Only {free_gb:.1f} GB free — 8 GB recommended.")
        except Exception:
            results["disk"] = True

        # Memory
        try:
            mem_gb = 0.0
            mem_ok = True
            try:
                import psutil  # type: ignore
                mem_gb = psutil.virtual_memory().total / (1024 ** 3)
                mem_ok = mem_gb >= 7.5
            except ImportError:
                if sys.platform == "darwin":
                    out    = subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=3).decode().strip()
                    mem_gb = int(out) / (1024 ** 3)
                    mem_ok = mem_gb >= 7.5
            results["memory"] = mem_ok
            details["memory"] = f"{mem_gb:.1f} GB RAM" if mem_gb else "unknown"
            _log(f"REQ memory: {'OK' if mem_ok else 'WARN'} — {details['memory']}")
            if not mem_ok:
                errors.append(f"Only {mem_gb:.1f} GB RAM — 8 GB recommended.")
        except Exception:
            results["memory"] = True

        # Network
        try:
            _net_result: list[bool] = []
            _net_done = threading.Event()

            def _ping():
                try:
                    sock = socket.create_connection(("ollama.com", 443), timeout=4)
                    sock.close()
                    _net_result.append(True)
                except Exception as e:
                    _log(f"REQ network error: {e}", "WARN")
                    _net_result.append(False)
                finally:
                    _net_done.set()

            t = threading.Thread(target=_ping, daemon=True)
            t.start()
            _net_done.wait(timeout=6)
            net_ok = bool(_net_result and _net_result[0])
            results["network"] = net_ok
            details["network"] = "reachable" if net_ok else "unreachable (offline?)"
            _log(f"REQ network: {'OK' if net_ok else 'WARN'} — {details['network']}")
            if not net_ok:
                errors.append("Network appears offline. Internet is required for first download.")
        except Exception:
            results["network"] = True

        all_ok = all(results.values())

        def _update():
            try:
                self._stop_dots()
                for key, ok in results.items():
                    lbl = self._req_rows.get(key)
                    if lbl:
                        detail = details.get(key, "")
                        icon   = "✅" if ok else "⚠️"
                        lbl.configure(text=f"{icon}  {detail}" if detail else f"{icon}  {'OK' if ok else 'Warning'}")
                        lbl.configure(text_color=C_OK if ok else C_WARN)
                if errors:
                    self._req_error_lbl.configure(text="⚠️  " + "  ·  ".join(errors))
                self._next_btn.configure(state="normal")
                self.update_idletasks()
                if self._vizzy:
                    self._vizzy.say("req_ok" if all_ok else "req_warn")
            except Exception as exc:
                _log_exc(f"_update crashed: {exc}")
                try:
                    self._next_btn.configure(state="normal")
                except Exception:
                    pass

        self._post_ui(_update)

    # ─────────────────────────────────────────────────────────────────────
    # Step 2 — Ollama
    # ─────────────────────────────────────────────────────────────────────

    def _step_ollama(self) -> None:
        self._next_btn.configure(text="Continue →", state="disabled",
                                  fg_color=C_ACCENT)
        self._step_header(
            "Install AI Runtime (Ollama)",
            "Ollama runs open-source AI models locally on your machine. "
            "It only needs to be installed once.",
        )
        srow = ctk.CTkFrame(self._content, fg_color=C_SURFACE,
                             border_width=1, border_color=C_BORDER, corner_radius=10)
        srow.pack(fill="x", padx=30, pady=(0, 10))
        irow = ctk.CTkFrame(srow, fg_color="transparent")
        irow.pack(fill="x", padx=16, pady=14)

        self._ollama_status_lbl = ctk.CTkLabel(
            irow, text="Checking for Ollama…",
            font=ctk.CTkFont(size=13), text_color=C_MUTED, anchor="w")
        self._ollama_status_lbl.pack(side="left", expand=True, fill="x")

        self._ollama_install_btn = ctk.CTkButton(
            irow, text="Install Ollama", width=140,
            fg_color=C_ACCENT, text_color="#ffffff",
            command=self._do_install_ollama, state="disabled")
        self._ollama_install_btn.pack(side="right")

        self._ollama_log_box = ctk.CTkTextbox(
            self._content, height=120,
            fg_color=C_SURF2, text_color=C_MUTED,
            font=ctk.CTkFont(family="Courier", size=11),
            border_width=1, border_color=C_BORDER, corner_radius=8)
        self._ollama_log_box.pack(fill="x", padx=30, pady=(0, 8))
        self._ollama_log_box.configure(state="disabled")

        self._add_vizzy("ollama_check")
        self._start_dots("ollama_check", slow_key="ollama_slow",
                         slow_after_ticks=14, delay_ms=420)
        threading.Thread(target=self._check_ollama_installed, daemon=True).start()

    def _ollama_log_append(self, text: str) -> None:
        _log(f"OLLAMA_LOG: {text}")
        def _do():
            self._ollama_log_box.configure(state="normal")
            self._ollama_log_box.insert("end", text + "\n")
            self._ollama_log_box.see("end")
            self._ollama_log_box.configure(state="disabled")
        self._post_ui(_do)

    def _check_ollama_installed(self) -> None:
        _log("Ollama check: pinging daemon…")
        self._ollama_log_append("Pinging Ollama daemon on localhost:11434…")
        daemon_up = False
        try:
            import requests as _req
            r = _req.get("http://localhost:11434/", timeout=0.7)
            daemon_up = r.status_code in (200, 404)
        except Exception as exc:
            _log(f"Ollama daemon not reachable: {exc}", "WARN")

        if daemon_up:
            self._ollama_log_append("✅  Daemon is responding.")
            self._post_ui(self._ollama_already_running)
            return

        self._ollama_log_append("Daemon not found — scanning for binary…")
        binary_found = bool(shutil.which("ollama"))
        for candidate in [
            "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama",
            str(Path.home() / ".ollama" / "ollama"),
            str(Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
        ]:
            if Path(candidate).exists():
                binary_found = True
                _log(f"Found binary at: {candidate}")
                break

        mac_app = Path("/Applications/Ollama.app")
        if not binary_found and mac_app.exists():
            binary_found = True
            _log("Found Ollama.app bundle")

        if binary_found:
            self._ollama_log_append("Binary found — attempting to start daemon…")
            self._start_ollama_daemon()
            for _ in range(10):
                time.sleep(0.35)
                try:
                    import requests as _req
                    r = _req.get("http://localhost:11434/", timeout=0.4)
                    if r.status_code in (200, 404):
                        self._ollama_log_append("✅  Daemon is now running.")
                        self._post_ui(self._ollama_already_running)
                        return
                except Exception:
                    pass
            _log("Ollama binary found but daemon didn't respond in time.", "WARN")
            self._post_ui(self._ollama_binary_not_running)
        else:
            _log("Ollama binary not found.")
            self._ollama_log_append("⚠️  Ollama not installed.")
            self._post_ui(self._ollama_not_installed)

    def _start_ollama_daemon(self) -> None:
        try:
            if sys.platform == "darwin":
                if Path("/Applications/Ollama.app").exists():
                    subprocess.Popen(["open", "-a", "Ollama"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["ollama", "serve"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform == "win32":
                subprocess.Popen(["ollama", "serve"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen(["ollama", "serve"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            _log_exc(f"Could not start Ollama daemon: {exc}")

    def _ollama_already_running(self) -> None:
        self._stop_dots()
        self._ollama_status_lbl.configure(
            text="✅  Ollama is installed and running", text_color=C_OK)
        self._next_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.say("ollama_running")

    def _ollama_binary_not_running(self) -> None:
        self._stop_dots()
        self._ollama_status_lbl.configure(
            text="⚠️  Ollama found but not responding — try 'Install Ollama' to repair",
            text_color=C_WARN)
        self._ollama_install_btn.configure(state="normal")
        self._next_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.say("ollama_missing")

    def _ollama_not_installed(self) -> None:
        self._stop_dots()
        self._ollama_status_lbl.configure(
            text="Ollama is not installed — click 'Install Ollama' to continue",
            text_color=C_WARN)
        self._ollama_install_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.say("ollama_missing")

    def _do_install_ollama(self) -> None:
        self._ollama_install_btn.configure(state="disabled")
        self._next_btn.configure(state="disabled")
        _log("User triggered Ollama install.")
        if sys.platform == "darwin":
            self._ollama_status_lbl.configure(
                text="⚠️  A macOS password dialog will appear — enter your admin password to continue.",
                text_color=C_WARN)
        else:
            self._ollama_status_lbl.configure(text="Installing Ollama…", text_color=C_MUTED)
        if self._vizzy:
            self._vizzy.say("ollama_install")
        threading.Thread(target=self._install_ollama_thread, daemon=True).start()

    def _install_ollama_thread(self) -> None:
        try:
            if sys.platform == "darwin":
                self._ollama_log_append("Requesting administrator privileges…")
                script_path = "/tmp/te_qa_ollama_install.sh"
                log_path    = "/tmp/te_qa_ollama_install.log"
                with open(script_path, "w") as f:
                    f.write("#!/bin/bash\ncurl -fsSL https://ollama.com/install.sh | bash\n")
                os.chmod(script_path, 0o755)
                applescript = (
                    f'do shell script "bash {script_path} > {log_path} 2>&1" '
                    f'with administrator privileges'
                )
                result = subprocess.run(["osascript", "-e", applescript],
                                        capture_output=True, text=True, timeout=360)
                try:
                    with open(log_path) as lf:
                        for line in lf.read().splitlines():
                            if line.strip():
                                self._ollama_log_append(line)
                except Exception:
                    pass
                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    if "canceled" in stderr.lower() or "cancelled" in stderr.lower():
                        self._post_ui(lambda: self._ollama_install_failed(
                            "Installation cancelled — no changes were made."))
                    else:
                        msg = stderr or f"Exit code {result.returncode}"
                        self._post_ui(lambda m=msg: self._ollama_install_failed(m))
                    return

            elif sys.platform == "win32":
                self._ollama_log_append("Downloading Windows installer via PowerShell…")
                ps_cmd = (
                    "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' "
                    "-OutFile \"$env:TEMP\\OllamaSetup.exe\"; "
                    "Start-Process -FilePath \"$env:TEMP\\OllamaSetup.exe\" -Wait"
                )
                result = subprocess.run(["powershell", "-Command", ps_cmd],
                                        capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    msg = result.stderr.strip() or "Non-zero exit code."
                    self._post_ui(lambda m=msg: self._ollama_install_failed(m))
                    return
            else:
                self._post_ui(lambda: self._ollama_install_failed(
                    "Automatic install not supported on this OS. "
                    "Please install from ollama.com manually."))
                return

            self._ollama_log_append("Install complete — starting Ollama…")
            self._start_ollama_daemon()
            time.sleep(2.5)
            self._post_ui(self._ollama_install_done)

        except subprocess.TimeoutExpired:
            self._post_ui(lambda: self._ollama_install_failed(
                "Installation timed out — please try again or install manually from ollama.com"))
        except Exception as exc:
            _log_exc(f"Ollama install error: {exc}")
            self._post_ui(lambda e=str(exc): self._ollama_install_failed(e))

    def _ollama_install_done(self) -> None:
        self._ollama_status_lbl.configure(
            text="✅  Ollama installed and running!", text_color=C_OK)
        self._next_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.say("ollama_running")

    def _ollama_install_failed(self, reason: str) -> None:
        _log(f"Ollama install failed: {reason}", "ERROR")
        self._ollama_status_lbl.configure(
            text="Installation failed — see log below", text_color=C_ERR)
        self._ollama_log_append(f"ERROR: {reason}")
        self._ollama_install_btn.configure(state="normal", text="Retry Install")
        if self._vizzy:
            self._vizzy.say("ollama_error")

    # ─────────────────────────────────────────────────────────────────────
    # Step 3 — Model download
    # ─────────────────────────────────────────────────────────────────────

    def _step_model(self) -> None:
        self._next_btn.configure(text="Continue →", state="disabled",
                                  fg_color=C_ACCENT)
        self._step_header(
            "Download AI Model",
            "Choose a model and download it.  It will be stored locally "
            "and used to answer your questionnaires.",
        )
        self._model_var = ctk.StringVar(value=self._selected)
        for m in _MODELS:
            row = ctk.CTkFrame(self._content, fg_color=C_SURFACE,
                               border_width=1, border_color=C_BORDER, corner_radius=8)
            row.pack(fill="x", padx=30, pady=3)
            rb = ctk.CTkRadioButton(
                row, text=m["name"],
                font=ctk.CTkFont(size=13, weight="bold"), text_color=C_TEXT,
                variable=self._model_var, value=m["id"],
                fg_color=C_ACCENT,
                command=lambda mid=m["id"]: self._set_model(mid))
            rb.pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(row, text=f"⬇ {m['size']}", font=ctk.CTkFont(size=11),
                         text_color=C_MUTED).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(row, text=f"🧠 {m['ram']}", font=ctk.CTkFont(size=11),
                         text_color=C_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=m["desc"],
                         font=ctk.CTkFont(size=11), text_color=C_MUTED,
                         wraplength=270, justify="left").pack(side="right", padx=12, pady=4)

        ctrl = ctk.CTkFrame(self._content, fg_color="transparent")
        ctrl.pack(fill="x", padx=30, pady=(12, 4))
        self._dl_btn = ctk.CTkButton(
            ctrl, text="⬇  Download", width=150,
            fg_color=C_ACCENT, text_color="#ffffff",
            command=self._do_pull_model)
        self._dl_btn.pack(side="left")
        self._dl_status = ctk.CTkLabel(
            ctrl, text="Select a model and click Download.",
            font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._dl_status.pack(side="left", padx=16)

        self._dl_bar = ctk.CTkProgressBar(
            self._content, progress_color=C_ACCENT,
            fg_color=C_SURF2, height=10, corner_radius=5)
        self._dl_bar.pack(fill="x", padx=30, pady=(4, 1))
        self._dl_bar.set(0)
        self._dl_bytes_lbl = ctk.CTkLabel(
            self._content, text="",
            font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._dl_bytes_lbl.pack(anchor="e", padx=30)

        self._add_vizzy("model_pick")

    def _set_model(self, mid: str) -> None:
        self._selected = mid
        _log(f"Model selected: {mid}")

    def _do_pull_model(self) -> None:
        model = self._selected
        _log(f"Starting model download: {model}")
        self._dl_btn.configure(text="⏳  Downloading…", state="disabled",
                                fg_color=C_SURF2, text_color=C_WARN)
        self._dl_status.configure(text="Connecting to Ollama…", text_color=C_MUTED)
        self._dl_bar.set(0)
        self._dl_bytes_lbl.configure(text="")
        if self._vizzy:
            self._vizzy.say("model_start")

        def prog(fraction: float, status: str,
                 completed_bytes: int = 0, total_bytes: int = 0) -> None:
            frac = min(fraction, 1.0)
            if total_bytes > 0:
                done_gb  = completed_bytes / 1_073_741_824
                total_gb = total_bytes     / 1_073_741_824
                pct      = int(frac * 100)
                byte_txt   = f"{done_gb:.2f} GB / {total_gb:.2f} GB  ({pct}%)"
                status_txt = f"Downloading {model}…"
                vkey, vfmt = "model_dl", dict(done=f"{done_gb:.1f}GB",
                                               total=f"{total_gb:.1f}GB", pct=pct)
            elif "verify" in status.lower() or "sha256" in status.lower():
                byte_txt, status_txt = "", "Verifying download…"
                vkey, vfmt = "model_verify", {}
            elif "manifest" in status.lower() or "pulling" in status.lower():
                byte_txt, status_txt = "", "Fetching model info…"
                vkey, vfmt = "model_start", {}
            else:
                byte_txt   = ""
                status_txt = status or "Working…"
                vkey, vfmt = "model_start", {}

            def _ui(f=frac, st=status_txt, bt=byte_txt, k=vkey, kw=vfmt):
                self._dl_bar.set(f)
                self._dl_status.configure(text=st)
                self._dl_bytes_lbl.configure(text=bt)
                if self._vizzy:
                    self._vizzy.say(k, **kw)
            self._post_ui(_ui)

        def _run():
            try:
                from src.llm_engine import ollama_pull
                ollama_pull(model, progress_cb=prog)
                _log(f"Model download complete: {model}")
                self._post_ui(lambda m=model: self._model_dl_done(m))
            except Exception as exc:
                _log_exc(f"Model download failed: {exc}")
                self._post_ui(lambda e=str(exc): self._model_dl_failed(e))

        threading.Thread(target=_run, daemon=True).start()

    def _model_dl_done(self, model: str) -> None:
        self._dl_bar.set(1.0)
        self._dl_btn.configure(text="✅  Downloaded", state="disabled",
                                fg_color=C_OK, text_color=C_BG)
        self._dl_status.configure(text=f"✅  {model} is ready!", text_color=C_OK)
        self._dl_bytes_lbl.configure(text="")
        self._next_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.say("model_done")

    def _model_dl_failed(self, reason: str) -> None:
        self._dl_btn.configure(text="⬇  Retry Download", state="normal",
                                fg_color=C_ERR, text_color=C_BG)
        self._dl_status.configure(
            text="Download failed — see Debug Log for details", text_color=C_ERR)
        if self._vizzy:
            self._vizzy.say("ollama_error")

    # ─────────────────────────────────────────────────────────────────────
    # Step 4 — Finish
    # ─────────────────────────────────────────────────────────────────────

    def _step_finish(self) -> None:
        self._next_btn.configure(text="✅  Finish Setup", state="normal",
                                  fg_color=C_OK)
        self._step_header(
            "You're all set!",
            "Everything is installed and configured. Click Finish Setup to begin.",
        )
        for icon, text in [
            ("✅", "Ollama AI runtime installed"),
            ("✅", f"Model '{self._selected}' downloaded"),
            ("✅", "Ready to process ThousandEyes questionnaires"),
        ]:
            row = ctk.CTkFrame(self._content, fg_color="transparent")
            row.pack(fill="x", padx=40, pady=4)
            ctk.CTkLabel(row, text=icon,
                         font=ctk.CTkFont(size=16)).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(row, text=text,
                         font=ctk.CTkFont(size=13), text_color=C_TEXT).pack(side="left")
        self._divider()
        ctk.CTkLabel(
            self._content,
            text="💡  Tip: Keep Ollama running in the background for fastest startup.",
            font=ctk.CTkFont(size=12), text_color=C_MUTED, wraplength=560,
        ).pack(anchor="w", padx=30, pady=(4, 0))
        self._add_vizzy("finish")
        self._next_btn.configure(command=self._finish)
        self._back_btn.configure(state="disabled")

    def _finish(self) -> None:
        _log(f"Setup complete — model={self._selected}")
        SETUP_FLAG.touch()
        try:
            PREFS_FILE.write_text(json.dumps({"model": self._selected}))
        except Exception as exc:
            _log_exc(f"Could not write prefs: {exc}")
        self._completed = True
        self._on_complete(self._selected)
        self.destroy()
