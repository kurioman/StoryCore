"""Music library (v1.8): one library for the whole app, in <project>/Music, described by Music/library.json.

* Tracks have a title and tags (TAGS below, plus any custom tag). The player adds them in the app (Music page) or by
  copying files and editing library.json.
* A lore pack never ships music. It may only pick from the library: pack.json "music" can switch music off for its
  world, pin tracks for some tags, and name a default tag. Without a pick, a random track with the wanted tag plays.
* During a story the narrator writes a hidden music tag ([Music:combat]) when the mood or place changes; it is removed
  from the text like the portrait tags (portrait_tags.TagFilter). Without one, the scene's location suggests a tag
  (a tavern -> "tavern"). Otherwise the music keeps going.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIO_EXTS = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".wav": "audio/wav"}
MAX_BYTES = 60 * 1024 * 1024
LIBRARY = "library.json"
NARRATOR_TAG_LIFETIME = 8  # replies: after that, the scene's location chooses again
MUSIC_TAG = re.compile(r"\[\s*(?:music|musique|bgm)\s*[:|]\s*([A-Za-zÀ-ÿ0-9 _\-]{2,40}?)\s*\]", re.IGNORECASE)

# id, group, English label, French label
_TAGS = [
    # mood
    ("calm", "mood", "Calm", "Calme"), ("peaceful", "mood", "Peaceful", "Paisible"), ("happy", "mood", "Happy", "Joyeux"),
    ("funny", "mood", "Funny", "Drôle"), ("romance", "mood", "Romance", "Romance"), ("sad", "mood", "Sad", "Triste"),
    ("melancholic", "mood", "Melancholic", "Mélancolique"), ("mysterious", "mood", "Mysterious", "Mystérieux"),
    ("scary", "mood", "Scary", "Effrayant"), ("tense", "mood", "Tense", "Tension"), ("dark", "mood", "Dark", "Sombre"),
    ("epic", "mood", "Epic", "Épique"), ("heroic", "mood", "Heroic", "Héroïque"), ("hopeful", "mood", "Hopeful", "Plein d'espoir"),
    ("solemn", "mood", "Solemn", "Solennel"), ("dreamy", "mood", "Dreamy", "Onirique"), ("emotional", "mood", "Emotional", "Émouvant"),
    # action
    ("action", "action", "Action", "Action"), ("combat", "action", "Combat", "Combat"),
    ("final_battle", "action", "Final battle", "Combat final"), ("boss", "action", "Boss", "Boss"),
    ("chase", "action", "Chase", "Poursuite"), ("duel", "action", "Duel", "Duel"), ("war", "action", "War", "Guerre"),
    ("stealth", "action", "Stealth", "Infiltration"), ("victory", "action", "Victory", "Victoire"),
    ("defeat", "action", "Defeat", "Défaite"), ("danger", "action", "Danger", "Danger"),
    # places
    ("forest", "place", "Forest", "Forêt"), ("city", "place", "City", "Ville"), ("village", "place", "Village", "Village"),
    ("inn", "place", "Inn", "Auberge"), ("tavern", "place", "Tavern", "Taverne"), ("cave", "place", "Cave", "Grotte"),
    ("castle", "place", "Castle", "Château"), ("palace", "place", "Palace", "Palais"), ("dungeon", "place", "Dungeon", "Donjon"),
    ("academy", "place", "Academy", "Académie"), ("temple", "place", "Temple", "Temple"), ("sea", "place", "Sea", "Mer"),
    ("desert", "place", "Desert", "Désert"), ("mountain", "place", "Mountain", "Montagne"), ("snow", "place", "Snow", "Neige"),
    ("market", "place", "Market", "Marché"), ("countryside", "place", "Countryside", "Campagne"),
    ("ruins", "place", "Ruins", "Ruines"), ("demon_realm", "place", "Demon realm", "Royaume démoniaque"),
    ("heaven", "place", "Heaven", "Céleste"), ("night", "place", "Night", "Nuit"),
    # moments
    ("exploration", "moment", "Exploration", "Exploration"), ("travel", "moment", "Travel", "Voyage"),
    ("daily_life", "moment", "Daily life", "Vie quotidienne"), ("festival", "moment", "Festival", "Fête"),
    ("ceremony", "moment", "Ceremony", "Cérémonie"), ("training", "moment", "Training", "Entraînement"),
    ("investigation", "moment", "Investigation", "Enquête"), ("rest", "moment", "Rest", "Repos"),
    ("intrigue", "moment", "Intrigue", "Intrigue"), ("prologue", "moment", "Prologue", "Prologue"),
    ("ending", "moment", "Ending", "Fin"), ("menu", "moment", "Menu", "Menu"),
]
TAGS = [{"id": i, "group": g, "label": {"en": en, "fr": fr}} for i, g, en, fr in _TAGS]
TAG_IDS = {t["id"] for t in TAGS}
GROUPS = [{"id": "mood", "label": {"en": "Mood", "fr": "Ambiance"}}, {"id": "action", "label": {"en": "Action", "fr": "Action"}},
          {"id": "place", "label": {"en": "Places", "fr": "Lieux"}}, {"id": "moment", "label": {"en": "Moments", "fr": "Moments"}}]

# words in a scene's location (or its lore type) that suggest a place tag, when the narrator wrote no music tag
PLACE_WORDS = {
    "tavern": ("tavern", "taverne", "pub", "bar"), "inn": ("inn", "auberge"), "forest": ("forest", "forêt", "woods", "grove", "bois"),
    "cave": ("cave", "grotte", "cavern", "caverne"), "palace": ("palace", "palais", "throne", "trône", "avalon", "royal"),
    "castle": ("castle", "château", "fortress", "forteresse", "citadel"), "academy": ("academy", "académie", "school", "école", "classroom", "dormitory", "campus"),
    "temple": ("temple", "church", "église", "cathedral", "cathédrale", "shrine", "sanctuary"), "dungeon": ("dungeon", "donjon", "labyrinth", "crypt", "crypte", "prison"),
    "sea": ("sea", "ocean", "océan", "beach", "plage", "port", "harbor", "harbour", "mer"), "desert": ("desert", "désert", "dune"),
    "mountain": ("mountain", "montagne", "peak", "pic", "caldera"), "snow": ("snow", "neige", "frozen", "glacier"),
    "market": ("market", "marché", "bazaar", "bazar"), "village": ("village", "hamlet", "hameau"),
    "city": ("city", "ville", "capital", "capitale", "town", "street", "rue", "district", "quartier"),
    "ruins": ("ruin", "ruine"), "demon_realm": ("demon realm", "royaume démon", "demon king", "roi démon", "nightmares"),
    "heaven": ("white space", "espace blanc", "heaven", "paradis", "divine realm"),
}


_FOLDER: Path | None = None  # set by main.create_app (settings.music_dir)


def set_folder(folder: Path) -> None:
    global _FOLDER
    _FOLDER = folder


def folder() -> Path:
    if _FOLDER is None:
        from ..config import PROJECT_ROOT
        return PROJECT_ROOT / "Music"
    return _FOLDER


def norm_tag(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(t).strip().lower()).strip("_")[:40]


def tag_for(text: str) -> str | None:
    """A narrator's [Music:...] tag value (any language label) -> tag id."""
    key = norm_tag(text)
    if key in TAG_IDS:
        return key
    for t in TAGS:
        if key in {norm_tag(t["label"]["en"]), norm_tag(t["label"]["fr"])}:
            return t["id"]
    return key or None


