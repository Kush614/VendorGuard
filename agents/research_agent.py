"""
VendorGuard AI — Research Agent
Multi-dimensional vendor risk analysis using Azure OpenAI GPT-4o.

Agents modelled here:
  1. Research Agent  — gathers intelligence via GPT-4o training data
  2. Risk Scoring Agent — scores 4 dimensions with weights
  3. Report Agent  — formats structured enterprise report
  4. Decision Agent — applies decision logic (APPROVE / FLAG / REJECT)
"""

import json
import re
from datetime import datetime
from utils.azure_client import get_client, get_deployment

# --------------------------------------------------------------------------- #
#  Weights                                                                      #
# --------------------------------------------------------------------------- #
WEIGHTS = {
    "financial": 0.25,
    "security": 0.35,
    "compliance": 0.25,
    "reputation": 0.15,
}

# --------------------------------------------------------------------------- #
#  System prompt                                                                #
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """\
You are VendorGuard AI, a senior enterprise vendor risk intelligence agent.

Analyse the given vendor across four risk dimensions using all publicly known
information: regulatory actions, security incidents, financial news, lawsuits,
press coverage.

DIMENSIONS AND WEIGHTS:
  Financial Risk   (25%) — bankruptcy risk, revenue decline, debt, restatements, layoffs
  Security Risk    (35%) — data breaches, CVEs, ransomware, supply-chain compromises
  Compliance Risk  (25%) — GDPR/CCPA/HIPAA/FTC/SEC fines, sanctions, investigations
  Reputation Risk  (15%) — negative press, executive misconduct, lawsuits, whistleblowers

SCORING: Each dimension 1 (lowest risk) to 10 (highest risk).

WEIGHTED SCORE = financial*0.25 + security*0.35 + compliance*0.25 + reputation*0.15

DECISION THRESHOLDS:
  1.0 – 3.5  → APPROVE
  3.6 – 6.5  → FLAG FOR HUMAN REVIEW
  6.6 – 10.0 → REJECT

RULES:
- Never REJECT without citing at least one specific, verifiable incident.
- For FLAG: populate recommendation_reason with actionable reviewer guidance.
- Confidence: High = strong evidence found; Medium = some evidence; Low = limited data.
- If no public information exists for a dimension, score it 5 and note limited data.
- Return ONLY a valid JSON object — no markdown fences, no extra text.

OUTPUT SCHEMA (exact field names required):
{
  "vendor_name": "<name>",
  "analysis_date": "<YYYY-MM-DD>",
  "financial_risk": {
    "score": <integer 1-10>,
    "explanation": "<one clear sentence>",
    "key_facts": ["<fact with date/source>", "<fact with date/source>"]
  },
  "security_risk": {
    "score": <integer 1-10>,
    "explanation": "<one clear sentence>",
    "key_facts": ["<fact with date/source>", "<fact with date/source>"]
  },
  "compliance_risk": {
    "score": <integer 1-10>,
    "explanation": "<one clear sentence>",
    "key_facts": ["<fact with date/source>", "<fact with date/source>"]
  },
  "reputation_risk": {
    "score": <integer 1-10>,
    "explanation": "<one clear sentence>",
    "key_facts": ["<fact with date/source>", "<fact with date/source>"]
  },
  "weighted_score": <float rounded to 1 decimal>,
  "confidence_level": "<High|Medium|Low>",
  "confidence_reason": "<why this confidence level>",
  "executive_summary": "<2-3 sentence executive summary>",
  "recommendation": "<APPROVE|FLAG FOR HUMAN REVIEW|REJECT>",
  "recommendation_reason": "<specific reason with evidence>",
  "next_steps": ["<step1>", "<step2>", "<step3>"]
}
"""


# --------------------------------------------------------------------------- #
#  Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _extract_json(raw: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("No JSON object found in model response.")


def _enforce_scores(result: dict) -> dict:
    """Clamp scores to [1,10], recalculate weighted score, enforce decision thresholds."""
    dim_keys = ["financial", "security", "compliance", "reputation"]
    scores = {}
    for k in dim_keys:
        dim = result.get(f"{k}_risk", {})
        score = max(1, min(10, int(dim.get("score", 5))))
        dim["score"] = score
        scores[k] = score

    weighted = round(
        scores["financial"] * WEIGHTS["financial"]
        + scores["security"] * WEIGHTS["security"]
        + scores["compliance"] * WEIGHTS["compliance"]
        + scores["reputation"] * WEIGHTS["reputation"],
        1,
    )
    result["weighted_score"] = weighted

    if weighted <= 3.5:
        result["recommendation"] = "APPROVE"
    elif weighted <= 6.5:
        result["recommendation"] = "FLAG FOR HUMAN REVIEW"
    else:
        result["recommendation"] = "REJECT"

    return result


def _fallback(vendor_name: str, error: str) -> dict:
    return {
        "vendor_name": vendor_name,
        "analysis_date": datetime.utcnow().date().isoformat(),
        "financial_risk": {
            "score": 5,
            "explanation": "Analysis unavailable due to an error.",
            "key_facts": [f"Error: {error}"],
        },
        "security_risk": {
            "score": 5,
            "explanation": "Analysis unavailable due to an error.",
            "key_facts": [],
        },
        "compliance_risk": {
            "score": 5,
            "explanation": "Analysis unavailable due to an error.",
            "key_facts": [],
        },
        "reputation_risk": {
            "score": 5,
            "explanation": "Analysis unavailable due to an error.",
            "key_facts": [],
        },
        "weighted_score": 5.0,
        "confidence_level": "Low",
        "confidence_reason": f"API error: {error}",
        "executive_summary": (
            f"Analysis failed due to: {error}. "
            "Please verify API credentials in .env and retry."
        ),
        "recommendation": "FLAG FOR HUMAN REVIEW",
        "recommendation_reason": (
            "Automated analysis could not complete. Manual research is required."
        ),
        "next_steps": [
            "Verify AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT in .env",
            "Confirm the Azure AI Foundry deployment is active",
            "Retry analysis once connectivity is confirmed",
        ],
        "_error": error,
    }


# --------------------------------------------------------------------------- #
#  Public API                                                                   #
# --------------------------------------------------------------------------- #

def run_vendor_analysis(vendor_name: str) -> dict:
    """
    Run a full four-dimension vendor risk analysis.

    Returns a dict matching the schema defined in SYSTEM_PROMPT.
    Falls back gracefully on any API error.
    """
    client = get_client()

    prompt = (
        f"Assess the vendor **{vendor_name}** across all four risk dimensions "
        f"(financial, security, compliance, reputation). "
        f"Draw on all known public information and produce the JSON risk report."
    )

    try:
        response = client.chat.completions.create(
            model=get_deployment(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        raw = response.choices[0].message.content or ""
        result = _extract_json(raw)
        result = _enforce_scores(result)
        result.setdefault("vendor_name", vendor_name)
        result.setdefault("analysis_date", datetime.utcnow().date().isoformat())
        return result

    except json.JSONDecodeError as exc:
        return _fallback(vendor_name, f"JSON parse error — {exc}")
    except Exception as exc:
        return _fallback(vendor_name, str(exc))
