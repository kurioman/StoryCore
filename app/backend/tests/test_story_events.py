"""v0.6 planned events (services/story_events.py): due events in the turn's context, hidden marks, choices, Lumencia."""
import unittest
from pathlib import Path
from types import SimpleNamespace

import support  # noqa: F401  (puts the backend on sys.path)
from support import AppTestCase

from story.services import pack_manifest, portrait_tags, story_events

PACK = {
    "choices": [{"id": "wing", "name": {"en": "wing"}, "options": [
        {"id": "knight", "name": {"en": "Knight wing"}, "keywords": ["knight wing", "aile des chevaliers"]},
        {"id": "magic", "name": {"en": "Magic wing"}, "keywords": ["magic wing", "aile de magie"]}]}],
    "events": [
        {"id": "ceremony", "title": {"en": "Ceremony", "fr": "Cérémonie"}, "brief": "The ceremony.", "from_turn": 1},
        {"id": "orientation", "brief": "Orientation.", "after": ["ceremony"], "delay_turns": 2, "skip_if_choice": "wing"},
        {"id": "exam", "brief": "The wing exam.", "after": ["ceremony", "orientation"], "needs_choice": "wing",
         "variants": {"knight": "A duel.", "magic": "A crystal."}},
        {"id": "final", "brief": "Final exam.", "after": ["exam"], "from_date": {"month": "December", "day": 20}},
    ],
}


def user(text, command=None):
    return SimpleNamespace(role="user", kind="story", content=text, command_json=command, deleted_at=None)


def reply(asked=None, tags=(), choices=()):
    md = {"context": {"planned_event": {"id": asked} if asked else None}}
    if tags:
        md["event_tags"] = list(tags)
    if choices:
        md["choice_tags"] = list(choices)
    return SimpleNamespace(role="assistant", kind="story", content="...", status="complete", deleted_at=None,
                           generation_metadata_json=md)


def due_id(path, scene=None):
    d = story_events.due(PACK, story_events.progress(PACK, path), scene or {}, "March")
    return (d["event"]["id"], d["firm"], d["variant"]) if d else None


class EngineTest(unittest.TestCase):
    def test_order_delay_skip_and_variant(self):
        opening = [user("start", {"name": "start"}), reply()]
        self.assertIsNone(due_id(opening))  # not before the player's first turn
        path = opening + [user("I look around.")]
        self.assertEqual(due_id(path), ("ceremony", False, None))
        path += [reply("ceremony", tags=["ceremony"]), user("I wait.")]
        self.assertIsNone(due_id(path))  # orientation waits two turns, the exam waits for the wing
        path += [reply(), user("I wait again.")]
        self.assertEqual(due_id(path)[0], "orientation")
        path += [reply("orientation"), user("I want the knight wing.")]  # the player's words settle the choice
        self.assertEqual(due_id(path), ("exam", False, "A duel."))

    def test_narrator_choice_mark_wins_and_firm_then_given_up(self):
        path = [user("Hello."), reply("ceremony", tags=["ceremony"], choices=[{"choice": "wing", "value": "magic"}])]
        for i in range(2):
            path += [user(f"turn {i}"), reply("exam")]
        path.append(user("again"))
        self.assertEqual(due_id(path), ("exam", True, "A crystal."))  # asked twice without its mark: firmly now
        for i in range(4):
            path += [reply("exam"), user(f"more {i}")]
        prog = story_events.progress(PACK, path)
        self.assertEqual(prog["how"].get("exam"), "given_up")  # never asked forever

    def test_dated_event_follows_the_story_year(self):
        path = [user("a"), reply("ceremony", tags=["ceremony"], choices=[{"choice": "wing", "value": "knight"}]),
                user("b"), reply("exam", tags=["exam"]), user("c")]
        self.assertIsNone(due_id(path, {"month": "November", "day": 30}))
        self.assertEqual(due_id(path, {"month": "December", "day": 21})[0], "final")
        self.assertEqual(due_id(path, {"month": "January", "day": 2})[0], "final")  # still the same school year
        self.assertIsNone(due_id(path, {"month": "March", "day": 2}))
        self.assertIsNone(due_id(path, {}))  # an unknown date never triggers it

    def test_note_and_marks(self):
        d = story_events.due(PACK, story_events.progress(PACK, [user("hi")]), {}, "March")
        note = story_events.narrator_note(d, PACK, lambda cid: cid, "Kaïs")
        self.assertIn("The ceremony.", note)
        self.assertIn("[Event:ceremony]", note)
        self.assertIn("never decide Kaïs's words", note)
        rule = story_events.choice_rule(PACK, {}, "Kaïs")
        self.assertIn("[Choice:wing=option]", rule)
        self.assertEqual(story_events.choice_rule(PACK, {"wing": "knight"}, "Kaïs"), "")
        self.assertIsNone(story_events.choice_from_words(PACK["choices"][0], "knight wing or magic wing?"))

    def test_marks_are_removed_from_the_text_and_put_back_for_the_model(self):
        f = portrait_tags.TagFilter()
        out = f.feed("[Event:ceremony]\nThe hall [Choice:wing=knight] fills.") + f.flush()
        self.assertEqual(out, "The hall fills.")
        self.assertEqual((f.events, f.choices), (["ceremony"], [{"choice": "wing", "value": "knight"}]))
        m = SimpleNamespace(content="The hall fills.", edited_at=None,
                            generation_metadata_json={"event_tags": ["ceremony"]})
        self.assertEqual(portrait_tags.retag(m, m.content, None), "[Event:ceremony]\nThe hall fills.")

    def test_pack_checks(self):
        raw = {"events": [{"id": "a", "brief": "x", "after": ["missing"], "needs_choice": "nope", "variants": {"z": "t"}},
                          {"id": "b"}]}
        rep = pack_manifest._Report()
        events = pack_manifest._events(raw["events"], rep)
        self.assertEqual([e["id"] for e in events], ["a"])
        warnings = rep.warnings + pack_manifest.check_choices({"events": events})
        self.assertTrue(any("missing" in w for w in warnings))
        self.assertTrue(any("unknown choice" in w for w in warnings))
        self.assertTrue(any("unknown option" in w for w in warnings))

    def test_lumencia_pack_is_valid(self):
        root = Path(__file__).resolve().parents[3] / "Lorepack" / "lumencia_academy_lore_pack"
        manifest, report = pack_manifest.load(root)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual([e["id"] for e in manifest["events"]],
                         ["entrance_ceremony", "entrance_exam", "wing_exam", "wing_event", "final_exam"])


