"""用临时目录验证 Harness 的边界、重试与断点续跑。"""

import tempfile
import unittest
import json
from pathlib import Path

from harness import DEFAULT_DAY, Harness
from workspace import observe, schedule_focus, verify


class BadDecider:
    """模拟模型返回未经授权的工具名。"""

    def decide(self, observation: dict) -> dict:
        return {"action": "delete_everything", "task_id": "eval", "slot_id": "09:00",
                "reason": "错误演示"}


class HarnessTests(unittest.TestCase):
    def test_pause_resume_and_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            harness = Harness.start(DEFAULT_DAY, runs, "demo", fail_once=False, trace=False)
            first = harness.run(max_decisions=2)
            self.assertEqual(first["status"], "paused")
            self.assertEqual(first["verification"]["scheduled_blocks"], 2)

            resumed = Harness.resume(first["run_id"], runs, trace=False)
            final = resumed.run()
            self.assertEqual(final["status"], "completed")
            self.assertTrue(final["verification"]["success"])
            self.assertEqual(final["model_calls"], 0)
            brief = Path(final["brief"]).read_text(encoding="utf-8")
            self.assertIn("组会", brief)
            self.assertIn("- [ ] **09:00–10:00**", brief)
            self.assertTrue((resumed.folder / "events.jsonl").exists())

    def test_transient_failure_counts_both_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness.start(DEFAULT_DAY, Path(tmp), "demo", fail_once=True, trace=False)
            result = harness.run()
            self.assertTrue(result["verification"]["success"])
            self.assertEqual(result["tool_attempts"], 6)  # 5 次成功安排 + 1 次失败尝试

    def test_tool_budget_pause_then_resume_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            harness = Harness.start(DEFAULT_DAY, runs, "demo", fail_once=True, trace=False)
            first = harness.run(max_tool_attempts=1)
            self.assertEqual(first["status"], "paused")
            self.assertEqual(first["verification"]["scheduled_blocks"], 0)

            resumed = Harness.resume(first["run_id"], runs, trace=False)
            final = resumed.run()
            self.assertTrue(final["verification"]["success"])
            self.assertEqual(final["tool_attempts"], 6)

    def test_unauthorized_action_never_reaches_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness.start(DEFAULT_DAY, Path(tmp), "demo", fail_once=False, trace=False)
            result = harness.run(max_decisions=2, decider=BadDecider())
            self.assertEqual(result["status"], "paused")
            self.assertEqual(result["tool_attempts"], 0)
            self.assertEqual(result["verification"]["scheduled_blocks"], 0)

    def test_business_rules_reject_busy_and_early_dependency(self):
        from workspace import load_day

        day = load_day(DEFAULT_DAY)
        assignments = []
        self.assertEqual(schedule_focus(day, assignments, "paper", "11:00")["error"], "SLOT_BUSY")
        self.assertEqual(schedule_focus(day, assignments, "brief", "09:00")["error"],
                         "DEPENDENCY_NOT_READY")
        self.assertFalse(verify(day, assignments)["success"])

    def test_observation_cannot_mutate_runtime_state(self):
        from workspace import load_day

        day = load_day(DEFAULT_DAY)
        assignments = []
        snapshot = observe(day, assignments, None)
        snapshot["assignments"].append({"task_id": "paper", "slot_id": "09:00"})
        snapshot["day"]["slots"][0]["busy"] = True
        self.assertEqual(assignments, [])
        self.assertFalse(day["slots"][0]["busy"])

    def test_task_run_turn_step_and_state_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            first = Harness.start(DEFAULT_DAY, runs, "demo", fail_once=False, trace=False)
            second = Harness.start(DEFAULT_DAY, runs, "demo", fail_once=False, trace=False)
            self.assertEqual(first.state["task_id"], second.state["task_id"])
            self.assertNotEqual(first.state["run_id"], second.state["run_id"])
            first.run(max_decisions=1)
            events = [json.loads(line) for line in (first.folder / "events.jsonl").read_text().splitlines()]
            turn_one = [row for row in events if row["turn"] == 1]
            self.assertEqual([row["step"] for row in turn_one], list(range(1, len(turn_one) + 1)))
            self.assertEqual(turn_one[0]["kind"], "observation")
            self.assertEqual(turn_one[-1]["kind"], "turn_finished")
            with self.assertRaises(ValueError):
                first._transition("completed", "skip_verification")

    def test_replayed_tool_action_is_idempotent(self):
        from workspace import load_day

        day = load_day(DEFAULT_DAY)
        assignments = []
        self.assertTrue(schedule_focus(day, assignments, "eval", "09:00")["ok"])
        replay = schedule_focus(day, assignments, "eval", "09:00")
        self.assertTrue(replay["already_applied"])
        self.assertEqual(len(assignments), 1)

    def test_cancel_is_terminal_but_pause_can_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            harness = Harness.start(DEFAULT_DAY, runs, "demo", fail_once=False, trace=False)
            harness.run(max_decisions=1)
            cancelled = Harness.cancel(harness.state["run_id"], runs, trace=False)
            self.assertEqual(cancelled.state["status"], "cancelled")
            self.assertIn("cancelled", (cancelled.folder / "daily_plan.md").read_text())
            with self.assertRaises(ValueError):
                Harness.resume(harness.state["run_id"], runs, trace=False)

    def test_old_checkpoint_can_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            harness = Harness.start(DEFAULT_DAY, runs, "demo", fail_once=False, trace=False)
            harness.run(max_decisions=1)
            path = harness.folder / "checkpoint.json"
            state = json.loads(path.read_text(encoding="utf-8"))
            for key in ("task_id", "turn_number", "step_number"):
                del state[key]
            path.write_text(json.dumps(state), encoding="utf-8")
            resumed = Harness.resume(harness.state["run_id"], runs, trace=False)
            self.assertEqual(resumed.state["task_id"], harness.state["task_id"])
            self.assertTrue(resumed.run()["verification"]["success"])


if __name__ == "__main__":
    unittest.main()
