"""
User feedback store for the ThousandEyes Questionnaire Automator.

Persists hand-corrected answers permanently to disk.  Unlike the LLM cache
(7-day TTL, auto-generated), feedback entries:
  • Never expire
  • Take priority over both the LLM cache and fresh LLM inference
  • Store the original answer alongside the correction for one-click revert
  • Are matched fuzzily — a stored correction for "Does TE support BGP?"
    also applies to "Does ThousandEyes support BGP monitoring?" (≥0.80 similarity)

Storage: ~/.te_qa_feedback.json
"""

from __future__ import annotations

import difflib
import json
import time
from pathlib import Path
from typing import Optional

FEEDBACK_PATH = Path.home() / ".te_qa_feedback.json"
_FUZZY_THRESHOLD = 0.80   # SequenceMatcher ratio required for a match


def _normalise(text: str) -> str:
    """Lowercase, strip, collapse whitespace for consistent comparison."""
    return " ".join(text.lower().split())


class FeedbackStore:
    """
    Permanent store for user-corrected answers.

    Keys are normalised question strings (not hashes) so fuzzy lookup can
    compare them against incoming questions at match time.

    Thread safety: reads are safe from any thread; writes are serialised by
    the GIL + atomic file replacement (write-on-every-set).  Concurrent
    write contention is negligible — a human saves one correction at a time.
    """

    def __init__(self) -> None:
        # {normalised_question: {question, answer, source_url,
        #                        original_answer, corrected_at}}
        self._data: dict[str, dict] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, question: str) -> Optional[dict]:
        """
        Return the stored correction for *question*, or ``None``.

        Lookup order:
        1. Exact match on the normalised question string.
        2. Best fuzzy match via ``difflib.SequenceMatcher`` if ratio ≥ 0.80.
        """
        norm = _normalise(question)
        if norm in self._data:
            return self._data[norm]

        # Fuzzy fallback
        best_ratio  = 0.0
        best_entry  = None
        for stored_norm, entry in self._data.items():
            ratio = difflib.SequenceMatcher(
                None, norm, stored_norm, autojunk=False
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_entry = entry

        return best_entry if best_ratio >= _FUZZY_THRESHOLD else None

    def set(
        self,
        question: str,
        answer: str,
        source_url: Optional[str] = None,
        original_answer: Optional[str] = None,
    ) -> None:
        """Persist a user correction."""
        norm = _normalise(question)
        self._data[norm] = {
            "question":        question,
            "answer":          answer,
            "source_url":      source_url,
            "original_answer": original_answer,
            "corrected_at":    time.time(),
        }
        self._save()

    def remove(self, question: str) -> bool:
        """
        Delete the correction for *question* (exact or fuzzy match).
        Returns True if an entry was found and deleted.
        """
        norm = _normalise(question)
        if norm in self._data:
            del self._data[norm]
            self._save()
            return True

        # Fuzzy removal — find the best match and delete it
        best_ratio = 0.0
        best_key   = None
        for stored_norm in self._data:
            ratio = difflib.SequenceMatcher(
                None, norm, stored_norm, autojunk=False
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_key   = stored_norm

        if best_ratio >= _FUZZY_THRESHOLD and best_key:
            del self._data[best_key]
            self._save()
            return True

        return False

    def clear(self) -> int:
        """Remove all corrections.  Returns the count of deleted entries."""
        count = len(self._data)
        self._data.clear()
        self._save()
        return count

    def stats(self) -> dict:
        """Return ``{"entries": N, "path": str}``."""
        return {
            "entries": len(self._data),
            "path":    str(FEEDBACK_PATH),
        }

    def all_entries(self) -> list[dict]:
        """Return all corrections sorted newest-first."""
        return sorted(
            self._data.values(),
            key=lambda e: e.get("corrected_at", 0),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        try:
            if FEEDBACK_PATH.exists():
                return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save(self) -> None:
        try:
            FEEDBACK_PATH.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # Non-fatal — the in-memory store still works for this session
