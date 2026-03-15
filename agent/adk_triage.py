"""
ADK (Bedrock AgentCore) entrypoint for the triage agent.
Run this app to deploy the triage agent to Amazon Bedrock AgentCore:

  pip install bedrock-agentcore
  python -m agent.adk_triage

Or use the Starter Toolkit / CDK to deploy. The app exposes POST /invocations
with payload {"alert": {"labels": {...}, "annotations": {...}}} and returns
{"severity": "...", "should_investigate": bool, "summary": "..."}.
"""
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _triage_entrypoint(payload: dict) -> dict:
    """ADK entrypoint: run triage on alert from payload and return result dict."""
    from agent.triage import triage_alert, triage_result_to_dict

    alert = payload.get("alert") or payload
    if not isinstance(alert, dict):
        return {
            "severity": "medium",
            "should_investigate": True,
            "summary": "Invalid payload: missing or invalid 'alert'.",
            "namespace": None,
            "pod": None,
        }
    result = triage_alert(alert)
    return triage_result_to_dict(result)


def main() -> None:
    try:
        from bedrock_agentcore import BedrockAgentCoreApp
    except ImportError:
        logger.error(
            "bedrock-agentcore not installed. Install with: pip install bedrock-agentcore"
        )
        raise SystemExit(1)

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def triage_agent(payload: dict) -> dict:
        return _triage_entrypoint(payload)

    host = os.getenv("TRIAGE_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("TRIAGE_AGENT_PORT", "8001"))
    logger.info("Triage agent (ADK) listening on %s:%s", host, port)
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
