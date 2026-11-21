"""Step 1 of the plan after the 50-turn test (Lumencia, Rocinante 12B, 19/11/2026): no broken reply reaches the screen
or the history sent to the model. The replies below are copied from that story ("Claude Test - Lumencia 50 turns EN")."""
import asyncio
import unittest

import support  # noqa: F401  (puts the backend on sys.path)

from story.services import context_builder, reply_cleanup
from story.services.runtime import length_cap

ME = {"Kurio", "Kai"}

# turn 7 (#14 / #15): the reply opened by telling the player's action again, in the second person
T7_PLAYER = 'I return to my seat next to Lilia and quietly ask her, "So, which wing are you hoping for? You look like a fighter."'
T7_REPLY = ('```\n\nYou return to your seat next to Lilia and quietly ask her, "So, which wing are you hoping for? You look '
            'like a fighter."\n\nLilia turns to you with a surprised look on her face. She seems pleased that you noticed '
            'her martial prowess.\n\n"Really? I\'m not sure if I should be flattered or insulted," she jokes. "But yes, I do '
            'hope to get placed in the Knight Department."')
# turn 27 (#54 / #55): the first sentence only, then the story goes on in the same paragraph
T27_PLAYER = ("I grab Rena and Sia by the wrists and sprint out of the tower door, slamming it shut behind us. We run "
              "across the courtyard toward the faculty building, shouting for help.")
T27_REPLY = ("```\nYou grab Rena and Sia by the wrists and sprint out of the tower door, slamming it shut behind you. The "
             "sounds of pursuit echo from within as you race across the courtyard.\n\n\"Kurio, what's going on? Who were "
             "those people?\" Sia cries out, her voice trembling with fear.")
# turn 26 (#53), turn 33 (#67, first version), turn 39 (#79, first version): nothing but notes or the player's turn
T26_REPLY = "```\n[The scene continues in the next message. Please wait for my response before sending another message.]"
T33_REPLY = "```\n[The player's turn]\n```"
T39_PLAYER = ('"We stay out of the professors\' way." I pull Sia behind a stone pillar and keep a shield up while the '
              'faculty clash with the cultists.')
T39_REPLY = "```\n[The player's turn]\n" + T39_PLAYER
# turn 49 (#99): the label, then a real reply
T49_REPLY = ("```\n[The player's turn]\nYou walk into the dining hall, the smell of breakfast foods wafting towards you. "
             "Students in uniform mill about, some chatting animatedly while others focus on their meals.\n\n"
             "\"Good morning, Kurio! Sleep well?\"")


class FencesAndLabelsTest(unittest.TestCase):
    def test_code_fences_are_removed(self):
        text, _s, report = reply_cleanup.clean(T27_REPLY, [], player_turn="", protagonist=ME)
        self.assertNotIn("```", text)
        self.assertTrue(text.startswith("You grab Rena"), text)
        self.assertEqual(report["code_fences"], 1)
        closed = "```text\nLilia smiles.\n\n\"Morning.\"\n```"
        self.assertEqual(reply_cleanup.clean(closed, [])[0], "Lilia smiles.\n\n\"Morning.\"")

    def test_the_label_goes_and_the_story_stays(self):
        text, _s, report = reply_cleanup.clean(T49_REPLY, [], protagonist=ME)
        self.assertTrue(text.startswith("You walk into the dining hall"), text)
        self.assertNotIn("[The player", text)
        self.assertEqual(report["technical_lines"], 1)

    def test_replies_without_story(self):
        for reply, player in ((T26_REPLY, "Everyone out, now!"), (T33_REPLY, "I fire a bolt at his wrist."),
                              (T39_REPLY, T39_PLAYER)):
            self.assertFalse(reply_cleanup.has_story(reply, player, ME), reply)
        self.assertTrue(reply_cleanup.has_story(T49_REPLY, "I head to the dining hall.", ME))
        self.assertTrue(reply_cleanup.has_story(T7_REPLY, T7_PLAYER, ME))

    def test_tags_and_story_brackets_are_kept(self):
        reply = "[Music:battle]\nThe door bursts open.\n\n[Lilia:4] \"Get down!\""
        self.assertEqual(reply_cleanup.clean(reply, [])[0], reply)

    def test_the_app_notes_are_removed(self):
        reply = ("<narrator-note>Story only, in the third person.</narrator-note>\nLilia laughs.\n</context>")
        self.assertEqual(reply_cleanup.clean(reply, [])[0], "Lilia laughs.")


