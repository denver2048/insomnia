from config.settings import settings

from tools.k8s_log_client import get_logs as get_k8s_logs
from tools.loki_client import get_logs as get_loki_logs


def get_logs(namespace, pod):

    if settings.LOG_PROVIDER == "loki":

        return get_loki_logs(namespace, pod)

    return get_k8s_logs(namespace, pod)