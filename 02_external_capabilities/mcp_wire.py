"""不用 MCP SDK，直接发三次 JSON-RPC 请求，观察 MCP 的协议外形。"""

import argparse
import asyncio
import json

import httpx


# 本例固定使用 MCP Python SDK 2.x 支持的现代协议版本。
VERSION = "2026-07-28"
WINDOW = {
    "start_time": "2026-11-09T10:00:00+08:00",
    "end_time": "2026-11-09T11:00:00+08:00",
}


async def main():
    parser = argparse.ArgumentParser(description="观察 MCP 的原始 HTTP + JSON-RPC 消息")
    parser.add_argument("--url", default="http://127.0.0.1:18081/mcp")
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        async def send(request_id: int, method: str, parameters: dict | None = None) -> dict:
            # 现代 MCP 在每个请求里带协议版本与客户端能力；HTTP 头与正文要一致。
            params = dict(parameters or {})
            params["_meta"] = {
                "io.modelcontextprotocol/protocolVersion": VERSION,
                "io.modelcontextprotocol/clientInfo": {"name": "phone-wire-lab", "version": "1.0"},
                "io.modelcontextprotocol/clientCapabilities": {},
            }
            request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            headers = {
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": VERSION,
                "Mcp-Method": method,
            }
            if method == "tools/call":
                headers["Mcp-Name"] = params["name"]
            print(f"\n>>> HTTP POST {args.url}")
            print("MCP headers:", {key: value for key, value in headers.items() if key.startswith("MCP-") or key.startswith("Mcp-")})
            print("JSON-RPC request:", json.dumps(request, ensure_ascii=False, indent=2))
            response = await client.post(args.url, headers=headers, json=request)
            print("HTTP status:", response.status_code)
            # 本地示例默认返回 JSON；明确检查，避免把 SSE 当 JSON 解码。
            if "application/json" not in response.headers.get("content-type", ""):
                raise RuntimeError(f"预期 JSON 响应，实际得到 {response.headers.get('content-type')}")
            reply = response.json()
            print("JSON-RPC response:", json.dumps(reply, ensure_ascii=False, indent=2))
            if reply.get("id") != request_id:
                raise RuntimeError("响应 id 与请求 id 不一致")
            if "error" in reply:
                raise RuntimeError(f"MCP 错误：{reply['error']}")
            response.raise_for_status()
            return reply["result"]

        discovery = await send(1, "server/discover")
        if VERSION not in discovery.get("supportedVersions", []):
            raise RuntimeError(f"服务端不支持本实验固定的协议版本 {VERSION}")
        tools = await send(2, "tools/list")
        assert "get_calendar_events" in {tool["name"] for tool in tools["tools"]}
        await send(3, "tools/call", {"name": "get_calendar_events", "arguments": WINDOW})


if __name__ == "__main__":
    asyncio.run(main())
