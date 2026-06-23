"""
Vertical Detector — automatically identifies the industry vertical from a batch
of RFP/questionnaire questions using weighted keyword scoring.

Usage
─────
    from src.vertical_detector import VerticalDetector

    detector = VerticalDetector()
    vertical = detector.detect(questions)   # e.g. "Healthcare" or None

Scoring
───────
  - Strong keywords → 2 points each
  - Medium keywords → 1 point each
  - Confidence = raw_score / max_possible_score for the winning vertical
  - Returns None if the best score falls below *min_confidence* (default 0.30)

The detected vertical is passed to the processor's vertical KB lookup so that
matching is scoped to the most relevant industry before falling back to an
all-verticals search.
"""

from __future__ import annotations

from typing import Optional


class VerticalDetector:
    """
    Detects the most likely industry vertical from a list of question strings.
    """

    # -----------------------------------------------------------------------
    # Keyword taxonomy (must mirror the vertical names in the JSON files)
    # -----------------------------------------------------------------------

    VERTICAL_KEYWORDS: dict[str, dict[str, list[str]]] = {
        "Healthcare": {
            "strong": [
                "hipaa", "hitech", "ehr", "emr", "epic", "cerner",
                "hl7", "fhir", "patient", "clinical", "hospital",
                "telehealth", "medical",
            ],
            "medium": [
                "healthcare", "health", "provider", "practice", "physician",
            ],
        },
        "Manufacturing": {
            "strong": [
                "mes", "scada", "iot", "plm", "production", "factory",
                "plant", "industrial", "manufacturing",
            ],
            "medium": [
                "supply chain", "warehouse", "erp", "sap", "oracle",
            ],
        },
        "Software & Technology": {
            "strong": [
                "saas", "api", "microservices", "cdn", "devops", "ci/cd",
                "cloud", "aws", "azure", "gcp",
            ],
            "medium": [
                "software", "platform", "application", "service",
            ],
        },
        "Financial Services": {
            "strong": [
                "pci dss", "finra", "trading", "payment", "banking", "atm",
                "financial", "securities", "investment",
            ],
            "medium": [
                "transaction", "credit", "account", "fraud",
            ],
        },
        "Retail & E-commerce": {
            "strong": [
                "ecommerce", "pos", "bopis", "checkout", "shopify",
                "magento", "retail", "store", "inventory",
            ],
            "medium": [
                "shopping", "product", "cart", "order",
            ],
        },
        "Education": {
            "strong": [
                "lms", "canvas", "blackboard", "moodle", "student", "campus",
                "ferpa", "education", "university", "school",
            ],
            "medium": [
                "learning", "classroom", "enrollment", "academic",
            ],
        },
        "Government & Public Sector": {
            "strong": [
                "fedramp", "fisma", "cjis", "government", "federal",
                "public safety", "911", "election", "agency",
            ],
            "medium": [
                "citizen", "public", "municipal", "state",
            ],
        },
    }

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def detect(
        self,
        questions: list[str],
        min_confidence: float = 0.30,
    ) -> Optional[str]:
        """
        Detect the most likely industry vertical from *questions*.

        Parameters
        ----------
        questions:
            List of question / requirement strings extracted from the RFP file.
        min_confidence:
            Minimum normalised confidence (0–1) required to commit to a
            vertical.  If the best score is below this threshold, ``None``
            is returned and the processor will search all verticals.

        Returns
        -------
        str | None
            Human-readable vertical name (e.g. ``"Healthcare"``) or ``None``.
        """
        if not questions:
            return None

        all_text = " ".join(questions).lower()

        scores: dict[str, float] = {}
        for vertical, keywords in self.VERTICAL_KEYWORDS.items():
            score = 0.0
            for kw in keywords["strong"]:
                if kw in all_text:
                    score += 2.0
            for kw in keywords["medium"]:
                if kw in all_text:
                    score += 1.0
            scores[vertical] = score

        if not any(scores.values()):
            return None

        best_vertical = max(scores, key=lambda v: scores[v])
        best_score    = scores[best_vertical]

        kw = self.VERTICAL_KEYWORDS[best_vertical]
        max_possible = len(kw["strong"]) * 2.0 + len(kw["medium"]) * 1.0
        confidence = best_score / max_possible if max_possible > 0 else 0.0

        if confidence >= min_confidence:
            return best_vertical
        return None

    # -----------------------------------------------------------------------
    # Convenience
    # -----------------------------------------------------------------------

    def score_all(self, questions: list[str]) -> dict[str, float]:
        """
        Return normalised confidence scores for every vertical (useful for
        debugging / logging).  Scores are in [0, 1].
        """
        if not questions:
            return {}
        all_text = " ".join(questions).lower()
        result: dict[str, float] = {}
        for vertical, keywords in self.VERTICAL_KEYWORDS.items():
            raw = sum(
                2.0 for kw in keywords["strong"] if kw in all_text
            ) + sum(
                1.0 for kw in keywords["medium"] if kw in all_text
            )
            max_p = len(keywords["strong"]) * 2.0 + len(keywords["medium"]) * 1.0
            result[vertical] = raw / max_p if max_p else 0.0
        return result
