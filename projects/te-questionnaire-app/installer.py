"""
TE Questionnaire Automator — First-Run Installer / Setup Wizard

Guides the user through:
  1. Welcome
  2. System requirements check
  3. Ollama installation & start
  4. LLM model download
  5. Finish / launch

Vizzy (the ThousandEyes eye mascot) guides the user through each step with
contextual tips and animated feedback.

Debug menu (top menubar → Debug) exposes a real-time log window and error info.
"""

from __future__ import annotations

import json
import os
import queue as _queue
import platform
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
from PIL import Image, ImageTk

# ── Colour palette (matches main app) ────────────────────────────────────────

C_BG      = "#0d1117"
C_SURFACE = "#161b22"
C_SURF2   = "#1c2330"
C_BORDER  = "#30363d"
C_TEXT    = "#e6edf3"
C_MUTED   = "#8b949e"
C_ACCENT  = "#58a6ff"
C_OK      = "#3fb950"
C_WARN    = "#e3b341"
C_ERR     = "#f85149"
C_ORANGE  = "#ff6600"

# ── Global constants ──────────────────────────────────────────────────────────

SETUP_FLAG  = Path.home() / ".te_qa_installed"
PREFS_FILE  = Path.home() / ".te_qa_prefs.json"
WIN_W, WIN_H = 880, 640

MODELS = [
    {
        "id":   "llama3.2",
        "name": "Llama 3.2 3B  (Recommended ⭐)",
        "size": "2.0 GB",
        "ram":  "8 GB",
        "desc": "Meta's Llama 3.2 — fast, smart, great instruction-following.",
    },
    {
        "id":   "phi3:mini",
        "name": "Phi-3 Mini",
        "size": "2.3 GB",
        "ram":  "8 GB",
        "desc": "Microsoft Phi-3 — very fast and surprisingly capable.",
    },
    {
        "id":   "llama3.2:3b",
        "name": "Llama 3.2 3B (explicit tag)",
        "size": "2.0 GB",
        "ram":  "8 GB",
        "desc": "Same as Llama 3.2 with explicit 3b tag.",
    },
    {
        "id":   "llama3.1:8b",
        "name": "Llama 3.1 8B",
        "size": "4.7 GB",
        "ram":  "16 GB",
        "desc": "Larger model — better answers, needs more RAM.",
    },
    {
        "id":   "mistral",
        "name": "Mistral 7B",
        "size": "4.1 GB",
        "ram":  "16 GB",
        "desc": "Strong reasoning, good for complex questions.",
    },
    {
        "id":   "qwen2.5:7b",
        "name": "Qwen 2.5 7B",
        "size": "4.4 GB",
        "ram":  "16 GB",
        "desc": "Alibaba's Qwen — excellent at structured tasks.",
    },
]

STEPS = ["Welcome", "Requirements", "Install AI Runtime", "Download Model", "All Done!"]


# ─────────────────────────────────────────────────────────────────────────────
# Debug / logging subsystem
# ─────────────────────────────────────────────────────────────────────────────

_debug_lines: List[str] = []
_debug_window_ref: Optional[object] = None   # weak ref to open debug window


def _log(msg: str, level: str = "INFO") -> None:
    """Append a timestamped line to the in-memory debug log."""
    ts   = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{level:<5}] {msg}"
    _debug_lines.append(line)
    # Live-update the open debug window if one exists
    global _debug_window_ref
    try:
        if _debug_window_ref and _debug_window_ref.winfo_exists():
            _debug_window_ref.append_line(line)
    except Exception:
        pass


def _log_exc(msg: str) -> None:
    """Log an exception with full traceback."""
    _log(msg, "ERROR")
    for ln in traceback.format_exc().splitlines():
        _log(f"    {ln}", "TRACE")


