import json

from llm import analyze


async def root_cause(state):

    evidence = {
        "kubernetes": state.get("kubernetes"),
        "logs": state.get("logs"),
        "metrics": state.get("metrics"),
        "registry": state.get("registry"),
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

    return state