"""Phase 2, step 4: the info table the narrator writes at the end of each reply (services/info_table.py)."""
import time
import unittest

import support  # noqa: F401
from support import AppTestCase

from story.services import info_table


class ParseTest(unittest.TestCase):
    def test_lines(self):
        items = info_table.parse("place: infirmary\ntime: night\ndays: +1\npresent: Lilia, Sera\n"
                                 "Lilia: trust +1, affection +2 (Kurio saved the group)\nhp: -10\nmana: -15\n"
                                 "condition: +bruised\nitem: -healing potion\nmood: Lilia 3, Sera 1\n"
                                 "fact: Mirabel was stabbed in the old library tower\nweather: none")
        kinds = [i["kind"] for i in items]
        self.assertEqual(kinds, ["place", "time", "days", "present", "relationship", "relationship", "stat", "stat",
                                 "condition", "item", "mood", "mood", "fact"])
        rel = items[4]
        self.assertEqual((rel["who"], rel["axis"], rel["delta"], rel["reason"]), ("Lilia", "trust", 1, "Kurio saved the group"))
        self.assertEqual(items[6], {"kind": "stat", "stat": "hp", "delta": -10, "text": "hp: -10"})
        self.assertTrue(items[9]["remove"])
        self.assertEqual(info_table.parse(""), [])
        self.assertEqual(info_table.parse("no change"), [])

    def test_stream_filter(self):
        f = info_table.InfoFilter()
        shown = "".join(f.feed(p) for p in ["Lilia smiles. \"Goodnight.\"\n\n<in", "fo>\nmood: Lil", "ia 6\n</info>"])
        shown += f.flush()
        self.assertEqual(shown, "Lilia smiles. \"Goodnight.\"\n\n")
        self.assertEqual(f.block.strip(), "mood: Lilia 6")
        g = info_table.InfoFilter()
        out = "".join(g.feed(p) for p in ["a < b, and <i", "t> stays"]) + g.flush()
        self.assertEqual(out, "a < b, and <it> stays")
        self.assertIsNone(g.block)

    def test_block_without_tags(self):
        text, block = info_table.split_loose("Lilia laughs.\n\nInfo:\nmood: Lilia 2\nhp: -5")
        self.assertEqual(text, "Lilia laughs.")
        self.assertIn("mood: Lilia 2", block)
        self.assertEqual(info_table.split_loose("She says: no.\nHe says: yes.")[1], None)


class ApplyTest(AppTestCase):
    def test_apply_check_cancel_and_revert(self):
        story = self.new_story("Info", world_slug="lumencia_academy")
        sid = story["id"]
        r = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, r["assistant_message_id"])
        time.sleep(0.3)
        from story.models import Message, Story
        from story.services import state_service, story_tree
        with self.ctx.db.session() as s:
            st = s.get(Story, sid)
            m = s.get(Message, r["assistant_message_id"])
            info = info_table.apply(s, st, m, block="Lilia: trust +1 (shared a joke)\nLilia: fear +5 (saw the duel)\n"
                                                     "Nobody: trust +1\nhp: -500\ncondition: +bruised\n"
                                                     "place: dining hall\npresent: Lilia\nfact: Lilia snores")
            by = {l["label"].split(" (")[0]: l for l in info["lines"]}
            self.assertEqual(by["Lilia Valenheart: trust +1"]["status"], "applied", info["lines"])
            self.assertEqual(by["Lilia Valenheart: fear +5"]["status"], "proposed")
            self.assertEqual([l for l in info["lines"] if "Nobody" in l["label"]][0]["status"], "dropped")
            hp = next(x for x in state_service.current(s, st.active_branch_id).state_json["stats"] if x["label"] == "HP")
            self.assertEqual(hp["value"], 0)  # kept between 0 and the maximum
            scene = state_service.current(s, st.active_branch_id).state_json["scene"]
            self.assertEqual(scene["location"], "dining hall")
            self.assertEqual(scene["present"], ["lilia_valenheart"])
        # the player cancels the HP line: HP comes back
        msgs = self.get(f"/stories/{sid}/messages")["messages"]
        mm = next(x for x in msgs if x["id"] == r["assistant_message_id"])
        lines = mm["generation"]["info_table"]["lines"]
        i = next(l["i"] for l in lines if l["kind"] == "stat")
        self.post(f"/stories/{sid}/messages/{mm['id']}/info", {"line": i, "value": None})
        with self.ctx.db.session() as s:
            st = s.get(Story, sid)
            state = state_service.current(s, st.active_branch_id).state_json
            self.assertEqual(next(x for x in state["stats"] if x["label"] == "HP")["value"], 100)
            self.assertTrue(any(c["label"] == "bruised" for c in state["conditions"]))
            # everything from that reply leaves with it
            m = s.get(Message, r["assistant_message_id"])
            info_table.revert(s, st, story_tree.get_branch(s, st), m, "test")
            state = state_service.current(s, st.active_branch_id).state_json
            self.assertFalse(any(c["label"] == "bruised" for c in state["conditions"]))
            rel = [x for x in state["relationships"] if x.get("target_id") == "lilia_valenheart" or
                   x.get("source_id") == "lilia_valenheart"]
            self.assertTrue(all(not (x.get("axes") or {}).get("trust") for x in rel), rel)


if __name__ == "__main__":
    unittest.main()
