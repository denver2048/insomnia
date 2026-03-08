import uvicorn
import asyncio
import os

from mcp_client import list_tools


async def startup():

    print("\nINSOMNIA starting...\n")
    print("Intelligent Night Operations Monitoring & Investigation Agentt\n")
    print(f"Using LLM model: {os.getenv('OPENAI_MODEL', 'gpt-5.2')}")

    try:
        tools = await list_tools()

        print("Discovered MCP tools:")

        for tool in tools:
            print(f" ✓ {tool.name}")

    except Exception as e:
        print("Failed to connect to MCP server")
        print(e)


if __name__ == "__main__":

    asyncio.run(startup())

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8080
    )