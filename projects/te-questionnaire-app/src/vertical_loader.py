"""
Vertical Knowledge Base — loads industry-specific pre-validated Q&A pairs from
JSON files and provides fuzzy requirement matching.

Priority in the processor pipeline
───────────────────────────────────
  User feedback (permanent corrections)          ← priority 1
  Vertical KB  (high confidence ≥ 0.85)          ← priority 2  ← THIS MODULE
  LLM cache    (7-day TTL)                        ← priority 3
  Fresh LLM    (+ vertical hint if 0.60–0.84)    ← priority 4

High-confidence matches return a pre-validated answer instantly (< 1 ms).
Medium-confidence matches are surfaced as context hints that steer the LLM
without bypassing it, giving more consistent answers without sacrificing
accuracy for borderline cases.

Data directory
──────────────
Development : <project_root>/data/vertical_knowledge/
PyInstaller : sys._MEIPASS/data/vertical_knowledge/
"""

from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Path resolution (source or PyInstaller bundle)
# ---------------------------------------------------------------------------

def _default_data_dir() -> Path:
    """
    Resolve the data/vertical_knowledge directory regardless of whether the
    app is running from source or inside a frozen PyInstaller .app bundle.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)          # inside .app bundle
    else:
        base = Path(__file__).parent.parent  # src/ → project root
    return base / "data" / "vertical_knowledge"


# ---------------------------------------------------------------------------
# Confidence thresholds (exposed so processor.py can reference them cleanly)
# ---------------------------------------------------------------------------

HIGH_CONFIDENCE = 0.85   # use pre-validated answer directly (bypass LLM)
MED_CONFIDENCE  = 0.60   # use as context hint; still run LLM inference


# ---------------------------------------------------------------------------
# VerticalKnowledgeBase
# ---------------------------------------------------------------------------

class VerticalKnowledgeBase:
    """
    Loads all ``vertical_knowledge_*.json`` files from *knowledge_dir* and
    provides :meth:`match` for fuzzy requirement lookup.

    Each JSON file follows the schema::

        {
          "vertical": "Healthcare",
          "description": "...",
          "last_updated": "2026-04-03",
          "common_requirements": [
            {
              "category": "...",
              "requirement": "...",
              "support_level": "yes|partial|not_applicable",
              "answer": "...",
              "source_url": "https://...",
              "keywords": [...]
            }
          ]
        }
    """

    def __init__(self, knowledge_dir: Optional[Path | str] = None) -> None:
        self._dir = (
            Path(knowledge_dir) if knowledge_dir else _default_data_dir()
        )
        # vertical name (lowercase) → full JSON dict
        self.verticals: dict[str, dict] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """Load every ``vertical_knowledge_*.json`` in the data directory."""
        if not self._dir.exists():
            return
        for jf in sorted(self._dir.glob("vertical_knowledge_*.json")):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                name = data.get("vertical", jf.stem).lower()
                self.verticals[name] = data
            except Exception:
                pass   # skip malformed files silently; errors are non-fatal

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def loaded_count(self) -> int:
        """Return the number of verticals successfully loaded."""
        return len(self.verticals)

    def list_verticals(self) -> list[str]:
        """Return all loaded vertical names (lowercase)."""
        return list(self.verticals.keys())

    def match(
        self,
        text: str,
        vertical: Optional[str] = None,
        threshold: float = MED_CONFIDENCE,
    ) -> Optional[dict]:
        """
        Find the best-matching requirement entry for *text*.

        Parameters
        ----------
        text:
            The incoming question or RFP requirement.
        vertical:
            If given, restrict search to this vertical (case-insensitive).
            Falls back to all verticals if the name is not found.
        threshold:
            Minimum score required to return a match (0–1).  Use
            ``HIGH_CONFIDENCE`` (0.85) for "use directly" decisions and
            ``MED_CONFIDENCE`` (0.60) for "context hint" decisions.

        Returns
        -------
        dict | None
            The best matching entry (all original JSON fields) with two
            extra keys:  ``"vertical"`` (human-readable name) and
            ``"match_score"`` (float).  Returns *None* if no entry meets
            *threshold*.
        """
        text_lower = text.lower()

        if vertical and vertical.lower() in self.verticals:
            search = {vertical.lower(): self.verticals[vertical.lower()]}
        else:
            search = self.verticals

        best: Optional[dict] = None
        best_score = 0.0

        for vert_name, vert_data in search.items():
            if not vert_data:
                continue
            for req in vert_data.get("common_requirements", []):
                score = self._score(
                    text_lower,
                    req.get("requirement", "").lower(),
                    req.get("keywords", []),
                )
                if score > best_score and score >= threshold:
                    best_score = score
                    best = {
                        **req,
                        "vertical":    vert_data.get("vertical", vert_name),
                        "match_score": score,
                    }

        return best

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score(
        self,
        query: str,
        stored: str,
        keywords: list[str],
    ) -> float:
        """
        Multi-signal similarity score in [0, 1].

        Signals applied in order (returns as soon as a high score is found):

        1. Exact match                                    → 1.00
        2. Substring containment                          → 0.95
        3. Keyword hits (3+ → 0.84-0.92, 2 → 0.82, 1 → 0.72)
        4. Jaccard token overlap × 0.60                  → 0–0.60
        5. SequenceMatcher ratio × 0.55                  → 0–0.55
        """
        if query == stored:
            return 1.0

        if query in stored or stored in query:
            return 0.95

        kw_hits = sum(1 for kw in keywords if kw.lower() in query)
        if kw_hits >= 3:
            return min(0.92, 0.80 + kw_hits * 0.04)
        if kw_hits == 2:
            return 0.82
        if kw_hits == 1:
            return 0.72

        q_tok = set(query.split())
        s_tok = set(stored.split())
        union = len(q_tok | s_tok)
        if union:
            jaccard = len(q_tok & s_tok) / union
            if jaccard >= 0.01:
                return jaccard * 0.60

        # SequenceMatcher as final fallback (catches paraphrases)
        ratio = SequenceMatcher(None, query, stored).ratio()
        return ratio * 0.55
