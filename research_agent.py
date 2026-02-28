"""
VendorGuard AI — Research Agent
Uses Azure AI Foundry v1 API (OpenAI client + /openai/v1/ base_url).
No api-version required. No AzureOpenAI client.
"""

import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DISCLAIMER = (
    "⚠️ **Responsible AI Disclaimer**: This is AI-generated analysis based on publicly "
    "available information. All vendor decisions require human review and verification. "
    "Scores are probabilistic estimates, not definitive assessments. Do not use this "
    "report as the sole basis for any procurement or business decision."
)

SYSTEM_PROMPT = """\
You are VendorGuard AI, an enterprise vendor risk intelligence agent.

Your task is to assess a vendor's risk profile across four dimensions using your knowledge
of publicly reported events, regulatory actions, security incidents, and financial news.

DIMENSIONS:
1. Financial Risk  — bankruptcy, credit downgrades, revenue decline, debt, layoffs, restatements
2. Security Risk   — data breaches, CVEs, ransomware, supply-chain compromises, CISA/NVD alerts
3. Compliance Risk — GDPR/CCPA/HIPAA/FTC/SEC fines, sanctions, government investigations
4. Reputation Risk — negative press, executive misconduct, class-action lawsuits, whistleblowers

SCORING: Each dimension scored 1 (very low risk) to 10 (very high risk).

DECISION LOGIC:
- Overall score 1–3  → APPROVE
- Overall score 4–6  → FLAG FOR HUMAN REVIEW
- Overall score 7–10 → REJECT

OUTPUT: Return ONLY a valid JSON object (no markdown fences) with this exact schema:

{
  "vendor": "<name>",
  "analysis_date": "<YYYY-MM-DD>",
  "overall_score": <integer 1-10>,
  "recommendation": "<APPROVE | FLAG FOR HUMAN REVIEW | REJECT>",
  "confidence": "<High | Medium | Low>",
  "dimensions": {
    "financial": {
      "score": <1-10>,
      "summary": "<2-3 sentences>",
      "findings": ["<finding with source/date>"],
      "sources": ["<url or publication name>"]
    },
    "security": {
      "score": <1-10>,
      "summary": "<2-3 sentences>",
      "findings": ["<finding with source/date>"],
      "sources": ["<url or publication name>"]
    },
    "compliance": {
      "score": <1-10>,
      "summary": "<2-3 sentences>",
      "findings": ["<finding with source/date>"],
      "sources": ["<url or publication name>"]
    },
    "reputation": {
      "score": <1-10>,
      "summary": "<2-3 sentences>",
      "findings": ["<finding with source/date>"],
      "sources": ["<url or publication name>"]
    }
  },
  "key_findings": ["<top 3-5 most important findings across all dimensions>"],
  "human_review_reason": "<Explain why human review is needed — only populate when FLAG FOR HUMAN REVIEW>",
  "disclaimer": "This is AI-generated analysis. All vendor decisions require human review."
}

RULES:
- Never fabricate sources. If no public information exists, state that explicitly.
- For REJECT: cite at least one specific, verifiable incident.
- For FLAG: explain the uncertainty in human_review_reason.
- overall_score = average of the four dimension scores, rounded to nearest integer.
- Confidence: High = strong evidence found; Medium = some evidence; Low = limited public data.
"""


def _build_prompt(vendor_name: str) -> str:
    return (
        f"Assess the vendor **{vendor_name}** across the four risk dimensions "
        f"(financial, security, compliance, reputation). Draw on all known public "
        f"information — regulatory actions, security incidents, financial news, "
        f"press coverage — and produce the JSON risk report."
    )


def _extract_json(raw: str) -> dict:
    """Parse JSON from model output, handling accidental markdown fences."""
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("No JSON object found in model response.")


def _enforce_scores(result: dict) -> dict:
    """Clamp scores to [1,10] and recalculate overall score and recommendation."""
    dim_ids = ["financial", "security", "compliance", "reputation"]
    scores = []
    for d in dim_ids:
        dim = result.get("dimensions", {}).get(d, {})
        score = max(1, min(10, int(dim.get("score", 5))))
        dim["score"] = score
        scores.append(score)

    overall = max(1, min(10, round(sum(scores) / len(scores))))
    result["overall_score"] = overall

    if overall <= 3:
        result["recommendation"] = "APPROVE"
    elif overall <= 6:
        result["recommendation"] = "FLAG FOR HUMAN REVIEW"
    else:
        result["recommendation"] = "REJECT"

    return result


def _fallback(vendor_name: str, error: str) -> dict:
    return {
        "vendor": vendor_name,
        "analysis_date": datetime.utcnow().date().isoformat(),
        "overall_score": 5,
        "recommendation": "FLAG FOR HUMAN REVIEW",
        "confidence": "Low",
        "dimensions": {
            dim: {
                "score": 5,
                "summary": "Analysis unavailable due to an error.",
                "findings": [f"Error: {error}"],
                "sources": [],
            }
            for dim in ["financial", "security", "compliance", "reputation"]
        },
        "key_findings": [f"Analysis failed: {error}"],
        "human_review_reason": (
            f"Automated analysis could not complete ({error}). "
            "Manual research is required before any decision."
        ),
        "disclaimer": DISCLAIMER,
        "_error": error,
    }


def run_vendor_analysis(vendor_name: str) -> dict:
    """
    Run a full vendor risk analysis using the Azure AI Foundry v1 API.
    Uses OpenAI() client with base_url pointing to /openai/v1/ — no api-version needed.
    """
    api_key = os.getenv("AZURE_OPENAI_KEY", "").strip()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o").strip()

    if not api_key or not endpoint or "your-resource" in endpoint:
        return _fallback(
            vendor_name,
            "Azure OpenAI credentials not configured. "
            "Set AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT in .env",
        )

    # Foundry v1 API: append /openai/v1/ to the resource endpoint
    base_url = endpoint.rstrip("/") + "/openai/v1/"

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(vendor_name)},
            ],
            temperature=0.2,
            max_tokens=4096,
        )

        raw = response.choices[0].message.content or ""
        result = _extract_json(raw)
        result = _enforce_scores(result)
        result.setdefault("vendor", vendor_name)
        result.setdefault("analysis_date", datetime.utcnow().date().isoformat())
        result["disclaimer"] = DISCLAIMER
        return result

    except json.JSONDecodeError as e:
        return _fallback(vendor_name, f"JSON parse error — {e}")
    except Exception as e:
        return _fallback(vendor_name, str(e))
