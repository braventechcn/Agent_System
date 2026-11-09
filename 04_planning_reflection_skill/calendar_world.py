"""虚拟日历环境：保存任务状态，并为 Agent 提供可执行的日历工具。

规划器只能根据观察到的状态提出方案；会议和提醒是否真的创建成功，
由本模块的方法执行并返回结果。所有数据只保存在当前 Python 进程内。
"""

from dataclasses import dataclass, field


# 固定候选时段，使离线对照实验的初始条件和结果可重复。
SLOTS = ("10:00", "10:30", "11:00", "11:30")


@dataclass
class CalendarWorld:
    """管理虚拟日历的忙碌时段、会议记录和一次性故障。

    每次 run() 都新建一个实例，因此不同命令不会共享日历状态。
    """

    # 10:00 预先被占用；规划器应从其余候选时段中选择。
    busy: set[str] = field(default_factory=lambda: {"10:00"})
    # 会议 ID 映射到实际保存的会议内容；提醒也保存在对应会议中。
    meetings: dict[str, dict] = field(default_factory=dict)
    # 为 True 时，第一次设置提醒会失败一次，之后可正常重试。
    reminder_fails_once: bool = True
    # 创建会议时递增，方便观察是否错误地创建了重复会议。
    next_id: int = 1

    def list_events(self) -> dict:
        """读取最新日历，供初始规划、反思和重新规划使用。

        Returns:
            dict: 已占用时段，以及当前保存的会议列表。
        """
        return {"busy_slots": sorted(self.busy), "meetings": list(self.meetings.values())}

    def inject_conflict(self, slot: str) -> None:
        """在执行前占用计划选中的时段，模拟环境状态变化。

        Args:
            slot: 刚才规划器选中的候选时段。
        """
        # 这是实验环境主动制造的变化，不是模型请求的日历工具调用。
        self.busy.add(slot)

    def create_meeting(self, slot: str, title: str) -> dict:
        """尝试创建会议，执行时重新检查候选时段是否仍可用。

        Args:
            slot: 计划选中的时段。
            title: 要保存的会议标题。

        Returns:
            dict: 成功时包含 meeting_id 和 slot；失败时包含错误码。
        """
        # 模型输出的时段只是一项建议，环境仍须拒绝非法或已占用的时段。
        if slot not in SLOTS:
            return {"error": "INVALID_SLOT", "slot": slot}
        if slot in self.busy:
            return {"error": "SLOT_CONFLICT", "slot": slot}

        # 先创建无提醒的会议；提醒是后续独立工具操作。
        meeting_id = f"meeting-{self.next_id}"
        self.next_id += 1
        meeting = {"id": meeting_id, "title": title, "slot": slot, "reminder_minutes": None}
        self.meetings[meeting_id] = meeting
        self.busy.add(slot)
        return {"meeting_id": meeting_id, "slot": slot}

    def set_reminder(self, meeting_id: str, minutes: int) -> dict:
        """为已经创建的会议设置提醒，并模拟一次暂时故障。

        Args:
            meeting_id: create_meeting() 返回的会议 ID。
            minutes: 提前提醒的分钟数，本实验要求为 30。

        Returns:
            dict: 成功时包含提醒分钟数；失败时包含错误码。
        """
        # 工具参数必须指向真实存在的会议，并满足任务中的 30 分钟约束。
        if meeting_id not in self.meetings:
            return {"error": "UNKNOWN_MEETING"}
        if minutes != 30:
            return {"error": "INVALID_REMINDER"}

        # 故障只影响提醒：已经创建的会议仍留在日历中，不能重复创建。
        if self.reminder_fails_once:
            self.reminder_fails_once = False
            return {"error": "TEMPORARY_REMINDER_FAILURE", "meeting_id": meeting_id}
        self.meetings[meeting_id]["reminder_minutes"] = minutes
        return {"meeting_id": meeting_id, "reminder_minutes": minutes}

    def verify(self, meeting_id: str, slot: str) -> dict:
        """读取最终状态，检查会议时段与提醒是否同时满足目标。

        Args:
            meeting_id: 要核验的会议 ID。
            slot: 当前计划选定的时段。

        Returns:
            dict: passed 表示任务是否完成，meeting 是实际保存的数据。
        """
        meeting = self.meetings.get(meeting_id)
        # 创建会议成功但提醒仍为空时，整体任务尚未完成。
        passed = bool(
            meeting
            and meeting["slot"] == slot
            and meeting["reminder_minutes"] == 30
        )
        return {"passed": passed, "meeting": meeting}
