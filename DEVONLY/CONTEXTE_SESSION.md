Bonjour Claude. On continue le développement de StoryCore. Voici tout le contexte pour reprendre dans de bonnes conditions.

## Qui je suis / comment travailler avec moi
- Je m'appelle Kurio (GitHub : kurioman). Je suis débutant : explique-moi les choses simplement, étape par étape, en français.
- Présente-moi toujours le plan AVANT d'agir, puis exécute.
- Tu as mon autorisation complète pour ajouter, modifier ou supprimer des fichiers du projet (j'ai une sauvegarde).
  Pour que git puisse faire ses commits, demande l'autorisation de suppression sur le dossier du projet en début de session.
- Fais un commit git après chaque étape. Termine chaque message de commit par les lignes d'attribution demandées par le système.
- Je pousse moi-même sur GitHub avec `DEVONLY\Push vers GitHub.bat` (dépôt privé, branche `main`). Rappelle-le-moi en fin de phase.

## Le projet en bref
StoryCore (version **0.6.0** ; la numérotation est repartie de zéro après la 1.7.0 : on vise une vraie V1) est un moteur
local de jeu de rôle textuel par IA, basé sur des « Lore packs » (des mondes).
- Dossier : `C:\Users\Kurio\Desktop\StoryCore`
- Backend : Python FastAPI (`app/backend/story`), SQLite, migrations Alembic (`migrations/versions`, la dernière est la **0010**).
- Frontend : React 19 + Vite + Tailwind 4 (`app/frontend/src`). Compilé dans **`app/frontend/dist`** et servi à la racine **`/`**
  (l'ancienne interface `/old` et l'adresse `/next/` n'existent plus : elles redirigent vers `/`).
- Traductions : `msg("texte anglais")`. Le texte anglais sert de clé, et le français va dans `app/frontend/src/i18n/locales/fr.json`
  (avec « vous », et « Go » pour les gigaoctets).
- Documentation développeur : `DEVONLY/` (`02_BACKEND.txt`, `04_LOREPACK.txt`, `05_NARRATOR_AND_CONTEXT.txt`, `08_API_REFERENCE.txt`,
  `13_FRONTEND_SOURCE.md`…). Notes de version : `RELEASE_NOTES.md`. Format des packs : `LOREPACK_FORMAT.md`.
- Deux packs inclus : « Hero's Chronicle » (2 débuts : Avalon, et « Début alternatif : le Roi Démon » avec Beelzebub) et
  « Lumencia Academy » (1 début : « Inscription », le 1er mars). Lily et Beelzebub existent dans les deux packs avec des
  portraits différents (Beelzebub adolescente dans Lumencia, adulte dans Hero's Chronicle) : les portraits sont **par monde**.
- Ma config : RTX 3060 12 Go, 32 Go de RAM, LM Studio.

## Méthode de travail technique (déjà rodée)
- La machine de travail (VM) peut être remise à zéro entre deux sessions. Si `$HOME/v312`, `$HOME/fe` ou `$HOME/tools` manquent :
  - Python de test : `cd $HOME && uv venv -q -p 3.12 v312 && uv pip install -q -p v312/bin/python alembic==1.20.1 fastapi==0.162.0 httpx==0.28.1 keyring pillow==13.0.0 pydantic==2.14.2 python-multipart pyyaml sqlalchemy==2.1.6 starlette==1.10.0 uvicorn==0.54.0`
  - Frontend : `mkdir -p $HOME/fe && cp app/frontend/{package.json,package-lock.json,tsconfig.json,vite.config.ts,index.html} $HOME/fe/ && cd $HOME/fe && npm ci`
  - Outil des clés de traduction : `mkdir -p $HOME/tools && cp DEVONLY/tools/frontend_reconstruction/keys.mjs $HOME/tools/ && cd $HOME/tools && npm init -y && npm i @babel/parser @babel/traverse`
- Compilation : `rsync -a --delete app/frontend/src/ $HOME/fe/src/`, puis dans `$HOME/fe` : `npx tsc --noEmit && npm run build`,
  puis recopier `$HOME/fe/dist/` dans `app/frontend/dist/` (supprimer l'ancien `dist` d'abord). Ne pas faire `npm install` dans le dossier monté.
- Tests (**73**, ~3 min 15 au total : la commande a une limite de 3 min, donc **les lancer en deux moitiés**) :
  `PYTHONPYCACHEPREFIX=$HOME/pyc $HOME/v312/bin/python DEVONLY/run_tests.py test_api_basics test_bug_report test_codex test_lmstudio test_music test_narration_language test_pack_check test_providers test_remote test_usage test_continuity`
  puis `... DEVONLY/run_tests.py test_context_layout test_story_flow test_summaries test_creator test_phase9`.
- Clés de traduction manquantes : `node $HOME/tools/keys.mjs app/frontend/src app/frontend/src/i18n/locales/en.json`
  (met à jour en.json), puis comparer avec fr.json (chaque clé de en.json doit exister dans fr.json). Ajouter les traductions
  avec un petit script node (Object.assign) pour garder le format du fichier.
- Les fichiers `.txt` de DEVONLY sont en fins de ligne Windows (CRLF) : les modifier en les conservant.
- Variables d'une lettre du code reconstruit : `node DEVONLY/tools/frontend_reconstruction/rename.mjs <fichier> <fonction> o=query ...`
  (copier dans `$HOME/tools`, à côté de keys.mjs). `fr.json` est indenté avec **un espace** (`JSON.stringify(fr, null, 1)`).
- Fichiers écrits depuis le conteneur cloud avec `device_commit_files` : utiliser `force: true` si le fichier existe déjà
  (sinon il peut ne pas être remplacé sans erreur).
- Vérification visuelle : mettre `app/backend` et `app/frontend/dist` dans `_work/upd.tgz`, le transférer dans le conteneur
  cloud et l'extraire dans `/home/claude/sc` (le conteneur a aussi besoin de `scripts`, `Lorepack`, `Music`), lancer
  `python3 scripts/serve.py --port 8765 --no-browser --data-dir /home/claude/scdata` (d'abord `pkill -f scripts/serve.py`),
  puis des captures Playwright avec `/usr/bin/google-chrome` et `NO_PROXY=127.0.0.1`. Interface en français : `localStorage 'lsd:language' = 'fr'`.
- Les requêtes POST, PUT et DELETE de l'interface doivent envoyer l'en-tête `X-Story-Client: 1`.
- Les réglages sont dans `settings_service.DEFAULTS`. Une requête PUT `/api/settings` refuse les clés inconnues.
- Piège : ne jamais appeler `msg()` au niveau d'un module (la langue peut changer sans recharger) : utiliser des fonctions.
- Release : `python3 DEVONLY/make_release.py $HOME/tmp/rel` (sur le disque local de la VM, ~1 min), puis copier le zip dans `_release\`.
  Le zip exclut `data\`, mes musiques (Music part vide), `DEVONLY\Push vers GitHub.bat` et les captures de l'ancienne interface.
  Licences tierces : `DEVONLY/tools/js_notices.py` régénère la partie JavaScript de `THIRD_PARTY_NOTICES.txt`.

## Ce qui est fait (v0.5)
- Phases 0 à 5 : Récap / Signaler un problème, accueil plein écran, Lore packs format 2 + Codex, Bibliothèque, musique,
  assistant de premier lancement.
- Phase 6 : jouer depuis un téléphone (même Wi-Fi, QR code + code à 6 chiffres, badge, page `#/mobile`, se coupe à la fermeture).
- Suppression de l'ancienne interface, catalogue de modèles traduit.
- Phase 7 (mémoire et tokens) :
  - 7.1 résumés automatiques (dans la requête de capture mémoire, sinon rattrapage), table `memory_summaries` (migration 0010) ;
  - 7.2 mémoire en couches (scènes → chapitres → « histoire jusqu'ici »), souvenirs par personnage, fils ouverts, scènes rappelées ;
  - 7.3 requête « stable » (contexte du tour collé au message du joueur, fenêtre par paliers), cache Claude, lore court ;
  - 7.4 récap pour le joueur (bouton doré), onglet « Mémoire de l'IA » du Journal, commande `/chapitre` ;
  - 7.5 compteur de tokens (cache, coût), estimation corrigée par les vrais chiffres ;
  - 7.6 vérifications sans tokens (répétitions, personnage mort qui parle, heure qui recule, contradiction avec un souvenir épinglé).
- Version 0.5.0, zip `_release\StoryCore_v0.5.0.zip`.
- Correctif portraits : chaque écran utilise les portraits du monde de l'histoire ; dossiers rattachés à un monde ; page
  Portraits séparée par histoire ; les anciens dossiers `Documents\LumenciaStoryDesk\...` sont rattachés à leur monde au démarrage.
- Libellés traduits au moment de l'affichage (plus de tableaux de `msg()` au chargement d'un fichier).
- Interface découpée par page (`React.lazy` dans `app/App.jsx`) : le fichier principal passe de 1,3 Mo à ~380 Ko.

- **Phase 8 (v0.6.0)** : créateur de mondes (`#/creator`, `features/creator/*`, `services/pack_editor.py`,
  `services/creator_assist.py`, `routers/creator.py`) : 10 onglets, enregistrement automatique, portraits et couverture
  (convertis en WebP), « Proposer avec l'IA », copie des packs inclus (les originaux ne sont jamais modifiés), export et
  import .zip (Bibliothèque), réservé à l'ordinateur. Barre latérale rendue lisible. Zip `_release\StoryCore_v0.6.0.zip`.
- **Phase 9.1** : requêtes plus petites (fiches de lore compactes, consignes `ai/` et scénarios exclus du lore,
  consignes fixes raccourcies ; importeur version 6). Mesures dans `DEVONLY/05_NARRATOR_AND_CONTEXT.txt`.

- **Phase 9.2 à 9.4** (testé en direct avec mon LM Studio) : plus de scènes rejouées (« Continuer » v3, règle
  anti-répétition, `services/reply_cleanup.py` qui retire les paragraphes recopiés, le menu final et un tour « Human: »
  écrit par le modèle), longueur des réponses plafonnée, `repeat_penalty` envoyé à LM Studio sous le bon nom, marqueurs
  d'arrêt, budget de contexte qui suit le modèle (jusqu'à 24 000), narration prioritaire (analyse/capture/résumés
  arrêtés quand j'écris), règle contre les passés communs inventés, consignes d'analyse raccourcies.
- **Mon LM Studio (réglé par Claude le 18/11)** : Rocinante 12B **Q4_K_M** (`rocinante-12b-v1.1@q4_k_m`), contexte 24 576,
  cache K/V Q8_0, Flash Attention, format **ChatML** enregistré dans les réglages par défaut du modèle (le GGUF n'en a
  pas : sans lui le modèle répète et écrit « Human: »), « Limit Model Offload to Dedicated GPU Memory » activé.
  Vitesse mesurée : ~14-16 tokens/s (attendu 30-40 sur une 3060) : reste à comprendre (autres applis sur la carte ?).

## Pas encore vérifié avec du vrai matériel
- Phase 6 sur mon vrai téléphone (pare-feu Windows : cocher « Réseaux privés »).
- Phase 7 avec mon modèle LM Studio (qualité des résumés et du récap, vitesse avec la requête stable).
- Phase 8 : « Proposer avec l'IA » avec mon modèle LM Studio (qualité des brouillons JSON).
- Phase 9.1 : qualité du narrateur avec les fiches de lore compactes.

## Feuille de route restante
Vision : après la Phase 8 (version **0.6.0**), le reste du travail jusqu'à la **V1** sera surtout des optimisations
(comme celles ci-dessous) et l'ajout de nouveaux Lore packs.

1. **Phase 9 (suite)** : style de narration à travailler ensemble (j'aime : réponses courtes, actions entre *astérisques*,
   proche d'OOC.AI) ; début fixe de Lumencia (je le conçois moi-même) ; vitesse de génération (14 tok/s) ; les balises
   de portrait que Rocinante n'écrit presque jamais. Continuer à rendre
   lisible le code reconstruit (`journal.jsx`, `Providers.jsx`, `dialogs.jsx`) au fur et à mesure des fichiers touchés.
   **Phase 10** : deux nouveaux Lore packs, créés par moi avec le créateur.
2. **Optimisations images et vitesse** (après la Phase 8) :
   - **Vérification d'abord** : contrôler à quel moment le portrait s'affiche aujourd'hui. Il doit apparaître dès que
     l'IA écrit la balise `[Nom:N]` pendant la génération, et non après la fin de la réponse ou après l'analyse de scène.
     (D'après les notes de la v1.7, il s'affiche à la fin de la réponse : à confirmer dans le code, `portrait_tags.py`,
     `runtime.py` (tag_filter) et l'écran de jeu, puis par un test.)
   - **Portrait en direct** : dès que la balise est reconnue pendant le flux, envoyer un événement à l'interface
     et afficher le portrait tout de suite (même principe que l'URL d'image d'une application concurrente, mais avec
     notre balise courte : ~5 tokens au lieu de 15–30, pas d'adresse inventée, portraits du monde de l'histoire).
   - **Préchargement** des 6 expressions des personnages présents dans la scène (changement d'expression instantané).
   - **Narration prioritaire** : LM Studio traite une requête à la fois. Les requêtes secondaires (analyse de scène,
     capture mémoire, résumés) ne doivent pas faire attendre le message du joueur ni effacer le cache du narrateur :
     les mettre en pause ou les reporter quand le joueur envoie un message.
3. Petits restes : conseils LM Studio (Flash Attention, cache K/V en Q8) dans l'assistant ; mettre en avant l'option
   « réponses courtes » (préréglage Fast) ; chapitre fermé automatiquement après un changement de lieu ou un saut dans
   le temps ; le narrateur de démonstration recopie le texte des consignes.
4. Nouveaux Lore packs (moi), avec le créateur de la Phase 8. Moi aussi : les images manquantes de Lumencia Academy.
5. **Installateur Windows** (gardé). Priorité générale : pouvoir jouer dans de bonnes conditions (génération rapide,
   fonctionnalités efficaces) avant tout le reste.
   **Application Android (APK) avec une IA en ligne : pour la V1**, une fois l'application terminée (pas avant).
   Abandonnés pour le moment (trop mineurs) : mécaniques de jeu optionnelles, arbre de choix.
6. En tout dernier : lien d'invitation Discord (`DISCORD_URL` vide dans `lib/links.ts`).

## Ce que je te demande maintenant
(à compléter)
