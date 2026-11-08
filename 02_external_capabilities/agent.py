"""
同一个 LLM Agent Loop 对比本地函数、直接 REST API 与 MCP 三种工具接入方式

实现三个 Backend 作为 Agent Runtime 的工具接入后端
    - DirectBackend 直接调用本地 Python 工具实现
    - RESTBackend 直接请求虚拟手机 REST API
    - MCPBackend 通过 MCP Client 发现并调用 MCP Server 暴露的工具

三个 Backend 向上层提供统一的 tools() 和 call() 接口，实现模型决策逻辑与工具连接方式的解耦
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
import httpx
from openai import AsyncOpenAI, OpenAIError

from phone_core import FIELDS, WRITE_TOOLS, PhoneStore
from tool_contracts import TOOLS


INSTRUCTIONS = (
    "你是虚拟手机助手，当前日期为 2026-11-08，时区为 Asia/Shanghai。"
    "只能根据工具结果报告日历和备忘录状态；时间参数使用带 +08:00 的 ISO 8601 格式。"
    "如果用户要求写入，可以请求创建工具；是否真正执行由运行程序的执行端决定。"
    "工具返回错误时说明失败，不要声称已经完成。请用中文回答。"
)
DEFAULT_MESSAGE = "查询 2026 年 11 月 9 日上午 10 点到 11 点的日程，并查找包含“评审”的备忘录。"
MAX_ROUNDS = 6


class DirectBackend:
    """直接工具调用后端：通过 Python 函数执行虚拟手机操作

    - 工具定义(Tool Definition)来自本地 TOOLS
    - 工具执行(Tool Execution)委托给 PhoneStore
    - 不经过 MCP Client / Server (适合单进程内的工具集成)"""

    execution_label = "PhoneStore"

    def __init__(self):
        # 为当前 Backend 创建独立的虚拟手机数据实例
        self.store = PhoneStore()

    async def tools(self):
        """返回预先定义的工具契约，供 LLM 选择工具并生成参数

        - 使用 async def 是为了与 MCPBackend 保持统一的异步接口
        - 此方法本身不执行异步 I/O

        Returns:
            list: 工具契约列表
        """
        return TOOLS  # 直接返回本地定义的工具契约列表

    async def call(self, name: str, arguments: dict) -> dict:
        """通过本地 PhoneStore 执行指定工具并返回业务结果

        Args:
            name: 工具名称，例如 get_calendar_events
            arguments: 已解析的工具参数字典

        Returns:
            dict: PhoneStore 返回的业务执行结果
        """
         # 直接调用同步方法；不会发起 MCP 协议请求
        return self.store.call(name, arguments)


class RESTBackend:
    """REST 工具调用后端：把 Function Call 映射为虚拟手机 HTTP 请求

    - 工具定义仍来自本地 TOOLS，REST API 不会自动变成模型工具
    - 工具执行通过明确的 HTTP 方法与路径映射完成，不接受模型指定任意 URL
    - 与 MCPBackend 共用同一个 REST API 服务端数据实例
    """

    execution_label = "REST API"
    # 工具名到 HTTP 接口的映射属于执行端配置，而不是模型生成的参数。
    ROUTES = {
        "get_calendar_events": ("GET", "/api/calendar/events"),
        "create_calendar_event": ("POST", "/api/calendar/events"),
        "search_notes": ("GET", "/api/notes"),
        "create_note": ("POST", "/api/notes"),
    }

    def __init__(self, base_url: str, *, trace: bool = False):
        # base_url 指向 REST API 服务，不包含具体工具路径。
        self.base_url = base_url.rstrip("/")
        self.trace = trace

    async def tools(self):
        """返回本地维护的 Function Tool Schema，供模型决定调用哪个工具。"""
        return TOOLS

    async def call(self, name: str, arguments: dict) -> dict:
        """将工具请求转换为 HTTP 请求，并返回 REST API 的业务结果。"""
        # 再次检查映射，确保 Backend 不能被用来请求未登记的路径。
        if name not in self.ROUTES:
            return {"ok": False, "error": {
                "code": "TOOL_NOT_ALLOWED", "message": "未注册的 REST 工具",
            }}
        method, path = self.ROUTES[name]
        if self.trace:
            print(f"[REST Client] {method} {self.base_url + path}, "
                  f"arguments={json.dumps(arguments, ensure_ascii=False)}")

        # GET 参数放在 URL 查询串，POST 参数放在 JSON 请求体；httpx 负责 URL 编码。
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.request(
                method, self.base_url + path,
                params=arguments if method == "GET" else None,
                json=arguments if method == "POST" else None,
            )
        if self.trace:
            print(f"[REST Client] HTTP {response.status_code}, body={response.text}")

        # 409、422 可能包含 PhoneStore 的业务错误，应让模型看到具体错误码。
        # 服务器故障或非 JSON 响应则由上层 Agent Loop 转为 BACKEND_ERROR。
        if response.status_code >= 500:
            response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or "ok" not in result:
            raise ValueError("REST API did not return a PhoneStore result")
        return result


class MCPBackend:
    """MCP 工具调用后端：通过 MCP Client 访问 MCP Server

    - 工具定义通过 MCP tools/list 动态发现
    - 工具执行通过 MCP tools/call 请求服务端完成

    对 Agent Runtime 暴露与 DirectBackend 一致的接口，使上层 Agent Loop 不必关心工具的具体接入方式
    """
    execution_label = "MCP Client"
    def __init__(self, client, *, trace: bool = False):
        # 保存已建立连接的 MCP Client, Client 的连接生命周期由上层 async with 管理
        self.client = client
        # 是否输出协议调用和结果解析过程的调试信息
        self.trace = trace


    async def tools(self):
        """发现 MCP 工具，并转换为模型 API 所需的工具定义

        Returns:
            list[dict]: 经过白名单筛选的 Function Tool 定义

        Raises:
            RuntimeError: MCP Server 未提供预期的全部工具
        """
        if self.trace:
            print("[MCP Client] list_tools() --> MCP tools/list")

        # 通过 MCP 协议请求服务端工具列表
        #   - await 在等待响应时允许事件循环调度其他任务
        result = await self.client.list_tools()
        # MCP 返回的 Tool 元数据不能直接假定为模型 API 格式
        #   - 将 MCP 的 name、description、input_schema 映射为 OpenAI Responses API 所需的 Function Tool 结构
        #   - 同时通过 FIELDS 限制允许暴露给模型的工具范围
        tools = [
            {
                "type": "function",
                "name": item.name,
                "description": item.description or item.name,
                "parameters": item.input_schema,
            }
            for item in result.tools if item.name in FIELDS
        ]
        # 检查服务端是否提供了当前 Agent 预期使用的全部工具
        #   - FIELDS 在本项目中承担预期工具名称集合的作用
        missing = set(FIELDS) - {item["name"] for item in tools}
        if missing:
            raise RuntimeError(f"MCP Server missing tools: {', '.join(sorted(missing))}")
        if self.trace:
            print("[MCP Client] discovered:", ", ".join(item["name"] for item in tools))
        return tools

    async def call(self, name: str, arguments: dict) -> dict:
        """通过 MCP Server 执行工具，并统一返回结果格式

        Args:
            name: MCP 工具名称
            arguments: 工具输入参数字典

        Returns:
            dict: 成功时返回结构化业务数据；工具执行失败或结果不可解析时返回错误对象

        Notes:
            - MCP 工具级错误通过 is_error 识别
            - 网络异常、协议异常等可能由 MCP Client 抛出，交由上层 Agent Runtime 捕获
        """
        if self.trace:
            print(f"[MCP Client] call_tool() → MCP tools/call: {name}({json.dumps(arguments, ensure_ascii=False)})")

        # 发起 MCP 工具调用请求。
        #   - MCP Server 负责实际执行工具，可能进一步访问 REST API、数据库、SDK 或本地函数
        result = await self.client.call_tool(name, arguments)

        if self.trace:
            # 仅用于日志：判断结果优先来自结构化字段还是内容块
            source = "structured_content" if result.structured_content is not None else "content"
            print(f"[MCP Client] tools/call returned: is_error={result.is_error}, payload={source}")

        # 处理 MCP 工具级执行错误
        #   - is_error 表示工具报告了执行错误，不等同于 HTTP 状态码或 JSON-RPC 协议错误
        if result.is_error:
            return {"ok": False, "error": {
                "code": "MCP_TOOL_ERROR", "message": "MCP Tool execution failed; check MCP Server logs for details.",
            }}

        # 优先读取结构化结果
        #   - structured_content 适合直接传递 JSON 结构化业务数据
        if result.structured_content is not None:
            return result.structured_content

        # 兼容文本内容块
        #   - 部分 MCP 工具会将 JSON 数据序列化为文本返回，因此尝试将 text content 解析为 Python 对象
        #   - 这个 SDK 版本会把返回的 dict 放入 text content；按 JSON 解析
        for block in result.content:
            if block.type == "text":
                try:
                    # 直接将文本块解析为 JSON 对象并返回
                    #   - 如果文本不是合法 JSON，则跳过并继续检查下一个文本块
                    return json.loads(block.text)
                except json.JSONDecodeError:
                    break

        # 未获得可解析的 JSON 结果，返回统一错误对象
        #   - 避免上层 Agent 将无法解析的响应误判为执行成功
        return {"ok": False, "error": {
            "code": "MCP_INVALID_RESULT",
            "message": "MCP Tool returned unparseable result; expected JSON object in structured_content or text content.",
        }}


def history_types(history: list) -> list[str]:
    """
    将模型对话历史中的每一项转换为类型字符串列表，便于调试输出
    """
    return [item.get("type", item.get("role")) if isinstance(item, dict) else item.type
            for item in history]


async def run_agent(backend, model: str, message: str, *, allow_write: bool, confirm_write: bool, trace: bool):
    """运行基于 Function Calling 的多轮 LLM Agent Loop

    Agent 根据模型生成的 Function Call 调用工具，并将执行结果回填给模型，直到生成最终回答或达到最大轮次

    Args:
        backend: 工具接入后端，支持 DirectBackend、RESTBackend 或 MCPBackend
        model: 使用的 LLM 模型名称
        message: 用户输入的自然语言任务
        allow_write: 是否允许虚拟手机数据写入
        confirm_write: 是否确认本次写入授权
        trace: 是否输出详细运行日志

    Returns:
        dict: 模型 API 请求次数、工具请求次数和后端调用次数
    """

    # ==========================================================
    # Step 1：初始化工具、执行策略和对话上下文
    # ==========================================================

    # 获取工具定义：
    #   - DirectBackend 返回本地预定义的 Tool Schema
    #   - RESTBackend 同样使用本地 Tool Schema，但通过 HTTP 执行
    #   - MCPBackend 通过 MCP tools/list 发现并转换工具定义
    tools = await backend.tools()

    # 将写入授权状态告知 LLM，辅助模型决策
    #   - 注意：Prompt 中的授权说明不是安全边界，实际执行前仍需由 Python 代码检查写入权限
    write_status = ("This command has been authorized for virtual writing."
        if allow_write and confirm_write
        else "This command has not been authorized for virtual writing."
    )

    if trace:
        print("Available tools:", ", ".join(tool["name"] for tool in tools))

    # 保存对话上下文，包括用户消息、模型输出及工具执行结果
    #   - 后续每轮模型请求都会携带更新后的 history
    history = [{"role": "user", "content": message}]

    # 记录模型 API 请求、Function Call 请求及实际后端调用次数
    counts = {"model_api": 0, "tool_requests": 0, "tool_executions": 0}

    # 创建异步 OpenAI 客户端，用于向模型服务发起请求
    client = AsyncOpenAI()
    try:
        # ======================================================
        # Step 2：启动 Agent Loop，向 LLM 发起推理请求
        # ======================================================

        # 每轮循环对应一次 Responses API 请求，MAX_ROUNDS 限制模型调用轮次，避免无限工具调用循环
        for round_number in range(1, MAX_ROUNDS + 1):
            counts["model_api"] += 1
            if trace:
                print(f"[Round {round_number}] Responses API request: model={model}, "
                      f"input_types={history_types(history)}, tool_choice=auto, parallel_tool_calls=False")

            # 向 LLM 提供系统指令、工具定义及完整对话上下文，模型可以生成最终回答，也可以产生 Function Call
            #   - tool_choice="auto"：允许模型自主决定是否调用工具
            #   - parallel_tool_calls=False：禁用并行工具调用
            response = await client.responses.create(
                model=model,
                instructions=INSTRUCTIONS + write_status,
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=False,
                input=history,
            )
            if trace:
                print(f"[Round {round_number}] Responses API returned: status={response.status}, "
                      f"output_types={[item.type for item in response.output]}, "
                      f"output_text={response.output_text or '(none)'}")
            # 仅处理已完成的模型响应
            #   - 未完成时终止当前 Agent Loop，避免处理不完整输出
            if response.status != "completed":
                print(f"Model response status: {response.status}; no complete answer was returned.")
                return counts

            # ==================================================
            # Step 3：保存模型输出，并判断是否需要调用工具
            # ==================================================

            # 原样保留模型输出，包括工具请求(Function Call)、消息与可能的 reasoning 项供后续模型请求使用
            history.extend(response.output)
            if trace:
                print(f"[Round {round_number}] Saved model output: history_items={len(history)}")

            # 从模型输出中提取 Function Call
            #   - Function Call 仅代表调用请求，工具尚未真正执行
            calls = [
                item for item in response.output
                if item.type == "function_call"
            ]
            # 没有 Function Call，说明本轮不需要执行工具
            #   - 当前实现将其视为 Agent Loop 的终止条件
            if not calls:
                print("Final answer:", response.output_text or "(none)")
                return counts

            # ==================================================
            # Step 4：解析 Function Call，并进行执行前校验
            # ==================================================

            # 遍历模型产生的工具调用请求
            for call in calls:
                counts["tool_requests"] += 1
                if trace:
                    print(f"[Round {round_number}] function_call: name={call.name}, "
                          f"arguments={call.arguments}, call_id={call.call_id}")
                # arguments 在 Responses API 中是 JSON 字符串，需要解析为 Python 字典后才能传递给工具
                try:
                    arguments = json.loads(call.arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError("Function Call arguments must be a JSON object")
                except (ValueError, TypeError):
                    # 参数无法解析时不执行工具，而是构造错误结果
                    result = {"ok": False, "error": {
                        "code": "INVALID_JSON", "message": "Function Call arguments must be a valid JSON object",
                    }}
                    if trace:
                        print(f"[Round {round_number}] Python rejected request: invalid JSON arguments")
                else:  # try 中没有抛出异常：继续检查工具名和权限
                    # 校验一：工具名称必须处于执行端白名单中
                    #   - 不信任模型自行生成的工具名称
                    if call.name not in FIELDS:
                        result = {"ok": False, "error": {
                            "code": "TOOL_NOT_ALLOWED", "message": "unregistered tool: " + call.name,
                        }}
                        if trace:
                            print(f"[Round {round_number}] Python rejected request: tool not allowed")
                    # 校验二：写操作必须同时满足允许和确认条件
                    #   - 即使 LLM 请求创建日历或备忘录，未授权时也不能执行写入操作
                    elif call.name in WRITE_TOOLS and not (allow_write and confirm_write):
                        result = {"ok": False, "error": {
                            "code": "WRITE_NOT_AUTHORIZED", "message": "write operations require --allow-write and --confirm-write",
                        }}
                        if trace:
                            print(f"[Round {round_number}] Python rejected request: write not authorized")
                    else:
                        # ======================================
                        # Step 5：通过 Backend 执行实际工具调用
                        # ======================================
                        try:
                            if trace:
                                print(f"[Round {round_number}] Python executes via {backend.execution_label}")
                            # 统一工具调用接口：
                            #   - DirectBackend：执行本地 PhoneStore 函数
                            #   - RESTBackend：向 REST API 发送 HTTP 请求
                            #   - MCPBackend：通过 MCP tools/call 调用服务端
                            # await 等待后端返回实际执行结果
                            result = await backend.call(call.name, arguments)
                            # 统计正常返回的后端调用
                            #   - 注意：正常返回不代表业务执行一定成功
                            counts["tool_executions"] += 1
                        except Exception as exc:
                            # 捕获后端调用异常，转换为结构化错误结果，不直接将 Python 异常作为最终用户回答
                            result = {"ok": False, "error": {
                                "code": "BACKEND_ERROR", "message": type(exc).__name__,
                            }}
                            if trace:
                                print(f"[Round {round_number}] Python backend raised {type(exc).__name__}")
                if trace:
                    print(f"[Round {round_number}] Python result: {json.dumps(result, ensure_ascii=False)}")

                # ==================================================
                # Step 6：构造 Function Call Output 并回填上下文
                # ==================================================

                # 将执行结果转换为 Responses API 的工具输出项
                #   - call_id 必须与模型原始 Function Call 的 ID 对应，以便模型服务关联调用请求与执行结果
                feedback = {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
                # 将工具结果加入历史上下文
                #   - 下一轮模型请求会携带该结果，形成反馈闭环
                history.append(feedback)
                if trace:
                    print(f"[Round {round_number}] function_call_output: call_id={feedback['call_id']}, "
                          f"output={feedback['output']}")
                    print(f"[Round {round_number}] Saved tool feedback: history_items={len(history)}")
        print(f"Reached {MAX_ROUNDS} model rounds without a final answer.")
        return counts
    finally:
        # 无论正常返回还是发生异常，都释放 OpenAI 客户端资源
        await client.close()


# 将 main() 定义为协程函数（Coroutine Function），以便在其中使用 await 调用异步方法
async def main():
    # 使用 argparse 解析命令行参数，设置默认值和帮助信息
    parser = argparse.ArgumentParser(description="Virtual Phone Agent")
    parser.add_argument("--backend", choices=("direct", "rest", "mcp"), default="direct") # 选择本地函数、REST API 或 MCP 工具接入方式
    parser.add_argument("--message", default=DEFAULT_MESSAGE)   # 用户输入的消息，作为模型的初始指令
    parser.add_argument("--api-url", default="http://127.0.0.1:18080") # REST API 服务地址，仅用于 rest 后端
    parser.add_argument("--mcp-url", default="http://127.0.0.1:18081/mcp") # MCP Server 的 URL，默认指向本地
    parser.add_argument("--allow-write", action="store_true", help="授权修改虚拟手机数据")      # 允许模型执行写入操作的标志（用于权限控制）
    parser.add_argument("--confirm-write", action="store_true", help="确认本次命令允许写入")    # 确认本次命令允许写入的标志（用于权限控制）
    parser.add_argument("--trace", action="store_true")     # 启用详细调试输出，显示模型调用、工具请求和执行的详细信息
    args = parser.parse_args()

    # 加载环境变量，确保 OPENAI_MODEL 和 OPENAI_API_KEY 已设置
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
    model = os.getenv("OPENAI_MODEL")
    if not model or not os.getenv("OPENAI_API_KEY"):
        parser.error("Please set OPENAI_MODEL and OPENAI_API_KEY in the '.env' file.")

    print(f"Backend: {args.backend}; Message: {args.message}")
    # 记录整次运行耗时：包含模型 API、工具执行和网络等待，仅供观察。
    started_at = time.perf_counter()
    try:
        if args.backend == "direct":
            counts = await run_agent(
                DirectBackend(), model, args.message,
                allow_write=args.allow_write, confirm_write=args.confirm_write, trace=args.trace,
            )
        elif args.backend == "rest":
            counts = await run_agent(
                RESTBackend(args.api_url, trace=args.trace), model, args.message,
                allow_write=args.allow_write, confirm_write=args.confirm_write, trace=args.trace,
            )
        else:
            from mcp import Client

            async with Client(args.mcp_url) as mcp_client:
                if args.trace:
                    print(f"[MCP Client] Connected: Protocol_version={mcp_client.protocol_version}")
                counts = await run_agent(
                    MCPBackend(mcp_client, trace=args.trace), model, args.message,
                    allow_write=args.allow_write, confirm_write=args.confirm_write, trace=args.trace,
                )
        print("Call counts:", counts)
        print(f"Elapsed time: {time.perf_counter() - started_at:.2f}s")
    except OpenAIError as exc:
        parser.exit(1, f"OpenAI API request failed: {exc}\n")


if __name__ == "__main__":
    # 创建 'main()' 协程对象并使用 'asyncio.run()' 管理事件循环 ，运行顶层协程直到完成
    asyncio.run(main())