class LumenciaFlowTest(AppTestCase):
    def test_ceremony_then_wing_then_artemis(self):
        from story.models import Message
        av = self.post("/avatars", {"name": "Kaïs"})
        story = self.new_story("Événements", world_slug="lumencia_academy", starter_id="enrollment", avatar_id=av["id"])
        sid = story["id"]
        start = self.post(f"/stories/{sid}/start")
        self.wait_reply(sid, start["assistant_message_id"])

        def turn(text):
            t = self.post(f"/stories/{sid}/turns", {"content": text})
            self.wait_reply(sid, t["assistant_message_id"])
            ctx = self.get(f"/stories/{sid}/messages/{t['assistant_message_id']}/context")["context"]
            return t["assistant_message_id"], (ctx.get("planned_event") or {}).get("id")

        mid, asked = turn("Je regarde autour de moi.")
        self.assertEqual(asked, "entrance_ceremony")
        with self.ctx.db.session() as db:  # the narrator played it and marked it
            m = db.get(Message, mid)
            m.generation_metadata_json = {**(m.generation_metadata_json or {}), "event_tags": ["entrance_ceremony"]}
        self.assertEqual(turn("Je veux rejoindre l'aile des chevaliers.")[1], None)
        self.assertEqual(turn("Je me rends à la salle d'entraînement.")[1], "wing_exam")
        full = self.get(f"/stories/{sid}/context?full=true")
        sent = full["system"] + "\n".join(m["content"] for m in full["messages"])
        self.assertIn("one-on-one duel against her", sent)  # Artemis' exam, the Knight wing
        self.assertIn("[Event:wing_exam]", sent)
        self.assertNotIn("[Choice:wing=", full["system"])  # the wing is known: the choice rule is gone
        self.assertIn("events", self.get(f"/stories/{sid}/events"))  # the Journal's timeline keeps its own address
        played = self.get(f"/stories/{sid}/planned-events?lang=fr")["played"]
        self.assertEqual([(p["id"], p["title"]) for p in played], [("entrance_ceremony", "Cérémonie d'entrée")])
        wing = self.get(f"/stories/{sid}/planned-events?lang=fr")["choices"]
        self.assertEqual([(c["value"], c["label"]) for c in wing], [("knight", "aile des Chevaliers")])


if __name__ == "__main__":
    unittest.main()
