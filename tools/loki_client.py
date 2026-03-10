import requests

from config.settings import settings


def get_logs(namespace, pod):

    query = f'{{namespace="{namespace}", pod="{pod}"}}'

    url = f"{settings.LOKI_URL}/loki/api/v1/query_range"

    params = {
        "query": query,
        "limit": settings.LOG_LINES,
    }

    r = requests.get(url, params=params)

    data = r.json()

    logs = []

    for stream in data.get("data", {}).get("result", []):

        for entry in stream.get("values", []):
            logs.append(entry[1])

    return logs