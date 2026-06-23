"""
LLM Engine — drives answers using a locally-running Ollama model.

No API keys, no cloud services, no data leaves the machine.
Ollama must be running at localhost:11434 before calling answer().

Docs: https://github.com/ollama/ollama
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Ollama API helpers
# ---------------------------------------------------------------------------

OLLAMA_BASE = "http://localhost:11434"
_TIMEOUT_CHAT = 120  # seconds — local inference can be slow on CPU
_TIMEOUT_API = 5


def ollama_is_running() -> bool:
    """Return True if the Ollama daemon is reachable."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/", timeout=_TIMEOUT_API)
        return r.status_code == 200
    except Exception:
        return False


def ollama_list_models() -> list[str]:
    """Return list of locally-available model names."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=_TIMEOUT_API)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def ollama_pull(model: str, progress_cb=None) -> None:
    """
    Pull *model* from the Ollama registry with streaming progress.

    *progress_cb* receives (fraction: float, status: str,
                             completed_bytes: int, total_bytes: int).
    """
    with requests.post(
        f"{OLLAMA_BASE}/api/pull",
        json={"name": model, "stream": True},
        stream=True,
        timeout=3600,
    ) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            status    = data.get("status",    "")
            total     = data.get("total",     0)
            completed = data.get("completed", 0)
            fraction  = (completed / total) if total else 0.0
            if progress_cb:
                progress_cb(fraction, status, completed, total)


# ---------------------------------------------------------------------------
# ThousandEyes capability baseline — injected into every prompt
# ---------------------------------------------------------------------------
# This gives the LLM accurate foundational knowledge so it answers correctly
# even when the fetched doc page doesn't perfectly match the question.
# It should reflect current ThousandEyes capabilities accurately.

_TE_BASELINE = """\
=== ThousandEyes Platform — Comprehensive Capability Reference ===

ThousandEyes (acquired by Cisco 2020) is a network intelligence and digital
experience monitoring platform providing end-to-end visibility across Internet,
cloud, WAN, and enterprise networks.

CORE MONITORING CAPABILITIES:

1. Network Monitoring:
   ✓ ICMP-based network testing, path visualization (hop-by-hop latency/loss/jitter)
   ✓ BGP monitoring (routing changes, prefix monitoring, route leaks/hijacks)
   ✓ VoIP/RTP monitoring (MOS scores, jitter, latency, packet loss)
   ✓ NetFlow/sFlow integration for traffic analysis
   ⚠ PARTIAL: SNMP polling available for network devices via Device Layer
   ✗ NOT: Traditional SNMP/syslog collector for comprehensive infrastructure monitoring

2. Application & Service Monitoring:
   ✓ HTTP/HTTPS synthetic testing (availability, response time, SSL/TLS)
   ✓ API monitoring and multi-step transaction testing
   ✓ Page load metrics and waterfall analysis
   ✓ DNS resolution monitoring
   ✓ Web transaction recording (Selenium-based browser automation)
   ⚠ PARTIAL: Monitors applications externally but not code-level APM
   ✗ NOT: Database query performance, deadlock detection (use AppDynamics)

3. Cloud & SaaS Monitoring:
   ✓ Multi-cloud support (AWS, Azure, GCP) for connectivity and service testing
   ✓ SaaS application monitoring (Microsoft 365, Salesforce, Zoom, Webex, etc.)
   ✓ Cloud provider outage detection via Internet Insights
   ⚠ PARTIAL: Monitors cloud service availability but not infrastructure management
   ✗ NOT: Cloud cost optimization, resource rightsizing

4. Endpoint User Experience:
   ✓ Endpoint Agents for Windows and macOS workstations and laptops
   ✓ WiFi performance, local network, DNS, VPN tunnel metrics
   ✓ Real user monitoring (RUM) via browser extensions
   ✓ Scheduled synthetic tests from endpoint agents
   ⚠ PARTIAL: Limited to Windows/macOS desktops; no mobile device support
   ✗ NOT: iOS/Android mobile device monitoring, medical device monitoring

5. Integration & Automation:
   ✓ Native integrations: ServiceNow, Slack, PagerDuty, Jira, Microsoft Teams
   ✓ REST API for programmatic test creation, result export, and automation
   ✓ Webhooks for custom integrations
   ✓ SSO via SAML (Okta, Azure AD, etc.)
   ✓ Splunk integration for SIEM correlation
   ⚠ PARTIAL: IAM integration via SSO; not a full IAM management platform

