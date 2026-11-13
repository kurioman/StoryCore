# StoryCore v1.7.0 for Windows

## What this is

StoryCore is a local interactive-fiction engine. You play one character and an AI narrates the world around you. Each story world is a **lore pack**: a folder in `Lorepack` with a `pack.json` and its lore files (see `LOREPACK_FORMAT.md`). Every pack there is loaded automatically at start. It comes with two worlds: **Hero's Chronicle** (heroic fantasy: a summoned hero, the Central Empire, the holy nation of Lumina and the Demon Realm, 21 characters) and **Lumencia Academy** (a fantasy academy with about 30 characters). Both have six portrait expressions per character. Anyone can add a new world by adding a folder; developers should read the `DEVONLY` folder.

The app runs on your own PC and opens in your web browser. It keeps track of your story, the characters you meet, relationships, a journal and memory.

It is a free, independent, unofficial fan project. See `CREDITS.md`. Please do not re-share it without asking the person who gave it to you.

## Windows requirements

- 64-bit Windows 10 or 11. It was tested on Windows 11.
- A current browser such as Edge, Chrome or Firefox.
- About 300 MB of free disk space, plus room for your stories and backups.
- Internet access if you use OpenRouter. Not needed with LM Studio, Ollama or the Mock narrator.

You do **not** need to install Python or Node.js. The app brings its own copy of Python.

## Extract the ZIP

1. Right-click the ZIP and choose **Extract All...**
2. Pick a normal folder that you can write to, such as Documents or Desktop.
3. Wait for it to finish. There are several thousand small files, so this can take a minute or two.

Avoid `Program Files`, because the app must be able to write its `data` folder next to itself. Spaces and accented letters in the folder path are fine.

If you want to avoid some Windows warnings, right-click the ZIP before extracting, choose **Properties**, tick **Unblock** if it is shown, and press OK.

## Start the app

1. Open the `StoryCore` folder.
2. Double-click **`Start StoryCore.bat`**.
3. If Windows shows "Windows protected your PC", choose **More info**, then **Run anyway**. This appears because the app is not code-signed.
4. A black window opens, and your browser opens the app shortly after. The first start can take up to a minute.

Keep the black window open while you play. It is the app. To stop, close that window or press Ctrl+C in it. Finish or stop any reply first.

## First-run setup

On the first start the app creates an empty `data` folder and loads the bundled lore and portraits by itself. There are no stories, characters of yours or API keys in a new copy.

The built-in **Mock narrator** is selected at first. It works offline and writes clearly labelled demo text and suggestions so you can look around. It cannot read the story, so it shows no character portraits or relationship changes. For a real story, connect a model: LM Studio, Ollama (both local and free) or OpenRouter (hosted), as described below.

The complete experience is on by default, so once a model is connected everything works by itself. You can change any of it afterwards.

## Create a story

