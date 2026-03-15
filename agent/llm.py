"""
LLM analysis for Kubernetes incident root cause.
Uses OpenAI when OPENAI_API_KEY is set; otherwise returns a stub report.
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

_OPENAI_KEY_MISSING_MSG = (
    "ERROR: OPENAI_API_KEY is not set or empty. Create secret 'insomnia-openai' with "
    "OPENAI_API_KEY or set OPENAI_API_KEY in the environment to enable LLM root-cause analysis."
)


def analyze(prompt: str) -> str:
    """Analyze incident evidence and return a root-cause report (sync)."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        return _analyze_openai(prompt, api_key)
    logger.error(_OPENAI_KEY_MISSING_MSG)
    print(_OPENAI_KEY_MISSING_MSG, file=sys.stderr, flush=True)
    return _analyze_stub(prompt)


def _analyze_stub(prompt: str) -> str:
    """Return a placeholder report when no LLM is configured."""
    return (
        "[Stub] No OPENAI_API_KEY set. Configure OPENAI_API_KEY for LLM analysis.\n"
        "Evidence was collected; run with OpenAI for root cause, confidence, and suggested fix."
    )


def _analyze_openai(prompt: str, api_key: str) -> str:
    """Call OpenAI (or gateway) to analyze the incident evidence."""
    try:
        from openai import OpenAI
    except ImportError:
        return _analyze_stub(prompt) + "\n(openai package not installed; add openai to requirements.txt)"

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip() or None
    client = OpenAI(api_key=api_key, base_url=base_url)

    system = (
        "You are a senior Kubernetes SRE. Analyze the incident evidence and respond with: "
        "root cause, confidence (low/medium/high), and suggested fix. Be concise."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()
