import logging

from tools.k8s_client import get_pod, get_pod_events

logger = logging.getLogger(__name__)


async def kubernetes_investigator(state):

    namespace = state["namespace"]
    pod_name = state["pod"]
    logger.info("Step: kubernetes investigator → fetching pod %s/%s", namespace, pod_name)

    pod = get_pod(namespace, pod_name)

    events = get_pod_events(namespace, pod_name)

    containers = []

    for c in pod.status.container_statuses or []:

        containers.append(
            {
                "name": c.name,
                "restart_count": c.restart_count,
                "state": str(c.state),
                "last_state": str(c.last_state),
            }
        )

    state["kubernetes"] = {
        "pod": pod_name,
        "phase": pod.status.phase,
        "node": pod.spec.node_name,
        "containers": containers,
        "events": events,
    }

    return state