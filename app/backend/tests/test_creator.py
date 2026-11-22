"""World creator (Phase 8): a world made in the app is a real lore pack that loads, plays, is copied and shared."""
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import support  # noqa: F401  (puts the backend on sys.path)
from fastapi.testclient import TestClient
from PIL import Image

from story.config import PROJECT_ROOT, Settings
from story.main import create_app

HEADERS = {"X-Story-Client": "1"}


def png(color=(200, 40, 40), size=(1600, 2000)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


class CreatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="storycore_creator_"))
        cls.project = cls.tmp / "project"
        (cls.project / "Lorepack").mkdir(parents=True)
        shutil.copytree(PROJECT_ROOT / "Lorepack" / "hero_chronicle_lore_pack",
                        cls.project / "Lorepack" / "hero_chronicle_lore_pack")
        settings = Settings(data_dir=cls.tmp / "data", secrets_backend="memory", music_dir_override=cls.tmp / "music",
                            project_root=cls.project)
        cls.app = create_app(settings, testing=True)
        cls.client = TestClient(cls.app, headers=HEADERS)
        cls.client.__enter__()
        from story.bundled import sync_lore_packs
        sync_lore_packs(cls.app.state.ctx)

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def call(self, method, path, expect=200, **kw):
        r = self.client.request(method, "/api" + path, **kw)
        self.assertEqual(r.status_code, expect, f"{method} {path}: {r.text[:400]}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r

    def worlds(self):
        return {w["slug"]: w for w in self.call("GET", "/worlds")["worlds"]}

    def test_create_edit_and_play(self):
        pid = self.call("POST", "/creator/worlds", json={"name": "Le Royaume d'Écume"})["id"]
        self.assertEqual(pid, "le_royaume_d_ecume")
        doc = self.call("GET", f"/creator/worlds/{pid}")
        self.assertEqual(doc["characters"], [])
        self.assertIn("Narrator rules", doc["narrator"])

        saved = self.call("PUT", f"/creator/worlds/{pid}", json={
            "summary": "Une cité marchande sur la mer.", "tags": ["Pirates", "Aventure"],
            "premise": "# Écume\n\nUne cité portuaire.",
            "characters": [
                {"id": "", "name": "Mara Vent", "type": "Capitaine", "personality_traits": ["fière"],
                 "hidden": ["Elle est la fille du roi déchu."], "custom_field": "kept"},
                {"id": "", "name": "   "},  # an empty card is not saved
            ],
            "locations": [{"name": "Le Port", "description": "Bruyant."}],
            "groups": [{"name": "La Guilde", "type": "Guilde"}],
            "glossary": [{"term": "Écu", "definition": "La monnaie."}],
            "starters": [{"id": "arrivee", "name": "Arrivée", "blueprint": "Begin on the docks at dawn."}],
            "posts": [{"id": "captain", "title": "Captain of the Port", "character": "mara_vent"}],
        })["world"]
        self.assertEqual([c["id"] for c in saved["characters"]], ["mara_vent"])
        self.assertEqual(saved["characters"][0]["custom_field"], "kept")

        w = self.worlds()[pid]
        self.assertEqual(w["name"], "Le Royaume d'Écume")
        detail = self.call("GET", f"/worlds/{w['id']}")
        text = json.dumps(detail, ensure_ascii=False)
        self.assertIn("Arrivée", text)
        self.assertNotIn("fille du roi", text)  # narrator-only notes never reach the player

        # portraits: converted to webp, at most 1024 px, matched to the character
        self.call("POST", f"/creator/worlds/{pid}/portraits/mara_vent/1", files={"file": ("a.png", png(), "image/png")})
        self.call("POST", f"/creator/worlds/{pid}/portraits/mara_vent/2", files={"file": ("b.png", png(), "image/png")})
        doc = self.call("GET", f"/creator/worlds/{pid}")
        self.assertEqual(doc["portraits"], {"mara_vent": [1, 2]})
        img = self.call("GET", f"/creator/worlds/{pid}/image", params={"path": "images/mara_vent_1.webp"})
        im = Image.open(io.BytesIO(img.content))
        self.assertEqual(im.format, "WEBP")
        self.assertLessEqual(max(im.size), 1024)
        self.call("DELETE", f"/creator/worlds/{pid}/portraits/mara_vent", params={"n": 2})
        self.assertEqual(self.call("GET", f"/creator/worlds/{pid}")["portraits"], {"mara_vent": [1]})
        self.call("POST", f"/creator/worlds/{pid}/cover", files={"file": ("c.png", png(), "image/png")})
        self.assertEqual(self.call("GET", f"/creator/worlds/{pid}")["cover"], "cover.webp")
        self.call("GET", f"/creator/worlds/{pid}/image", params={"path": "cover.webp"})
        self.call("GET", f"/creator/worlds/{pid}/image", expect=404, params={"path": "pack.json"})

        check = self.call("GET", f"/creator/worlds/{pid}/check")
        self.assertTrue(check["ok"], check)

        # a story can be played in it, and then the world cannot be deleted
        story = self.call("POST", "/stories", json={"title": "Test", "world_id": w["id"]})
        self.call("DELETE", f"/creator/worlds/{pid}", expect=400)
        self.call("DELETE", f"/stories/{story['id']}", params={"confirm": "true"})

        # share: export, then import (the id is taken, so the copy gets a new one)
        z = self.call("GET", f"/creator/worlds/{pid}/export")
        with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
            self.assertIn("le_royaume_d_ecume_lore_pack/pack.json", zf.namelist())
        imp = self.call("POST", "/creator/import", files={"file": ("w.zip", z.content, "application/zip")})
        self.assertEqual(imp["id"], "le_royaume_d_ecume_2")
        self.assertTrue(imp["check"]["ok"], imp["check"])
        self.assertIn("le_royaume_d_ecume_2", self.worlds())

        for p in (pid, "le_royaume_d_ecume_2"):
            self.call("DELETE", f"/creator/worlds/{p}")
            self.assertNotIn(p, self.worlds())
        self.assertFalse((self.project / "Lorepack" / f"{pid}_lore_pack").exists())

    def test_place_backgrounds(self):
        # v0.6.2: one picture per place (images/places/<id>.webp), behind the story text while the scene is there
        pid = self.call("POST", "/creator/worlds", json={"name": "Décors"})["id"]
        self.call("PUT", f"/creator/worlds/{pid}", json={
            "characters": [{"id": "", "name": "Mara Vent"}],
            "locations": [{"name": "Le Port"}, {"name": "Grand Phare"}]})
        self.call("POST", f"/creator/worlds/{pid}/places/le_port/image", files={"file": ("p.png", png(size=(3000, 1500)), "image/png")})
        self.call("POST", f"/creator/worlds/{pid}/portraits/mara_vent/1", files={"file": ("a.png", png(), "image/png")})
        doc = self.call("GET", f"/creator/worlds/{pid}")
        self.assertEqual(doc["place_files"], {"le_port": "images/places/le_port.webp"})
        self.assertEqual(doc["portraits"], {"mara_vent": [1]})  # a place picture is not a portrait
        im = Image.open(io.BytesIO(self.call("GET", f"/creator/worlds/{pid}/image",
                                             params={"path": "images/places/le_port.webp"}).content))
        self.assertLessEqual(max(im.size), 1920)
        w = self.worlds()[pid]
        story = self.call("POST", "/stories", json={"title": "Décor", "world_id": w["id"]})
        self.assertIsNone(self.call("GET", f"/stories/{story['id']}/backdrop")["place_id"])  # no place yet
        from story.services import state_service, story_tree
        ctx = self.app.state.ctx
        for loc, want in (("Le Port, au petit matin", "le_port"), ("Grand Phare", None)):  # the lighthouse has no picture
            with ctx.db.session() as db:
                st = story_tree.get_story(db, story["id"])
                b = story_tree.get_branch(db, st)
                cur = state_service.current(db, b.id)
                state = dict(cur.state_json if cur else {})
                state["scene"] = {**(state.get("scene") or {}), "location": loc}
                state_service.save(db, st.id, b.id, state, source="test", summary="place")
            bd = self.call("GET", f"/stories/{story['id']}/backdrop")
            self.assertEqual(bd["place_id"], want, loc)
        self.call("GET", f"/worlds/{w['id']}/places/le_port/image")
        self.call("GET", f"/worlds/{w['id']}/places/grand_phare/image", expect=404)
        self.call("DELETE", f"/creator/worlds/{pid}/places/le_port/image")
        self.assertEqual(self.call("GET", f"/creator/worlds/{pid}")["place_files"], {})
        self.call("DELETE", f"/stories/{story['id']}", params={"confirm": "true"})
        self.call("DELETE", f"/creator/worlds/{pid}")

    def test_copy_a_bundled_pack(self):
        src = self.project / "Lorepack" / "hero_chronicle_lore_pack"
        before = {p.relative_to(src).as_posix(): p.stat().st_mtime_ns for p in src.rglob("*") if p.is_file()}
        self.call("GET", "/creator/worlds/hero_chronicle", expect=400)  # not made with the creator: copy it
        listed = {w["id"]: w for w in self.call("GET", "/creator/worlds")["worlds"]}
        self.assertFalse(listed["hero_chronicle"]["editable"])

        pid = self.call("POST", "/creator/worlds", json={"name": "Ma Chronique", "copy_from": "hero_chronicle"})["id"]
        doc = self.call("GET", f"/creator/worlds/{pid}")
        ids = {c["id"] for c in doc["characters"]}
        self.assertIn("lily", ids)
        self.assertIn("grandel", {x["id"] for x in doc["locations"]})
        self.assertTrue(doc["groups"])
        self.assertTrue(doc["glossary"])
        self.assertTrue(doc["starters"])
        self.assertIn("lily", doc["portraits"])
        self.assertTrue(any(c.get("hidden") for c in doc["characters"]), "narrator-only notes are kept in the copy")
        self.assertIn("Arche", doc["narrator"])

        orig = self.worlds()["hero_chronicle"]
        copy = self.worlds()[pid]
        def total(w):
            return sum(self.call("GET", f"/worlds/{w['id']}")["categories"].values())
        self.assertEqual(total(orig), total(copy))
        check = self.call("GET", f"/creator/worlds/{pid}/check")
        self.assertTrue(check["ok"], check)
        self.assertFalse([w for w in check["warnings"] if "duplicate" in w.lower()], check["warnings"])

        after = {p.relative_to(src).as_posix(): p.stat().st_mtime_ns for p in src.rglob("*") if p.is_file()}
        self.assertEqual(before, after, "the original pack is never changed")
        self.call("DELETE", f"/creator/worlds/{pid}")


    def test_ai_suggestion(self):
        from story.services import creator_assist as ca

        self.assertEqual(ca.parse_json_object('Sure!\n```json\n{"name": "Ana", "hidden": ["x",], "a": "}"}\n```'),
                         {"name": "Ana", "hidden": ["x"], "a": "}"})
        with self.assertRaises(ValueError):
            ca.parse_json_object("no card here")
        draft = ca.clean_draft("character", {"name": " Ana ", "race": "", "personality_traits": ["calme", ""]})
        self.assertEqual(draft, {"name": "Ana", "personality_traits": ["calme"]})
        doc = {"name": "Écume", "premise": "# Écume\nUne cité.", "characters": [{"name": "Mara"}]}
        system, prompt = ca.build_prompt(doc, "character", "un vieux pêcheur", "fr")
        self.assertIn("French", system)
        self.assertIn("Mara", prompt)
        self.assertIn("un vieux pêcheur", prompt)

        pid = self.call("POST", "/creator/worlds", json={"name": "Monde IA"})["id"]
        self.call("POST", f"/creator/worlds/{pid}/assist", expect=400, json={"kind": "spaceship", "idea": "x"})
        # the demo narrator cannot write a card: the player gets a clear message, never a crash
        r = self.client.post(f"/api/creator/worlds/{pid}/assist", json={"kind": "narrator", "idea": "sombre"})
        self.assertIn(r.status_code, (200, 400, 409, 502), r.text)
        self.call("DELETE", f"/creator/worlds/{pid}")


    def test_helpers(self):
        from story.services import pack_editor as pe

        self.assertEqual(pe.slugify("Le Royaume d’Écume"), "le_royaume_d_ecume")
        merged = pe._merge_same_ids([{"id": "a", "name": "A"}, {"id": "a", "type": "Guild", "name": "B"}, {"id": "b"}])
        self.assertEqual(merged, [{"id": "a", "name": "A", "type": "Guild"}, {"id": "b"}])
        with tempfile.TemporaryDirectory() as tmp:  # portraits named lily_1, lily_01 or lily/1 are all found
            images = Path(tmp) / "images"
            (images / "kai").mkdir(parents=True)
            for rel in ("lily_1.webp", "lily_02.webp", "kai/3.png", "notes.txt"):
                (images / rel).write_bytes(b"x")
            self.assertEqual(pe.portraits(images), {"lily": [1, 2], "kai": [3]})
            self.assertEqual(pe.portrait_files(Path(tmp), images)["kai"], {3: "images/kai/3.png"})


    def test_lore_sent_to_the_narrator_is_compact(self):
        """Phase 9: no AI instructions retrieved as lore; records without id/name/bookkeeping lines."""
        from sqlalchemy import select
        from story.models import LoreChunk, World
        from story.services.lore_import import record_text

        with self.app.state.ctx.db.session() as db:
            w = db.scalar(select(World).where(World.slug == "hero_chronicle"))
            chunks = list(db.scalars(select(LoreChunk).where(LoreChunk.world_id == w.id)))
            self.assertTrue(chunks)
            self.assertFalse([c.title for c in chunks if c.title.startswith("narrative_system_prompt")])
            lily = next(c for c in chunks if c.entity_id == "lily")
            self.assertNotIn("\nid:", "\n" + lily.content)
            self.assertNotIn("name: Lily", lily.content)
        text = record_text({"id": "x", "name": "X", "confidence": "high", "appearance": {"hair": "red", "eyes": "green"}})
        self.assertEqual(text, "appearance: hair: red; eyes: green")
        self.assertTrue(record_text({"id": "y", "confidence": "low", "notes": "n"}).startswith("[confidence: low]"))


if __name__ == "__main__":
    unittest.main()
