from tools.k8s_client import get_pod_logs


def get_logs(namespace, pod, lines=200):

    try:

        logs = get_pod_logs(
            namespace,
            pod,
            tail_lines=lines,
        )

        return logs.splitlines()

    except Exception:

        return []