# --------------------------------------------------------------------------- library file
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(folder: Path) -> dict[str, Any]:
    f = folder / LIBRARY
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except (OSError, ValueError):
        data = {}
    tracks = [t for t in data.get("tracks", []) if isinstance(t, dict) and t.get("id") and t.get("file")]
    for t in tracks:
        t["tags"] = [norm_tag(x) for x in t.get("tags") or [] if norm_tag(x)]
        t["available"] = (folder / t["file"]).is_file()
    return {"format_version": 1, "tracks": tracks}


def save(folder: Path, lib: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    clean = {"format_version": 1, "_comment": "StoryCore music library: edit in the app (Music page) or by hand.",
             "tracks": [{k: v for k, v in t.items() if k != "available"} for t in lib["tracks"]]}
    tmp = folder / (LIBRARY + ".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(folder / LIBRARY)


def _unique_id(lib: dict[str, Any], base: str) -> str:
    ids = {t["id"] for t in lib["tracks"]}
    base = norm_tag(base) or "track"
    cand, n = base, 2
    while cand in ids:
        cand, n = f"{base}_{n}", n + 1
    return cand


def add(folder: Path, filename: str, data: bytes, *, title: str = "", tags: list[str] | None = None) -> dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext not in AUDIO_EXTS:
        raise ValueError(f"\"{filename}\": use an .mp3 file (also accepted: {', '.join(sorted(AUDIO_EXTS))}).")
    if not data:
        raise ValueError(f"\"{filename}\" is empty.")
    if len(data) > MAX_BYTES:
        raise ValueError(f"\"{filename}\" is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    lib = load(folder)
    stem = Path(filename).stem
    tid = _unique_id(lib, stem)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{tid}{ext}"
    (folder / name).write_bytes(data)
    track = {"id": tid, "file": name, "title": (title or stem.replace("_", " ").strip())[:120],
             "tags": [norm_tag(t) for t in tags or [] if norm_tag(t)], "artist": "", "license": "", "added_at": _now()}
    lib["tracks"].append(track)
    save(folder, lib)
    return {**track, "available": True}


def update(folder: Path, tid: str, changes: dict[str, Any]) -> dict[str, Any]:
    lib = load(folder)
    t = next((x for x in lib["tracks"] if x["id"] == tid), None)
    if t is None:
        raise KeyError(tid)
    for k in ("title", "artist", "license"):
        if isinstance(changes.get(k), str):
            t[k] = changes[k].strip()[:200]
    if isinstance(changes.get("tags"), list):
        t["tags"] = list(dict.fromkeys(norm_tag(x) for x in changes["tags"] if norm_tag(x)))
    save(folder, lib)
    return t


def delete(folder: Path, tid: str) -> None:
    lib = load(folder)
    t = next((x for x in lib["tracks"] if x["id"] == tid), None)
    if t is None:
        raise KeyError(tid)
    lib["tracks"].remove(t)
    save(folder, lib)
    f = folder / t["file"]
    if f.is_file() and f.resolve().parent == folder.resolve():
        f.unlink()


def file_of(folder: Path, tid: str) -> Path | None:
    t = next((x for x in load(folder)["tracks"] if x["id"] == tid), None)
    if not t:
        return None
    f = (folder / t["file"]).resolve()
    return f if f.is_file() and folder.resolve() in f.parents else None


# --------------------------------------------------------------------------- narrator instruction
def instruction(folder: Path) -> str:
    """Narrator rule: only the tags that have music in the library (nothing when the library is empty)."""
    used = sorted({tag for t in load(folder)["tracks"] if t["available"] for tag in t["tags"]})
    if not used:
        return ""
    return ("Background music: at the very start of the story, and later only when the mood or the place clearly "
            "changes, write one music tag on its own line before the text: [Music:tag], with one tag from this list: "
            f"{', '.join(used)}. Do not repeat it while the mood stays the same. The app removes it before the player "
            "reads the text and plays a matching track.")


# --------------------------------------------------------------------------- choosing the music of a story
def pack_settings(world: Any) -> dict[str, Any]:
    raw = (((world.data_json or {}).get("pack") or {}).get("music")) if world is not None else None
    if raw is False:
        return {"enabled": False, "choices": {}, "default": None}
    raw = raw if isinstance(raw, dict) else {}
    choices = raw.get("choices") if isinstance(raw.get("choices"), dict) else {}
    return {"enabled": raw.get("enabled", True) is not False,
            "choices": {norm_tag(k): [str(x) for x in v] for k, v in choices.items() if isinstance(v, list)},
            "default": norm_tag(raw["default"]) if isinstance(raw.get("default"), str) else None}


def place_tag(text: str) -> str | None:
    low = f" {str(text or '').lower()} "
    for tag, words in PLACE_WORDS.items():
        if any(w in low for w in words):
            return tag
    return None


def pick(tracks: list[dict[str, Any]], tag: str | None, settings: dict[str, Any], seed: str) -> dict[str, Any] | None:
    """The pack's pinned tracks for the tag first, else a track with the tag, else nothing. Stable for a given seed."""
    usable = [t for t in tracks if t["available"]]
    pool: list[dict[str, Any]] = []
    if tag:
        pinned = settings["choices"].get(tag) or []
        pool = [t for t in usable if t["id"] in pinned] or [t for t in usable if tag in t["tags"]]
    if not pool:
        return None
    h = int(hashlib.sha1(seed.encode()).hexdigest(), 16)
    return pool[h % len(pool)]


def for_story(folder: Path, world: Any, replies: list[Any], scene: dict[str, Any], location_type: str = "",
              skip: int = 0) -> dict[str, Any]:
    """What should play now. replies: the story's assistant replies on the active branch, oldest first."""
    settings = pack_settings(world)
    tracks = load(folder)["tracks"]
    if not settings["enabled"]:
        return {"enabled": False, "reason": "pack"}
    if not any(t["available"] for t in tracks):
        return {"enabled": True, "track": None, "reason": "empty_library"}
    tag, source, since = None, None, ""
    # the latest music tag the narrator wrote, if it is recent (an old one is stale: the scene has moved on since)
    for age, m in enumerate(reversed(replies)):
        tags = (m.generation_metadata_json or {}).get("music_tags") or []
        if tags:
            if age < NARRATOR_TAG_LIFETIME:
                tag, source, since = tag_for(tags[-1]["tag"]), "narrator", m.id
            break
    loc_tag = place_tag(f"{scene.get('location') or ''} {location_type}")
    if loc_tag and tag is None:
        tag, source, since = loc_tag, "location", f"loc:{scene.get('location')}"
    if tag is None and settings["default"]:
        tag, source, since = settings["default"], "pack_default", "default"
    story_seed = getattr(replies[0], "story_id", "") if replies else ""
    track = pick(tracks, tag, settings, f"{story_seed}|{tag}|{since}|{skip}")
    if track is None:  # nothing with that tag: any track, so there is always music when the library has some
        usable = [t for t in tracks if t["available"]]
        h = int(hashlib.sha1(f"{story_seed}|any|{since}|{skip}".encode()).hexdigest(), 16)
        track, source = usable[h % len(usable)], (source or "any")
    return {"enabled": True, "tag": tag, "source": source,
            "track": {k: track[k] for k in ("id", "title", "tags", "artist")}}

