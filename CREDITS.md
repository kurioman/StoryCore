# Credits and notices

Lumencia Story Desk is an **independent, unofficial fan project**. It is not affiliated with, endorsed by or connected to OOC, DreamRunner, or the creators of the Lumencia Academy story. This beta is free, non-commercial and shared privately with a small group of invited friends.

This file records what is known. Where something is unknown, it says so. Nothing here claims permission or a license that has not been documented, and being free or private does not by itself grant any rights.

## Setting and lore: fan-community origins

The Lumencia Academy setting comes from a story on the OOC platform and from the community around it. The lore pack in this beta is a research-based reconstruction made for this project. It is **not** an official dump of the original story, and its own files label which details are recurring, reconstructed by the community, or unknown.

Sources recorded in the pack (`lumencia_academy_lore_pack_v1/lumencia_academy_lore_pack/reference/sources.json`):

- **Lumencia Academy, OOC story page:** the official listing. <https://ooc.ai/story/69f414d90abbab6f6a2c8131>
- **Public DreamRunner adaptation by Zeph.** <https://app.dreamrunner.ai/story/s/5dfbef3d-918f-41c1-9f98-4ee8aad829fd>
- **An alternate public DreamRunner version.** Its author is not recorded. <https://app.dreamrunner.ai/story/s/b19baaa5-1cc1-48f7-b518-3d719fc81111>
- **Community discussions in r/OOC_official** on Reddit: character reviews, a wiki and info thread, canon constant data, a school-year and power-system post, and start-mode discussions. Thanks to the players who wrote and compiled them. The individual posters are not recorded here; the thread links are in `sources.json`.

**Uncertain:** the original authors of many individual details, and how far each detail matches the private original story. No license or written permission for the lore is on record.

## Portraits and artwork

The beta includes 180 WEBP portraits: 30 characters with six expressions each.

- **Illustrations generated for this project:** about ten of the images were generated specifically for this project. Which exact files these are is not recorded.
- **The remaining images:** they come from the fan community around the setting. **Their individual creators, tools and license terms are uncertain and are not recorded.** The image files contain no author or license metadata.

If you recognise a creator, please tell the person who shared this beta, so that this file can credit them properly.

## Software

The beta bundles open-source software. Their notices are reproduced in `THIRD_PARTY_NOTICES.txt`, and the package metadata is kept under `app/python/Lib/site-packages`.

- **Python 3.12** (Python Software Foundation License): see `app/python/LICENSE.txt`, which also covers bundled components such as OpenSSL, SQLite, libffi and zlib.
- **Backend:** FastAPI, Starlette, Uvicorn, SQLAlchemy, Alembic, Pydantic, HTTPX, Pillow, keyring and their dependencies.
- **Interface:** React, TanStack Query, Radix UI, react-markdown, remark-gfm, Zod, clsx and their dependencies, built with Vite, TypeScript and Tailwind CSS.
- **Icons:** Lucide (`lucide-react`), compiled into the interface.

## Fonts

No font files are bundled. The app uses fonts already on your system, such as Segoe UI, Palatino Linotype, Georgia and Consolas, which remain under their own licenses.

## External services

OpenRouter and Ollama are independent projects with their own terms. They are optional, and you use them with your own account or installation. Neither has endorsed this project.
