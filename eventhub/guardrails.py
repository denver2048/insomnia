"""
Guardrails: validate and filter alerts before Insomnia investigation.
Runs after Alertmanager webhook and before the investigation pipeline.
"""
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GuardrailResult:
    """Result of guardrails check for a single alert."""
    passed: bool
    reason: str
    namespace: Optional[str] = None
    pod: Optional[str] = None


def _parse_list_env(name: str, default: Optional[list[str]] = None) -> list[str]:
    """Parse comma-separated env var into list of stripped non-empty strings."""
    val = os.getenv(name, "").strip()
    if not val:
        return default or []
    return [x.strip() for x in val.split(",") if x.strip()]


# In-memory rate limit: last investigation time per (namespace, pod)
_last_investigation: dict[tuple[str, str], float] = {}
# Config: allowed alert names (empty = allow all), blocked alert names, cooldown seconds
GUARDRAIL_ALLOWED_ALERTNAMES = _parse_list_env("INSOMNIA_GUARDRAIL_ALLOWED_ALERTNAMES")
GUARDRAIL_BLOCKED_ALERTNAMES = _parse_list_env("INSOMNIA_GUARDRAIL_BLOCKED_ALERTNAMES")
GUARDRAIL_COOLDOWN_SECONDS = int(os.getenv("INSOMNIA_GUARDRAIL_COOLDOWN_SECONDS", "300"))


def check_guardrails(alert: dict) -> GuardrailResult:
    """
    Run guardrails on a single alert. Returns GuardrailResult.
    Checks: required labels (namespace, pod), allowlist/blocklist by alertname, rate limit.
    """
    labels = alert.get("labels") or {}
    namespace = (labels.get("namespace") or "").strip()
    pod = (labels.get("pod") or "").strip()
    alertname = (labels.get("alertname") or "").strip()

    if not namespace or not pod:
        return GuardrailResult(
            passed=False,
            reason="missing required labels: namespace and pod",
            namespace=namespace or None,
            pod=pod or None,
        )

    if GUARDRAIL_ALLOWED_ALERTNAMES and alertname not in GUARDRAIL_ALLOWED_ALERTNAMES:
        return GuardrailResult(
            passed=False,
            reason=f"alertname '{alertname}' not in allowlist",
            namespace=namespace,
            pod=pod,
        )

    if alertname and alertname in GUARDRAIL_BLOCKED_ALERTNAMES:
        return GuardrailResult(
            passed=False,
            reason=f"alertname '{alertname}' is blocklisted",
            namespace=namespace,
            pod=pod,
        )

    key = (namespace, pod)
    now = time.time()
    last = _last_investigation.get(key, 0)
    if now - last < GUARDRAIL_COOLDOWN_SECONDS:
        return GuardrailResult(
            passed=False,
            reason=f"rate limit: cooldown {GUARDRAIL_COOLDOWN_SECONDS}s for {namespace}/{pod}",
            namespace=namespace,
            pod=pod,
        )

    _last_investigation[key] = now
    return GuardrailResult(passed=True, reason="", namespace=namespace, pod=pod)
