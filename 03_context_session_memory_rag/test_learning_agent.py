"""不调用模型，验证信息边界和检索来源。"""

import tempfile
import unittest
from pathlib import Path

from context import build_context
from retrieval import index_project, search
from store import Store


ROOT = Path(__file__).resolve().parents[1]


class LearningAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "lab.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_session_isolation_and_resume(self):
        self.store.ensure_session("a", "student")
        self.store.append_exchange("a", "Which room?", "Room C")
        self.store.ensure_session("b", "student")
        self.assertEqual(self.store.messages("a")[1]["content"], "Room C")
        self.assertEqual(self.store.messages("b"), [])
        with self.assertRaises(ValueError):
            self.store.ensure_session("a", "someone_else")

    def test_memory_survives_other_sessions_and_can_change(self):
        self.store.remember("student", "explanation_style", "Use short examples")
        self.store.ensure_session("a", "student")
        self.store.ensure_session("b", "student")
        self.assertEqual(self.store.memories("student")[0]["value"], "Use short examples")
        self.store.remember("student", "explanation_style", "Use detailed examples")
        self.assertEqual(self.store.memories("student")[0]["value"], "Use detailed examples")
        self.assertEqual(self.store.memories("another_profile"), [])
        self.assertTrue(self.store.forget("student", "explanation_style"))
        self.assertEqual(self.store.memories("student"), [])

    def test_retrieval_uses_real_project_guides(self):
        self.assertGreater(index_project(self.store, ROOT), 10)
        hits = search(self.store, "MCP Server REST API tool request", 3)
        self.assertTrue(hits)
        self.assertEqual(hits[0][1]["source"], "02_external_capabilities/README.md")
        self.assertIn("MCP", hits[0][1]["content"])

    def test_context_preserves_question_and_respects_budget(self):
        history = [
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
        ]
        memories = [{"key": "explanation_style", "value": "Use code examples"}]
        plan = build_context("What is MCP?", history, memories, [], budget=1000)
        self.assertLessEqual(plan.char_count, 1000)
        self.assertEqual(plan.messages[-1]["role"], "user")
        self.assertIn("What is MCP?", plan.messages[-1]["content"])
        self.assertEqual(len(plan.selected_history), 2)
        self.assertEqual(plan.selected_memories[0]["key"], "explanation_style")

    def test_no_retrieval_means_no_project_excerpt(self):
        plan = build_context("What is the project-specific MCP port?", [], [], [])
        self.assertEqual(plan.selected_chunks, [])
        self.assertNotIn("18081", str(plan.messages))


if __name__ == "__main__":
    unittest.main()
