"""
Triage agent: classify alert severity and decide whether to run full investigation.
Supports Bedrock AgentCore (ADK) when bedrock-agentcore is installed and configured.
"""
import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TriageResult:
    """Result of triage for a single alert."""
    severity: str  # low | medium | high | critical
    should_investigate: bool
    summary: str
    namespace: Optional[str] = None
    pod: Optional[str] = None


def _extract_alert_context(alert: dict) -> dict:
    """Extract labels and annotations for triage input."""
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    return {
        "labels": dict(labels),
        "annotations": dict(annotations),
        "status": alert.get("status"),
        "startsAt": alert.get("startsAt"),
    }


def _triage_stub(alert: dict) -> TriageResult:
    """Default: treat all alerts as medium severity and recommend investigation."""
    labels = alert.get("labels") or {}
    namespace = (labels.get("namespace") or "").strip() or None
    pod = (labels.get("pod") or "").strip() or None
    return TriageResult(
        severity="medium",
        should_investigate=True,
        summary="Triage not configured; defaulting to investigate.",
        namespace=namespace,
        pod=pod,
    )


def _triage_with_llm(alert: dict, prompt: str, response_text: str) -> TriageResult:
    """Parse LLM triage response into TriageResult."""
    labels = alert.get("labels") or {}
    namespace = (labels.get("namespace") or "").strip() or None
    pod = (labels.get("pod") or "").strip() or None
    severity = "medium"
    should_investigate = True
    summary = response_text[:500] if response_text else "No summary."

    # Try to parse structured output (e.g. JSON or key lines)
    text_lower = response_text.lower()
    for sev in ("critical", "high", "medium", "low"):
        if sev in text_lower and severity == "medium":
            severity = sev
            break
    if "do not investigate" in text_lower or "skip investigation" in text_lower or "no investigation" in text_lower:
        should_investigate = False
    if "investigate" in text_lower and "not" in text_lower and "do not" in text_lower:
        should_investigate = False

    try:
        # Optional JSON block
        if "{" in response_text and "}" in response_text:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            obj = json.loads(response_text[start:end])
            severity = str(obj.get("severity", severity)).lower()[:20]
            if "should_investigate" in obj:
                should_investigate = bool(obj["should_investigate"])
            if obj.get("summary"):
                summary = str(obj["summary"])[:500]
    except (json.JSONDecodeError, ValueError):
        pass

    return TriageResult(
        severity=severity,
        should_investigate=should_investigate,
        summary=summary,
        namespace=namespace,
        pod=pod,
    )


def triage_alert(alert: dict) -> TriageResult:
    """
    Triage a single alert: classify severity and decide if full investigation is needed.
    Uses Bedrock AgentCore (ADK) when BEDROCK_AGENTCORE_AGENT_ID is set and
    bedrock_agentcore is available; otherwise uses OpenAI if OPENAI_API_KEY is set;
    otherwise returns stub (investigate=True).
    """
    if os.getenv("INSOMNIA_TRIAGE_AGENT_URL", "").strip():
        return _triage_via_adk(alert)
    return _triage_via_openai_or_stub(alert)


def _triage_via_adk(alert: dict) -> TriageResult:
    """Call remote ADK triage agent when INSOMNIA_TRIAGE_AGENT_URL is set."""
    url = os.getenv("INSOMNIA_TRIAGE_AGENT_URL", "").strip()
    if not url:
        return _triage_via_openai_or_stub(alert)
    try:
        import urllib.request
        context = _extract_alert_context(alert)
        payload = json.dumps({"alert": context}).encode("utf-8")
        req = urllib.request.Request(
            url.rstrip("/") + "/invocations",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        out = json.loads(body) if body.strip() else {}
        # ADK entrypoint returns triage result dict
        severity = str(out.get("severity", "medium")).lower()
        should_investigate = out.get("should_investigate", True)
        summary = str(out.get("summary", ""))[:500] or "Triage from ADK agent."
        labels = alert.get("labels") or {}
        return TriageResult(
            severity=severity,
            should_investigate=should_investigate,
            summary=summary,
            namespace=(labels.get("namespace") or "").strip() or None,
            pod=(labels.get("pod") or "").strip() or None,
        )
    except Exception as e:
        logger.exception("ADK triage agent call failed: %s", e)
        return _triage_stub(alert)


def _triage_via_openai_or_stub(alert: dict) -> TriageResult:
    """Use OpenAI for triage if configured, else stub."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _triage_stub(alert)

    try:
        from openai import OpenAI
    except ImportError:
        return _triage_stub(alert)

    context = _extract_alert_context(alert)
    prompt = (
        "Triage this Kubernetes alert. Respond with JSON only: "
        '{"severity": "low|medium|high|critical", "should_investigate": true|false, "summary": "brief reason"}'
        "\n\nAlert context:\n" + json.dumps(context, indent=2)
    )
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    system = (
        "You are a Kubernetes SRE. Classify alert severity and whether to run full root-cause investigation. "
        "Reply only with the JSON object."
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    text = (response.choices[0].message.content or "").strip()
    return _triage_with_llm(alert, prompt, text)


async def triage_alert_async(alert: dict) -> TriageResult:
    """Async wrapper for triage_alert (runs in thread pool if needed for ADK/OpenAI)."""
    import asyncio
    return await asyncio.to_thread(triage_alert, alert)


def triage_result_to_dict(result: TriageResult) -> dict:
    """Serialize TriageResult for API/ADK response."""
    return asdict(result)
