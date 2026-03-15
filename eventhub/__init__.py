# Event hub: receives Alertmanager webhooks, applies guardrails, then forwards to Insomnia investigation.

from eventhub.hub import process_webhook
from eventhub.guardrails import GuardrailResult

__all__ = ["process_webhook", "GuardrailResult"]
