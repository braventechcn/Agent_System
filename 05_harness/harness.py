"""研究与工作冲刺台：用一个小型 Harness 管理 Agent 的完整运行。

决策器只能提出下一步；Harness 负责状态、工具执行、边界、事件轨迹、
断点续跑和最终验证。默认 DemoDecider 不调用 API；--engine llm 才调用模型。
"""

import argparse
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
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
        state = {"run_id": run_id, "engine": engine, "day": day, "assignments": [],
                 "status": "running", "decisions": 0, "model_calls": 0, "tool_attempts": 0,
                 "last_result": None, "fail_once_pending": fail_once, "event_number": 0}
        harness = cls(runs_dir / run_id, state, trace)
        harness._event("run_started", {"engine": engine, "input": str(input_path),
                                       "fail_once": fail_once})
        return harness

    @classmethod
    def resume(cls, run_id: str, runs_dir: Path, trace: bool = True) -> "Harness":
        """从磁盘恢复上次观察和已执行操作，不重新读取可能已变化的输入文件。"""
        if Path(run_id).name != run_id or run_id in (".", ".."):
            raise ValueError("run_id 必须是单个目录名")
        folder = runs_dir / run_id
        state = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
        if state["status"] not in ("paused", "running", "incomplete"):
            raise ValueError(f"运行状态 {state['status']} 不能续跑")
        harness = cls(folder, state, trace)
        harness.state["status"] = "running"
        harness._event("run_resumed", {"decisions": state["decisions"],
                                       "tool_attempts": state["tool_attempts"]})
        return harness

    def _save(self) -> None:
        """先写临时文件，再替换检查点，避免只写到一半的 JSON。"""
        target = self.folder / "checkpoint.json"
        temporary = self.folder / "checkpoint.tmp"
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(target)

    def _event(self, kind: str, data: dict) -> None:
        """每个关键步骤追加一条 JSONL 事件，并保存最新状态。"""
        self.state["event_number"] += 1
        row = {"n": self.state["event_number"], "time": datetime.now(timezone.utc).isoformat(),
               "kind": kind, "data": data}
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
                self.state["status"] = "paused"
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
                self.state["status"] = "paused"
                self._event("budget_stop", {"reason": "decisions", "limit": max_decisions})
                break
            if self.state["tool_attempts"] >= max_tool_attempts:
                self.state["status"] = "paused"
                self._event("budget_stop", {"reason": "tool_attempts", "limit": max_tool_attempts})
                break

            snapshot = observe(self.state["day"], self.state["assignments"],
                               self.state["last_result"])
            # 模型调用次数和决策次数分开统计：离线模式的 model_calls 永远是 0。
            if self.state["engine"] == "llm":
                self.state["model_calls"] += 1
            self.state["decisions"] += 1
            try:
                decision = decider.decide(snapshot)
            except Exception as exc:
                self.state["status"] = "paused"
                self._event("decision_error", {"error": str(exc)})
                break
            self._event("decision", {"number": self.state["decisions"], "proposal": decision})

            rejected = self._check_decision(decision)
            if rejected:
                self.state["last_result"] = rejected
                self._event("rejected", rejected)
                continue
            if decision["action"] == "finish":
                check = verify(self.state["day"], self.state["assignments"])
                self.state["status"] = "completed" if check["success"] else "incomplete"
                self.state["last_result"] = {"verification": check}
                self._event("verification", check)
                break
            self._execute(decision, max_tool_attempts)

        # 暂停时也写出当前计划；续跑会覆盖同一路径，用户始终能查看进度。
        check = verify(self.state["day"], self.state["assignments"])
        brief = self.folder / "sprint_brief.md"
        brief.write_text(make_brief(self.state["day"], self.state["assignments"],
                                   self.state["status"], check), encoding="utf-8")
        return {"run_id": self.state["run_id"], "status": self.state["status"],
                "decisions": self.state["decisions"], "model_calls": self.state["model_calls"],
                "tool_attempts": self.state["tool_attempts"], "verification": check,
                "brief": str(brief)}


def main() -> None:
    """提供 start、resume、show 三个入口，避免实验代码和使用命令混在一起。"""
    parser = argparse.ArgumentParser(description="研究与工作冲刺台：一个可观察、可续跑的小型 Agent Harness")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS, help="运行记录保存目录")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="开始一次新冲刺")
    start.add_argument("--input", type=Path, default=DEFAULT_DAY)
    start.add_argument("--engine", choices=["demo", "llm"], default="demo")
    start.add_argument("--fail-once", action="store_true", help="首次工具执行模拟短暂故障")
    start.add_argument("--max-decisions", type=int, default=12)
    start.add_argument("--max-tool-attempts", type=int, default=12)
    resume = sub.add_parser("resume", help="从检查点继续")
    resume.add_argument("run_id")
    resume.add_argument("--max-decisions", type=int, default=12)
    resume.add_argument("--max-tool-attempts", type=int, default=12)
    show = sub.add_parser("show", help="查看某次运行的状态")
    show.add_argument("run_id")
    args = parser.parse_args()

    if args.command == "show":
        if Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
            parser.error("run_id 必须是单个目录名")
        path = args.runs_dir / args.run_id / "checkpoint.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({"run_id": state["run_id"], "status": state["status"],
                          "decisions": state["decisions"], "model_calls": state["model_calls"],
                          "tool_attempts": state["tool_attempts"],
                          "assignments": state["assignments"]}, ensure_ascii=False, indent=2))
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
