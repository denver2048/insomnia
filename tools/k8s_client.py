from kubernetes import client, config


config.load_incluster_config()

core = client.CoreV1Api()
apps = client.AppsV1Api()


def get_pod(namespace, name):

    return core.read_namespaced_pod(name, namespace)


def get_pod_events(namespace, name):

    events = core.list_namespaced_event(namespace)

    return [
        e.message
        for e in events.items
        if e.involved_object.name == name
    ]


def get_pod_logs(namespace, name, container=None, tail_lines=200):

    return core.read_namespaced_pod_log(
        name=name,
        namespace=namespace,
        container=container,
        tail_lines=tail_lines,
    )