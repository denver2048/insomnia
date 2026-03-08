def check_image_pull_secrets(pod):

    if not isinstance(pod, dict):
        return False, []

    spec = pod.get("spec", {})

    secrets = spec.get("imagePullSecrets", [])

    if not secrets:
        return False, []

    return True, [s["name"] for s in secrets]