class EchoTest(unittest.TestCase):
    def test_the_whole_copied_opening_goes(self):
        text, spans, report = reply_cleanup.clean(T7_REPLY, [], player_turn=T7_PLAYER, protagonist=ME)
        self.assertTrue(text.startswith("Lilia turns to you"), text)
        self.assertIn("player_echo_chars", report)

    def test_only_the_copied_sentence_goes(self):
        text, _s, _r = reply_cleanup.clean(T27_REPLY, [], player_turn=T27_PLAYER, protagonist=ME)
        self.assertTrue(text.startswith("The sounds of pursuit"), text)

    def test_third_person_echo(self):
        player = "I adjust the strap of my satchel and look around for anyone who seems to be guiding new students."
        reply = ("Kurio adjusted the strap of his satchel and looked around for anyone guiding new students.\n\n"
                 "A tall girl with white hair raised a hand. \"First-years, this way.\"")
        text, _s, _r = reply_cleanup.clean(reply, [], player_turn=player, protagonist=ME)
        self.assertTrue(text.startswith("A tall girl"), text)

    def test_a_reply_that_uses_some_of_the_same_words_is_kept(self):
        player = "As the leader raises his dagger, I fire a focused bolt of light at his wrist to make him drop it."
        reply = ("The bolt slams into the cultist leader's wrist. He hisses in pain and the dagger clatters on the "
                 "flagstones.\n\n\"You dare strike me, mortal?\"")
        self.assertEqual(reply_cleanup.clean(reply, [], player_turn=player, protagonist=ME)[0], reply)


class RepetitionTest(unittest.TestCase):
    def test_lookback_is_eight_replies(self):
        self.assertEqual(reply_cleanup.LOOKBACK, 8)
        para = ("The cultists press forward, dark energy crackling around their fists as they seek to overwhelm the "
                "makeshift defense.")
        earlier = [para] + ["Something else happens in the courtyard, quite different each time %d." % i for i in range(6)]
        text, _s, report = reply_cleanup.clean(f"Artemis raises her sword.\n\n{para}", earlier)
        self.assertEqual(text, "Artemis raises her sword.")

    def test_a_short_line_said_again_is_removed(self):
        earlier = ['The leader snarls. "You shall pay dearly for this!"']
        reply = 'Artemis parries the blow.\n\n"You shall pay dearly for this!"\n\nThe tower shakes.'
        text, _s, report = reply_cleanup.clean(reply, earlier)
        self.assertEqual(text, "Artemis parries the blow.\n\nThe tower shakes.")
        self.assertEqual(report["repeated_lines"], 1)
        short = 'Lilia nods.\n\n"Thank you."'  # too short to be a repetition worth removing
        self.assertEqual(reply_cleanup.clean(short, ['"Thank you."'])[0], short)


class HistoryAndRulesTest(unittest.TestCase):
    def test_history_sent_without_fences_and_labels(self):
        self.assertEqual(reply_cleanup.strip_for_history(T49_REPLY).split("\n")[0][:30], "You walk into the dining hall,")
        self.assertNotIn("```", reply_cleanup.strip_for_history(T7_REPLY))

    def test_third_person_rules_by_default(self):
        prof = context_builder.PROMPT_PROFILES[context_builder.DEFAULT_PROMPT_PROFILE]
        rules = prof["rules"].format(name="Kurio")
        self.assertIn("third person", rules)
        self.assertNotIn('when you write "you", that is', rules)
        self.assertNotIn("OOC", prof["reminder"])
        self.assertNotIn("player's turn", context_builder.TURN_CLOSE.lower())

    def test_word_targets_get_a_tighter_ceiling(self):
        self.assertEqual(length_cap("medium (3–4 paragraphs)"), 650)
        self.assertEqual(length_cap("medium (3–4 paragraphs)", words=True), 440)
        self.assertLess(length_cap("short", words=True), length_cap("long", words=True))


if __name__ == "__main__":
    unittest.main()