6. Scalability & Global Coverage:
   ✓ Cloud-based SaaS platform with 193+ global vantage point locations
   ✓ High-availability architecture with enterprise redundancy
   ✓ Enterprise Agent clusters for on-premise redundancy
   ✓ Continuous monitoring mode (one-second granularity)
   ✓ Real-time alerting with configurable thresholds

7. Security & Compliance:
   ✓ SOC 2 Type II certified
   ✓ ISO 27001 certified
   ✓ Encryption in transit (TLS) and at rest
   ✓ Role-based access control (RBAC)
   ✓ Multi-factor authentication (MFA) support
   ✓ Audit logging for user actions
   ⚠ PARTIAL: HIPAA compliance available with Business Associate Agreement (BAA) — verify with Cisco
   ⚠ PARTIAL: Monitors for security-impacting network events but is not a SIEM

8. Analytics & Reporting:
   ✓ Customizable dashboards with role-based access controls
   ✓ Historical data analysis and trend reporting
   ✓ AI-powered anomaly detection
   ✓ Path visualization and topology mapping
   ✓ Internet Insights for collective cross-customer intelligence

OUT OF SCOPE (Requires Complementary Tools):
• OS-level server health (CPU, RAM, disk) → AppDynamics Infrastructure Agent
• Database query performance, replication, deadlocks → AppDynamics / Dynatrace
• Application code-level APM / distributed tracing → AppDynamics
• IT asset inventory / CMDB population → Cisco CX Cloud / ServiceNow
• Full packet capture / deep packet inspection → Cisco Stealthwatch
• Virtual infrastructure management (VMware, Hyper-V)
• Mobile device management (MDM) / iOS / Android monitoring
• Physical security systems

EVALUATION GUIDE:
1. If ThousandEyes fully and natively addresses the requirement → "yes"
2. If ThousandEyes partially addresses it (with noted gaps or complementary tools) → "partial"
3. If the requirement is entirely outside network/application monitoring scope → "not_applicable"
"""


# ---------------------------------------------------------------------------
# Q&A prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a ThousandEyes expert assistant helping Solution Engineers respond to
customer questionnaires and RFPs accurately.

{baseline}

RESPONSE RULES:
1. Use the documentation context snippets (from docs.thousandeyes.com) in each
   user message as the primary source. The baseline above is background knowledge.
2. When context is sparse, rely on the baseline rather than defaulting to
   "not supported" or "CANNOT ANSWER".
3. For partial coverage: state what ThousandEyes DOES cover first, then name
   the complementary Cisco tool for the gap. Do not lead with the limitation.
4. Only use CANNOT ANSWER if the question is entirely unrelated to Cisco
   networking or monitoring. Format: CANNOT ANSWER: <reason>
5. Never fabricate version numbers or undocumented feature names.
6. Keep answers to 2–3 concise sentences. Avoid hedging words like
   "generally," "typically," "usually," or "it depends."
7. Format: [Direct support statement]. [Technical detail]. [Gap/complement if partial].

EXAMPLE — good:
"Yes. ThousandEyes provides real-time alerting via email, webhook, SMS, and
native integrations with ServiceNow, PagerDuty, and Slack."

EXAMPLE — bad:
"ThousandEyes generally supports real-time monitoring and typically can send
alerts through various channels depending on configuration..."
""".format(baseline=_TE_BASELINE)

_USER_TEMPLATE = """\
=== ThousandEyes Documentation Context ===
{context}

=== Question ===
{question}

Answer (draw on both the documentation context AND your ThousandEyes expertise):"""

_CANNOT_RE = re.compile(r"^CANNOT ANSWER\s*[:：]\s*", re.IGNORECASE)

# ---------------------------------------------------------------------------
# RFP evaluation prompts
# ---------------------------------------------------------------------------

