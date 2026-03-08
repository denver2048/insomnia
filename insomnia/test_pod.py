import asyncio
from mcp_client import call


async def main():

    pod = await call(
        "pods_list",
        {}
    )

    print(pod)


asyncio.run(main())