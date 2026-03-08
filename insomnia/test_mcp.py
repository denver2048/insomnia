import asyncio
from mcp_client import list_tools


async def main():

    print("Connecting to MCP...")

    tools = await list_tools()

    print("Connected!")

    for tool in tools:
        print("-", tool.name)


asyncio.run(main())