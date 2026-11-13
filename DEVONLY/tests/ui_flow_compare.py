"""Same user journey on the old (/) and new (/next/) interface, each on a fresh data folder.
Screenshots every step to /root/inv/flow/<tag>_<nn>_<step>.png and records console errors."""
import asyncio, os, shutil, subprocess, sys, time, urllib.request, json
from playwright.async_api import async_playwright

PORT = 8771 if sys.argv[1] == "old" else 8772
B = f"http://127.0.0.1:{PORT}/"
TAG, BASE = sys.argv[1], (B if sys.argv[1] == "old" else B + "next/")
OUT = "/root/inv/flow"; os.makedirs(OUT, exist_ok=True)

def restart():
    subprocess.run("pkill -f 'python3 -m story'", shell=True)
    import socket
    for _ in range(40):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", PORT)); s.close(); break
        except OSError:
            s.close(); time.sleep(0.5)
    shutil.rmtree("/root/flowdata", ignore_errors=True)
    subprocess.Popen(f"cd /root/sc/app/backend && STORY_DATA_DIR=/root/flowdata setsid nohup python3 -m story --no-browser --port {PORT} > /root/flow_server.log 2>&1 < /dev/null &", shell=True)
    for _ in range(60):
        try:
            urllib.request.urlopen(B + "api/health", timeout=1); return
        except Exception:
            time.sleep(0.5)

async def main():
    restart()
    n = 0
    errs = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1440, "height": 900})
        pg.on("console", lambda m: errs.append(m.text[:200]) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:300]))

        async def shot(name, wait=900):
            nonlocal n
            await pg.wait_for_timeout(wait)
            n += 1
            await pg.screenshot(path=f"{OUT}/{TAG}_{n:02d}_{name}.png")

        async def click(role, name, **kw):
            await pg.get_by_role(role, name=name, **kw).first.click()

        await pg.goto(BASE + "#/"); await shot("home", 1500)
        # wizard
        await pg.goto(BASE + "#/new"); await pg.wait_for_timeout(1000)
        await pg.get_by_placeholder("e.g. The Commoner").fill("Flow Test")
        await click("button", "Next"); await pg.wait_for_timeout(800)
        sel = pg.locator("select").first
        await sel.select_option(label="Hero's Chronicle"); await pg.wait_for_timeout(800)
        await pg.get_by_text("The Summoned Hero").first.click()
        await shot("wizard_world")
        for _ in range(3):
            await click("button", "Next"); await pg.wait_for_timeout(700)
        await click("button", "Create & preview first context"); await shot("created", 2500)
        await click("button", "Generate the opening scene"); await shot("opening", 9000)
        ta = pg.get_by_placeholder("What do you do? Type / for commands")
        await ta.fill("I look at Lily."); await ta.press("Enter"); await shot("turn", 9000)
        # right panel tabs
        for tab in ["Known", "Relations", "Cast", "Items", "Quests", "Status"]:
            loc = pg.get_by_role("tab", name=tab)
            if await loc.count():
                await loc.first.click(); await shot("tab_" + tab, 700)
        # slash palette
        await ta.fill("/"); await shot("slash", 800)
        await ta.fill("")
        # journal
        await click("button", "Journal & Memory"); await shot("journal", 1200)
        for tab in ["Review", "Memories & facts", "Current state", "Characters", "Recaps", "Maintenance"]:
            loc = pg.get_by_role("tab", name=tab)
            if await loc.count():
                await loc.first.click(); await shot("journal_" + tab.replace(" ", "_").replace("&", "and"), 900)
        await pg.get_by_text("Story", exact=True).first.click()
        await pg.wait_for_timeout(800)
        # more tools menu: savepoints
        await pg.get_by_role("button", name="More story tools").first.click(timeout=5000); await pg.wait_for_timeout(500)
        await pg.get_by_text("Savepoints").first.click(); await shot("savepoints", 1000)
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(400)
        # scene correction dialog
        loc = pg.get_by_role("button", name="Correct the current scene (day, date, time, weather, place)")
        if await loc.count():
            await loc.first.click(); await shot("scene_dialog", 900); await pg.keyboard.press("Escape")
        # message context dialog
        loc = pg.get_by_role("button", name="Context sent to the model")
        if await loc.count():
            await loc.last.click(); await shot("msg_context", 1500); await pg.keyboard.press("Escape")
        # sidebar story actions
        await pg.get_by_role("button", name="Actions for Flow Test").first.click(); await shot("story_actions", 700)
        await pg.keyboard.press("Escape")
        # avatars: create one
        await pg.goto(BASE + "#/avatars/new"); await pg.wait_for_timeout(1200)
        await pg.get_by_placeholder("Avatar name").fill("Kael")
        for tab in ["Appearance", "Background & personality", "Abilities", "Stats & inventory", "Additional info", "Prompt preview"]:
            loc = pg.get_by_role("tab", name=tab)
            if await loc.count():
                await loc.first.click(); await shot("avatar_" + tab.split(" ")[0], 600)
        # lore: open a record and search
        await pg.goto(BASE + "#/lore"); await pg.wait_for_timeout(1200)
        await pg.get_by_text("Arbel").first.click(); await shot("lore_record", 1200)
        await pg.get_by_placeholder("Search all lore (names, aliases, text)").fill("dragon"); await shot("lore_search", 1500)
        # commands: open the editor
        await pg.goto(BASE + "#/commands"); await pg.wait_for_timeout(1000)
        await click("button", "New command"); await shot("command_new", 900); await pg.keyboard.press("Escape")
        # settings providers: add provider dialog
        await pg.goto(BASE + "#/settings/providers"); await shot("providers", 1500)
        loc = pg.get_by_text("All providers and advanced options")
        if await loc.count():
            await loc.first.click(); await shot("providers_advanced", 1000)
        # help
        await pg.goto(BASE + "#/"); await pg.wait_for_timeout(800)
        await click("button", "Help"); await shot("help", 900)
        await b.close()
    json.dump(errs, open(f"{OUT}/{TAG}_errors.json", "w"), indent=1)
    print(TAG, "steps", n, "errors", len(errs), errs[:6])

asyncio.run(main())