# Expanded feature-category set — covers the full ThousandEyes product surface
_RFP_FEATURES = {
    "synthetics": (
        "Synthetic monitoring — HTTP, TCP, DNS, BGP, Page Load, Transaction "
        "(browser automation), FTP, SIP tests from Cloud and Enterprise Agents. "
        "Proactive testing of app/network availability from external vantage points."
    ),
    "network path": (
        "Hop-by-hop path visibility — traceroute-style latency, loss, jitter "
        "measurement per hop; DSCP, MTU, and interface data; visualised as "
        "dynamic path maps between any source and destination."
    ),
    "bgp & routing": (
        "BGP prefix monitoring, AS-path changes, route leak and hijack detection, "
        "internet routing analytics. Monitors reachability of prefixes from "
        "hundreds of global BGP vantage points."
    ),
    "device layer": (
        "Network device health — SNMP polling for CPU, memory, interface counters "
        "and errors; CDP/LLDP-based device discovery and topology mapping; "
        "physical and virtual device diagnostics."
    ),
    "endpoint": (
        "End-user experience — Endpoint Agent on user devices captures WiFi signal, "
        "local LAN, DNS, proxy, VPN tunnel metrics; measures SaaS/app performance "
        "from real users (remote & office)."
    ),
    "cloud insights": (
        "Cloud infrastructure monitoring — AWS, Azure, GCP connectivity tests; "
        "VPC flow log ingestion; cloud topology mapping; cloud provider outage "
        "detection via Internet Insights."
    ),
    "internet insights": (
        "Collective intelligence across millions of ThousandEyes vantage points — "
        "ISP, CDN, and cloud provider outage correlation; internet health maps; "
        "shared visibility without sharing proprietary data."
    ),
    "alerting & api": (
        "Rule-based threshold alerts with webhook delivery, PagerDuty, Slack, "
        "ServiceNow, and Splunk integrations. Full REST API for programmatic "
        "test creation, result export, and dashboard automation."
    ),
}

_RFP_SYSTEM_PROMPT = """\
You are a ThousandEyes platform expert evaluating RFP/questionnaire requirements.
Your job is to ACCURATELY classify each requirement using a three-tier system
and identify the specific ThousandEyes feature categories that apply.

{baseline}

ThousandEyes feature categories — use EXACTLY these names in your JSON output:
{features}

EVALUATION RULES — THREE-TIER CLASSIFICATION:

1. Use "yes" when ThousandEyes FULLY covers the requirement with native capabilities.
   No external tools needed. Example: HTTP synthetic monitoring, BGP monitoring.

2. Use "partial" when:
   - ThousandEyes covers SOME aspects but not all
   - The requirement needs integration with a complementary Cisco tool (AppDynamics, etc.)
   - Coverage is limited to specific platforms (e.g., Windows/macOS only, not mobile)
   - There are meaningful constraints (e.g., monitors app availability but not DB internals)
   Example: Server health monitoring (TE covers network path; AppDynamics covers OS metrics)

3. Use "not_applicable" when:
   - The requirement is ENTIRELY outside network/application monitoring scope
   - Requires capabilities like VM management, database administration, cost optimization
   - Focuses on ERP, HR, physical security, or medical device management
   Example: Database query optimization, iOS/Android MDM, physical security cameras

EXPLANATION GUIDELINES:
- "yes":             State what ThousandEyes provides in 1–2 sentences. Be specific.
- "partial":         Lead with what IS covered, then state what requires additional tools.
- "not_applicable":  Briefly explain why this is outside ThousandEyes scope.
- Max length:        2 sentences / ~45 words. No hedging ("generally", "typically").
- Avoid:             "not supported" phrasing for "partial" items — it misrepresents coverage.

GENERAL RULES:
- Use the documentation context + capability reference above as primary sources.
- Include ALL feature categories that contribute to the requirement.
- Clear feature_categories list for "not_applicable" responses.
- Respond with valid JSON ONLY — no prose before or after the JSON block.
""".format(
    baseline=_TE_BASELINE,
    features="\n".join(f'- "{k}": {v}' for k, v in _RFP_FEATURES.items()),
)

_RFP_USER_TEMPLATE = """\
=== ThousandEyes Documentation Context ===
{context}

=== RFP Requirement ===
Section:     {section}
Category:    {category}
Requirement: {description}

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "support_level": "yes" or "partial" or "not_applicable",
  "feature_categories": ["exact category name", ...],
  "explanation": "1-2 concise sentences. For 'yes': state what TE provides. For 'partial': what IS covered then what needs complementary tools. For 'not_applicable': brief reason why outside scope."
}}"""


# ---------------------------------------------------------------------------
# Engine class
# ---------------------------------------------------------------------------

