from __future__ import annotations
import logging

from services.ollama_service import generate

logger = logging.getLogger("ecopulse.energy_ai")


def _build_prompt(energy: dict) -> str:

    prompt = f"""
You are a senior Green AI and Sustainable Machine Learning expert.

Analyze the following Energy Audit.

ENERGY SUMMARY

Energy Consumed:
{energy.get("energy_kwh", 0)} kWh

Carbon Emissions:
{energy.get("carbon_kg", 0)} kg CO₂

Model:
{energy.get("model", "Unknown")}

Epochs:
{energy.get("epochs", "Unknown")}

Samples:
{energy.get("num_samples", "Unknown")}

Provide the response in plain English.

Do NOT use markdown.

Use EXACTLY these numbered headings.

1. EXECUTIVE SUMMARY

2. SUSTAINABILITY RATING

3. ENVIRONMENTAL IMPACT

4. KEY FINDINGS

5. RECOMMENDATIONS

Keep the response under 250 words.
"""

    return prompt


def _extract_section(text: str, start_marker: str, end_marker: str | None):

    if not text:
        return ""

    lower = text.lower()

    start = lower.find(start_marker.lower())

    if start == -1:
        return ""

    start += len(start_marker)

    if end_marker:

        end = lower.find(end_marker.lower(), start)

        if end != -1:
            return text[start:end].strip(" \n:-*")

    return text[start:].strip(" \n:-*")


def _parse_response(text: str):

    result = {

        "summary":
            _extract_section(
                text,
                "1. EXECUTIVE SUMMARY",
                "2."
            ),

        "rating":
            _extract_section(
                text,
                "2. SUSTAINABILITY RATING",
                "3."
            ),

        "environment":
            _extract_section(
                text,
                "3. ENVIRONMENTAL IMPACT",
                "4."
            ),

        "findings":
            _extract_section(
                text,
                "4. KEY FINDINGS",
                "5."
            ),

        "recommendations":
            _extract_section(
                text,
                "5. RECOMMENDATIONS",
                None
            ),

        "raw": text,
    }

    if text and not any(
        result[k]
        for k in (
            "summary",
            "rating",
            "environment",
            "findings",
            "recommendations",
        )
    ):
        result["summary"] = text

    return result


def analyze_energy(metrics: dict):

    logger.info("Calling Ollama for Energy AI analysis")

    prompt = _build_prompt(metrics)

    raw = generate(prompt)

    return _parse_response(raw)