1. Choose **New story** on the home page.
2. Go through the five steps: **Story**, **World & start**, **Protagonist**, **Tone & model**, **Review**.
3. In **World & start**, choose a **World** (for example **Hero's Chronicle**). "No preset world" gives you a story with no lore. Then pick a start; each world offers its own openings. On **Protagonist**, the **World default** stat sheet uses the world's own stats.
4. In **Review**, choose **Create & preview first context**, then **Generate the opening scene**.
5. Write what your character does in the message box at the bottom and press Enter.

The **?** Help button in the sidebar gives a short tour of the rest.

## What happens after each reply

**Portraits appear as soon as a reply ends.** The narrator marks each character's spoken line with a small portrait
tag (for example `[Selphina:3]` = Selphina, sad). The app removes the tag before you read the text and shows the
matching portrait: 1 neutral, 2 happy / smiling, 3 sad / sobbing, 4 angry / aggressive, 5 disdain / disgust,
6 love / shy.

Then, by default, the app reads the scene and:

- **Completes the portraits** of characters who react without speaking, and anyone the narrator forgot to tag.
- **Can write three suggested replies** in your character's voice (off by default; turn on **Suggest three replies** in **Settings > Memory capture**). Picking one only fills the message box, so you can edit it. Nothing is sent until you press Send, and text you have already typed is never replaced without asking.
- **Updates relationships** when something clear happens: trust, affection, respect, familiarity, rivalry and fear. Small changes apply at once; big ones wait for your review. Every change keeps its reason.

An incomplete reply is not analysed. If the analysis fails, your reply stays, and you see the reason and a **Retry** button.

## Settings you can change

Everything below is in **Settings > Memory capture**, and your choices are kept.

| Setting | Options | Default |
|---|---|---|
| Run scene analysis | Automatic (every model, including hosted ones), Local models only, Off | Automatic |
| Relationship changes | Automatic, Review every change, Off | Automatic |
| Where portraits appear | Story text and above the message box, Story text only, Above the message box only, Hidden | Both |
| Suggest three replies | On, Off | Off |
| Update portrait expressions automatically | On, Off | On |

Scene analysis powers suggestions, relationship tracking and expression changes, so they stop while it is off. With **Local models only**, replies from hosted models are not analysed, and the app says so under the reply. Turning one feature off leaves the others running. **Relationship changes: Off** keeps your existing relationships as they are.

**Interface language** (Settings > Appearance, new interface): English or French. It changes menus, buttons and help; the lore stays in the language of its pack.

**Story language** (Settings > Narration & context, new interface): English by default, or French. The narrator then writes the story in French; character names and lore stay as the pack writes them. Each story can override it in its options (the sliders button above the story). French prose quality depends on your model: small local models usually write best in English.

**Token settings** are in **Settings > Narration & context** and in each model's parameters:

| Setting | Default | What it does |
|---|---|---|
| Context budget | 10000 tokens | The most a request may use |
| Reserved for the reply | 2000 tokens | Kept free of story context when a request is planned. It does not limit the reply |
| Max output tokens | 3000 tokens | The real limit on a reply. You only pay for what is written |
| Output length | Medium | How long the narrator aims to write |
| Thinking (story replies) | Off | Hidden reasoning shares the output limit with the story, so it stays off unless you turn it on |

On a local model, the 3000 limit applies when the model's window is 16,384 tokens or more. In a smaller or unknown window the model keeps 1024, because a larger limit would cost story context.

## OpenRouter account and API key

OpenRouter gives access to hosted AI models. You need your own account; nothing is shared with you by StoryCore.

1. Create an account at [openrouter.ai](https://openrouter.ai/).
2. Add a small amount of credit if your chosen model is not free. See [pricing](https://openrouter.ai/pricing).
3. Create an API key on the [keys page](https://openrouter.ai/settings/keys). **Set a spending limit on the key.** That limit is your real protection, not anything in this app.
4. In the app, open **Settings > Providers & models**. Paste the key in the OpenRouter guide and press **Save key**.
5. Press **Select** on a model card. To use a model in a story, pick it from the top bar of that story.
6. Press **Test connection**. This checks your key and costs nothing. **Test model** sends a small paid request, and asks first.

Anyone with your key can spend your credit, so never paste it into a story or a public post. The first time you use a cloud provider the app asks for your approval, because story content will be sent to it.

### Possible API costs

- OpenRouter bills you by tokens. The bill is between you and OpenRouter. StoryCore itself costs nothing.
- One turn makes several requests: the reply, scene analysis, and memory capture. Each is billed on a paid model. Turning scene analysis or memory capture off removes that request.
- Long stories send more context, so turns get more expensive as a story grows.
- Prices and model availability change. The app shows live prices in Settings, but they can differ by the provider OpenRouter routes to.
- Check what you actually spent on your [OpenRouter activity page](https://openrouter.ai/activity).

## LM Studio (local models)

LM Studio runs models on your own PC, with no API cost and no story text leaving your computer.

1. Install LM Studio from [lmstudio.ai](https://lmstudio.ai/), download a model and load it. Set its **Context Length** (8192 or more is a good start).
2. In LM Studio, open the **Developer** tab and start the local server (it listens on port 1234).
3. In StoryCore, open **Settings > Providers & models**, then under **All providers** press **Add provider** and choose **LM Studio (local)** (address `http://localhost:1234/v1`, no key).
4. Press **Test connection**, add the loaded model, and select it. Under the model's **Parameters**, set its context limit to the same value as in LM Studio.

Any other program with an OpenAI-compatible local server (llama.cpp, KoboldCpp, text-generation-webui...) works the same way with **Custom OpenAI-compatible**.

## Ollama (optional, local models)

Ollama runs models on your own PC, with no API cost and no story text leaving your computer.

1. Install Ollama from [ollama.com/download](https://ollama.com/download) and start it.
2. In the app, open **Settings > Providers & models** and switch the guide to Ollama. Press **Add local Ollama to StoryCore**.
3. Install a model yourself. You can use Ollama directly, or the download box on the **Ollama models** page. Browse the [model library](https://ollama.com/library). The app never downloads a model unless you ask, and models can be several gigabytes.
4. Press **Check Ollama**, select the model, and set its context size and output length under **Parameters** in **All providers**.

**Hardware limits.** Speed and quality depend on the model size and on your CPU, graphics card and memory. As a rough guide, models around 7B to 14B want at least 16 GB of system memory, and a graphics card with 8 GB or more of video memory helps a lot. On a CPU alone they can be very slow. Small models also keep track of long stories, many characters and strict formats less reliably than large hosted models.

## Privacy and local data

- Your stories, characters, journal, settings and logs are stored in the `data` folder inside `StoryCore`. Nothing is uploaded to the developer. The app has no analytics.
- The app only listens on your own computer (`127.0.0.1`). Other devices cannot reach it.
- With **OpenRouter**, your messages, recent story text, notes and lore excerpts are sent through OpenRouter to the model's provider, over the internet. Providers differ in how they keep data. Check the model's policy and the [OpenRouter privacy policy](https://openrouter.ai/privacy).
- With **LM Studio**, **Ollama** or the **Mock narrator**, story text stays on your PC.
- Opening **Settings > Providers & models** may download the public OpenRouter price list. That request contains no key and no story text.
- Your API key is kept in Windows Credential Manager. If that is unavailable, the app says so and uses `data\secrets.json` instead, so keep that folder private. Keys are never included in stories, backups or logs.
- To remove your key, open the provider in **Settings > Providers & models** and clear it before you delete the app.

Adult content is off by default, and sexual content involving minors is never allowed, whatever the settings. Your model provider's own rules also apply.

## Backup and export

- **Full backup:** **Settings > Data & backups > Back up now**. It contains your database and uploaded images, but not API keys. Backups are stored in `data\backups`, so copy them somewhere else to be safe.
- **One story:** open the story's menu in the sidebar and choose **Export package**. This gives you a `.zip`. Imports always create a copy.
- **Moving or updating:** close the app, then copy the whole `data` folder into the new `StoryCore` folder. Your stories, relationships and settings carry over. You can also move or rename the whole folder. The app finds its lore and portraits again at the next start.

Deleting the `data` folder deletes your stories for good.

## Troubleshooting

| Problem | What to do |
|---|---|
| "Windows protected your PC" | Choose **More info**, then **Run anyway**. The app is not code-signed. |
| Antivirus blocks or removes a file | The bundled Python and an unsigned launcher can trigger warnings. If you trust the person who sent this, allow the folder and extract again. |
| "cannot find its files" | You ran it from inside the ZIP window, or only part of the ZIP was extracted. Extract everything first. |
| "cannot write to this folder" | Move the whole folder to Documents or Desktop. |
| Extraction fails or names are cut off | Extract closer to the top of the drive, for example `C:\Games`. |
| The browser does not open | Look in the black window for an address such as `http://127.0.0.1:8765/` and open it in your browser. |
| The black window closes at once | Open the folder, click the address bar, type `cmd`, press Enter, then type `"Start StoryCore.bat"` and press Enter to read the error. |
| The app seems frozen, and the black window shows "Select" in its title | You clicked inside the black window. Press Esc in it. |
| The address changed from port 8765 | Another program, or a second copy of the app, is using that port. The app picks the next free one. Run only one copy at a time. |
| "Suggestions unavailable" under a reply | The message says why, usually a key or credit problem. Fix it and press **Retry**. Your reply is safe. |
| No suggestions | Check **Run scene analysis** and **Suggest three replies** in **Settings > Memory capture**. |
| "Scene analysis is off" or "Local models only" under a reply | That is your setting, not an error. Change it in **Settings > Memory capture**. |
| No portraits in a story | The Mock narrator shows none. With a real model, check **Where portraits appear** in **Settings > Memory capture**, and that the story uses a world whose pack has portraits (Lumencia Academy, Hero's Chronicle). If the home page offers **Scan portraits**, press it. |
| The latest reply of a story from an older version has no suggestions | Press **Suggest actions**, or just play on. New replies are analysed automatically. |
| Key rejected, or an error about credits | Check the key and your balance on OpenRouter, then press **Test connection**. |
| A reply is marked incomplete | The model reached its output limit. Retry sends a new request, which is billed on a paid model. |
| Ollama is not found | Make sure Ollama is running, then press **Check Ollama**. |
| LM Studio is not found | In LM Studio, load a model and start the server in the **Developer** tab, then press **Test connection**. |
| Local replies stop with a timeout | The first reply on a slow PC can take long while the model reads the context. Try a smaller model or a smaller **Context budget** (Settings > Narration & context). |
| Local replies are very slow or poor | Try a smaller model for speed, or a larger or hosted model for quality. |

## Reporting a bug

Send your report to the person who shared StoryCore with you. Please include:

- What you did, what you expected and what happened.
- Your Windows version and the app version: v1.7.0.
- The model you used, if the problem is about a reply. The **ⓘ** button on a reply shows useful figures.
- The end of the log, from **Settings > Data & backups**, or `data\logs\app.log`.

Read logs and screenshots before you send them. They can show your Windows user name in folder paths, and screenshots can show story text. Never send your API key, and do not send your `data` folder unless you are happy to share your stories.

## For developers

To check a lore pack you are writing, double-click **Check Lore Packs.bat**: it lists errors (the app would skip something), warnings (something will look wrong) and notes for every pack in `Lorepack`, without starting the app.

The `DEVONLY` folder documents the whole project: how it starts, the backend, the database, the lore pack format, how the narrator's context is built, AI providers, the frontend, the API, recipes and a release checklist. Start with `DEVONLY/00_READ_FIRST.txt`.
