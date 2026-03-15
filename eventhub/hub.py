"""
Event hub: receives Alertmanager webhook payloads, normalizes alerts,
runs guardrails, runs triage (optional), and forwards approved alerts
to the investigation pipeline when triage recommends it.
"""
import logging
import os
from typing import Any, Awaitable, Callable, List, Optional

from eventhub.guardrails import check_guardrails, GuardrailResult

from agent.triage import TriageResult, triage_alert_async

logger = logging.getLogger(__name__)


def _normalize_alerts(payload: dict) -> List[dict]:
    """Extract and normalize alert(s) from Alertmanager webhook payload."""
    raw = payload.get("alerts") or payload.get("alert")
    if not raw:
        return []
    if isinstance(raw, list):
        return [a for a in raw if isinstance(a, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _use_triage() -> bool:
    """Whether to run triage (env INSOMNIA_USE_TRIAGE, default True)."""
    val = os.getenv("INSOMNIA_USE_TRIAGE", "true").strip().lower()
    return val in ("1", "true", "yes")


async def process_webhook(
    payload: dict,
    *,
    on_approved: Callable[[dict], Awaitable[Any]],
    use_triage: Optional[bool] = None,
) -> tuple[list[GuardrailResult], list[dict], list[Optional[TriageResult]]]:
    """
    Process a webhook payload: normalize alerts, run guardrails per alert,
    optionally run triage; call on_approved only for alerts that pass and
    (if use_triage) triage says should_investigate.
    Returns (rejected_results, approved_alerts, triage_results).
    """
    if use_triage is None:
        use_triage = _use_triage()
    alerts = _normalize_alerts(payload)
    if not alerts:
        logger.info("Event hub: no alerts in payload")
        return ([], [], [])

    if use_triage:
        logger.info(
            "Event hub: triage enabled — classifying each alert and running investigation only when triage recommends."
        )
    else:
        logger.info(
            "Event hub: triage disabled — all approved alerts will be fully investigated. "
            "To enable triage: set INSOMNIA_USE_TRIAGE=true (default). "
            "To use a remote ADK triage agent: set INSOMNIA_TRIAGE_AGENT_URL to the agent base URL (e.g. http://triage-agent:8001)."
        )

    rejected: list[GuardrailResult] = []
    approved: list[dict] = []
    triage_results: list[Optional[TriageResult]] = []

    for alert in alerts:
        result = check_guardrails(alert)
        if not result.passed:
            rejected.append(result)
            triage_results.append(None)
            logger.info(
                "Event hub: guardrails rejected alert namespace=%s pod=%s reason=%s",
                result.namespace or "?",
                result.pod or "?",
                result.reason,
            )
            continue

        triage_result: Optional[TriageResult] = None
        if use_triage:
            triage_result = await triage_alert_async(alert)
            triage_results.append(triage_result)
            logger.info(
                "Event hub: triage severity=%s should_investigate=%s namespace=%s pod=%s",
                triage_result.severity,
                triage_result.should_investigate,
                triage_result.namespace or "?",
                triage_result.pod or "?",
            )
            if not triage_result.should_investigate:
                logger.info(
                    "Event hub: triage skipped investigation namespace=%s pod=%s",
                    triage_result.namespace or "?",
                    triage_result.pod or "?",
                )
                continue
        else:
            triage_results.append(None)

        approved.append(alert)
        labels = alert.get("labels", {})
        ns = labels.get("namespace", "?")
        pod = labels.get("pod", "?")
        logger.info("Event hub: guardrails passed → forwarding to investigation namespace=%s pod=%s", ns, pod)
        await on_approved(alert)

    return (rejected, approved, triage_results)
