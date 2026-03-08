import re


def is_ecr_image(image: str):

    return ".dkr.ecr." in image


def extract_registry(image: str):

    match = re.match(r"([0-9]+\.dkr\.ecr\.[^.]+\.amazonaws\.com)", image)

    if match:
        return match.group(1)

    return None