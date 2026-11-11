"""用临时目录验证 Harness 的边界、重试与断点续跑。"""

import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
