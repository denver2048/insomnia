import logging

from tools.log_client import get_logs

logger = logging.getLogger(__name__)


async def log_investigator(state):

    namespace = state["namespace"]
    pod = state["pod"]
    logger.info("Step: logs investigator → fetching logs for %s/%s", namespace, pod)

    logs = get_logs(namespace, pod)

    errors = [
        line
        for line in logs
        if "error" in line.lower()
        or "exception" in line.lower()
    ]

    state["logs"] = {
        "errors": errors[:10],
        "sample": logs[-20:],
    }

    return state