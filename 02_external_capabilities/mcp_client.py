"""不用 LLM，直接观察 MCP 工具发现和一次只读调用。"""

import asyncio
import json

from mcp import Client


async def main():
    async with Client("http://127.0.0.1:18081/mcp") as client:
        print("Protocol version:", client.protocol_version)
        print("MCP Client → Server: tools/list")
        tools = await client.list_tools()
        for tool in tools.tools:
            print("Discovered:", tool.name, json.dumps(tool.input_schema, ensure_ascii=False))
        arguments = {
            "start_time": "2026-11-09T10:00:00+08:00",
            "end_time": "2026-11-09T11:00:00+08:00",
        }
        print("MCP Client → Server: tools/call get_calendar_events", json.dumps(arguments, ensure_ascii=False))
        result = await client.call_tool("get_calendar_events", arguments)
        print("is_error:", result.is_error)
        print("structured_content:", json.dumps(result.structured_content, ensure_ascii=False))
        print("content:", [block.text for block in result.content if block.type == "text"])


if __name__ == "__main__":
    asyncio.run(main())
