import logging

from agent.graph import agent
from tools.jira_itsm import notify_jira_itsm_async

logger = logging.getLogger(__name__)


async def investigate(alert):

    namespace = alert["labels"]["namespace"]
    pod = alert["labels"]["pod"]
    logger.info("Step: investigation pipeline starting for %s/%s", namespace, pod)

    state = {
        "namespace": namespace,
        "pod": pod,
        "alert": alert,
    }

    result = await agent.ainvoke(state)
    logger.info("Step: investigation pipeline finished for %s/%s", namespace, pod)

    try:
        await notify_jira_itsm_async(alert, result)
    except Exception:
        logger.exception("Jira ITSM notification failed (investigation result still returned)")

    return result