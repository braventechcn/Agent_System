"""
虚拟手机的业务逻辑
Function Calling 与 REST/MCP 共用这一层
"""

from copy import deepcopy
from datetime import datetime, timedelta


SEED_EVENTS = [{
    "id": "event_001", "title": "产品评审会议",
    "start_time": "2026-11-09T10:30:00+08:00",
    "end_time": "2026-11-09T11:30:00+08:00",
}]
SEED_NOTES = [{
    "id": "note_001", "title": "项目待办",
    "content": "准备产品评审材料，并确认会议室。",
}]

FIELDS = {
    "get_calendar_events": {"start_time", "end_time"},
    "create_calendar_event": {"title", "start_time", "end_time"},
    "search_notes": {"keyword"},
    "create_note": {"title", "content"},
}
WRITE_TOOLS = {"create_calendar_event", "create_note"}


class PhoneError(Exception):
    """给调用方返回稳定的错误码，避免暴露内部异常。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_time(value: str) -> datetime:
    """
    解析 ISO 8601 时间字符串，要求带时区。
        - 例如: 2026-11-09T10:30:00+08:00
    """
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PhoneError("INVALID_TIME", "时间必须是带时区的 ISO 8601 格式") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise PhoneError("INVALID_TIME", "时间必须带时区，例如 +08:00")
    return result


def validate_range(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    """
    验证时间范围的有效性
    """
    start, end = parse_time(start_time), parse_time(end_time)
    if start >= end:
        raise PhoneError("INVALID_RANGE", "结束时间必须晚于开始时间")
    if end - start > timedelta(days=7):
        raise PhoneError("INVALID_RANGE", "一次查询或创建不能超过 7 天")
    return start, end


def overlaps(event: dict, start: datetime, end: datetime) -> bool:
    """
    检查事件是否与时间范围重叠
        - 使用半开区间 [start, end)，前一个事件刚结束不算冲突
    """
    return parse_time(event["start_time"]) < end and parse_time(event["end_time"]) > start


class PhoneStore:
    def __init__(self):
        self.events = deepcopy(SEED_EVENTS)
        self.notes = deepcopy(SEED_NOTES)
        self.next_event = 2
        self.next_note = 2

    def call(self, name: str, arguments: dict) -> dict:
        """所有入口统一进行工具白名单和参数校验。"""
        try:
            expected = FIELDS.get(name)
            if expected is None:
                raise PhoneError("TOOL_NOT_ALLOWED", f"未注册工具：{name}")
            if not isinstance(arguments, dict) or set(arguments) != expected:
                raise PhoneError("INVALID_ARGUMENTS", f"参数必须恰好包含：{', '.join(sorted(expected))}")
            if any(not isinstance(value, str) for value in arguments.values()):
                raise PhoneError("INVALID_ARGUMENTS", "所有参数必须是字符串")
            method = getattr(self, name)
            return {"ok": True, "data": method(**arguments)}
        except PhoneError as exc:
            return {"ok": False, "error": {"code": exc.code, "message": exc.message}}

    def get_calendar_events(self, start_time: str, end_time: str) -> dict:
        """获取日历事件"""
        start, end = validate_range(start_time, end_time)
        events = [deepcopy(event) for event in self.events if overlaps(event, start, end)]
        return {"count": len(events), "events": events}

    def create_calendar_event(self, title: str, start_time: str, end_time: str) -> dict:
        """创建日历事件"""
        title = title.strip()
        if not title:
            raise PhoneError("INVALID_ARGUMENTS", "日程标题不能为空")
        start, end = validate_range(start_time, end_time)
        if any(overlaps(event, start, end) for event in self.events):
            raise PhoneError("CALENDAR_CONFLICT", "该时段已有日程，未创建")
        event = {
            "id": f"event_{self.next_event:03d}", "title": title,
            "start_time": start_time, "end_time": end_time,
        }
        self.next_event += 1
        self.events.append(event)
        return {"event": deepcopy(event)}

    def search_notes(self, keyword: str) -> dict:
        """搜索备忘录"""
        keyword = keyword.strip().casefold()
        notes = [
            deepcopy(note) for note in self.notes
            if keyword in (note["title"] + " " + note["content"]).casefold()
        ]
        return {"count": len(notes), "notes": notes}

    def create_note(self, title: str, content: str) -> dict:
        """创建备忘录"""
        title, content = title.strip(), content.strip()
        if not title or not content:
            raise PhoneError("INVALID_ARGUMENTS", "备忘录标题和内容不能为空")
        note = {"id": f"note_{self.next_note:03d}", "title": title, "content": content}
        self.next_note += 1
        self.notes.append(note)
        return {"note": deepcopy(note)}
