"""用虚拟会议安排任务展示 Planning、Reflection 与 Skill 如何协作。

决策器负责提出计划或修正建议；Python 负责检查建议、调用日历工具、
读取执行结果和验证目标。demo 与 llm 两种决策器共用同一段执行流程。
"""

import argparse
import json
import os
from pathlib import Path

from calendar_world import CalendarWorld, SLOTS


# 实验目录和 Skill 文件位置；使用绝对路径避免受运行命令的当前目录影响。
ROOT = Path(__file__).resolve().parent
SKILL_PATH = ROOT / "skills" / "schedule-meeting" / "SKILL.md"

# 固定任务及其执行顺序，便于比较不同决策方式在同一场景中的表现。
GOAL = "Schedule a 30-minute technical discussion on 2030-05-20, avoid conflicts, and remind me 30 minutes beforehand."
TITLE = "Technical discussion"
PLAN_STEPS = ["create_meeting", "set_reminder", "verify"]

# 规划输出必须有候选时段、步骤和理由，但 Schema 不知道此刻日历是否已变化。
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "slot": {"type": "string", "enum": list(SLOTS)},
        "steps": {"type": "array", "items": {"type": "string", "enum": PLAN_STEPS}},
        "reason": {"type": "string"},
    },
    "required": ["slot", "steps", "reason"],
    "additionalProperties": False,
}
# 反思输出包含失败诊断和下一步建议；允许的建议限定为三种。
REFLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnosis": {"type": "string"},
        "correction": {"type": "string", "enum": ["replan", "retry_reminder", "stop"]},
    },
    "required": ["diagnosis", "correction"],
    "additionalProperties": False,
}


def load_skill(goal: str, enabled: bool, emit) -> str:
    """发现 Skill 元数据，并在任务匹配时向决策器提供正文。

    Args:
        goal: 当前自然语言任务，用来判断是否与会议安排有关。
        enabled: 用户是否通过 --skill on 启用该 Skill。
        emit: 输出实验轨迹的回调函数。

    Returns:
        str: 匹配时返回 Skill 正文；未启用或不匹配时返回空字符串。
    """
    # 文件头部的 name/description 用于发现；正文是任务匹配后才提供给决策器的指导。
    raw = SKILL_PATH.read_text(encoding="utf-8")
    _, frontmatter, body = raw.split("---", 2)
    metadata = dict(line.split(": ", 1) for line in frontmatter.strip().splitlines())
    emit("Skill discovery", metadata)

    # --skill off 可用于对照：不把可复用流程放入规划和反思的模型输入。
    if not enabled or not any(word in goal.lower() for word in ("meeting", "schedule")):
        emit("Skill activation", "skipped")
        return ""
    body = body.strip()
    emit("Skill activation", {"path": str(SKILL_PATH.relative_to(ROOT)), "body": body})
    return body


class DemoDecider:
    """使用固定规则生成计划和反思，提供零 API 成本的对照轨迹。

    它和 LLMDecider 具有相同的 decide() 接口，但不代表模型的真实表现。
    """

    # 实例第一次增加 calls 时会创建自己的计数，记录本次运行的决策次数。
    calls = 0

    def decide(self, kind: str, payload: dict, schema: dict) -> dict:
        """根据当前状态生成候选计划，或根据工具错误生成修正建议。

        Args:
            kind: plan 或 reflection。
            payload: 规划时包含日历状态；反思时包含观察到的错误。
            schema: 与真实模型接口保持一致，本规则实现不读取它。

        Returns:
            dict: 与对应 JSON Schema 同形状的决策结果。
        """
        self.calls += 1
        if kind == "plan":
            # 只依据最近一次日历观察，选择最早的未占用候选时段。
            free = [slot for slot in SLOTS if slot not in payload["state"]["busy_slots"]]
            return {"slot": free[0] if free else SLOTS[-1], "steps": PLAN_STEPS,
                    "reason": "Choose the earliest observed free slot; create, remind, verify."}

        # 错误类型决定修正范围：时段冲突需重新规划，提醒故障只需重试提醒。
        error = payload["observation"].get("error")
        if error == "SLOT_CONFLICT":
            return {"diagnosis": "The calendar changed after planning.", "correction": "replan"}
        if error == "TEMPORARY_REMINDER_FAILURE":
            return {"diagnosis": "The meeting exists, but its reminder failed.",
                    "correction": "retry_reminder"}
        return {"diagnosis": "Unknown failure.", "correction": "stop"}


