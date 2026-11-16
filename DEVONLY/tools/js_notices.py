"""Refresh the JavaScript part of THIRD_PARTY_NOTICES.txt from the interface's installed packages.

Usage (after "npm install" in the folder that holds node_modules, e.g. app/frontend or a build copy):
    cd <frontend folder> && npm ls --omit=dev --all --parseable > deps.txt
    python DEVONLY/tools/js_notices.py <frontend folder>/deps.txt THIRD_PARTY_NOTICES.txt
The Python part (list and licence texts) is kept as it is; the JavaScript list and licence texts are rebuilt from the
production dependency tree (each package's package.json and LICENSE file).
"""
import json
import re
import sys
from pathlib import Path

SEP = "=" * 78


def main() -> None:
    deps_file, notices = Path(sys.argv[1]), Path(sys.argv[2])
    dirs = [Path(x) for x in deps_file.read_text(encoding="utf-8").split() if x.strip()][1:]  # first line: the app
    pkgs = {}
    for d in dirs:
        try:
            p = json.loads((d / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        lic = p.get("license")
        lic = lic if isinstance(lic, str) else (lic or {}).get("type") or "see licence file"
        files = sorted(f for f in d.iterdir() if f.is_file() and re.match(r"^(licen[cs]e|copying)(\.|$|-)", f.name, re.I))
        pkgs[(p["name"], p["version"])] = {"license": lic, "file": files[0] if files else None}
    text = notices.read_text(encoding="utf-8").replace("\r\n", "\n")
    head, rest = text.split("JavaScript packages\n-------------------\n", 1)
    head = head.replace("Lumencia Story Desk (private beta)", "StoryCore").replace("with this beta", "with this release")
    py_names = {line.split(" ")[0].lower() for line in head.split("Python packages\n---------------\n", 1)[1].splitlines()
                if ":" in line}
    blocks = re.split(rf"(?m)^{SEP}\n", rest)
    # blocks: [js list, title, body, title, body, ...]; keep the Python licence texts
    kept = []
    for i in range(1, len(blocks) - 1, 2):
        title, body = blocks[i].strip(), blocks[i + 1]
        if title.split(" ")[0].lower() in py_names:
            kept.append((title, body))
    out = [head, "JavaScript packages\n-------------------\n"]
    for (name, ver), info in sorted(pkgs.items(), key=lambda x: x[0][0].lower().lstrip("@")):
        note = " (Cinzel font by Natanael Gama)" if name == "@fontsource/cinzel" else ""
        out.append(f"{name} {ver}{note}: {info['license']}\n")
    out.append("\n")
    texts = list(kept)
    for (name, ver), info in sorted(pkgs.items(), key=lambda x: x[0][0].lower().lstrip("@")):
        if info["file"] is not None:
            body = info["file"].read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").strip() + "\n\n"
            texts.append((f"{name} {ver} ({info['file'].name})", body))
    for title, body in texts:
        out.append(f"{SEP}\n{title}\n{SEP}\n{body}")
    notices.write_text("".join(out).replace("\n", "\r\n") if "\r\n" in text else "".join(out), encoding="utf-8")
    print(f"{len(pkgs)} JavaScript packages, {len(texts)} licence texts")


if __name__ == "__main__":
    main()
