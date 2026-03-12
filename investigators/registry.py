import logging

logger = logging.getLogger(__name__)


async def registry_investigator(state):

    logger.info("Step: registry investigator → checking image registry")
    state["registry"] = {}

    return state