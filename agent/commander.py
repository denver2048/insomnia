import logging

from agent.graph import agent

logger = logging.getLogger(__name__)


async def investigate(alert):

    namespace = alert["labels"]["namespace"]
    pod = alert["labels"]["pod"]
    logger.info("Step: investigation pipeline starting for %s/%s", namespace, pod)

    state = {
        "namespace": namespace,
        "pod": pod,
    }

    result = await agent.ainvoke(state)
    logger.info("Step: investigation pipeline finished for %s/%s", namespace, pod)
    return result