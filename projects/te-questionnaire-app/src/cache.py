"""
On-disk answer cache for the ThousandEyes Questionnaire Automator.

Caches LLM answers to avoid re-running expensive local inference on
questions that have already been answered.  This also provides implicit
*progress resume*: if the app crashes mid-run the user can restart
processing and every previously answered item is returned instantly.

Storage:  ~/.te_qa_cache/<sha256_digest>.json
TTL:      7 days (TE documentation is stable enough that week-old answers
          are still accurate; users can clear manually from the UI).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

CACHE_DIR = Path.home() / ".te_qa_cache"
_TTL_SECONDS = 7 * 24 * 3600   # 7 days


class AnswerCache:
    """
    File-based LRU-style cache keyed by SHA-256(model + normalised question).

    Thread-safe for concurrent reads; concurrent writes to the *same* key
    are idempotent (last writer wins, result is identical).
    """

    def __init__(self, model: str) -> None:
        self._model = model
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # Non-fatal — cache won't persist but the app still works.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, text: str) -> Optional[Any]:
        """
        Return the cached value for *text*, or ``None`` if absent / expired.
        Expired entries are deleted on first miss.
        """
        path = self._entry_path(text)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - data.get("ts", 0) > _TTL_SECONDS:
                path.unlink(missing_ok=True)
                return None
            return data["value"]
        except Exception:
            return None

    def set(self, text: str, value: Any) -> None:
        """Persist *value* to disk under a key derived from *text*."""
        path = self._entry_path(text)
        try:
            path.write_text(
                json.dumps({"ts": time.time(), "value": value}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # Non-fatal — just a missed cache write.

    def clear(self) -> int:
        """Delete all cache entries.  Returns the number of deleted files."""
        count = 0
        for p in CACHE_DIR.glob("*.json"):
            try:
                p.unlink()
                count += 1
            except Exception:
                pass
        return count

    def stats(self) -> dict:
        """Return ``{"entries": N, "size_kb": K}`` for the cache directory."""
        files = list(CACHE_DIR.glob("*.json"))
        total = sum(f.stat().st_size for f in files if f.exists())
        return {"entries": len(files), "size_kb": round(total / 1024, 1)}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _entry_path(self, text: str) -> Path:
        """Map *text* (question / description) to a deterministic file path."""
        raw    = f"{self._model}:{text.strip().lower()}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return CACHE_DIR / f"{digest}.json"
