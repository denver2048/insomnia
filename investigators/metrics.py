import logging

from tools.prom_client import query_prometheus

logger = logging.getLogger(__name__)


async def metrics_investigator(state):

    pod = state["pod"]
    logger.info("Step: metrics investigator → querying Prometheus for pod=%s", pod)

    expr = f'container_memory_usage_bytes{{pod="{pod}"}}'

    result = query_prometheus(expr)

    state["metrics"] = result

    return state