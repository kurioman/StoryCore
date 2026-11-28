"""v0.7.7: player actions as attempts (context_builder.with_action_resolution) and "who knows what" in secrets
(services/secret_knowledge.py, Check Lore Packs)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import support  # noqa: F401  (puts the backend on sys.path)
from story.config import PROJECT_ROOT
from story.services import context_builder as cb
from story.services import secret_knowledge as sk
from story.services.lore_import import strip_hidden
from story.services.pack_check import check_pack, format_report


def ent(name, eid, aliases=()):
    return SimpleNamespace(name=name, entity_id=eid, aliases_json=list(aliases))


class AttemptsTest(unittest.TestCase):
    def test_attempts_replace_the_free_rule(self):
        p = cb.PROMPT_PROFILES["v6_third_person"]
        rules, note = cb.with_action_resolution(p["rules"], p["reminder"], "attempts")
        text = rules.format(name="Ren")
        self.assertIn("what Ren TRIES to say and do", text)
        self.assertNotIn("never tell the player's action again", text)
        self.assertIn("attempt, not a fact", note.format(name="Ren"))
        self.assertTrue(note.endswith("</narrator-note>"))

    def test_free_keeps_the_rules_as_before(self):
        p = cb.PROMPT_PROFILES["v6_third_person"]
        self.assertEqual(cb.with_action_resolution(p["rules"], p["reminder"], "free"), (p["rules"], p["reminder"]))
        old = cb.PROMPT_PROFILES["v4_second_person"]  # other profiles are not changed
        self.assertEqual(cb.with_action_resolution(old["rules"], old["reminder"], "attempts")[0], old["rules"])

    def test_setting_order_and_default(self):
        self.assertEqual(cb.action_resolution({}, {}), "attempts")
        self.assertEqual(cb.action_resolution({"action_resolution": "free"}, {}), "free")
        self.assertEqual(cb.action_resolution({"action_resolution": "free"}, {"action_resolution": "attempts"}), "attempts")
        self.assertEqual(cb.action_resolution({"action_resolution": "nonsense"}, {}), "attempts")

    def test_knowledge_rule_in_v6(self):
        self.assertIn("never what happened where she was absent", cb.NARRATION_RULES_V6)

    def test_rank_on_the_short_card(self):
        le = SimpleNamespace(name="Artemis", entity_type="faculty", summary="", data_json={
            "gender": "female", "role": "Knight instructor", "power": {"rank": "Master Adept"}})
        self.assertIn("rank: Master Adept", cb.character_card(le))


class SecretKnowledgeTest(unittest.TestCase):
    LOOK = sk.name_lookup([ent("Beelzebub", "beelzebub", ["Demon King"]), ent("Kriemhild", "kriemhild"),
                           ent("Emily Starlight", "emily")])

    def test_parse_forms(self):
        self.assertEqual(sk.parse("(Known by: Beelzebub, Kriemhild) A bond.")[1:], ("list", ["Beelzebub", "Kriemhild"], "A bond."))
        self.assertEqual(sk.parse("(Connu de : Emily et Beelzebub) Un lien.")[1:3], ("list", ["Emily", "Beelzebub"]))
        self.assertEqual(sk.parse("(Known by: nobody) X")[1], "nobody")
        self.assertEqual(sk.parse("(connu de : tout le monde) X")[1], "everyone")
        self.assertEqual(sk.parse("[4th Legion] (Known by: Kriemhild) X")[0], "[4th Legion]")
        self.assertIsNone(sk.parse("A plain secret.")[1])

    def test_render(self):
        line = sk.render("Kriemhild", "(Known by: demon king) Soul-bound.", self.LOOK, subject_is_character=True)
        self.assertIn("Known ONLY by: Beelzebub, Kriemhild.", line)
        self.assertIn("Every other character does NOT know it", line)
        self.assertNotIn("(Known by", line)
        self.assertIn("Known ONLY by Kriemhild", sk.render("Kriemhild", "(Known by: nobody) X", self.LOOK,
                                                          subject_is_character=True))
        self.assertIn("NO character", sk.render("4th Legion", "(Known by: nobody) X", self.LOOK, subject_is_character=False))
        self.assertEqual(sk.render("Kriemhild", "Plain.", self.LOOK, subject_is_character=True), "- Kriemhild: Plain.")
        self.assertIn("Emily Starlight", sk.render("Lilia", "(Known by: Emily) X", self.LOOK, subject_is_character=True))

    def test_json_object_secret(self):
        _, notes = strip_hidden({"id": "k", "hidden": [{"text": "Soul-bound.", "known_by": ["beelzebub"]}, "Old."]})
        self.assertEqual(notes, ["(Known by: beelzebub) Soul-bound.", "Old."])

    def test_check_lore_packs_warns_about_unknown_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "hc_pack"
            shutil.copytree(PROJECT_ROOT / "Lorepack" / "hero_chronicle_lore_pack", pack)
            f = pack / "characters" / "characters.json"
            data = json.loads(f.read_text(encoding="utf-8"))
            recs = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
            rec = next(r for r in recs if r.get("id") == "kriemhild")
            rec["hidden"] = ["(Known by: Beelzebub, Gandalf) She is soul-bound."]
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            r = check_pack(pack)
            text = format_report(r)
            self.assertTrue(any("Gandalf" in w and "Beelzebub" not in w for w in r["warnings"]), text)
            self.assertEqual(r["stats"].get("secrets_with_known_by"), 1, text)


if __name__ == "__main__":
    unittest.main()
