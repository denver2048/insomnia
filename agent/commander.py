from agent.graph import agent


async def investigate(alert):

    namespace = alert["labels"]["namespace"]
    pod = alert["labels"]["pod"]

    state = {
        "namespace": namespace,
        "pod": pod,
    }

    result = await agent.ainvoke(state)

    return result