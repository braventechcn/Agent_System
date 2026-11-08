"""MCP Server：把虚拟手机 REST API 包装为可发现的 MCP 工具。"""

import os
import json

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError


API_BASE = os.getenv("PHONE_API_URL", "http://127.0.0.1:18080")
mcp = MCPServer("Virtual Phone", instructions="Virtual calendar and notes; timestamps require UTC offsets.")


async def request_api(method: str, path: str, *, params=None, body=None) -> dict:
    try:
        # 本地服务不应经过用户终端配置的 HTTP 代理。
        payload = params if params is not None else body
        print(f"[MCP Server → REST API] {method} {path}, "
              f"input={json.dumps(payload, ensure_ascii=False)}", flush=True)
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.request(method, API_BASE + path, params=params, json=body)
        print(f"[REST API → MCP Server] HTTP {response.status_code}, body={response.text}", flush=True)
        if response.status_code >= 500:
            raise ToolError(f"虚拟手机 API 返回 HTTP {response.status_code}")
        return response.json()
    except (httpx.RequestError, ValueError) as exc:
        raise ToolError("无法读取虚拟手机 API，请先启动 api_server.py") from exc


@mcp.tool()
async def get_calendar_events(start_time: str, end_time: str) -> dict:
    """查询虚拟手机日历中与时间段重叠的日程，时间必须带时区。"""
    return await request_api("GET", "/api/calendar/events", params={
        "start_time": start_time, "end_time": end_time,
    })


@mcp.tool()
async def create_calendar_event(title: str, start_time: str, end_time: str) -> dict:
    """创建虚拟日历事件；调用方应先取得写入授权。"""
    return await request_api("POST", "/api/calendar/events", body={
        "title": title, "start_time": start_time, "end_time": end_time,
    })


@mcp.tool()
async def search_notes(keyword: str) -> dict:
    """按关键词查找虚拟手机备忘录；空字符串表示列出全部。"""
    return await request_api("GET", "/api/notes", params={"keyword": keyword})


@mcp.tool()
async def create_note(title: str, content: str) -> dict:
    """创建虚拟手机备忘录；调用方应先取得写入授权。"""
    return await request_api("POST", "/api/notes", body={"title": title, "content": content})


if __name__ == "__main__":
    try:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=18081)
    except KeyboardInterrupt:
        pass
