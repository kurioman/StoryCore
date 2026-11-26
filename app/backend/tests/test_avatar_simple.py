"""The simple avatar (Nov 2026): older profiles are folded into name / appearance / abilities / player note."""
import unittest

from story.services.avatar_profile import simplify
from story.services.context_builder import render_avatar


class SimpleAvatarTest(unittest.TestCase):
    def test_old_fields_go_to_the_player_note(self):
        old = {"display_name": "Kael", "age": "24", "appearance": {"description": "Tall.", "structured": {"hair": "black"}},
               "backstory": "Exiled knight.", "powers": "Fire magic", "stats": [{"label": "HP", "value": 10}]}
        p, name = simplify(old, "My hero")
        self.assertEqual(name, "Kael")
        self.assertEqual(p["format"], 2)
        self.assertEqual(p["appearance"]["description"], "Tall. (hair: black)")
        self.assertEqual(p["abilities"], "Fire magic")
        self.assertIn("Age: 24", p["user_note"])
        self.assertIn("Backstory: Exiled knight.", p["user_note"])
        self.assertEqual(p["stats"], old["stats"])  # kept for the advanced options
        self.assertEqual(simplify(p, name), (p, name))  # idempotent

    def test_render_simple_avatar(self):
        text = render_avatar({"name": "Kael", "profile": {"format": 2, "appearance": {"description": "Tall."},
                                                          "abilities": "Fire magic", "user_note": "Now a knight."}})
        self.assertIn("Name: Kael", text)
        self.assertIn("Abilities: Fire magic", text)
        self.assertIn("Now a knight.", text)


if __name__ == "__main__":
    unittest.main()
