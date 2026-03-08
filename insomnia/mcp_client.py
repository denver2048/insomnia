from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

MCP_URL = "http://localhost:8081/sse"


async def list_tools():

    async with sse_client(MCP_URL) as (read_stream, write_stream):

        async with ClientSession(read_stream, write_stream) as session:

            await session.initialize()

            tools = await session.list_tools()

            return tools.tools


async def call(tool_name: str, args: dict):

    async with sse_client(MCP_URL) as (read_stream, write_stream):

        async with ClientSession(read_stream, write_stream) as session:

            await session.initialize()

            result = await session.call_tool(tool_name, args)

            return result.content