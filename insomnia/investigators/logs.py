from mcp_client import call


async def log_investigator(state):

    ns = state["alert"]["namespace"]
    pod = state["alert"]["pod"]

    logs = await call(
        "pods_log",
        {
            "namespace": ns,
            "name": pod,
            "tail_lines": 100
        }
    )

    state["logs"] = logs

    return state