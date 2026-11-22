"""v0.6.2: rewrite one paragraph of a reply (a proposal first, then the kept text saved as an edit)."""
from support import AppTestCase
from story.services import rewrite


class RewriteTest(AppTestCase):
    import_packs = False

    def test_clean_and_replace(self):
        self.assertEqual(rewrite.clean("```\n[Lily:2] « Bonjour. »\n```"), "« Bonjour. »")
        self.assertEqual(rewrite.clean("Voici le paragraphe réécrit :\nIl pleut.\n<info>\nlieu: cour\n</info>"), "Il pleut.")
        text = "Un.\n\nDeux.\n\n\nTrois."
        self.assertEqual(rewrite.split(text), ["Un.", "Deux.", "Trois."])
        self.assertEqual(rewrite.replace(text, 1, " Autre. "), "Un.\n\nAutre.\n\n\nTrois.")

    def test_propose_then_keep(self):
        story = self.new_story("Rewrite", world_slug=None)
        sid = story["id"]
        r = self.post(f"/stories/{sid}/start")
        mid = r["assistant_message_id"]
        self.wait_reply(sid, mid)
        before = next(m for m in self.get(f"/stories/{sid}/messages")["messages"] if m["id"] == mid)["content"]
        parts = rewrite.split(before)
        out = self.post(f"/stories/{sid}/messages/{mid}/rewrite", {"paragraph": 1, "instruction": "plus sombre"})
        self.assertEqual(out["original"], parts[1])
        self.assertTrue(out["text"])
        after = self.get(f"/stories/{sid}/messages")["messages"]
        self.assertEqual(next(m for m in after if m["id"] == mid)["content"], before)  # nothing saved yet
        m = self.post(f"/stories/{sid}/messages/{mid}/rewrite", {"paragraph": 1, "keep": "Un nouveau paragraphe."})
        self.assertEqual(rewrite.split(m["content"])[1], "Un nouveau paragraphe.")
        self.assertEqual(rewrite.split(m["content"])[0], parts[0])
        self.assertGreaterEqual(m.get("version_count") or 0, 1)  # the edit history can bring the old text back
        r = self.client.post(f"/api/stories/{sid}/messages/{mid}/rewrite", json={"paragraph": 99})
        self.assertEqual(r.status_code, 400)
