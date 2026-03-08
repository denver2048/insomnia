from mcp_client import call


async def kubernetes_investigator(state):

    ns = state["alert"]["namespace"]
    pod = state["alert"]["pod"]

    pod_info = await call(
        "pods_get",
        {
            "namespace": ns,
            "name": pod
        }
    )

    events = await call(
        "events_list",
        {
            "namespace": ns
        }
    )

    state["k8s_data"] = {
        "pod": pod_info,
        "events": events
    }

    return state