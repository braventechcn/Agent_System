"""验证评估器能发现误报完成，并能看见反馈修复的效果。"""

import json
import tempfile
import unittest
from pathlib import Path

from evaluate import audit_run, run_case


class EvaluationTests(unittest.TestCase):
    def test_feedback_changes_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repaired = run_case("wrong_slot_repaired", root)
            stubborn = run_case("wrong_slot_stubborn", root)
            self.assertTrue(repaired["goal_met"])
            self.assertFalse(stubborn["goal_met"])
            self.assertGreater(stubborn["tool_errors"], 0)

    def test_auditor_catches_false_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_case("premature_finish", root)
            folder = Path(result["trace"]).parent
            checkpoint = folder / "checkpoint.json"
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
            state["status"] = "completed"  # 模拟有人只修改状态标签，没有执行任务
            checkpoint.write_text(json.dumps(state), encoding="utf-8")
            self.assertFalse(audit_run(folder)["valid"])
            self.assertIn("FALSE_COMPLETION", audit_run(folder)["problems"][0])


if __name__ == "__main__":
    unittest.main()
