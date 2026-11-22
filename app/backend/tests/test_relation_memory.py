"""v0.6.2: the narrator is told the stage of each relationship in words and, for the characters in the scene, why it
moved (a close friend met again 50 messages later stays a close friend)."""
import unittest

from story.services.context_builder import relationship_memories, render_relationships


class _Index:
    def name(self, cid):
        return {"lily": "Lilia", "sera": "Sera"}.get(cid, cid)


class RelationMemoryTest(unittest.TestCase):
    REC = {"target_id": "lily", "target_name": "Lilia", "label": "", "axes": {"trust": 30, "affection": 25},
           "history": [{"delta": 1, "reason": "info table"}, {"delta": 2, "reason": "Kurio defended her during the duel"},
                       {"delta": 1, "reason": "they shared lunch"}, {"delta": -1, "reason": "undo", "reverts": "m1"}]}

    def test_memories_and_stage(self):
        self.assertEqual(relationship_memories(self.REC), ["Kurio defended her during the duel", "they shared lunch"])
        here = render_relationships([self.REC], _Index(), focus={"lily"})[1]
        self.assertIn("Close / trusted", here)
        self.assertIn("remembered: Kurio defended her during the duel; they shared lunch", here)
        away = render_relationships([self.REC], _Index(), focus={"sera"})[1]
        self.assertIn("Close / trusted", away)  # the stage is always there
        self.assertNotIn("remembered", away)  # the reasons only for the characters in the scene (fewer tokens)
        self.assertEqual(relationship_memories({"history": []}), [])
