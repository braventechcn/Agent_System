"""离线验证 Planning、Reflection 和 Skill 实验的关键状态变化。

这些测试使用 DemoDecider，不请求模型 API，也不依赖真实日历服务。
"""

import contextlib
import io
import unittest

from agent import run


class LabTest(unittest.TestCase):
    """比较固定故障场景下，不同模式的实际日历结果。"""

    def quiet_run(self, **kwargs):
        """运行实验并收起终端输出，让断言聚焦返回的最终状态。"""
        # run() 无论是否启用详细轨迹都会输出 Result；测试时捕获这些文字。
        with contextlib.redirect_stdout(io.StringIO()):
            return run(trace=False, **kwargs)

    def test_initial_plan_cannot_survive_new_conflict(self):
        """计划生成后若环境变动，禁用反思就无法修复时段冲突。"""
        result = self.quiet_run(mode="plan-only")
        self.assertFalse(result["success"])
        # 离线规则只生成初始计划，不产生真正的模型 API 请求。
        self.assertEqual(result["decision_calls"], 1)
        self.assertEqual(result["model_api_calls"], 0)

    def test_reflection_repairs_both_failures_without_duplicate_meeting(self):
        """两次故障分别触发重新选时段和只重试提醒。"""
        result = self.quiet_run(mode="reflect")
        self.assertTrue(result["success"])
        # 重新规划选择 11:00；提醒已保存，会议编号仍为首次创建的 meeting-1。
        self.assertEqual(result["meeting"]["slot"], "11:00")
        self.assertEqual(result["meeting"]["reminder_minutes"], 30)
        self.assertEqual(result["meeting"]["id"], "meeting-1")
        self.assertTrue(result["skill_loaded"])

    def test_skill_can_be_disabled(self):
        """关闭 Skill 时不加载正文；离线规则仍可完成同一固定任务。"""
        result = self.quiet_run(skill=False)
        self.assertFalse(result["skill_loaded"])
        self.assertTrue(result["success"])

    def test_initial_plan_works_without_environment_change(self):
        """关闭故障后，初始计划本身足以完成任务。"""
        result = self.quiet_run(mode="plan-only", faults=False)
        self.assertTrue(result["success"])
        self.assertEqual(result["meeting"]["slot"], "10:30")


if __name__ == "__main__":
    # 允许直接运行此文件，也允许 unittest discover 发现这些测试。
    unittest.main()
