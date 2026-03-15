"""
Event hub: receives Alertmanager webhook payloads, normalizes alerts,
runs guardrails, and forwards approved alerts to the investigation pipeline.
"""
import logging
from typing import Any, Awaitable, Callable, List

from eventhub.guardrails import check_guardrails, GuardrailResult

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


async def process_webhook(
    payload: dict,
    *,
    on_approved: Callable[[dict], Awaitable[Any]],
) -> tuple[list[GuardrailResult], list[dict]]:
    """
    Process a webhook payload: normalize alerts, run guardrails per alert,
    call on_approved for each alert that passes. Returns (rejected_results, approved_alerts).
    """
    alerts = _normalize_alerts(payload)
    if not alerts:
        logger.info("Event hub: no alerts in payload")
        return ([], [])

    rejected: list[GuardrailResult] = []
    approved: list[dict] = []

    for alert in alerts:
        result = check_guardrails(alert)
        if not result.passed:
            rejected.append(result)
            logger.info(
                "Event hub: guardrails rejected alert namespace=%s pod=%s reason=%s",
                result.namespace or "?",
                result.pod or "?",
                result.reason,
            )
            continue
        approved.append(alert)
        labels = alert.get("labels", {})
        ns = labels.get("namespace", "?")
        pod = labels.get("pod", "?")
        logger.info("Event hub: guardrails passed → forwarding to investigation namespace=%s pod=%s", ns, pod)
        await on_approved(alert)

    return (rejected, approved)