class LLMDecider:
    """
    通过 Responses API 请 LLM 生成计划和反思建议

    本实验没有把日历方法注册为 Function Tools；模型返回的是 JSON 决策，
    而不是已执行的工具结果。后续的实际执行仍由 run() 中的 Python 代码完成。
    """

    def __init__(self, model: str):
        """创建 API 客户端，并记录本次实验选用的模型名称。"""
        # 将导入放在此处，使默认 demo 模式不依赖 openai 包。
        from openai import OpenAI

        self.client = OpenAI()
        self.model = model
        self.calls = 0

    def decide(self, kind: str, payload: dict, schema: dict) -> dict:
        """发起一次模型请求，并解析严格结构化的 JSON 决策。

        Args:
            kind: plan 或 reflection，同时作为输出 Schema 的名称。
            payload: 本轮目标、状态、约束、Skill 或错误反馈。
            schema: 限定本轮回答形状的 JSON Schema。

        Returns:
            dict: 模型产生的计划或修正建议，尚未经过业务校验。
        """
        # 每次规划或反思各对应一次 Responses API 请求
        self.calls += 1
        instructions = (
            "You plan actions for a virtual calendar. Return a concise JSON decision. "
            "For a plan, select a currently free slot and order the actions as "
            "create_meeting, set_reminder, verify. For reflection, diagnose the observed "
            "error and choose a targeted correction. Do not claim a tool has run."
        )
        # input 提供本轮已知事实；text.format 要求模型返回指定结构的 JSON
        # 此请求没有 tools 参数，因此不会由模型直接发起日历 Function Call
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=json.dumps({"decision": kind, **payload}, ensure_ascii=False),
            text={"format": {"type": "json_schema", "name": kind,
                             "strict": True, "schema": schema}},
        )
        # 不完整或没有文本的响应不能被当作可执行计划
        if response.status != "completed" or not response.output_text:
            raise RuntimeError(f"Model returned no usable {kind}: {response.status}")
        return json.loads(response.output_text)


