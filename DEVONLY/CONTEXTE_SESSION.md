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
- Tests (**117**, plus les 4 de l'installateur en cours ; ~3 min 40 au total : la commande a une limite de 3 min, donc **les lancer en deux moitiés**) :
  `PYTHONPYCACHEPREFIX=$HOME/pyc $HOME/v312/bin/python DEVONLY/run_tests.py test_api_basics test_bug_report test_codex test_lmstudio test_music test_narration_language test_pack_check test_providers test_remote test_usage test_continuity test_cinematic`
  puis `... DEVONLY/run_tests.py test_context_layout test_story_flow test_summaries test_creator test_phase9 test_portraits_live test_story_events test_report_30_turns`,
  et (phase 2) `... test_report_50_turns test_info_table test_phase2_flow`. Avec la limite de 3 min, lancer test_summaries seul.
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

- **Portraits (19/11, testé en direct avec Rocinante sur mon PC)** : `services/live_speakers.py` repère qui parle
  pendant l'écriture (nom à côté des guillemets, sans token) et l'écran affiche le portrait aussitôt (événement
  `portraits`) ; sans balise, ces portraits sont enregistrés tout de suite, l'analyse corrige ensuite ; balises remises
  dans l'historique (aussi pour les vieilles réponses analysées) ; rappel `[Lily:2] « Bonjour. »` à côté de mon message ;
  préchargement des 6 expressions ; interrupteur « Demander à l'IA d'indiquer qui parle » (Réglages > Mémoire).
  Mesures : sans balise, portrait à 2,2 s (pendant l'écriture) au lieu de 9,9 s ; en direct, Rocinante s'est mis à
  écrire `[Lily:2]` lui-même dès le 3e tour. Tests : `test_portraits_live` (80 tests au total ; la 2e moitié de la
  commande des tests reçoit aussi `test_portraits_live`). Vitesse vue pendant ce test : ~23-26 tokens/s.
  Une histoire « [TEST portraits] à supprimer » est restée dans ma liste.
  Ensuite (même jour) : un personnage peut avoir plusieurs portraits dans une réponse (neutre puis triste) : chaque
  réplique garde son expression (sa balise, sinon l'humeur lue dans son paragraphe, mots français et anglais,
  `expressions.mood_of`) ; l'écran remontre le portrait quand l'expression change ou après un autre personnage.

- **Rapport de test 30 tours (19/11)** : les 15 bugs B1 à B15 corrigés (commits « Rapport de test 30 tours (1/6) » à
  « (5/6) », tests `test_report_30_turns`). Mémoire : capture arrêtée = `cancelled`, reprise à la réponse suivante par
  échanges de 2 messages (`extraction.RESUME_CHUNK_MESSAGES`). Horloge : repères de la narration
  (`world_state.time_cues` / `with_cues`, aussi appliqués juste après la réponse dans `turns._clock_from_cues`).
  Portraits et présence : `services/speaker_guard.py`. Narration entre guillemets : `reply_cleanup.quoted_narration_spans`.
  Titres inventés : `roles.office_conflicts`. Les avertissements (`continuity_alerts`) sont maintenant envoyés à l'écran.
  À faire ensuite (axes du rapport, pas des bugs) : langue de l'histoire demandée dans l'assistant, apparence et liens
  de famille dans le pack Hero's Chronicle, portraits plus petits, traduction des derniers textes anglais. Refaire
  30 tours en français dès le départ avec 60 s entre les tours.

- **Test 2 (19/11, 30 tours en anglais joués par Claude sur mon PC)** : rapport « StoryCore 0.6.0 — Test 2 » (Claude Docs).
  Corrigé ensuite (commit « Test 2 (30 tours en anglais) : corrections ») : capture avant l'analyse quand la mémoire a
  du retard (`extraction.behind`), défilement (`overflow-anchor: none`, suivi coupé seulement par un geste du joueur),
  lieu (citation proche + arrivées de la narration, `world_state.place_cue`), présence silencieuse nommée, étiquettes de
  nom (`attribute_dialogue`), lignes « (OOC: …) » retirées, horloge (sommeil puis aube = nouveau jour). 121 tests.
  Attention : après un redémarrage, recharger la page (F5), sinon l'ancienne interface reste en mémoire.
  Le volet navigateur de Claude caché ne dessine rien : les mesures de défilement s'y font en Chrome sans écran.
  Reste : réponses trop longues pour « Moyen », répétitions de descriptions, apparence et genre dans les fiches du
  pack, narrateur qui écrit les répliques du héros, 0 fait extrait par la capture mémoire.

## Phase 2 : qualité de la narration (21/11/2026, après le test « Lumencia 50 tours » avec Rocinante)
Plan suivi : `RELEASE_NOTES.md` (section « Phase 2 »). Étapes faites, un commit chacune (2 et 3 ensemble, 4 à 7 ensemble) :
1. Filet de sécurité (`services/reply_cleanup.py`) : ``` et étiquettes retirés (réponse, historique envoyé, anciennes
   histoires une fois au démarrage : `turns.sanitize_stored_replies`), écho du joueur retiré, réponse sans récit redemandée
   une fois puis erreur `no_story` (`runtime._run`), anti-répétition sur 8 réponses, narration à la 3e personne
   (profil `v6_third_person`, note `<narrator-note>` au lieu de « (OOC: …) »), contexte du tour entre `<context>` et
   `</context>` (l'ancienne étiquette « [The player's turn] » était recopiée), plafond de longueur en mots (Cinématique).
2. Instructions : prompt Lumencia réécrit (`ai/narrative_system_prompt.md`, avec « Fixed truths »), titres et consignes
   des sections raccourcis.
3. Lore : champ `gender` (tous les personnages des deux packs sont des femmes), fiche courte d'une ligne par personnage
   présent ou nommé (`context_builder.character_card`), lore sans métadonnées (`compact_record`), recherche par mots
   limitée, avertissement de Check Lore Packs, champ Genre du créateur. Aria : élève devenue la Sainte, qui enseigne aussi.
4. Tableau d'informations (`services/info_table.py`) : bloc `<info>` en lignes simples à la fin de chaque réponse, retiré
   du flux, vérifié, enregistré, affiché sous la réponse (corriger / annuler), annulé si la réponse est régénérée ou
   supprimée. Quand le bloc est là, l'analyse de scène n'est plus envoyée (elle revient si le modèle ne l'écrit pas).
5. Récaps (`services/summaries.py`, mode `recap_mode`) : un récap toutes les `recap_every` réponses (10), un récap global
   tous les 5, dans une tâche jamais stoppée (`main._recaps`), qui attend la fin du narrateur en local.
6. Contexte : messages non couverts par un récap seulement (au moins 8), journal et faits capturés non envoyés, capture de
   mémoire coupée avec les récaps, `cached_tokens` dans le journal.
7. Journal > Mémoire de l'IA : verrouiller, réécrire, revenir à la version de l'IA.
Mesure sur la requête du tour 50 du test : partie fixe ≈ 5 400 → ≈ 3 300 tokens ; avec les récaps, l'historique passe
de ≈ 17 000 tokens (100 messages) à 8-20 messages.
Prochaine étape : Kurio refait le test de 50 tours avec Rocinante, puis avec DeepSeek, et écrit un rapport. Si
Rocinante n'écrit pas le bloc `<info>`, l'analyse de scène prend le relais toute seule ; si ses récaps sont mauvais, les
corriger dans le Journal ou désactiver « Récaps automatiques » (Paramètres > Mémoire).

## Version 0.6.2 (22/11/2026, retour du test avec DeepSeek via OpenRouter)
DeepSeek donne beaucoup moins d'incohérences que Rocinante. Corrigé (commit « Retour du test DeepSeek ») :
- Défilement (`StoryPage.AutoScroll`) : l'écran ne suit plus le texte. À chaque nouveau message, il place UNE fois le
  message du joueur en haut, puis ne bouge plus ; à l'ouverture d'une histoire, il va à la fin. Vérifié en Chrome sans écran.
- Coût : `ProviderAdapter.spent_cost` additionne chaque requête payée (réponse redemandée, analyse réparée) ;
  `usage.summary` compte toutes les réponses (régénérées, supprimées, autres branches) ; `usage.record` n'ajoute que le
  nouveau. Affiché en doré dans la barre du haut (téléphone compris), 3 décimales. Les tests payants des paramètres ne
  comptent pas (OpenRouter, lui, les facture).
- Portraits : `LiveSpeakers.owns_line` / `_check_tags` et `portrait_tags.apply` : une balise sur une réplique de quelqu'un
  d'autre (« lança un étudiant de deuxième année ») ne montre rien ; un personnage silencieux n'a un portrait que s'il est
  nommé ET que son expression change. Mots d'école ajoutés à `speaker_guard.PERSON`.
- Téléphone (`styles.css`, fin du fichier) : texte 15 px, zone de saisie sur une ligne, bulle du joueur plus compacte.
126 tests (dont `test_usage.test_every_paid_request_counts`, `test_portraits_live.test_a_tag_on_someone_elses_line_shows_nothing`).

## Pas encore vérifié avec du vrai matériel
- Phase 6 sur mon vrai téléphone (pare-feu Windows : cocher « Réseaux privés »).
- Phase 7 avec mon modèle (qualité des résumés et du récap sur une longue partie).
- Phase 8 : « Proposer avec l'IA » avec mon modèle (qualité des brouillons JSON).
- Phase 9 : une vraie partie longue (plus de 30 tours) pour confirmer la fin des scènes rejouées.

## Feuille de route restante
Vision : le travail jusqu'à la **V1** = rendre le jeu confortable (vitesse, qualité, portraits), puis de nouveaux packs.
Priorité générale : pouvoir jouer dans de bonnes conditions avant tout le reste.

1. ~~Portraits~~ : **fait le 19/11** (voir « Ce qui est fait »), y compris plusieurs portraits d'un même personnage
   dans une réponse quand son expression change. À confirmer en jouant en français avec Rocinante.
2. ~~Style de narration~~ : **fait le 19/11** : style « Cinématique » (proche d'OOC.AI : 3e personne avec le nom du
   héros, paragraphes courts, émotions montrées par le corps, chute finale, actions en narration normale ; pour appuyer
   un mot, l'italique de l'application), par défaut des nouvelles histoires, longueur en mots ; affichage
   « Cinématique » (narration en gris plus sombre). **À tester avec Rocinante et à ajuster ensemble** (captures).
3. ~~Début fixe de Lumencia~~ : **remplacé le 19/11 par les « événements prévus »** (pas de scène fixe : des scènes
   décidées à l'avance que l'IA joue à sa façon, un à la fois ; obligatoires, surprise pour le joueur, visibles dans le
   Journal une fois joués). Moteur `services/story_events.py`, onglet « 8. Événements » du créateur, choix du joueur
   (l'aile). Lumencia : cérémonie d'entrée (Emily présente l'école, les règles et Artemis, Elena, Aria), examen d'entrée
   facultatif (élèves sans aile), examen de l'aile (duel contre Artemis / cristal de détection d'Elena / épreuve d'Aria
   inventée par l'IA), événement de début d'année (tournoi / sort ou mémoire à inventer / inventé par l'IA), examen de
   fin d'année (à partir du 20 décembre, choisi par l'IA). **À tester avec Rocinante.**
4. **Vitesse** : 14-16 tokens/s mesurés au lieu de 30-40 attendus sur ma 3060. Pistes : fermer les applications qui
   utilisent la carte (Opera GX…), vérifier la mémoire vidéo dans le Gestionnaire des tâches, essayer « Max Concurrent
   Predictions » à 1 dans LM Studio. Je peux supprimer l'ancien Rocinante Q6_K_L (10,4 Go) dans My Models.
5. **Assistant de premier lancement** : y ajouter les conseils LM Studio appris le 18/11 (Q4_K_M pour 12 Go, contexte
   16-24k, cache K/V Q8_0, Flash Attention, format ChatML si le GGUF n'en a pas, limite à la mémoire de la carte) et,
   si possible, détecter un modèle sans format de conversation.
6. Petits restes : mettre en avant l'option « réponses courtes » ; chapitre fermé automatiquement après un changement
   de lieu ou un saut dans le temps ; le narrateur de démonstration recopie le texte des consignes ; rendre lisible le
   code reconstruit (`journal.jsx`, `Providers.jsx`, `dialogs.jsx`) au fur et à mesure des fichiers touchés.
7. **Phase 10** : nouveaux Lore packs (moi), avec le créateur. Moi aussi : les images manquantes de Lumencia Academy.
8. **Installateur Windows** (gardé). **Application Android (APK) avec une IA en ligne : pour la V1**, une fois
   l'application terminée. Abandonnés pour le moment : mécaniques de jeu optionnelles, arbre de choix.
9. En tout dernier : lien d'invitation Discord (`DISCORD_URL` vide dans `lib/links.ts`).

## Ce que je te demande maintenant
(à compléter) — reste du 19/11 : les petits restes du point 6 (option « réponses courtes » mise en avant, chapitre
fermé après un changement de lieu ou un saut dans le temps, narrateur de démonstration, code lisible).