class LLMEngine:
    def __init__(self, model: str = "llama3.2") -> None:
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._model = value

    def answer_rfp(
        self,
        section: str,
        category: str,
        description: str,
        context: str,
    ) -> tuple[Optional[dict], Optional[str], Optional[str]]:
        """
        Evaluate a single RFP requirement against ThousandEyes capabilities.

        Returns (result_dict, source_url, reason).
        result_dict keys:
          support_level     : "yes" | "partial" | "not_applicable"  (new key)
          supported         : bool  (legacy compat — True when level is yes/partial)
          feature_categories: list[str]
          explanation       : str   (post-processed, hedge-stripped, ≤2 sentences)
        On failure, result_dict is None and reason is set.
        """
        if not ollama_is_running():
            return None, None, "Ollama is not running."

        ctx = context.strip() if context else "No documentation context available."
        user_msg = _RFP_USER_TEMPLATE.format(
            context=ctx,
            section=section or "General",
            category=category or "General",
            description=description,
        )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _RFP_SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,   # low but not zero — allows nuanced answers
                "num_predict": 400,   # enough for a 2-3 sentence explanation + JSON
            },
        }

        try:
            resp = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json=payload,
                timeout=_TIMEOUT_CHAT,
            )
            resp.raise_for_status()
            raw: str = resp.json()["message"]["content"].strip()
        except Exception as exc:
            return None, None, f"Ollama inference error: {exc}"

        result = _parse_rfp_json(raw, list(_RFP_FEATURES.keys()))
        if result is None:
            return None, None, f"Could not parse LLM response: {raw[:200]}"

        source_url = _first_source_url(context)
        return result, source_url, None

    def answer(
        self, question: str, context: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Returns (answer, source_url, reason).
        Exactly one of (answer, reason) will be non-None.
        """
        if not ollama_is_running():
            return None, None, "Ollama is not running. Please start Ollama and try again."

        ctx = context.strip() if context else "No documentation context available."
        user_msg = _USER_TEMPLATE.format(context=ctx, question=question)

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 700,   # allow detailed answers for complex questions
            },
        }

        try:
            resp = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json=payload,
                timeout=_TIMEOUT_CHAT,
            )
            resp.raise_for_status()
            raw: str = resp.json()["message"]["content"].strip()
        except Exception as exc:
            return None, None, f"Ollama inference error: {exc}"

        if _CANNOT_RE.match(raw):
            reason = _CANNOT_RE.sub("", raw).strip()
            return None, None, reason

        source_url = _first_source_url(context)
        return raw, source_url, None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_source_url(context: str) -> Optional[str]:
    m = re.search(r"\[Source:\s*(https?://[^\]]+)\]", context)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Answer format templates
# ---------------------------------------------------------------------------
# These templates define the canonical phrasing structure for each support tier.
# They are used in two ways:
#   1. As reference examples injected into the LLM system prompt (future).
#   2. As patterns for _post_process_explanation to enforce the correct
#      signal-word prefix on every RFP explanation before it reaches the doc.
#
# Template placeholders use {curly_brace} notation for future .format() calls
# when the templates are used to auto-generate canned answers (e.g. from the
# healthcare knowledge module or a pre-approved answer bank).

_ANSWER_TEMPLATES: dict[str, str] = {
    # "yes" tier — direct statement of what ThousandEyes provides natively
    "yes_monitoring":    "Yes. ThousandEyes monitors {capability} through {method}.",
    "yes_integration":   "Yes. ThousandEyes integrates with {platform} via {mechanism}.",
    "yes_feature":       "Yes. {feature_description} with {specifics}.",

    # "partial" tier — lead with what IS covered, then name the gap/tool
    "partial_platform":  (
        "Partial. ThousandEyes supports {what_supported} on {platforms} "
        "but does not cover {what_missing}."
    ),
    "partial_complement": (
        "Partial. ThousandEyes {what_covered}; {what_missing} requires {complementary_tool}."
    ),
    "partial_scope":     "Partial. Covers {covered_scope} but not {excluded_scope}.",

    # "not_applicable" tier — brief, respectful out-of-scope statement
    "not_applicable":    "Not applicable. {brief_reason}.",
}

# Signal-word prefix enforced at the start of every RFP explanation.
# Keeps output scannable: reviewers can skim the first word of each cell.
_LEVEL_PREFIX: dict[str, str] = {
    "yes":            "Yes. ",
    "partial":        "Partial. ",
    "not_applicable": "Not applicable. ",
}

# Acceptable opening words that satisfy each tier's prefix without duplication.
# If an explanation already starts with any of these, we skip the prefix.
_LEVEL_STARTS: dict[str, tuple[str, ...]] = {
    "yes":            ("yes.", "yes,", "yes "),
    "partial":        ("partial.", "partial,", "partial ", "partially"),
    "not_applicable": ("not applicable", "n/a", "outside scope", "not within"),
}

# Hedging phrases that weaken professional responses — strip them on output.
# Keyed as (find, replace) so we can do simple string substitution in order.
_HEDGE_SUBS: list[tuple[str, str]] = [
    ("it is generally ",   ""),
    ("it generally ",      ""),
    ("generally speaking, ", ""),
    ("generally, ",        ""),
    ("generally ",         ""),
    ("it is typically ",   ""),
    ("it typically ",      ""),
    ("typically, ",        ""),
    ("typically ",         ""),
    ("it is usually ",     ""),
    ("it usually ",        ""),
    ("usually, ",          ""),
    ("usually ",           ""),
    ("in most cases, ",    ""),
    ("in most cases ",     ""),
    ("it may ",            "it "),
    ("it can ",            "it "),
    ("might be able to ",  ""),
]

_SENTENCE_LIMIT = 2     # target sentence count for RFP explanations
_WORD_LIMIT     = 50    # hard word-count cap before sentence truncation


def _post_process_explanation(explanation: str, support_level: str) -> str:
    """
    Clean up an LLM-generated explanation for professional output quality.

    Actions performed (in order):
    1. Strip common hedging phrases (generally, typically, usually…).
    2. Collapse extra whitespace.
    3. Ensure the explanation starts with a capital letter.
    4. Truncate to at most _SENTENCE_LIMIT sentences if over _WORD_LIMIT words.
    5. Ensure the result ends with a period.
    6. Cap absolute length at 500 characters.
    """
    if not explanation:
        return explanation

    result = explanation

    # 1. Strip hedges — work case-insensitively by lowering only for matching,
    #    then reconstruct around the surrounding case.
    result_lower = result.lower()
    for hedge, replacement in _HEDGE_SUBS:
        idx = result_lower.find(hedge)
        while idx != -1:
            result       = result[:idx] + replacement + result[idx + len(hedge):]
            result_lower = result.lower()
            idx          = result_lower.find(hedge)

    # 2. Collapse whitespace (multiple spaces, leading/trailing)
    result = " ".join(result.split())

    # 3. Capitalise first character
    if result and not result[0].isupper():
        result = result[0].upper() + result[1:]

    # 4. Truncate to sentence limit when the text is long
    if len(result.split()) > _WORD_LIMIT:
        sentences = re.split(r"(?<=[.!?])\s+", result)
        if len(sentences) > _SENTENCE_LIMIT:
            result = " ".join(sentences[:_SENTENCE_LIMIT])
            if not result.endswith((".", "!", "?")):
                result += "."

    # 5. Ensure ends with a period
    if result and not result[-1] in (".", "!", "?"):
        result += "."

    # 6. Enforce the support-level signal-word prefix so reviewers can skim
    #    output by reading only the first word of each table cell.
    #    e.g. "Yes.", "Partial.", "Not applicable."
    #    Skip if the explanation already opens with an acceptable variant.
    acceptable = _LEVEL_STARTS.get(support_level, ())
    if acceptable and not any(result.lower().startswith(s) for s in acceptable):
        result = _LEVEL_PREFIX.get(support_level, "") + result

    # 7. Hard character cap (defence against very long single sentences)
    return result[:500]


def _parse_rfp_json(raw: str, valid_features: list[str]) -> Optional[dict]:
    """
    Extract and validate the JSON block from an LLM response.

    Tries progressively looser strategies:
    1. Parse the whole string as JSON.
    2. Find the outermost {...} block and parse that.
    3. Build a minimal result from keyword signals in the free text.

    All paths go through _validate_rfp_dict, which normalises the
    support_level value and handles backward-compat with old cached
    responses that carried a boolean "supported" key instead.
    """
    # Strategy 1 — whole response is already valid JSON
    try:
        return _validate_rfp_dict(json.loads(raw), valid_features)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2 — fish out the outermost {...} block
    start = raw.find("{")
    end   = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return _validate_rfp_dict(
                json.loads(raw[start : end + 1]), valid_features
            )
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3 — heuristic classification from free-text signals.
    # Used only when the LLM ignores the JSON format instruction entirely.
    text_lower = raw.lower()

    # Detect explicit "partial" language before checking for "not_applicable"
    partial_signals = ("partial", "partially", "some aspects", "not all", "limited to")
    na_signals      = ("not applicable", "out of scope", "outside scope",
                       "not supported", "cannot", "does not support")

    if any(s in text_lower for s in partial_signals):
        support_level = "partial"
    elif any(s in text_lower for s in na_signals):
        # Double-check: if the word "support" appears outside the "not supported"
        # phrases, the LLM may actually be describing coverage — default to "partial"
        cleaned = text_lower
        for phrase in na_signals:
            cleaned = cleaned.replace(phrase, "")
        support_level = "partial" if "support" in cleaned else "not_applicable"
    else:
        support_level = "yes"

    found_cats = [f for f in valid_features if f in text_lower]

    return {
        # Pass through _validate_rfp_dict so normalisation is consistent
        "support_level":      support_level,
        "feature_categories": found_cats if support_level != "not_applicable" else [],
        "explanation":        raw[:200].replace("\n", " "),
    }


def _validate_rfp_dict(d: dict, valid_features: list[str]) -> dict:
    """
    Normalise and validate the parsed JSON dict from the LLM.

    Accepts both the new three-tier schema ("support_level") and the legacy
    boolean schema ("supported") so that old cache entries continue to work
    without any cache-busting or migration step.

    New schema (preferred):
        {"support_level": "yes"|"partial"|"not_applicable", ...}

    Legacy schema (cache backward-compat):
        {"supported": true|false, ...}

    The returned dict always contains "support_level" (str) for new consumers
    and also a derived "supported" (bool) so existing code that checks the
    old key (file_writer, processor) doesn't break during the transition.
    """

    # ── Resolve support_level ─────────────────────────────────────────────────

    raw_level = d.get("support_level")         # new key — preferred

    if raw_level is not None:
        # Normalise whatever string the LLM produced to one of the three tiers
        level_str = str(raw_level).strip().lower()

        if level_str in ("yes", "true", "supported", "full", "fully supported"):
            support_level = "yes"
        elif level_str in ("partial", "partially", "partially supported",
                           "partial support", "limited"):
            support_level = "partial"
        else:
            # "not_applicable", "false", "no", "not supported", unknown → na
            support_level = "not_applicable"

    else:
        # ── Backward compatibility: old boolean "supported" key ───────────────
        # Cached answers written before this change carry:
        #   {"supported": true/false, ...}
        # Map them to the new three-tier system conservatively:
        #   true  → "yes"   (was fully supported then; treat as such)
        #   false → "not_applicable"  (was explicitly unsupported)
        old_bool = d.get("supported")
        if old_bool is True:
            support_level = "yes"
        elif old_bool is False:
            support_level = "not_applicable"
        else:
            support_level = "not_applicable"   # safe default for malformed entries

    # ── Normalise feature categories ──────────────────────────────────────────
    cats_raw = d.get("feature_categories", [])
    if not isinstance(cats_raw, list):
        cats_raw = []

    cleaned: list[str] = []
    for c in cats_raw:
        c_low = str(c).strip().lower()
        for f in valid_features:
            # Accept exact match OR substring overlap (handles "Synthetics" → "synthetics")
            if c_low == f or c_low in f or f in c_low:
                if f not in cleaned:
                    cleaned.append(f)
                break

    # No feature categories make sense for out-of-scope requirements
    if support_level == "not_applicable":
        cleaned = []

    # ── Explanation ───────────────────────────────────────────────────────────
    explanation = str(d.get("explanation", "")).strip()

    # Run through post-processor: strip hedges, enforce capitalisation, trim length
    explanation = _post_process_explanation(explanation, support_level)

    # ── Return unified dict ───────────────────────────────────────────────────
    # "supported" bool is kept for backward compatibility with file_writer.py
    # and any other consumer that pre-dates this change.  New code should read
    # "support_level" instead.
    return {
        "support_level":      support_level,
        "supported":          support_level in ("yes", "partial"),  # legacy compat key
        "feature_categories": cleaned,
        "explanation":        explanation,
    }