def run(engine: str = "demo", mode: str = "reflect", skill: bool = True,
        faults: bool = True, model: str | None = None, trace: bool = True) -> dict:
    """
    运行完整实验：发现 Skill、规划、执行、反思、重规划并验证

    Args:
        engine: demo 使用固定规则, llm 使用真实模型 API
        mode: plan-only 在首次失败后停止, reflect 根据反馈尝试修正
        skill: 是否把 Skill 正文加入决策输入
        faults: 是否注入日程冲突和一次提醒故障
        model: llm 模式使用的模型名称；为空时读取 OPENAI_MODEL
        trace: 是否打印每个决策、工具执行和环境变化

    Returns:
        dict: 最终验证结果，以及决策、模型 API 和工具执行次数
    """
    # ==========================================================
    # Step 1：准备轨迹输出、决策器与虚拟环境
    # ==========================================================
    sequence = 0

    def emit(label: str, value) -> None:
        """输出带序号的实验事件；--no-trace 时只保留内部计数"""
        nonlocal sequence
        sequence += 1
        if trace:
            rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            print(f"[{sequence:02d}] {label}: {rendered}")

    # 两种决策器共用后续流程；只有 llm 模式实际发出模型 API 请求
    decider = DemoDecider() if engine == "demo" else LLMDecider(model or os.environ["OPENAI_MODEL"])
    # 每次运行创建独立日历，故障开关也只影响本次实验
    world = CalendarWorld(reminder_fails_once=faults)
    skill_body = load_skill(GOAL, skill, emit)
    tool_calls = 0

    def tool(name: str, *args) -> dict:
        """
        统一执行日历方法，并记录 Python 实际发生的工具调用
        """
        nonlocal tool_calls
        tool_calls += 1
        # getattr 只使用本程序写死的工具名；模型不能提供任意 Python 方法名。
        result = getattr(world, name)(*args)
        emit(f"Tool #{tool_calls} {name}", {"arguments": args, "result": result})
        return result

    # ==========================================================
    # Step 2：生成并检查候选计划
    # ==========================================================
    def make_plan(state: dict, previous_error: dict | None = None) -> dict:
        """把目标、日历状态和约束交给决策器，并检查返回的计划

        Args:
            state: 最近一次 list_events() 得到的日历快照
            previous_error: 重新规划时附带的上一次工具错误

        Returns:
            dict: 已通过基本校验的候选计划
        """
        # previous_error 使重新规划知道旧方案为什么失败，而不只看到新状态。
        payload = {"goal": GOAL, "state": state, "available_slots": SLOTS,
                   "constraints": {"duration_minutes": 30, "reminder_minutes": 30},
                   "skill": skill_body, "previous_error": previous_error}
        plan = decider.decide("plan", payload, PLAN_SCHEMA)
        emit(f"Decision #{decider.calls} plan", plan)
        # JSON Schema 只保证数据形状；Python 再检查依赖顺序和已观察到的忙碌时段。
        # 此检查仍无法保证时段在执行时继续空闲，所以工具还会再次检查。
        if plan["steps"] != PLAN_STEPS or plan["slot"] in state["busy_slots"]:
            raise ValueError(f"Invalid plan for observed state: {plan}")
        return plan

    # ==========================================================
    # Step 3：把预期与实际工具结果交给反思决策器
    # ==========================================================
    def reflect(expected: str, observation: dict, allowed: str) -> bool:
        """诊断失败，并确认模型建议与当前错误可采用的修正一致。

        Args:
            expected: 原计划预期的工具执行结果。
            observation: 工具实际返回的结果或错误。
            allowed: 当前错误允许的修正类型。

        Returns:
            bool: 是否接受修正建议并继续执行。
        """
        # plan-only 只执行初始计划，用于观察缺少反思时的结果。
        if mode == "plan-only":
            emit("Reflection", "disabled in plan-only mode")
            return False

        # 重新查询日历，避免仅凭上一次错误推测当前环境状态。
        feedback = {"goal": GOAL, "expected": expected,
                    "observation": observation, "current_state": tool("list_events"),
                    "skill": skill_body}
        decision = decider.decide("reflection", feedback, REFLECTION_SCHEMA)
        emit(f"Decision #{decider.calls} reflection", decision)
        # 模型只能提出建议：时段冲突只接受 replan，暂时提醒故障只接受 retry_reminder。
        return decision["correction"] == allowed

    # ==========================================================
    # Step 4：先观察，再规划；随后按计划尝试创建会议
    # ==========================================================
    state = tool("list_events")
    plan = make_plan(state)
    conflict_injected = False
    meeting_id = None

    # 最多尝试三次创建会议，防止不断重规划导致无限循环。
    for attempt in range(3):
        # 首次规划后才注入冲突，展示“计划依据的旧状态”和执行时最新状态的差异。
        if faults and not conflict_injected:
            world.inject_conflict(plan["slot"])
            emit("Environment change", {"new_conflict": plan["slot"]})
            conflict_injected = True

        created = tool("create_meeting", plan["slot"], TITLE)
        if "error" in created:
            # 失败时不假装会议已创建；反思同意后重新读取日历并生成新计划。
            if attempt == 2 or not reflect("Meeting created in the selected slot", created, "replan"):
                break
            state = tool("list_events")
            plan = make_plan(state, created)
            continue

        # ======================================================
        # Step 5：会议已创建，单独处理提醒故障
        # ======================================================
        meeting_id = created["meeting_id"]
        # 提醒最多尝试两次；反思只允许重试提醒，不再创建第二个会议。
        for reminder_attempt in range(2):
            reminder = tool("set_reminder", meeting_id, 30)
            if "error" not in reminder:
                break
            if reminder_attempt == 1 or not reflect("30-minute reminder saved", reminder,
                                                    "retry_reminder"):
                break

        # ======================================================
        # Step 6：独立读取最终状态，不以模型建议或单次工具返回代替验证
        # ======================================================
        verification = tool("verify", meeting_id, plan["slot"])
        break
    else:
        # for 循环正常耗尽时，说明没有成功创建会议
        verification = {"passed": False, "meeting": None}

    if meeting_id is None:
        # 包括 plan-only 因冲突直接 break 的情况：没有会议就不能算成功
        verification = {"passed": False, "meeting": None}
    emit("Final verification", verification)

    # 分开统计决策次数、真实 API 请求次数和 Python 工具执行次数。
    # demo 的决策也会计数，但它从未调用模型 API。
    result = {"success": verification["passed"], "meeting": verification["meeting"],
              "decision_calls": decider.calls,
              "model_api_calls": decider.calls if engine == "llm" else 0,
              "tool_executions": tool_calls,
              "engine": engine, "mode": mode, "skill_loaded": bool(skill_body)}
    print("Result:", json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    """
    解析命令行参数，加载本地配置，并启动一次实验
    """
    # --engine 决定是否使用真实模型；其余开关用于构造可对照的实验条件
    parser = argparse.ArgumentParser(description="Planning, Reflection, and Skill lab")
    parser.add_argument("--engine", choices=("demo", "llm"), default="demo")
    parser.add_argument("--mode", choices=("plan-only", "reflect"), default="reflect")
    parser.add_argument("--skill", choices=("on", "off"), default="on")
    parser.add_argument("--no-faults", action="store_true")
    parser.add_argument("--model", help="Override OPENAI_MODEL for --engine llm")
    parser.add_argument("--no-trace", action="store_true")
    args = parser.parse_args()

    # 只有真实模型入口才需要安装 SDK、读取 API Key 与模型名称
    if args.engine == "llm":
        from dotenv import load_dotenv

        # 本项目以仓库根目录的 .env 为准，避免终端里残留的其他 API Key 抢先生效
        load_dotenv(ROOT.parent / ".env", override=True)
        if not os.getenv("OPENAI_API_KEY") or not (args.model or os.getenv("OPENAI_MODEL")):
            parser.error("Set OPENAI_API_KEY and OPENAI_MODEL in the repository .env")

    try:
        run(args.engine, args.mode, args.skill == "on", not args.no_faults,
            args.model, not args.no_trace)
    except Exception as exc:
        # API 错误向用户报告原因；其他程序错误继续抛出，保留调试堆栈
        if args.engine == "llm":
            from openai import OpenAIError

            if isinstance(exc, OpenAIError):
                parser.exit(1, f"OpenAI API request failed: {exc}\n")
        raise


if __name__ == "__main__":
    main()
