"""向模型公开的 Function Calling 工具契约。"""


def tool(name: str, description: str, fields: dict[str, str]) -> dict:
    return {
        "type": "function", "name": name, "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {key: {"type": "string", "description": value} for key, value in fields.items()},
            "required": list(fields),
            "additionalProperties": False,
        },
    }


TOOLS = [
    tool("get_calendar_events", "查询虚拟手机日历中与时间段重叠的日程。", {
        "start_time": "带时区的 ISO 8601 开始时间，例如 2026-11-09T10:00:00+08:00",
        "end_time": "带时区的 ISO 8601 结束时间",
    }),
    tool("create_calendar_event", "在虚拟手机日历中创建日程；执行端会检查写入授权和时间冲突。", {
        "title": "非空日程标题",
        "start_time": "带时区的 ISO 8601 开始时间",
        "end_time": "带时区的 ISO 8601 结束时间",
    }),
    tool("search_notes", "按关键词查找虚拟手机备忘录；空字符串表示列出全部。", {
        "keyword": "要查找的关键词，或空字符串",
    }),
    tool("create_note", "在虚拟手机中创建备忘录；执行端会检查写入授权。", {
        "title": "非空备忘录标题",
        "content": "非空备忘录内容",
    }),
]
