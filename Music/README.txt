STORYCORE MUSIC LIBRARY
=======================

One music library for the whole app, shared by every story. Lore packs never ship music: they can only pick from here.

Easiest: open StoryCore > Music (left bar). Add .mp3 files (button or drag and drop), listen, rename, add tags.

By hand: put the audio files in this folder and list them in library.json:
  {"id": "warm_hearth", "file": "warm_hearth.mp3", "title": "Warm hearth", "tags": ["tavern", "inn"],
   "artist": "", "license": ""}
Tags: the app's list (calm, combat, final_battle, romance, funny, forest, city, inn, tavern, cave, scary...) or your own.

During a story the narrator writes a hidden music tag when the mood or the place changes ([Music:combat]); without one,
the scene's place chooses (a tavern plays a "tavern" track). Only share music you are allowed to share.