class DebugWindow(ctk.CTkToplevel):
    """Floating debug log viewer."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Debug Log — TE Questionnaire Automator")
        self.geometry("780x480")
        self.configure(fg_color=C_BG)

        global _debug_window_ref
        _debug_window_ref = self

        self._append_q: _queue.Queue = _queue.Queue()
        self.after(60, self._drain_append_q)   # start draining immediately

        # ── Toolbar ───────────────────────────────────────────────────────
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
                      command=self._copy_all).pack(side="left", padx=(0, 8), pady=6)

        self._auto_scroll_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(bar, text="Auto-scroll",
                        variable=self._auto_scroll_var,
                        font=ctk.CTkFont(size=11),
                        text_color=C_MUTED,
                        fg_color=C_ACCENT).pack(side="left", padx=8)

        ctk.CTkLabel(bar, text="🔴 LIVE",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_ERR).pack(side="right", padx=12)

        # ── Log textbox ───────────────────────────────────────────────────
        self._txt = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Courier", size=11),
            fg_color=C_SURF2,
            text_color=C_TEXT,
            wrap="none",
        )
        self._txt.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        # Populate with existing lines
        if _debug_lines:
            self._txt.configure(state="normal")
            self._txt.insert("1.0", "\n".join(_debug_lines) + "\n")
            self._txt.configure(state="disabled")
            self._txt.see("end")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def append_line(self, line: str) -> None:
        """Called from _log() when window is open — uses a queue for thread safety."""
        # The DebugWindow itself polls via its own after loop started in __init__
        self._append_q.put(line)

    def _drain_append_q(self) -> None:
        try:
            while True:
                line = self._append_q.get_nowait()
                self._txt.configure(state="normal")
                self._txt.insert("end", line + "\n")
                self._txt.configure(state="disabled")
                if self._auto_scroll_var.get():
                    self._txt.see("end")
        except _queue.Empty:
            pass
        try:
            self.after(60, self._drain_append_q)
        except Exception:
            pass

    def _clear(self):
        _debug_lines.clear()
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.configure(state="disabled")

    def _copy_all(self):
        self.clipboard_clear()
        self.clipboard_append("\n".join(_debug_lines))

    def _on_close(self):
        global _debug_window_ref
        _debug_window_ref = None
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Vizzy Panel — mascot widget
# ─────────────────────────────────────────────────────────────────────────────

# PIL images are rendered once and reused — avoids re-loading PNG + re-drawing
# on every animation tick (which blocks the main thread for 50-200 ms each time).
_VIZZY_PIL_CACHE: dict[str, Image.Image] = {}

def _get_vizzy_pil(expression: str, size: int) -> Image.Image:
    key = f"{expression}_{size}"
    if key not in _VIZZY_PIL_CACHE:
        from src.vizzy import create_vizzy
        _VIZZY_PIL_CACHE[key] = create_vizzy(expression=expression, size=size)
    return _VIZZY_PIL_CACHE[key]


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
    "ollama_error":   ("working",     "Something went wrong. Check the message above and try again. (Tip: open Debug → View Log for details.)"),
    "model_pick":     ("idle",        "Pick a model from the list. I recommend Llama 3.2 — fast and smart! Click Download when ready."),
    "model_already":  ("happy",       "That model is already downloaded! ✅  Just hit Continue."),
    "model_start":    ("downloading", "Starting the download… grab a snack — this could take a few minutes! 🍕"),
    "model_dl":       ("downloading", "Downloading: {done} / {total}  ({pct}%)  —  almost there!"),
    "model_verify":   ("working",     "Verifying the download… almost done!"),
    "model_done":     ("happy",       "Model downloaded and ready! 🎉  You're all set!"),
    "finish":         ("done",        "You did it! 🚀  Click 'Launch App' to start answering questionnaires with ThousandEyes knowledge!"),
}


class VizzyPanel(ctk.CTkFrame):
    """Mascot strip — Vizzy image on the left, speech bubble on the right."""

    def __init__(self, parent, initial_key: str = "welcome", **kwargs):
        super().__init__(parent,
                         fg_color=C_SURF2,
                         border_width=1,
                         border_color=C_BORDER,
                         corner_radius=12,
                         **kwargs)
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._current_expression: str = ""

        self._img_lbl = ctk.CTkLabel(self, text="")
        self._img_lbl.pack(side="left", padx=(14, 6), pady=10)

        bubble = ctk.CTkFrame(self,
                               fg_color=C_SURFACE,
                               border_width=2,
                               border_color=C_ACCENT,
                               corner_radius=14)
        bubble.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=10)

        self._msg = ctk.CTkLabel(bubble,
                                  text="",
                                  font=ctk.CTkFont(size=13),
                                  text_color=C_TEXT,
                                  wraplength=400,
                                  justify="left")
        self._msg.pack(padx=14, pady=10, anchor="w")

        self.vizzy_say(initial_key)

    def vizzy_say(self, key: str, **fmt) -> None:
        expression, tmpl = _VIZZY_MSG.get(key, ("idle", key))
        text = tmpl.format(**fmt) if fmt else tmpl
        # Only update text (cheap) on every call
        self._msg.configure(text=text)
        # Only re-render the image when expression actually changes (expensive)
        if expression != self._current_expression:
            self._update_image(expression)

    def _update_image(self, expression: str) -> None:
        try:
            pil_img = _get_vizzy_pil(expression, 105)
            self._photo = ImageTk.PhotoImage(pil_img)
            self._img_lbl.configure(image=self._photo, text="")
            self._current_expression = expression
        except Exception as exc:
            _log(f"VizzyPanel image update failed: {exc}", "WARN")
            self._img_lbl.configure(text="👁", font=ctk.CTkFont(size=40), image=None)


# ─────────────────────────────────────────────────────────────────────────────
# Installer window
# ─────────────────────────────────────────────────────────────────────────────

class Installer(ctk.CTk):

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("TE Questionnaire Automator — Setup")
        self.geometry(f"{WIN_W}x{WIN_H}")
        self.resizable(False, False)
        self.configure(fg_color=C_BG)

        self._step_idx   = 0
        self._selected   = MODELS[0]["id"]
        self._installed  = False

        self._vizzy:     Optional[VizzyPanel] = None
        self._dots_job:  Optional[str]        = None
        self._dots_n:    int                  = 0
        self._dots_slow: int                  = 0

        # Thread-safe UI update queue.
        # Background threads MUST NOT call tkinter APIs directly — instead they
        # call self._post_ui(fn) which queues fn for execution on the main thread.
        self._ui_q: _queue.Queue = _queue.Queue()

        _log(f"Installer started — Python {sys.version.split()[0]} "
             f"on {sys.platform} ({platform.machine()})")

        self._build_ui()
        self._poll_ui_queue()   # start draining the queue before first step
        self._show_step(0)

    # ── Menubar ───────────────────────────────────────────────────────────

    # ── Thread-safe UI queue ──────────────────────────────────────────────

    def _post_ui(self, fn: Callable) -> None:
        """
        Thread-safe way to schedule fn() on the main (Tk) thread.

        tkinter's after() is *not* reliably safe when called from non-main
        threads (the callback can be silently dropped depending on Tcl/Tk
        timing).  Instead, background threads put callables here and the
        main thread drains the queue via _poll_ui_queue.
        """
        self._ui_q.put(fn)

    def _poll_ui_queue(self) -> None:
        """Drain all pending UI callbacks then reschedule self every 40 ms."""
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception as exc:
                    _log_exc(f"UI queue callback raised: {exc}")
        except _queue.Empty:
            pass
        # Keep polling for the lifetime of the window
        self.after(40, self._poll_ui_queue)

    # ── Menubar ───────────────────────────────────────────────────────────

    def _build_menubar(self):
        """Native OS menubar with a Debug menu."""
        import tkinter as tk
        menubar = tk.Menu(self)

        # ── Debug menu ────────────────────────────────────────────────────
        debug_menu = tk.Menu(menubar, tearoff=0,
                              bg=C_SURFACE, fg=C_TEXT,
                              activebackground=C_ACCENT,
                              activeforeground=C_BG)
        debug_menu.add_command(label="View Debug Log",
                                command=self._open_debug_window)
        debug_menu.add_command(label="Copy Log to Clipboard",
                                command=self._copy_log)
        debug_menu.add_separator()
        debug_menu.add_command(label="System Info",
                                command=self._show_sysinfo)

        menubar.add_cascade(label="Debug", menu=debug_menu)
        self.configure(menu=menubar)

    def _open_debug_window(self):
        global _debug_window_ref
        if _debug_window_ref:
            try:
                if _debug_window_ref.winfo_exists():
                    _debug_window_ref.lift()
                    return
            except Exception:
                pass
        win = DebugWindow(self)
        win.lift()

    def _copy_log(self):
        self.clipboard_clear()
        self.clipboard_append("\n".join(_debug_lines))
        _log("Log copied to clipboard.")

    def _show_sysinfo(self):
        lines = [
            f"Platform : {sys.platform}",
            f"Machine  : {platform.machine()}",
            f"OS       : {platform.version()}",
            f"Python   : {sys.version}",
            f"Frozen   : {getattr(sys, 'frozen', False)}",
        ]
        if getattr(sys, "frozen", False):
            lines.append(f"MEIPASS  : {sys._MEIPASS}")   # type: ignore
        for ln in lines:
            _log(f"SYSINFO: {ln}")

        info_str = "\n".join(lines)
        win = ctk.CTkToplevel(self)
        win.title("System Info")
        win.geometry("540x240")
        win.configure(fg_color=C_BG)
        txt = ctk.CTkTextbox(win,
                              font=ctk.CTkFont(family="Courier", size=12),
                              fg_color=C_SURF2, text_color=C_TEXT)
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        txt.insert("1.0", info_str)
        txt.configure(state="disabled")

    # ── Top-level layout ──────────────────────────────────────────────────

    def _build_ui(self):
        self._build_menubar()

        # Brand bar
        brand = ctk.CTkFrame(self, fg_color=C_SURFACE,
                              border_width=0, corner_radius=0, height=54)
        brand.pack(fill="x")
        brand.pack_propagate(False)
        dot = ctk.CTkLabel(brand, text="●", font=ctk.CTkFont(size=14),
                            text_color=C_ORANGE)
        dot.pack(side="left", padx=(20, 6))
        ctk.CTkLabel(brand, text="TE QUESTIONNAIRE AUTOMATOR",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C_MUTED).pack(side="left")
        ctk.CTkLabel(brand, text="Setup Wizard",
                     font=ctk.CTkFont(size=12),
                     text_color=C_ACCENT).pack(side="right", padx=20)

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self._sidebar = self._build_sidebar(body)
        self._content = ctk.CTkScrollableFrame(body, fg_color=C_BG,
                                                corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        # Button bar
        bar = ctk.CTkFrame(self, fg_color=C_SURFACE,
                            border_width=0, corner_radius=0, height=62)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._back_btn = ctk.CTkButton(bar, text="← Back", width=110,
                                        fg_color=C_SURF2,
                                        border_width=1, border_color=C_BORDER,
                                        text_color=C_MUTED,
                                        command=self._go_back)
        self._back_btn.pack(side="left", padx=20, pady=12)

        self._next_btn = ctk.CTkButton(bar, text="Continue →", width=150,
                                        fg_color=C_ACCENT,
                                        text_color=C_BG,
                                        command=self._go_next)
        self._next_btn.pack(side="right", padx=20, pady=12)

    def _build_sidebar(self, parent) -> ctk.CTkFrame:
        side = ctk.CTkFrame(parent, fg_color=C_SURFACE, width=195,
                             border_width=0, corner_radius=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        ctk.CTkLabel(side, text="STEPS",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED).pack(anchor="w", padx=20, pady=(20, 8))
        self._step_labels: list[ctk.CTkLabel] = []
        for i, name in enumerate(STEPS):
            lbl = ctk.CTkLabel(side, text=f"  {i+1}. {name}",
                               font=ctk.CTkFont(size=13),
                               text_color=C_MUTED, anchor="w")
            lbl.pack(fill="x", padx=8, pady=2)
            self._step_labels.append(lbl)

        # Debug shortcut at bottom of sidebar
        ctk.CTkButton(side, text="🐛 Debug Log", width=140,
                      fg_color="transparent", border_width=1,
                      border_color=C_BORDER, text_color=C_MUTED,
                      font=ctk.CTkFont(size=11),
                      command=self._open_debug_window).pack(
                          side="bottom", padx=16, pady=12)
        return side

    # ── Step navigation ───────────────────────────────────────────────────

    def _show_step(self, idx: int):
        self._step_idx = idx
        self._stop_dots()
        _log(f"Showing step {idx}: {STEPS[idx]}")

        for i, lbl in enumerate(self._step_labels):
            if i == idx:
                lbl.configure(text_color=C_ACCENT,
                              font=ctk.CTkFont(size=13, weight="bold"))
            elif i < idx:
                lbl.configure(text_color=C_OK,
                              font=ctk.CTkFont(size=13))
            else:
                lbl.configure(text_color=C_MUTED,
                              font=ctk.CTkFont(size=13))

        for w in self._content.winfo_children():
            w.destroy()
        self._vizzy = None
        self._back_btn.configure(state="normal" if idx > 0 else "disabled")

        [self._step_welcome,
         self._step_requirements,
         self._step_ollama,
         self._step_model,
         self._step_finish][idx]()

    def _go_next(self):
        if self._step_idx == len(STEPS) - 1:
            self._finish()
        elif self._step_idx < len(STEPS) - 1:
            self._show_step(self._step_idx + 1)

    def _go_back(self):
        if self._step_idx > 0:
            self._show_step(self._step_idx - 1)

    # ── Shared helpers ────────────────────────────────────────────────────

    def _step_header(self, title: str, subtitle: str):
        ctk.CTkLabel(self._content, text=title,
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=30, pady=(28, 4))
        ctk.CTkLabel(self._content, text=subtitle,
                     font=ctk.CTkFont(size=13), text_color=C_MUTED,
                     wraplength=610, justify="left").pack(
                         anchor="w", padx=30, pady=(0, 20))

    def _divider(self):
        ctk.CTkFrame(self._content, fg_color=C_BORDER,
                     height=1, corner_radius=0).pack(fill="x", padx=30, pady=8)

    def _add_vizzy(self, key: str = "welcome") -> VizzyPanel:
        vz = VizzyPanel(self._content, initial_key=key)
        vz.pack(fill="x", padx=30, pady=(14, 22))
        self._vizzy = vz
        return vz

    # ── Dots animation ────────────────────────────────────────────────────

    def _start_dots(self, key: str = "req_checking",
                    slow_key: str = "req_slow",
                    slow_after_ticks: int = 14,
                    delay_ms: int = 400):
        self._stop_dots()
        self._dots_n    = 0
        self._dots_slow = 0
        self._dots_key  = key
        self._dots_slow_key = slow_key
        self._dots_slow_after = slow_after_ticks

        def _tick():
            if self._vizzy is None:
                return
            n = self._dots_n % 4
            self._vizzy.vizzy_say(key, dots="." * n)
            self._dots_n += 1
            self._dots_slow += 1
            if self._dots_slow >= slow_after_ticks:
                if self._vizzy:
                    self._vizzy.vizzy_say(slow_key)
                return   # stop ticking — message is now "slow" fallback
            self._dots_job = self.after(delay_ms, _tick)

        _tick()

    def _stop_dots(self):
        if self._dots_job:
            self.after_cancel(self._dots_job)
            self._dots_job = None

    # ─────────────────────────────────────────────────────────────────────
    # Step 0 — Welcome
    # ─────────────────────────────────────────────────────────────────────

    def _step_welcome(self):
        self._next_btn.configure(text="Continue →", state="normal",
                                  fg_color=C_ACCENT)
        self._step_header(
            "Welcome to TE Questionnaire Automator",
            "This wizard will get everything set up so you can automatically "
            "answer ThousandEyes questionnaires using a local AI model — "
            "no internet connection required after setup, no API keys, "
            "and no data leaves your machine.",
        )
        for icon, text in [
            ("📄", "Accepts Excel, CSV, Word, PDF, and plain-text files"),
            ("🔍", "Searches docs.thousandeyes.com for accurate answers"),
            ("🤖", "Runs a local AI model via Ollama (100% private)"),
            ("📝", "Writes answers back into the original file"),
        ]:
            row = ctk.CTkFrame(self._content, fg_color="transparent")
            row.pack(fill="x", padx=40, pady=3)
            ctk.CTkLabel(row, text=icon,
                         font=ctk.CTkFont(size=18)).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(row, text=text,
                         font=ctk.CTkFont(size=13),
                         text_color=C_TEXT).pack(side="left")
        self._divider()
        ctk.CTkLabel(self._content,
                     text="Setup takes about 5–10 minutes depending on your connection.",
                     font=ctk.CTkFont(size=12), text_color=C_MUTED).pack(
                         anchor="w", padx=30, pady=(0, 4))
        self._add_vizzy("welcome")

    # ─────────────────────────────────────────────────────────────────────
    # Step 1 — System requirements
    # ─────────────────────────────────────────────────────────────────────

    def _step_requirements(self):
        self._next_btn.configure(text="Continue →", state="disabled",
                                  fg_color=C_ACCENT)
        self._step_header(
            "System Requirements",
            "Checking your system to make sure everything is compatible.",
        )

        # Result grid
        checks_meta = [
            ("os",      "Operating System",  "macOS 12+ or Windows 10+"),
            ("python",  "Python version",    f"{sys.version.split()[0]}"),
            ("disk",    "Free disk space",   "≥ 8 GB recommended"),
            ("memory",  "Memory",            "≥ 8 GB RAM recommended"),
            ("network", "Network",           "Required for first download"),
        ]

        self._req_rows: dict[str, ctk.CTkLabel] = {}
        grid = ctk.CTkFrame(self._content, fg_color=C_SURFACE,
                             border_width=1, border_color=C_BORDER,
                             corner_radius=10)
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
                                font=ctk.CTkFont(size=12),
                                text_color=C_MUTED, width=130, anchor="w")
            slbl.pack(side="left")
            self._req_rows[key] = slbl

        # Error / detail box (hidden initially)
        self._req_error_lbl = ctk.CTkLabel(
            self._content, text="",
            font=ctk.CTkFont(size=12), text_color=C_ERR,
            wraplength=580, justify="left")
        self._req_error_lbl.pack(anchor="w", padx=30, pady=(6, 0))

        vz = self._add_vizzy("req_checking")
        self._start_dots("req_checking", slow_key="req_slow",
                         slow_after_ticks=16, delay_ms=380)

        threading.Thread(target=self._run_req_checks, daemon=True).start()

    def _run_req_checks(self):
        """
        Run each check independently with individual try/except blocks and
        strict timeouts.  Nothing here can hang the UI.
        """
        time.sleep(0.15)   # let the UI render first
        results:  dict[str, bool]  = {}
        details:  dict[str, str]   = {}
        errors:   list[str]        = []

        # ── 1. OS ─────────────────────────────────────────────────────────
        try:
            os_ok = sys.platform in ("darwin", "win32", "linux")
            results["os"]  = os_ok
            details["os"]  = f"{sys.platform} / {platform.version()[:60]}"
            _log(f"REQ os: {'OK' if os_ok else 'FAIL'} — {details['os']}")
        except Exception as exc:
            results["os"] = True   # don't block on this
            _log_exc(f"REQ os check failed: {exc}")

        # ── 2. Python ─────────────────────────────────────────────────────
        try:
            pv     = sys.version_info
            py_ok  = (pv.major, pv.minor) >= (3, 10)
            results["python"] = py_ok
            details["python"] = f"{pv.major}.{pv.minor}.{pv.micro}"
            _log(f"REQ python: {'OK' if py_ok else 'FAIL'} — {details['python']}")
            if not py_ok:
                errors.append(f"Python {details['python']} detected — 3.10+ required.")
        except Exception as exc:
            results["python"] = True
            _log_exc(f"REQ python check failed: {exc}")

        # ── 3. Disk ───────────────────────────────────────────────────────
        try:
            stat      = shutil.disk_usage(Path.home())
            free_gb   = stat.free / (1024 ** 3)
            disk_ok   = free_gb >= 5.0
            results["disk"]  = disk_ok
            details["disk"]  = f"{free_gb:.1f} GB free"
            _log(f"REQ disk: {'OK' if disk_ok else 'WARN'} — {details['disk']}")
            if not disk_ok:
                errors.append(f"Only {free_gb:.1f} GB free — 8 GB recommended.")
        except Exception as exc:
            results["disk"] = True
            _log_exc(f"REQ disk check failed: {exc}")

        # ── 4. Memory ─────────────────────────────────────────────────────
        try:
            mem_ok = True
            mem_gb = 0.0
            # Try psutil first, fall back to platform-specific calls
            try:
                import psutil  # type: ignore
                mem_gb = psutil.virtual_memory().total / (1024 ** 3)
                mem_ok = mem_gb >= 7.5
            except ImportError:
                # macOS / Linux fallback
                if sys.platform == "darwin":
                    out = subprocess.check_output(
                        ["sysctl", "-n", "hw.memsize"], timeout=3).decode().strip()
                    mem_gb = int(out) / (1024 ** 3)
                    mem_ok = mem_gb >= 7.5
                else:
                    mem_ok = True   # can't determine — allow
            results["memory"]  = mem_ok
            details["memory"]  = f"{mem_gb:.1f} GB RAM" if mem_gb else "unknown"
            _log(f"REQ memory: {'OK' if mem_ok else 'WARN'} — {details['memory']}")
            if not mem_ok:
                errors.append(f"Only {mem_gb:.1f} GB RAM — 8 GB recommended.")
        except Exception as exc:
            results["memory"] = True
            _log_exc(f"REQ memory check failed: {exc}")

        # ── 5. Network ────────────────────────────────────────────────────
        # IMPORTANT: never use ThreadPoolExecutor as a context manager here.
        # On timeout the `with` block calls shutdown(wait=True) and hangs
        # indefinitely waiting for a stuck DNS/socket thread.
        # Instead we use a plain daemon thread + threading.Event.
        try:
            _log("REQ network: TCP ping to ollama.com:443 …")
            _net_result: list[bool] = []
            _net_done   = threading.Event()

            def _ping_daemon():
                try:
                    sock = socket.create_connection(("ollama.com", 443), timeout=4)
                    sock.close()
                    _net_result.append(True)
                except Exception as e:
                    _log(f"REQ network socket error: {e}", "WARN")
                    _net_result.append(False)
                finally:
                    _net_done.set()

            t = threading.Thread(target=_ping_daemon, daemon=True)
            t.start()
            _net_done.wait(timeout=6)   # block at most 6 s; daemon thread dies with app

            net_ok = bool(_net_result and _net_result[0])
            results["network"]  = net_ok
            details["network"]  = "reachable" if net_ok else "unreachable (offline?)"
            _log(f"REQ network: {'OK' if net_ok else 'WARN'} — {details['network']}")
            if not net_ok:
                errors.append(
                    "Network appears offline or blocked. "
                    "Internet is required for the first download.")
        except Exception as exc:
            results["network"] = True
            _log_exc(f"REQ network check failed: {exc}")

        # ── Update UI ─────────────────────────────────────────────────────
        all_ok = all(results.values())
        _log(f"REQ all checks done — all_ok={all_ok}")

        def _update():
            try:
                self._stop_dots()
                col_map  = {True: C_OK,   False: C_WARN}
                for key, ok in results.items():
                    lbl = self._req_rows.get(key)
                    if lbl:
                        detail = details.get(key, "")
                        icon   = "✅" if ok else "⚠️"
                        label_text = f"{icon}  {detail}" if detail else f"{icon}  {'OK' if ok else 'Warning'}"
                        # Split into two configure calls — avoids a CTkLabel
                        # silent-fail when both text and text_color are passed
                        # together inside a CTkScrollableFrame.
                        lbl.configure(text=label_text)
                        lbl.configure(text_color=col_map[ok])
                        _log(f"REQ UI updated: {key} → {label_text}")

                if errors:
                    self._req_error_lbl.configure(
                        text="⚠️  " + "  ·  ".join(errors))

                self._next_btn.configure(state="normal")
                # Force a visual refresh so the scrollable frame redraws
                self.update_idletasks()

                if self._vizzy:
                    self._vizzy.vizzy_say("req_ok" if all_ok else "req_warn")
            except Exception as exc:
                _log_exc(f"_update() crashed: {exc}")
                # Ensure Continue is always reachable even if update fails
                try:
                    self._next_btn.configure(state="normal")
                except Exception:
                    pass

        # Use _post_ui (not after(0,...)) — after() from a non-main thread
        # can silently drop the callback in some Tcl/Tk versions.
        self._post_ui(_update)

    # ─────────────────────────────────────────────────────────────────────
    # Step 2 — Ollama
    # ─────────────────────────────────────────────────────────────────────

    def _step_ollama(self):
        self._next_btn.configure(text="Continue →", state="disabled",
                                  fg_color=C_ACCENT)
        self._step_header(
            "Install AI Runtime (Ollama)",
            "Ollama runs open-source AI models locally on your machine. "
            "It only needs to be installed once.",
        )

        srow = ctk.CTkFrame(self._content, fg_color=C_SURFACE,
                             border_width=1, border_color=C_BORDER,
                             corner_radius=10)
        srow.pack(fill="x", padx=30, pady=(0, 10))

        irow = ctk.CTkFrame(srow, fg_color="transparent")
        irow.pack(fill="x", padx=16, pady=14)

        self._ollama_status_lbl = ctk.CTkLabel(
            irow, text="Checking for Ollama…",
            font=ctk.CTkFont(size=13), text_color=C_MUTED, anchor="w")
        self._ollama_status_lbl.pack(side="left", expand=True, fill="x")

        self._ollama_install_btn = ctk.CTkButton(
            irow, text="Install Ollama", width=140,
            fg_color=C_ACCENT, text_color=C_BG,
            command=self._do_install_ollama, state="disabled")
        self._ollama_install_btn.pack(side="right")

        self._ollama_log = ctk.CTkTextbox(
            self._content, height=120,
            fg_color=C_SURF2, text_color=C_MUTED,
            font=ctk.CTkFont(family="Courier", size=11),
            border_width=1, border_color=C_BORDER, corner_radius=8)
        self._ollama_log.pack(fill="x", padx=30, pady=(0, 8))
        self._ollama_log.configure(state="disabled")

        self._add_vizzy("ollama_check")
        self._start_dots("ollama_check", slow_key="ollama_slow",
                         slow_after_ticks=14, delay_ms=420)

        threading.Thread(target=self._check_ollama_installed, daemon=True).start()

    def _ollama_log_append(self, text: str):
        _log(f"OLLAMA_LOG: {text}")
        def _do():
            self._ollama_log.configure(state="normal")
            self._ollama_log.insert("end", text + "\n")
            self._ollama_log.see("end")
            self._ollama_log.configure(state="disabled")
        self._post_ui(_do)

    def _check_ollama_installed(self):
        """
        Fast two-stage check — 0.6 s daemon ping then binary scan.
        Never blocks longer than ~2 seconds total.
        """
        _log("Ollama check: pinging daemon…")
        self._ollama_log_append("Pinging Ollama daemon on localhost:11434…")

        daemon_up = False
        try:
            import requests as _req
            r = _req.get("http://localhost:11434/", timeout=0.7)
            daemon_up = r.status_code in (200, 404)
            _log(f"Ollama daemon HTTP status: {r.status_code}")
        except Exception as exc:
            _log(f"Ollama daemon not reachable: {exc}", "WARN")

        if daemon_up:
            self._ollama_log_append("✅  Daemon is responding.")
            self._post_ui(self._ollama_already_running)
            return

        self._ollama_log_append("Daemon not found — scanning for binary…")
        _log("Ollama check: scanning binary locations…")

        binary_found = bool(shutil.which("ollama"))
        for candidate in [
            "/usr/local/bin/ollama",
            "/opt/homebrew/bin/ollama",
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
            # Poll for daemon with fast sub-second checks
            for attempt in range(10):
                time.sleep(0.35)
                try:
                    import requests as _req
                    r = _req.get("http://localhost:11434/", timeout=0.4)
                    if r.status_code in (200, 404):
                        self._ollama_log_append("✅  Daemon is now running.")
                        _log("Ollama daemon started successfully.")
                        self._post_ui(self._ollama_already_running)
                        return
                except Exception:
                    pass
            _log("Ollama binary found but daemon didn't respond in time.", "WARN")
            self._post_ui(self._ollama_binary_not_running)
        else:
            _log("Ollama binary not found on this machine.")
            self._ollama_log_append("⚠️  Ollama not installed.")
            self._post_ui(self._ollama_not_installed)

    def _start_ollama_daemon(self):
        try:
            if sys.platform == "darwin":
                if Path("/Applications/Ollama.app").exists():
                    subprocess.Popen(["open", "-a", "Ollama"],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    _log("Launched Ollama.app via 'open'")
                else:
                    subprocess.Popen(["ollama", "serve"],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    _log("Launched 'ollama serve'")
            elif sys.platform == "win32":
                subprocess.Popen(["ollama", "serve"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen(["ollama", "serve"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except Exception as exc:
            _log_exc(f"Could not start Ollama daemon: {exc}")
            self._ollama_log_append(f"⚠️  Could not auto-start daemon: {exc}")

    def _ollama_already_running(self):
        self._stop_dots()
        self._ollama_status_lbl.configure(
            text="✅  Ollama is installed and running", text_color=C_OK)
        self._next_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.vizzy_say("ollama_running")

    def _ollama_binary_not_running(self):
        self._stop_dots()
        self._ollama_status_lbl.configure(
            text="⚠️  Ollama found but not responding — try 'Install Ollama' to repair",
            text_color=C_WARN)
        self._ollama_install_btn.configure(state="normal")
        self._next_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.vizzy_say("ollama_missing")

    def _ollama_not_installed(self):
        self._stop_dots()
        self._ollama_status_lbl.configure(
            text="Ollama is not installed — click 'Install Ollama' to continue",
            text_color=C_WARN)
        self._ollama_install_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.vizzy_say("ollama_missing")

    def _do_install_ollama(self):
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
            self._vizzy.vizzy_say("ollama_install")
        threading.Thread(target=self._install_ollama_thread, daemon=True).start()

    def _install_ollama_thread(self):
        try:
            if sys.platform == "darwin":
                self._ollama_log_append("Requesting administrator privileges…")
                _log("macOS install: using osascript for privileged execution")

                # Write the install script to a temp file so we don't have to
                # worry about shell-escaping a pipe inside the AppleScript string.
                script_path = "/tmp/te_qa_ollama_install.sh"
                log_path    = "/tmp/te_qa_ollama_install.log"
                with open(script_path, "w") as f:
                    f.write("#!/bin/bash\ncurl -fsSL https://ollama.com/install.sh | bash\n")
                os.chmod(script_path, 0o755)

                # 'do shell script ... with administrator privileges' raises the
                # native macOS authentication dialog — no terminal required.
                # The installer's output is captured to a log file we can read back.
                applescript = (
                    f'do shell script "bash {script_path} > {log_path} 2>&1" '
                    f'with administrator privileges'
                )
                _log(f"Launching AppleScript: {applescript}")
                result = subprocess.run(
                    ["osascript", "-e", applescript],
                    capture_output=True, text=True, timeout=360,
                )

                # Stream install log to UI
                try:
                    with open(log_path) as lf:
                        for line in lf.read().splitlines():
                            if line.strip():
                                self._ollama_log_append(line)
                                _log(f"INSTALL: {line}")
                except Exception as read_err:
                    _log(f"Could not read install log: {read_err}", "WARN")

                # Detect user-cancelled dialog
                stderr_txt = result.stderr.strip()
                if result.returncode != 0:
                    if "canceled" in stderr_txt.lower() or "cancelled" in stderr_txt.lower():
                        self._post_ui(lambda: self._ollama_install_failed(
                            "Installation cancelled — no changes were made."))
                    else:
                        msg = stderr_txt or f"Exit code {result.returncode}"
                        self._post_ui(lambda m=msg: self._ollama_install_failed(m))
                    return

            elif sys.platform == "win32":
                self._ollama_log_append("Downloading Windows installer via PowerShell…")
                ps_cmd = (
                    "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' "
                    "-OutFile \"$env:TEMP\\OllamaSetup.exe\"; "
                    "Start-Process -FilePath \"$env:TEMP\\OllamaSetup.exe\" -Wait"
                )
                result = subprocess.run(
                    ["powershell", "-Command", ps_cmd],
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
            _log("Ollama install timed out.", "ERROR")
            self._post_ui(lambda: self._ollama_install_failed(
                "Installation timed out — please try again or install manually from ollama.com"))
        except Exception as exc:
            _log_exc(f"Ollama install error: {exc}")
            self._post_ui(lambda e=str(exc): self._ollama_install_failed(e))

    def _ollama_install_done(self):
        self._ollama_status_lbl.configure(
            text="✅  Ollama installed and running!", text_color=C_OK)
        self._next_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.vizzy_say("ollama_running")

    def _ollama_install_failed(self, reason: str):
        _log(f"Ollama install failed: {reason}", "ERROR")
        self._ollama_status_lbl.configure(
            text="Installation failed — see log below", text_color=C_ERR)
        self._ollama_log_append(f"ERROR: {reason}")
        self._ollama_log_append("Tip: open Debug → View Log for full details.")
        self._ollama_install_btn.configure(state="normal", text="Retry Install")
        if self._vizzy:
            self._vizzy.vizzy_say("ollama_error")

    # ─────────────────────────────────────────────────────────────────────
    # Step 3 — Model download
    # ─────────────────────────────────────────────────────────────────────

    def _step_model(self):
        self._next_btn.configure(text="Continue →", state="disabled",
                                  fg_color=C_ACCENT)
        self._step_header(
            "Download AI Model",
            "Choose a model and download it.  It will be stored locally "
            "and used to answer your questionnaires.",
        )

        # Model radio buttons
        self._model_var = ctk.StringVar(value=self._selected)
        for m in MODELS:
            row = ctk.CTkFrame(self._content, fg_color=C_SURFACE,
                               border_width=1, border_color=C_BORDER,
                               corner_radius=8)
            row.pack(fill="x", padx=30, pady=3)
            rb = ctk.CTkRadioButton(
                row, text=m["name"],
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=C_TEXT,
                variable=self._model_var,
                value=m["id"],
                fg_color=C_ACCENT,
                command=lambda mid=m["id"]: self._set_model(mid))
            rb.pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(row, text=f"⬇ {m['size']}",
                         font=ctk.CTkFont(size=11),
                         text_color=C_MUTED).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(row, text=f"🧠 {m['ram']}",
                         font=ctk.CTkFont(size=11),
                         text_color=C_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=m["desc"],
                         font=ctk.CTkFont(size=11), text_color=C_MUTED,
                         wraplength=270, justify="left").pack(
                             side="right", padx=12, pady=4)

        # Controls
        ctrl = ctk.CTkFrame(self._content, fg_color="transparent")
        ctrl.pack(fill="x", padx=30, pady=(12, 4))

        self._dl_btn = ctk.CTkButton(
            ctrl, text="⬇  Download", width=150,
            fg_color=C_ACCENT, text_color=C_BG,
            command=self._do_pull_model)
        self._dl_btn.pack(side="left")

        self._dl_status = ctk.CTkLabel(
            ctrl, text="Select a model and click Download.",
            font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._dl_status.pack(side="left", padx=16)

        # Progress bar
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

    def _set_model(self, mid: str):
        self._selected = mid
        _log(f"Model selected: {mid}")

    def _do_pull_model(self):
        model = self._selected
        _log(f"Starting model download: {model}")
        self._dl_btn.configure(text="⏳  Downloading…", state="disabled",
                                fg_color=C_SURF2, text_color=C_WARN)
        self._dl_status.configure(text="Connecting to Ollama…", text_color=C_MUTED)
        self._dl_bar.set(0)
        self._dl_bytes_lbl.configure(text="")
        if self._vizzy:
            self._vizzy.vizzy_say("model_start")

        def prog(fraction: float, status: str,
                 completed_bytes: int = 0, total_bytes: int = 0):
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
                    self._vizzy.vizzy_say(k, **kw)
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

    def _model_dl_done(self, model: str):
        self._dl_bar.set(1.0)
        self._dl_btn.configure(text="✅  Downloaded", state="disabled",
                                fg_color=C_OK, text_color=C_BG)
        self._dl_status.configure(text=f"✅  {model} is ready!", text_color=C_OK)
        self._dl_bytes_lbl.configure(text="")
        self._next_btn.configure(state="normal")
        if self._vizzy:
            self._vizzy.vizzy_say("model_done")

    def _model_dl_failed(self, reason: str):
        self._dl_btn.configure(text="⬇  Retry Download", state="normal",
                                fg_color=C_ERR, text_color=C_BG)
        self._dl_status.configure(
            text=f"Download failed — see Debug Log for details",
            text_color=C_ERR)
        if self._vizzy:
            self._vizzy.vizzy_say("ollama_error")

    # ─────────────────────────────────────────────────────────────────────
    # Step 4 — Finish
    # ─────────────────────────────────────────────────────────────────────

    def _step_finish(self):
        self._next_btn.configure(text="🚀  Launch App", state="normal",
                                  fg_color=C_OK)
        self._step_header(
            "You're all set!",
            "Everything is installed and configured. Click Launch App to begin.",
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
                         font=ctk.CTkFont(size=13),
                         text_color=C_TEXT).pack(side="left")
        self._divider()
        ctk.CTkLabel(
            self._content,
            text="💡  Tip: Keep Ollama running in the background for fastest startup.",
            font=ctk.CTkFont(size=12), text_color=C_MUTED,
            wraplength=560,
        ).pack(anchor="w", padx=30, pady=(4, 0))
        self._add_vizzy("finish")
        self._next_btn.configure(command=self._finish)
        self._back_btn.configure(state="disabled")

    def _finish(self):
        _log("User completed setup — writing flag files.")
        SETUP_FLAG.touch()
        prefs = {"model": self._selected}
        try:
            PREFS_FILE.write_text(json.dumps(prefs))
        except Exception as exc:
            _log_exc(f"Could not write prefs: {exc}")
        self._installed = True
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_installer() -> bool:
    """Run the setup wizard.  Returns True if setup completed successfully."""
    app = Installer()
    app.mainloop()
    return app._installed


if __name__ == "__main__":
    run_installer()
