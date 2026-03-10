from tools.prom_client import query_prometheus


async def metrics_investigator(state):

    pod = state["pod"]

    expr = f'container_memory_usage_bytes{{pod="{pod}"}}'

    result = query_prometheus(expr)

    state["metrics"] = result

    return state