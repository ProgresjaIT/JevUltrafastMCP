import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_handshake_and_invalid_tool_call():
    async def check():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "jev_ultrafast_mcp.server"])
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "Jev Ultrafast MCP"
                tools = (await session.list_tools()).tools
                assert [tool.name for tool in tools] == ["browse"]
                assert set(tools[0].inputSchema["required"]) == {"url", "goal"}
                result = await session.call_tool("browse", {"url": "file:///secret", "goal": "Read"})
                assert result.isError
                assert "HTTP" in result.content[0].text

    asyncio.run(check())
