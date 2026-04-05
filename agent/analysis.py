import json
import logging

from agent.llm import analyze

logger = logging.getLogger(__name__)


async def root_cause(state):

    logger.info("Step: root cause analysis → calling LLM")
    evidence = {
        "kubernetes": state.get("kubernetes"),
        "logs": state.get("logs"),
        "metrics": state.get("metrics"),
        "registry": state.get("registry"),
        "jira": state.get("jira"),
    }

    prompt = f"""
Analyze Kubernetes incident.

Evidence:

{json.dumps(evidence, indent=2)}

Provide:

- root cause
- confidence
- suggested fix
"""

    report = analyze(prompt)
    state["report"] = report
    logger.info("Step: root cause analysis → report ready (length=%d)", len(report))
    logger.info("LLM answer:\n%s", report)
    return state