import requests
from config.settings import settings


def query_prometheus(expr):

    url = f"{settings.PROMETHEUS_URL}/api/v1/query"

    r = requests.get(url, params={"query": expr})

    return r.json()