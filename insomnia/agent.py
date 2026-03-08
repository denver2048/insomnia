import re

from langgraph.graph import StateGraph, END

from investigators.k8s import kubernetes_investigator
from investigators.logs import log_investigator

from dockerhub import search_image_tags
from ecr import is_ecr_image, extract_registry
from ecr_auth import check_image_pull_secrets

from llm import analyze
    
# ------------------------------------------------
# Evidence aggregation
# ------------------------------------------------

def aggregate(state):

    alert_pod = state.get("pod")

    k8s_data = state.get("k8s_data")

    if isinstance(k8s_data, list):

        k8s_data = [p for p in k8s_data if p.get("metadata", {}).get("name") == alert_pod]

    evidence = f"""
    Incident scope:
    Only analyze pod {state.get("pod")} in namespace {state.get("namespace")}.
    Kubernetes data:
    {state.get("k8s_data")}

    Logs:
    {state.get("logs")}
    """

    state["evidence"] = evidence

    return state


# ------------------------------------------------
# Root cause analysis
# ------------------------------------------------

async def root_cause(state):

    evidence = state["evidence"]

    match = re.search(r'image "([^"]+)"', evidence)

    if not match:

        report = analyze(evidence)
        state["report"] = report
        return state

    image = match.group(1)

    repo = image.split(":")[0]

    tag = image.split(":")[-1]

    # ------------------------------------------------
    # ECR investigation
    # ------------------------------------------------

    if is_ecr_image(image):

        pod = state.get("k8s_data")

        if isinstance(pod, list):
            pod = pod[0]

        

        has_secret, secret_names = check_image_pull_secrets(pod)

        if not has_secret:

            evidence += f"""

ECR authentication check:

Registry: {extract_registry(image)}

Result:
No imagePullSecrets configured.

Authentication to private ECR registry will fail.
"""

        else:

            evidence += f"""

ECR authentication check:

imagePullSecrets present:
{secret_names}

Authentication likely configured.
"""

            evidence += f"""

Tag verification:

Requested tag:
{tag}

Registry authentication passed.
Image tag should be verified in ECR repository.
"""

    # ------------------------------------------------
    # DockerHub investigation
    # ------------------------------------------------

    elif "." not in repo:

        tags = search_image_tags(repo)

        if tags:

            evidence += f"""

DockerHub tag verification:

Image repository:
{repo}

Available tags:
{tags}

Requested tag:
{tag}
"""

    # ------------------------------------------------
    # Other registry
    # ------------------------------------------------

    else:

        evidence += f"""

Registry detection:

Unknown container registry.

Manual verification required for image:
{image}
"""

    report = analyze(evidence)

    state["report"] = report

    return state


# ------------------------------------------------
# LangGraph pipeline
# ------------------------------------------------

graph = StateGraph(dict)

graph.add_node("k8s_investigator", kubernetes_investigator)
graph.add_node("log_investigator", log_investigator)
graph.add_node("aggregate", aggregate)
graph.add_node("analysis", root_cause)

graph.set_entry_point("k8s_investigator")

graph.add_edge("k8s_investigator", "log_investigator")
graph.add_edge("log_investigator", "aggregate")
graph.add_edge("aggregate", "analysis")
graph.add_edge("analysis", END)

agent = graph.compile()