"""每日专注规划师的业务环境：读取待办，检查安排，并生成可执行的日程。

这个文件不知道 LLM 或 Harness 的运行轮次。它只处理“某任务能否放进某时段”
这样的业务事实。Harness 会调用这里的函数，并把执行结果反馈给 Agent。
"""

import json
from copy import deepcopy
from pathlib import Path


def load_day(path: Path) -> dict:
    """读取用户可编辑的 JSON，并检查实验运行所需的基本结构。"""
    day = json.loads(path.read_text(encoding="utf-8"))
    slots = day["slots"]
    tasks = day["tasks"]
    slot_ids = [slot["id"] for slot in slots]
    task_ids = [task["id"] for task in tasks]

    if not slots or not tasks:
        raise ValueError("时段和任务都不能为空")
    if len(slot_ids) != len(set(slot_ids)):
        raise ValueError("时段 ID 不能重复")
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("任务 ID 不能重复")
    if slot_ids != sorted(slot_ids):
        raise ValueError("时段必须按时间先后排序")
    for task in tasks:
        if not isinstance(task["blocks"], int) or task["blocks"] < 1:
            raise ValueError(f"任务 {task['id']} 的 blocks 必须是正整数")
        if not 1 <= task["priority"] <= 5:
            raise ValueError(f"任务 {task['id']} 的 priority 必须在 1 到 5 之间")
        if any(dep not in task_ids or dep == task["id"] for dep in task["depends_on"]):
            raise ValueError(f"任务 {task['id']} 存在无效依赖")
    return day


def observe(day: dict, assignments: list[dict], last_result: dict | None) -> dict:
    """构造 Agent 本轮看到的快照；快照不允许直接修改真实状态。"""
    # 深拷贝隔离决策器：它即使误改 observation，也不会直接写进 Harness 的状态。
    return deepcopy({"day": day, "assignments": assignments, "last_result": last_result})


def schedule_focus(day: dict, assignments: list[dict], task_id: str, slot_id: str) -> dict:
    """执行一次安排；任何约束不满足时返回错误，绝不写入半成品。"""
    tasks = {task["id"]: task for task in day["tasks"]}
    slots = {slot["id"]: slot for slot in day["slots"]}
    task = tasks.get(task_id)
    slot = slots.get(slot_id)
    if task is None or slot is None:
        return {"error": "UNKNOWN_ID", "detail": "任务或时段不存在"}
    # 同一操作重复送达时返回原有结果，不再新增一条安排。这是本地幂等示范。
    if any(item["task_id"] == task_id and item["slot_id"] == slot_id
           for item in assignments):
        return {"ok": True, "task_id": task_id, "slot_id": slot_id, "already_applied": True}
    if slot["busy"] or any(item["slot_id"] == slot_id for item in assignments):
        return {"error": "SLOT_BUSY", "detail": f"{slot_id} 已被占用"}
    if sum(item["task_id"] == task_id for item in assignments) >= task["blocks"]:
        return {"error": "TASK_FULL", "detail": f"{task_id} 已安排足够的专注块"}

    # 依赖任务要先全部安排，而且其最后一个时段必须早于当前时段。
    for dependency in task["depends_on"]:
        needed = tasks[dependency]["blocks"]
        earlier = sum(item["task_id"] == dependency and item["slot_id"] < slot_id
                      for item in assignments)
        if earlier < needed:
            return {"error": "DEPENDENCY_NOT_READY", "detail": f"请先完成 {dependency} 的安排"}

    assignments.append({"task_id": task_id, "slot_id": slot_id})
    return {"ok": True, "task_id": task_id, "slot_id": slot_id}


def verify(day: dict, assignments: list[dict]) -> dict:
    """独立检查最终状态；Agent 声称完成，不等于业务目标真的完成。"""
    errors = []
    if len({item["slot_id"] for item in assignments}) != len(assignments):
        errors.append("同一时段被安排多次")
    for task in day["tasks"]:
        count = sum(item["task_id"] == task["id"] for item in assignments)
        if count != task["blocks"]:
            errors.append(f"{task['id']} 需要 {task['blocks']} 块，目前安排 {count} 块")
    # 用同一业务函数重放安排，检查占用和前置依赖；重放状态不影响真实结果。
    replay = []
    for item in sorted(assignments, key=lambda row: row["slot_id"]):
        result = schedule_focus(day, replay, item["task_id"], item["slot_id"])
        if "error" in result:
            errors.append(f"{item['slot_id']}：{result['error']}")
    return {"success": not errors, "errors": errors,
            "scheduled_blocks": len(assignments),
            "required_blocks": sum(task["blocks"] for task in day["tasks"])}


def make_brief(day: dict, assignments: list[dict], status: str, verification: dict) -> str:
    """生成真正能带去学习或工作的 Markdown 专注清单。"""
    tasks = {task["id"]: task for task in day["tasks"]}
    booked = {item["slot_id"]: item["task_id"] for item in assignments}
    lines = [f"# {day['day']} · 每日专注规划师", "", day["theme"], "",
             f"运行状态：**{status}**；已安排 {verification['scheduled_blocks']}/"
             f"{verification['required_blocks']} 个专注块。", "", "## 今日时间线", ""]
    for slot in day["slots"]:
        if slot["busy"]:
            line = f"- **{slot['label']}**  🔒 {slot.get('event', '已有安排')}"
        elif slot["id"] in booked:
            line = f"- [ ] **{slot['label']}**  {tasks[booked[slot['id']]]['title']}"
        else:
            line = f"- **{slot['label']}**  — 留白 / 机动"
        lines.append(line)
    lines.extend(["", "## 截止日期与进度", ""])
    for task in day["tasks"]:
        count = sum(item["task_id"] == task["id"] for item in assignments)
        lines.append(f"- **{task['deadline']}** · {task['title']}：{count}/{task['blocks']} 块")
    if verification["errors"]:
        lines.extend(["", "## 尚需处理", ""])
        lines.extend(f"- {error}" for error in verification["errors"])
    lines.extend(["", "## 收工前复盘", "", "- 今天完成了什么？", "- 哪个阻塞需要向导师或团队同步？", "- 明天最重要的第一步是什么？", ""])
    return "\n".join(lines)
