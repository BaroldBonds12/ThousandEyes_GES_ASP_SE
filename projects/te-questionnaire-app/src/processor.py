"""
Processor — orchestrates the full pipeline:
  1. Parse the input file
  2. Extract questions / requirements
  3a. Apply user feedback (permanent corrections — highest priority)
  3b. Apply vertical knowledge base (high-confidence instant answers)
  3c. Check the on-disk answer cache — skip items already answered (7-day TTL)
  4. Pre-fetch ThousandEyes doc context in parallel (I/O-bound)
     • RFP mode:     group by category → one fetch per unique category
     • Regular mode: one fetch per question, up to _FETCH_WORKERS concurrent
  5. Run LLM inference (sequential) for remaining items
     • Medium-confidence vertical KB matches are injected as context hints
  6. Persist new answers to the LLM cache
  7. Return results dict consumed by main.py and file_writer.py

Priority order:
  user feedback  >  vertical KB (≥0.85)  >  LLM cache  >  LLM (+ KB hint)

Speed impact:
  • Feedback hit:      ~0 s (in-memory dict + optional fuzzy scan)
  • Vertical KB hit:   ~0 s (in-memory match, 40-60% of vertical RFPs)
  • Cache hit:         ~0 s (disk read)
  • Parallel fetch:    wall-clock doc time ÷ _FETCH_WORKERS ≈ 4×
  • RFP batching:      5-6 category fetches instead of N requirement fetches
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from src import file_parser, question_extractor
from src.cache import AnswerCache
from src.feedback import FeedbackStore
from src.te_search import TESearcher
from src.llm_engine import LLMEngine
from src.qa_reference import load_reference, find_reference_context
from src.vertical_loader import VerticalKnowledgeBase, HIGH_CONFIDENCE, MED_CONFIDENCE
from src.vertical_detector import VerticalDetector

# Parallel workers for the I/O-bound doc-fetching phase.
_FETCH_WORKERS = 4


class FileProcessor:
    def __init__(
        self,
        model: str = "llama3.2",
        status_cb: Callable[[str], None] = lambda _: None,
        progress_cb: Callable[[float], None] = lambda _: None,
        eta_cb: Callable[[str], None] = lambda _: None,
    ) -> None:
        self._status   = status_cb
        self._progress = progress_cb
        self._eta      = eta_cb
        self._searcher = TESearcher()
        self._llm      = LLMEngine(model=model)
        self._cache    = AnswerCache(model=model)
        self._feedback = FeedbackStore()
        # Human-reviewed Q&A reference — loaded once, used to augment LLM context
        self._ref_rows = load_reference()
        # Vertical industry knowledge base — pre-validated Q&A pairs per sector
        self._vertical_kb = VerticalKnowledgeBase()
        self._detector     = VerticalDetector()
        # Detected vertical for the current file (set in process())
        self._detected_vertical: str | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def process(self, filepath: str) -> dict:
        path = Path(filepath)

        # ── Step 1: parse ────────────────────────────────────────────
        self._status("Parsing file…")
        self._progress(0.05)
        parsed = file_parser.parse(path)

        # ── Step 2: extract questions ─────────────────────────────────
        self._status("Extracting questions…")
        self._progress(0.10)
        questions = question_extractor.extract(parsed)

        if not questions:
            self._progress(1.0)
            self._status("No questions detected.")
            return {
                "filepath":      filepath,
                "parsed":        parsed,
                "questions":     [],
                "cache_hits":    0,
                "feedback_hits": 0,
            }

        total  = len(questions)
        is_rfp = any(q.get("rfp_requirement") for q in questions)

        # Stamp every question with a cache key and original-answer placeholder
        # so the UI can reference them without re-computing.
        for q in questions:
            q["_cache_key"]      = _cache_key(q)
            q["_original_answer"] = None   # filled in below per priority level

        # ── Step 2b: vertical detection ────────────────────────────────
        # Detect the industry vertical from the full question corpus so the KB
        # lookup is scoped first to the most relevant sector.
        q_texts = [
            q.get("question") or q.get("rfp_requirement") or q.get("description", "")
            for q in questions
        ]
        self._detected_vertical = self._detector.detect(q_texts)
        if self._detected_vertical and self._vertical_kb.loaded_count() > 0:
            self._status(
                f"Detected vertical: {self._detected_vertical} — "
                f"checking {self._vertical_kb.loaded_count()} knowledge bases…"
            )

        # ── Step 3a: feedback check (permanent user corrections) ──────
        self._status("Checking feedback and answer cache…")
        self._progress(0.13)
        feedback_hits = self._apply_feedback(questions)

        # ── Step 3b: vertical KB check (high-confidence instant answers) ──
        vertical_hits = self._apply_vertical(questions)

        # ── Step 3c: cache check (skip questions already covered above) ──
        cache_hits = self._apply_cache(questions)

        # ── Step 3d: enrich any cached/feedback items missing a real URL ──
        # Runs in parallel; updates question dicts and persists to cache.
        self._enrich_source_urls(questions)

        remaining = [
            q for q in questions
            if not q.get("_cached")
            and not q.get("_feedback")
            and not q.get("_vertical_kb")
        ]

        # Status message combining all saved sources
        saved_parts: list[str] = []
        if feedback_hits:
            saved_parts.append(
                f"⭐ {feedback_hits} from your correction{'s' if feedback_hits != 1 else ''}"
            )
        if vertical_hits:
            saved_parts.append(
                f"🏭 {vertical_hits} from vertical knowledge"
            )
        if cache_hits:
            saved_parts.append(
                f"⚡ {cache_hits} from cache"
            )
        if saved_parts:
            self._status(
                f"{', '.join(saved_parts)} — {len(remaining)} still to process."
            )

        if not remaining:
            self._progress(1.0)
            answered = sum(1 for q in questions if q.get("answer"))
            suffix   = " and ".join(saved_parts)
            self._status(f"Done ({suffix}) — {answered} answered.")
            return {
                "filepath":       filepath,
                "parsed":         parsed,
                "questions":      questions,
                "cache_hits":     cache_hits,
                "feedback_hits":  feedback_hits,
                "vertical_hits":  vertical_hits,
            }

        # ── ETA warning (only for uncached, non-feedback work) ────────
        secs_per_item = 20 if is_rfp else 25
        est_secs      = len(remaining) * secs_per_item
        if est_secs > 60:
            self._eta(_format_eta(len(remaining), est_secs, is_rfp))

        if is_rfp:
            self._status(
                f"RFP matrix detected — evaluating {len(remaining)} "
                f"requirement(s) against ThousandEyes docs…"
            )

        # ── Step 4: pre-fetch contexts in parallel ────────────────────
        worker_note = (
            "per-category batching" if is_rfp
            else f"up to {_FETCH_WORKERS} concurrent"
        )
        self._status(
            f"Fetching ThousandEyes docs for {len(remaining)} item(s)  "
            f"({worker_note})…"
        )
        self._progress(0.18)
        contexts = self._prefetch_contexts(remaining, is_rfp)
        self._progress(0.28)

        # ── Step 5: LLM inference (sequential, CPU-bound) ─────────────
        already_done = feedback_hits + vertical_hits + cache_hits
        for i, q in enumerate(remaining):
            short_q = q["question"][:60] + ("…" if len(q["question"]) > 60 else "")
            self._status(
                f"Evaluating {already_done + i + 1}/{total}: {short_q}"
            )
            self._progress(0.28 + 0.67 * (i / len(remaining)))

            context = contexts.get(i, "")
            ckey    = q["_cache_key"]

            # Augment context with any matching human-reviewed Q&As
            question_text = q.get("question") or q.get("rfp_requirement", "")
            ref_ctx = find_reference_context(question_text, self._ref_rows)
            if ref_ctx:
                context = (ref_ctx + "\n\n" + context).strip() if context else ref_ctx

            # Augment context with a medium-confidence vertical KB hint
            # (high-confidence items were already handled in _apply_vertical)
            vert_match = self._vertical_kb.match(
                question_text,
                vertical=self._detected_vertical,
                threshold=MED_CONFIDENCE,
            )
            if vert_match and vert_match["match_score"] < HIGH_CONFIDENCE:
                hint = (
                    f"Related ThousandEyes capability "
                    f"({vert_match['vertical']} vertical): {vert_match['answer']}"
                )
                context = (hint + "\n\n" + context).strip() if context else hint

            if q.get("rfp_requirement"):
                result_dict, source_url, reason = self._llm.answer_rfp(
                    section=q.get("section", ""),
                    category=q.get("category", ""),
                    description=q["description"],
                    context=context,
                )
                q["rfp_result"] = result_dict
                q["source_url"] = source_url
                q["reason"]     = reason
                if result_dict:
                    supported = result_dict.get("supported", False)
                    cats = ", ".join(result_dict.get("feature_categories", [])) or "—"
                    expl = result_dict.get("explanation", "")
                    cats_part = f"Features: {cats}" if cats != "—" else ""
                    answer_str = "\n".join(filter(None, [expl, cats_part])) or cats_part or "No relevant documentation found."
                    q["answer"]           = answer_str
                    q["_original_answer"] = answer_str
                    self._cache.set(
                        ckey, {"rfp_result": result_dict, "source_url": source_url}
                    )
                else:
                    q["answer"]           = None
                    q["_original_answer"] = None
            else:
                answer, source_url, reason = self._llm.answer(q["question"], context)
                q["answer"]           = answer
                q["source_url"]       = source_url
                q["reason"]           = reason
                q["_original_answer"] = answer   # LLM answer = original before any correction
                if answer:
                    self._cache.set(ckey, {"answer": answer, "source_url": source_url})

        self._progress(1.0)
        answered   = sum(1 for q in questions if q.get("answer"))
        unanswered = sum(1 for q in questions if not q.get("answer"))
        note_parts: list[str] = []
        if feedback_hits:
            note_parts.append(f"⭐ {feedback_hits} corrections")
        if vertical_hits:
            note_parts.append(f"🏭 {vertical_hits} vertical KB")
        if cache_hits:
            note_parts.append(f"⚡ {cache_hits} cached")
        note = f"  ({', '.join(note_parts)})" if note_parts else ""
        self._status(
            f"Done — {answered} answered, {unanswered} unanswerable.{note}"
        )

        return {
            "filepath":       filepath,
            "parsed":         parsed,
            "questions":      questions,
            "cache_hits":     cache_hits,
            "feedback_hits":  feedback_hits,
            "vertical_hits":  vertical_hits,
        }

    # ------------------------------------------------------------------
    # Feedback (priority 1)
    # ------------------------------------------------------------------

    def _apply_feedback(self, questions: list[dict]) -> int:
        """
        Apply permanent user corrections from FeedbackStore.

        Fuzzy-matches each question against stored corrections (≥0.80 ratio).
        Marks matched questions with ``q["_feedback"] = True`` so they are
        skipped by ``_apply_cache`` and the LLM loop.

        Returns the number of feedback hits.
        """
        hits = 0
        for q in questions:
            if q.get("rfp_requirement"):
                continue   # RFP editing not yet supported
            fb = self._feedback.get(q["question"])
            if fb is None:
                continue
            hits += 1
            q["_feedback"]        = True
            q["answer"]           = fb["answer"]
            q["source_url"]       = fb.get("source_url") or ""
            q["reason"]           = None
            q["_original_answer"] = fb.get("original_answer") or fb["answer"]
        return hits

    # ------------------------------------------------------------------
    # Vertical knowledge base (priority 2 — between feedback and cache)
    # ------------------------------------------------------------------

    def _apply_vertical(self, questions: list[dict]) -> int:
        """
        Match each question against the vertical knowledge base.

        Questions already answered by user feedback are skipped.  When a
        HIGH_CONFIDENCE match (≥ 0.85) is found the pre-validated answer is
        applied directly — the question is marked ``q["_vertical_kb"] = True``
        so that ``_apply_cache`` and the LLM loop both skip it.

        Medium-confidence matches (0.60–0.84) are *not* applied here; they are
        picked up as context hints inside the LLM inference loop.

        Returns the number of high-confidence hits.
        """
        if self._vertical_kb.loaded_count() == 0:
            return 0

        hits = 0
        for q in questions:
            if q.get("_feedback"):
                continue   # user correction takes absolute priority

            q_text = (
                q.get("question")
                or q.get("rfp_requirement")
                or q.get("description", "")
            ).strip()
            if not q_text:
                continue

            match = self._vertical_kb.match(
                q_text,
                vertical=self._detected_vertical,
                threshold=HIGH_CONFIDENCE,
            )
            if match is None:
                continue

            hits += 1
            q["_vertical_kb"]  = True
            q["_vertical_name"] = match["vertical"]
            q["_match_score"]   = match["match_score"]
            q["source_url"]     = match.get("source_url", "")
            q["reason"]         = None

            answer_text = match.get("answer", "")

            if q.get("rfp_requirement"):
                # Build a synthetic rfp_result compatible with the rest of the
                # pipeline (file_writer, UI review panel, etc.)
                support_level = match.get("support_level", "not_applicable")
                rfp_result = {
                    "support_level":     support_level,
                    "supported":         support_level in ("yes", "partial"),
                    "explanation":       answer_text,
                    "feature_categories": [match.get("category", "General")],
                }
                q["rfp_result"]       = rfp_result
                q["answer"]           = answer_text
                q["_original_answer"] = answer_text
            else:
                q["answer"]           = answer_text
                q["_original_answer"] = answer_text

        return hits

    # ------------------------------------------------------------------
    # Cache (priority 3)
    # ------------------------------------------------------------------

    def _apply_cache(self, questions: list[dict]) -> int:
        """
        Check the on-disk LLM cache for each question not already covered by
        user feedback.  Returns the count of cache hits.
        """
        hits = 0
        for q in questions:
            if q.get("_feedback") or q.get("_vertical_kb"):
                continue   # already handled at higher priority
            cached = self._cache.get(q["_cache_key"])
            if cached is None:
                continue
            hits += 1
            q["_cached"] = True
            if q.get("rfp_requirement"):
                rd = cached.get("rfp_result")
                q["rfp_result"] = rd
                q["source_url"] = cached.get("source_url") or ""
                q["reason"]     = None
                if rd:
                    cats = ", ".join(rd.get("feature_categories", [])) or "—"
                    expl = rd.get("explanation", "")
                    cats_part = f"Features: {cats}" if cats != "—" else ""
                    answer_str = "\n".join(filter(None, [expl, cats_part])) or cats_part or "No relevant documentation found."
                    q["answer"]           = answer_str
                    q["_original_answer"] = answer_str
            else:
                q["answer"]           = cached.get("answer")
                q["source_url"]       = cached.get("source_url") or ""
                q["reason"]           = None
                q["_original_answer"] = cached.get("answer")
        return hits

    # ------------------------------------------------------------------
    # URL enrichment for cached / feedback items missing a real source URL
    # ------------------------------------------------------------------

    def _enrich_source_urls(self, questions: list[dict]) -> None:
        """
        For any cached or feedback-driven question that lacks a real
        docs.thousandeyes.com content URL, perform a fast URL-only lookup
        (no page fetch) in parallel and update both the question dict and the
        on-disk cache so future runs don't repeat the lookup.

        This replaces the old fake-search-URL fallback with a real page URL.
        """
        from src.te_search import _is_content_url

        needs_url = [
            q for q in questions
            if (q.get("_cached") or q.get("_feedback"))
            and not q.get("_vertical_kb")   # vertical KB answers carry real URLs
            and not _is_content_url(q.get("source_url") or "")
        ]
        if not needs_url:
            return

        self._status(
            f"Looking up real doc URLs for {len(needs_url)} cached "
            f"answer{'s' if len(needs_url) != 1 else ''}…"
        )

        workers = max(1, min(_FETCH_WORKERS, len(needs_url)))

        def _lookup(q: dict) -> tuple[dict, str | None]:
            q_text = (q.get("question") or q.get("rfp_requirement") or "").strip()
            url = self._searcher.get_source_url(q_text) if q_text else None
            return q, url

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_lookup, q): q for q in needs_url}
            for fut in as_completed(futs):
                try:
                    q, url = fut.result(timeout=20)
                    if url:
                        q["source_url"] = url
                        # Persist to cache so subsequent runs skip this lookup
                        ckey = q.get("_cache_key")
                        if ckey:
                            cached = self._cache.get(ckey) or {}
                            if not cached.get("source_url"):
                                cached["source_url"] = url
                                self._cache.set(ckey, cached)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Parallel context prefetch
    # ------------------------------------------------------------------

    def _prefetch_contexts(
        self, questions: list[dict], is_rfp: bool
    ) -> dict[int, str]:
        """
        Fetch documentation context for each question in *questions* concurrently.
        Returns {index_in_questions: context_str}.
        """
        contexts: dict[int, str] = {}

        if is_rfp:
            cat_to_indices: dict[str, list[int]] = {}
            for idx, q in enumerate(questions):
                cat = q.get("category", "General")
                cat_to_indices.setdefault(cat, []).append(idx)

            def _fetch_cat(cat: str, indices: list[int]) -> tuple[list[int], str]:
                first_q    = questions[indices[0]]
                first_desc = _clean_search_query(first_q.get("description", ""))[:80]
                search_q   = f"ThousandEyes {cat} {first_desc}"
                ctx = self._searcher.search_and_fetch(search_q)
                return indices, ctx

            workers = max(1, min(_FETCH_WORKERS, len(cat_to_indices)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(_fetch_cat, cat, idxs): cat
                    for cat, idxs in cat_to_indices.items()
                }
                for fut in as_completed(futs):
                    cat = futs[fut]
                    try:
                        indices, ctx = fut.result()
                    except Exception:
                        indices, ctx = cat_to_indices[cat], ""
                    for idx in indices:
                        contexts[idx] = ctx

        else:
            def _fetch_q(idx: int, q: dict) -> tuple[int, str]:
                clean_q = _clean_search_query(q["question"])
                ctx = self._searcher.search_and_fetch(clean_q)
                return idx, ctx

            workers = max(1, min(_FETCH_WORKERS, len(questions)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(_fetch_q, idx, q): idx
                    for idx, q in enumerate(questions)
                }
                for fut in as_completed(futs):
                    idx = futs[fut]
                    try:
                        idx2, ctx = fut.result()
                        contexts[idx2] = ctx
                    except Exception:
                        contexts[idx] = ""

        return contexts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUERY_NOISE_RE = re.compile(
    r"""
    ^\s*
    (?:
        \[\s*[\d\.]+\s*[^\]]*\]   # [3.1.1 Solution] or [1.2]
      | \d+[\.\d]*\s+             # 3.1.1 or 1.2.3 followed by space
      | \(\s*\d+[\.\d]*\s*\)\s*  # (3.1) in parens
    )+
    """,
    re.VERBOSE,
)

_QUERY_PUNCT_RE = re.compile(r'[^\w\s\-\(\)]')


def _clean_search_query(text: str) -> str:
    """
    Strip RFP section numbering and punctuation noise from a question or
    requirement description before feeding it to a web search engine.

    Examples:
      "[3.1.1 Solution] End-to-end monitoring…"  →  "End-to-end monitoring…"
      "1.2.3 Does ThousandEyes support BGP?"     →  "Does ThousandEyes support BGP?"
    """
    cleaned = _QUERY_NOISE_RE.sub("", text).strip()
    # Ensure "ThousandEyes" is somewhere in the query for precision
    if "thousandeyes" not in cleaned.lower():
        cleaned = "ThousandEyes " + cleaned
    return cleaned[:200]


def _cache_key(q: dict) -> str:
    """Deterministic string key used by AnswerCache for a question / requirement."""
    if q.get("rfp_requirement"):
        cat  = q.get("category", "").strip().lower()
        desc = q.get("description", "").strip().lower()[:500]
        return f"rfp:{cat}:{desc}"
    return f"q:{q.get('question', '').strip().lower()[:500]}"


def _format_eta(count: int, est_secs: int, is_rfp: bool) -> str:
    """Return a human-friendly ETA string for the Vizzy speech bubble."""
    if est_secs < 120:
        time_str = "about a minute"
    elif est_secs < 3600:
        mins = round(est_secs / 60)
        time_str = f"roughly {mins} minutes"
    else:
        hrs  = est_secs // 3600
        mins = (est_secs % 3600) // 60
        time_str = (
            f"around {hrs}h {mins}m" if mins
            else f"around {hrs} hour{'s' if hrs > 1 else ''}"
        )

    kind = f"{count} RFP requirements" if is_rfp else f"{count} questions"
    return f"ETA:{time_str}|{kind}"
