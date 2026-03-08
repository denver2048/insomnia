import requests


def extract_repo(image: str):
    return image.split(":")[0]


def search_image_tags(image: str, limit: int = 5):

    repo = extract_repo(image)

    if "/" not in repo:
        repo = f"library/{repo}"

    url = f"https://registry.hub.docker.com/v2/repositories/{repo}/tags"

    try:
        r = requests.get(url, params={"page_size": limit}, timeout=5)

        r.raise_for_status()

        data = r.json()

        return [t["name"] for t in data.get("results", [])]

    except Exception:
        return []