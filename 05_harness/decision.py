"""
两种“做下一步决定”的实现；它们都不能直接修改日程

DemoDecider 让实验离线、可重复。LLMDecider 让真实模型根据当前观察提出候选动作
二者返回相同形状的字典；动作是否允许以及是否成功，由 harness.py 决定
"""

import json


# JSON Schema 用于验证模型输出的结构化动作
#   - action: schedule_focus | finish
#   - task_id: 任务 ID，若 action=finish 则为空字符串
#   - slot_id: 时段 ID，若 action=finish 则为空字符串
#   - reason: 简短的理由，供开发者阅读
DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["schedule_focus", "finish"]},
        "task_id": {"type": "string"},
        "slot_id": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["action", "task_id", "slot_id", "reason"],
    "additionalProperties": False,
}


class DemoDecider:
    """
    按截止日期、重要程度和依赖关系选择下一块专注时间
    """

    def decide(self, observation: dict) -> dict:
        """只读取当前快照；即使返回 schedule_focus，也尚未安排时段。"""
        day = observation["day"]
        assignments = observation["assignments"]
        tasks = {task["id"]: task for task in day["tasks"]}
        occupied = {slot["id"] for slot in day["slots"] if slot["busy"]}
        occupied.update(item["slot_id"] for item in assignments)
        available = [slot["id"] for slot in day["slots"] if slot["id"] not in occupied]

        # 同一天截止的任务优先安排高优先级；已完成的任务不再占用新时段。
        ordered = sorted(day["tasks"], key=lambda task: (task["deadline"], -task["priority"], task["id"]))
        for task in ordered:
            done = sum(item["task_id"] == task["id"] for item in assignments)
            if done >= task["blocks"]:
                continue
            # 依赖先完成，且当前时段必须晚于依赖任务的最后一个专注块。
            if any(sum(item["task_id"] == dep for item in assignments) < tasks[dep]["blocks"]
                   for dep in task["depends_on"]):
                continue
            latest_dependency = max((item["slot_id"] for item in assignments
                                     if item["task_id"] in task["depends_on"]), default="")
            slot_id = next((slot for slot in available if slot > latest_dependency), None)
            if slot_id:
                return {"action": "schedule_focus", "task_id": task["id"], "slot_id": slot_id,
                        "reason": f"{task['deadline']} 截止；优先级 {task['priority']}；依赖已满足"}

        # 没有合法时段时终止，Harness 会独立判断目标是否全部完成。
        return {"action": "finish", "task_id": "", "slot_id": "",
                "reason": "没有更多可以合法安排的专注块"}


class LLMDecider:
    """通过 Responses API 请模型决定下一步，但不把业务函数交给模型执行。"""

    def __init__(self, model: str):
        # 只在真实模型模式导入 SDK；离线实验不需要安装 openai。
        from openai import OpenAI

        self.client = OpenAI()
        self.model = model

    def decide(self, observation: dict) -> dict:
        """一次 API 请求产生一个结构化候选动作，随后仍需 Harness 校验。"""
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "You manage one day of focused work for an AI engineer and graduate student. "
                "Choose exactly one next action from schedule_focus or finish. "
                "Prefer earlier deadlines and higher priority. Schedule every required block, "
                "respect busy slots and task dependencies, and place dependencies earlier. "
                "A proposed action has not executed yet; the runtime will validate it. "
                "If the last result contains verification errors, fix them before finishing. "
                "If no legal action remains, choose finish. Keep the reason brief."
            ),
            input=json.dumps(observation, ensure_ascii=False),
            text={"format": {"type": "json_schema", "name": "next_action",
                             "strict": True, "schema": DECISION_SCHEMA}},
        )
        if response.status != "completed" or not response.output_text:
            raise RuntimeError(f"模型没有返回可用决策：{response.status}")
        return json.loads(response.output_text)
