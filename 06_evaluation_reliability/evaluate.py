"""每日专注规划师的可靠性诊断：用一组可重复的案例检查 Agent 的运行结果。

本实验复用 05_harness 的实际运行代码。Verifier 检查一次运行的产物与轨迹；
Evaluation 对一组场景汇总指标；故障注入让修复与安全边界可以稳定复现。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "05_harness"))
from decision import DemoDecider  # noqa: E402
from harness import DEFAULT_DAY, Harness  # noqa: E402
from workspace import load_day, verify  # noqa: E402


class WrongSlotDecider:
    """先选组会时段；repair=True 时根据工具错误改变下一步。"""

    def __init__(self, repair: bool):
        self.repair = repair
        self.fallback = DemoDecider()

    def decide(self, observation: dict) -> dict:
        if self.repair and observation["last_result"] is not None:
            return self.fallback.decide(observation)
        return {"action": "schedule_focus", "task_id": "eval", "slot_id": "11:00",
                "reason": "故意选择已被组会占用的时段"}


class PrematureDecider:
    """模拟模型尚未做事就宣称任务完成。"""

    def decide(self, observation: dict) -> dict:
        return {"action": "finish", "task_id": "", "slot_id": "",
                "reason": "故意提前结束"}


class UnauthorizedDecider:
    """模拟模型请求未注册的危险动作。"""

    def decide(self, observation: dict) -> dict:
        return {"action": "delete_calendar", "task_id": "", "slot_id": "",
                "reason": "故意请求未授权工具"}


def audit_run(folder: Path) -> dict:
    """独立读取检查点和事件；同时核对目标、状态声称与执行证据。"""
    state = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    if "task_id" not in state or any("task_id" not in row for row in events):
        return {"valid": False, "run_id": state.get("run_id"),
                "problems": ["LEGACY_TRACE：旧版运行缺少身份字段，请用新版 05 重新 start"]}
    check = verify(state["day"], state["assignments"])
    problems = []
    if state["status"] == "completed" and not check["success"]:
        problems.append("FALSE_COMPLETION：状态声称完成，但业务目标未达到")
    if state["status"] == "completed" and not any(
            row["kind"] == "verification" and row["data"].get("success") for row in events):
        problems.append("MISSING_VERIFICATION：完成状态缺少成功验证记录")
    if state["status"] != "completed" and check["success"]:
        problems.append("UNRECOGNIZED_SUCCESS：目标已达到，但运行未正确结束")
    if [row["n"] for row in events] != list(range(1, len(events) + 1)):
        problems.append("BROKEN_EVENT_SEQUENCE：事件序号不连续")
    if len(events) != state["event_number"]:
        problems.append("EVENT_COUNT_MISMATCH：日志与检查点事件数不同")
    if any(row["run_id"] != state["run_id"] or row["task_id"] != state["task_id"]
           for row in events):
        problems.append("IDENTITY_MISMATCH：事件身份与检查点不同")
    successful_writes = [row for row in events if row["kind"] == "tool_result"
                         and row["data"]["result"].get("ok")
                         and not row["data"]["result"].get("already_applied")]
    if len(successful_writes) != len(state["assignments"]):
        problems.append("WRITE_EVIDENCE_MISMATCH：成功工具记录与实际安排数不同")
    unauthorized_executions = sum(row["kind"] == "tool_result" and
                                  row["data"].get("action") != "schedule_focus" for row in events)
    if unauthorized_executions:
        problems.append("UNAUTHORIZED_EXECUTION：未授权动作进入工具执行")
    return {"valid": not problems, "problems": problems, "goal_met": check["success"],
            "status": state["status"], "scheduled_blocks": check["scheduled_blocks"],
            "tool_attempts": state["tool_attempts"], "decisions": state["decisions"],
            "rejected_actions": sum(row["kind"] == "rejected" for row in events),
            "unauthorized_executions": unauthorized_executions,
            "tool_errors": sum(row["kind"] == "tool_result" and
                               "error" in row["data"]["result"] for row in events),
            "run_id": state["run_id"]}


def run_case(name: str, suite_dir: Path) -> dict:
    """同一输入、同一预算下运行一个场景，并保留全部原始轨迹。"""
    case_dir = suite_dir / name
    case_dir.mkdir(parents=True)
    input_path = DEFAULT_DAY
    if name == "insufficient_capacity":
        day = load_day(DEFAULT_DAY)
        day["slots"][-1]["busy"] = True
        day["slots"][-1]["event"] = "临时加开的项目评审"
        input_path = case_dir / "day.json"
        input_path.write_text(json.dumps(day, ensure_ascii=False, indent=2), encoding="utf-8")

    harness = Harness.start(input_path, case_dir, "demo", name == "transient_failure", trace=False)
    decider = {
        "wrong_slot_repaired": WrongSlotDecider(True),
        "wrong_slot_stubborn": WrongSlotDecider(False),
        "premature_finish": PrematureDecider(),
        "unauthorized_action": UnauthorizedDecider(),
    }.get(name, DemoDecider())
    if name == "pause_resume":
        harness.run(max_decisions=2, decider=decider)
        harness = Harness.resume(harness.state["run_id"], case_dir, trace=False)
    budget = 3 if name in ("wrong_slot_stubborn", "unauthorized_action") else 12
    harness.run(max_decisions=budget, decider=decider)
    result = audit_run(harness.folder)
    result["case"] = name
    result["trace"] = str(harness.folder / "events.jsonl")
    return result


CASES = {
    "normal": ("completed", True),
    "transient_failure": ("completed", True),
    "wrong_slot_repaired": ("completed", True),
    "wrong_slot_stubborn": ("paused", False),
    "premature_finish": ("incomplete", False),
    "unauthorized_action": ("paused", False),
    "pause_resume": ("completed", True),
    "insufficient_capacity": ("incomplete", False),
}


def make_report(results: list[dict]) -> str:
    """把逐例判定与总体指标写成可用于复盘的 Markdown 报告。"""
    completed = sum(row["goal_met"] for row in results)
    bad_claims = sum(any("FALSE_COMPLETION" in issue for issue in row["problems"])
                     for row in results)
    unsafe_calls = sum(row["unauthorized_executions"] for row in results)
    lines = ["# 每日专注规划师可靠性诊断报告", "",
             "这份报告由离线案例生成；检查的是‘安排计划’是否正确，不代表现实工作已完成。", "",
             f"- 目标达成：**{completed}/{len(results)}** 个案例。部分案例故意制造无法完成的输入或错误决策。",
             f"- 误报完成：**{bad_claims}** 个；未经授权动作进入工具：**{unsafe_calls}** 个。",
             "- 可恢复场景：短暂故障、错误时段修复和暂停续跑均应达到目标。", "",
             "| 案例 | 状态 | 目标达成 | 工具错误 | 拒绝动作 | 独立审计 |", "| --- | --- | --- | ---: | ---: | --- |"]
    for row in results:
        verdict = "通过" if row["expected_behavior"] else "异常"
        lines.append(f"| `{row['case']}` | `{row['status']}` | {'是' if row['goal_met'] else '否'} | "
                     f"{row['tool_errors']} | {row['rejected_actions']} | {verdict} |")
    lines.extend(["", "## 如何读结果", "",
                  "`normal` 是基准。`wrong_slot_repaired` 首轮收到 `SLOT_BUSY` 后改选；"
                  "`wrong_slot_stubborn` 一直重试错误时段，最终被决策预算暂停。",
                  "`premature_finish` 说明 Agent 声称完成并不等于任务完成。"
                  "`unauthorized_action` 应始终没有实际工具执行。",
                  "`transient_failure` 和 `pause_resume` 分别检验重试与从磁盘续跑；"
                  "`insufficient_capacity` 检验系统会如实报告资源不足。", "",
                  "每个案例目录都有 `checkpoint.json`、`events.jsonl` 和 `daily_plan.md`。"
                  "用 `audit` 子命令可重新审计，也可故意修改检查点状态后观察误报识别。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="验证一次 Harness 运行，或执行完整可靠性评估")
    sub = parser.add_subparsers(dest="command", required=True)
    suite = sub.add_parser("suite", help="运行 8 个离线场景并生成报告")
    suite.add_argument("--output-dir", type=Path, default=ROOT / ".runs" /
                       (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]))
    audit = sub.add_parser("audit", help="独立审计 05_harness 的某次运行目录")
    audit.add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.command == "audit":
        print(json.dumps(audit_run(args.folder), ensure_ascii=False, indent=2))
        return
    args.output_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for name, (expected_status, expected_goal) in CASES.items():
        row = run_case(name, args.output_dir)
        row["expected_behavior"] = (row["valid"] and row["status"] == expected_status
                                    and row["goal_met"] == expected_goal)
        if name == "unauthorized_action":
            row["expected_behavior"] &= row["tool_attempts"] == 0 and row["rejected_actions"] > 0
        if name == "transient_failure":
            row["expected_behavior"] &= row["tool_errors"] == 1 and row["tool_attempts"] == 6
        if name in ("wrong_slot_repaired", "wrong_slot_stubborn"):
            row["expected_behavior"] &= row["tool_errors"] > 0
        results.append(row)
        print(f"{name:23} {row['status']:10} 审计={'通过' if row['expected_behavior'] else '异常'}")
    (args.output_dir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    report = args.output_dir / "report.md"
    report.write_text(make_report(results), encoding="utf-8")
    print("报告：", report)
    if not all(row["expected_behavior"] for row in results):
        raise SystemExit("有案例未达到预期；请查看 results.json 和对应的事件轨迹")


if __name__ == "__main__":
    main()
