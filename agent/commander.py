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

    result: dict = {}
    try:
        out = await agent.ainvoke(state)
        result = out if isinstance(out, dict) else {"report": str(out)}
    except Exception:
        logger.exception("Step: investigation pipeline failed for %s/%s", namespace, pod)
        result = {
            "report": f"Investigation failed before completion (see logs). Namespace={namespace} pod={pod}",
        }
        raise
    finally:
        logger.info("Step: investigation pipeline finished for %s/%s", namespace, pod)
        try:
            logger.info(
                "ITSM: sending investigation result to Jira (namespace=%s pod=%s report_chars=%s)",
                namespace,
                pod,
                len(str((result or {}).get("report") or "")),
            )
            await notify_jira_itsm_async(alert, result)
        except Exception:
            logger.exception("ITSM: Jira notification raised (investigation result still returned)")

    return result