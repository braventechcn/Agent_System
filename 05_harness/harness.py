"""每日专注规划师：用一个小型 Harness 管理 Agent 的完整运行。

决策器只能提出下一步；Harness 负责状态、工具执行、边界、事件轨迹、
断点续跑和最终验证。默认 DemoDecider 不调用 API；--engine llm 才调用模型。
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from decision import DemoDecider, LLMDecider
from workspace import load_day, make_brief, observe, schedule_focus, verify


ROOT = Path(__file__).resolve().parent
DEFAULT_DAY = ROOT / "example_day.json"
DEFAULT_RUNS = ROOT / ".runs"
TRANSITIONS = {
    "created": {"running"},
    "running": {"paused", "completed", "incomplete"},
    "paused": {"running", "cancelled"},
    "incomplete": {"running", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _task_identity(day: dict) -> str:
    """相同的输入目标与约束得到同一个 Task 身份。"""
    return hashlib.sha256(json.dumps(day, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def _upgrade_checkpoint(state: dict) -> dict:
    """旧版检查点缺少层级字段；补齐后仍沿用原 Run 与已安排内容。"""
    state.setdefault("task_id", _task_identity(state["day"]))
    state.setdefault("turn_number", state["decisions"])
    state.setdefault("step_number", 0)
    return state


class Harness:
    """持有一次运行的检查点和事件日志，控制 Agent 可以做到哪一步。"""

    def __init__(self, folder: Path, state: dict, trace: bool = True):
        self.folder = folder
        self.state = state
        self.trace = trace
        folder.mkdir(parents=True, exist_ok=True)

    @classmethod
    def start(cls, input_path: Path, runs_dir: Path, engine: str, fail_once: bool,
              trace: bool = True) -> "Harness":
        """从输入文件创建一次独立运行；输入内容复制进检查点，便于以后续跑。"""
        day = load_day(input_path)
        # 相同的目标与约束得到同一 Task 身份；每次 start 仍创建新的 Run。
        task_id = _task_identity(day)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
        state = {"task_id": task_id, "run_id": run_id, "engine": engine, "day": day,
                 "assignments": [], "status": "created", "turn_number": 0,
                 "step_number": 0, "decisions": 0, "model_calls": 0, "tool_attempts": 0,
                 "last_result": None, "fail_once_pending": fail_once, "event_number": 0}
        harness = cls(runs_dir / run_id, state, trace)
        harness._event("run_created", {"engine": engine, "input": str(input_path),
                                       "fail_once": fail_once})
        harness._transition("running", "start")
        return harness

    @classmethod
    def resume(cls, run_id: str, runs_dir: Path, trace: bool = True) -> "Harness":
        """从磁盘恢复上次观察和已执行操作，不重新读取可能已变化的输入文件。"""
        if Path(run_id).name != run_id or run_id in (".", ".."):
            raise ValueError("run_id 必须是单个目录名")
        folder = runs_dir / run_id
        state = _upgrade_checkpoint(json.loads((folder / "checkpoint.json").read_text(encoding="utf-8")))
        if state["status"] not in ("paused", "running", "incomplete"):
            raise ValueError(f"运行状态 {state['status']} 不能续跑")
        harness = cls(folder, state, trace)
        if state["status"] != "running":
            harness._transition("running", "resume")
        harness._event("run_resumed", {"decisions": state["decisions"],
                                       "tool_attempts": state["tool_attempts"]}, in_turn=False)
        return harness

    @classmethod
    def cancel(cls, run_id: str, runs_dir: Path, trace: bool = True) -> "Harness":
        """显式取消已暂停或未完成的 Run；取消后不能再续跑。"""
        if Path(run_id).name != run_id or run_id in (".", ".."):
            raise ValueError("run_id 必须是单个目录名")
        folder = runs_dir / run_id
        state = _upgrade_checkpoint(json.loads((folder / "checkpoint.json").read_text(encoding="utf-8")))
        if state["status"] not in ("paused", "incomplete"):
            raise ValueError(f"运行状态 {state['status']} 不能取消")
        harness = cls(folder, state, trace)
        harness._transition("cancelled", "user_cancelled")
        check = verify(state["day"], state["assignments"])
        (folder / "daily_plan.md").write_text(
            make_brief(state["day"], state["assignments"], "cancelled", check), encoding="utf-8")
        return harness

    def _transition(self, target: str, reason: str) -> None:
        """状态只能沿显式许可的边变化；完成的 Run 不能重新运行。"""
        source = self.state["status"]
        if target not in TRANSITIONS[source]:
            raise ValueError(f"非法状态转换：{source} -> {target}")
        self.state["status"] = target
        self._event("status_changed", {"from": source, "to": target, "reason": reason},
                    in_turn=False)

    def _save(self) -> None:
        """先写临时文件，再替换检查点，避免只写到一半的 JSON。"""
        target = self.folder / "checkpoint.json"
        temporary = self.folder / "checkpoint.tmp"
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(target)

    def _event(self, kind: str, data: dict, in_turn: bool = True) -> None:
        """每个关键步骤追加一条 JSONL 事件，并保存最新状态。"""
        self.state["event_number"] += 1
        if in_turn and self.state["turn_number"]:
            self.state["step_number"] += 1
        row = {"n": self.state["event_number"], "task_id": self.state["task_id"],
               "run_id": self.state["run_id"],
               "turn": self.state["turn_number"] if in_turn else None,
               "step": self.state["step_number"] if in_turn and self.state["turn_number"] else None,
               "time": datetime.now(timezone.utc).isoformat(), "kind": kind, "data": data}
        with (self.folder / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._save()
        if self.trace:
            print(f"[{row['n']:02d}] {kind}: {json.dumps(data, ensure_ascii=False)}")

    @staticmethod
    def _check_decision(decision: dict) -> dict | None:
        """白名单检查：模型输出只是字符串，不能直接变成任意 Python 调用。"""
        if not isinstance(decision, dict) or decision.get("action") not in ("schedule_focus", "finish"):
            return {"error": "INVALID_ACTION"}
        if not all(isinstance(decision.get(key), str)
                   for key in ("task_id", "slot_id", "reason")):
            return {"error": "INVALID_ARGUMENTS"}
        if decision["action"] == "schedule_focus" and (
                not decision["task_id"] or not decision["slot_id"]):
            return {"error": "MISSING_ARGUMENTS"}
        return None

    def _execute(self, decision: dict, max_tool_attempts: int) -> None:
        """执行工具；临时故障最多自动重试一次，每次尝试都计入预算。"""
        for attempt in range(2):
            if self.state["tool_attempts"] >= max_tool_attempts:
                self._transition("paused", "tool_attempt_budget")
                self._event("budget_stop", {"reason": "tool_attempts", "limit": max_tool_attempts})
                return
            self.state["tool_attempts"] += 1
            if self.state["fail_once_pending"]:
                # 可控故障展示 Harness 如何处理执行层的短暂失败；此时业务状态没有改变。
                self.state["fail_once_pending"] = False
                result = {"error": "TEMPORARY_TOOL_FAILURE", "detail": "模拟的一次性工具故障"}
            else:
                result = schedule_focus(self.state["day"], self.state["assignments"],
                                        decision["task_id"], decision["slot_id"])
            self.state["last_result"] = result
            self._event("tool_result", {"attempt": self.state["tool_attempts"],
                                        "retry": attempt == 1, "action": decision["action"],
                                        "task_id": decision["task_id"],
                                        "slot_id": decision["slot_id"], "result": result})
            if result.get("error") != "TEMPORARY_TOOL_FAILURE":
                return

    def run(self, max_decisions: int = 12, max_tool_attempts: int = 12,
            decider=None) -> dict:
        """持续 observe → decide → validate → execute，直到完成或触及预算。"""
        if max_decisions < 1 or max_tool_attempts < 1:
            raise ValueError("预算必须是正整数")
        if decider is None:
            decider = DemoDecider() if self.state["engine"] == "demo" else LLMDecider(
                os.environ["OPENAI_MODEL"])

        while self.state["status"] == "running":
            if self.state["decisions"] >= max_decisions:
                self._transition("paused", "decision_budget")
                self._event("budget_stop", {"reason": "decisions", "limit": max_decisions},
                            in_turn=False)
                break
            if self.state["tool_attempts"] >= max_tool_attempts:
                self._transition("paused", "tool_attempt_budget")
                self._event("budget_stop", {"reason": "tool_attempts", "limit": max_tool_attempts},
                            in_turn=False)
                break

            self.state["turn_number"] += 1
            self.state["step_number"] = 0
            snapshot = observe(self.state["day"], self.state["assignments"],
                               self.state["last_result"])
            self._event("observation", {"scheduled_blocks": len(snapshot["assignments"]),
                                        "last_result": snapshot["last_result"]})
            # 模型调用次数和决策次数分开统计：离线模式的 model_calls 永远是 0。
            if self.state["engine"] == "llm":
                self.state["model_calls"] += 1
            self.state["decisions"] += 1
            try:
                decision = decider.decide(snapshot)
            except Exception as exc:
                self._transition("paused", "decision_error")
                self._event("decision_error", {"error": str(exc)})
                self._event("turn_finished", {"outcome": "decision_error"})
                break
            self._event("decision", {"number": self.state["decisions"], "proposal": decision})

            rejected = self._check_decision(decision)
            if rejected:
                self.state["last_result"] = rejected
                self._event("rejected", rejected)
                self._event("turn_finished", {"outcome": "rejected"})
                continue
            if decision["action"] == "finish":
                check = verify(self.state["day"], self.state["assignments"])
                self.state["last_result"] = {"verification": check}
                self._event("verification", check)
                # 先持久化验证证据，再把 Run 标成完成或未完成。
                self._transition("completed" if check["success"] else "incomplete",
                                 "independent_verification")
                self._event("turn_finished", {"outcome": self.state["status"]})
                break
            self._execute(decision, max_tool_attempts)
            self._event("turn_finished", {"outcome": self.state["status"],
                                          "last_result": self.state["last_result"]})

        # 暂停时也写出当前计划；续跑会覆盖同一路径，用户始终能查看进度。
        check = verify(self.state["day"], self.state["assignments"])
        brief = self.folder / "daily_plan.md"
        brief.write_text(make_brief(self.state["day"], self.state["assignments"],
                                   self.state["status"], check), encoding="utf-8")
        return {"task_id": self.state["task_id"], "run_id": self.state["run_id"],
                "status": self.state["status"], "turns": self.state["turn_number"],
                "decisions": self.state["decisions"], "model_calls": self.state["model_calls"],
                "tool_attempts": self.state["tool_attempts"], "verification": check,
                "brief": str(brief)}


def main() -> None:
    """提供 start、resume、cancel、show 四个入口。"""
    parser = argparse.ArgumentParser(description="每日专注规划师：一个可观察、可续跑的小型 Agent Harness")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS, help="运行记录保存目录")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="开始一次新的任务安排")
    start.add_argument("--input", type=Path, default=DEFAULT_DAY)
    start.add_argument("--engine", choices=["demo", "llm"], default="demo")
    start.add_argument("--fail-once", action="store_true", help="首次工具执行模拟短暂故障")
    start.add_argument("--max-decisions", type=int, default=12)
    start.add_argument("--max-tool-attempts", type=int, default=12)
    resume = sub.add_parser("resume", help="从检查点继续")
    resume.add_argument("run_id")
    resume.add_argument("--max-decisions", type=int, default=12)
    resume.add_argument("--max-tool-attempts", type=int, default=12)
    cancel = sub.add_parser("cancel", help="取消已暂停或未完成的运行")
    cancel.add_argument("run_id")
    show = sub.add_parser("show", help="查看某次运行的状态")
    show.add_argument("run_id")
    args = parser.parse_args()

    if args.command == "show":
        if Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
            parser.error("run_id 必须是单个目录名")
        path = args.runs_dir / args.run_id / "checkpoint.json"
        state = _upgrade_checkpoint(json.loads(path.read_text(encoding="utf-8")))
        print(json.dumps({"task_id": state["task_id"], "run_id": state["run_id"],
                          "status": state["status"], "turns": state["turn_number"],
                          "decisions": state["decisions"], "model_calls": state["model_calls"],
                          "tool_attempts": state["tool_attempts"],
                          "assignments": state["assignments"]}, ensure_ascii=False, indent=2))
        return

    if args.command == "cancel":
        harness = Harness.cancel(args.run_id, args.runs_dir)
        print(f"已取消 Run {harness.state['run_id']}；已安排内容保存在 daily_plan.md")
        return

    if args.command == "start":
        harness = Harness.start(args.input, args.runs_dir, args.engine, args.fail_once)
    else:
        harness = Harness.resume(args.run_id, args.runs_dir)
    if harness.state["engine"] == "llm":
        # 仓库根目录的 .env 仅在真实模型模式读取；本地文件不进入版本控制。
        from dotenv import load_dotenv

        load_dotenv(ROOT.parent / ".env", override=True)
        if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
            parser.error("LLM 模式需要在项目根目录 .env 设置 OPENAI_API_KEY 和 OPENAI_MODEL")
    result = harness.run(args.max_decisions, args.max_tool_attempts)
    print("\n运行摘要：", json.dumps(result, ensure_ascii=False, indent=2))
    print("事件日志：", harness.folder / "events.jsonl")


if __name__ == "__main__":
    main()
