# Sebtix — assistant personnel

Fork d'[OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Apache 2.0, mention d'origine conservée).
Dépôt : `OnionJam/SEBTIX` (**public** — aucune donnée personnelle ne doit y être commitée).
Le cahier des charges complet a été donné dans la première session ; ce fichier en garde l'essentiel.

## Règles de travail (non négociables)
- On échange en **français**. L'utilisateur est débutant : expliquer chaque commande en une phrase simple
  avant de la lancer, et guider pas à pas toute action qu'il doit faire lui-même.
- **Une étape à la fois** : tester, montrer le résultat, attendre le feu vert.
- Une branche git par étape (`etape-N-nom`), commit puis fusion dans `main` après validation.
- Mettre à jour ce fichier à la fin de chaque étape.
- Prévenir avant toute dépense. Plafond total : **10 €/mois** (hébergement + API).
- Sebtix ne doit **jamais** envoyer, supprimer ni déplacer un mail, ni envoyer une candidature.
- Aucune action irréversible sans validation explicite de l'utilisateur.

## Identité de Sebtix
Nom partout : Sebtix (CLI `sebtix`, web, Telegram, voix). Tutoiement, direct, concis, un peu
d'humour, jamais bavard (surtout à l'oral). Parle français.

## Architecture retenue
- **Cerveau (Mac)** : MacBook Air M5, 16 Go. OpenJarvis + Ollama (modèle local), interface web,
  voix, tâches lourdes (candidatures, analyses).
- **Sentinelle (cloud 24h/24)** : **Cloudflare Workers, offre gratuite** (option A validée).
  Programme léger, PAS OpenJarvis : surveillance Outlook (toutes les ~2 min), notifications,
  brief du matin, réponses simples Mac fermé (Workers AI), file de tâches pour le Cerveau.
  Stocke l'état de référence (D1/KV) ; historique de conversation limité à 30 jours (proposé).
- **Canal téléphone** : bot Telegram privé (n'accepte que le chat_id de l'utilisateur).
- **Outlook** : Microsoft Graph, une seule connexion, lecture seule
  (`Mail.Read`, `Calendars.Read`, `offline_access`). Le connecteur Outlook d'origine
  (IMAP + mot de passe d'application) n'est pas utilisé.

## Choix techniques
- Code interne garde le nom de paquet `openjarvis` (pour suivre les mises à jour d'upstream) ;
  tout ce qui est visible est renommé Sebtix. **Code Sebtix dans `src/sebtix/`** (paquet
  séparé, déclaré dans `pyproject.toml`). Commande `sebtix` (l'alias `jarvis` reste : OpenJarvis
  se relance lui-même sous ce nom).
- Remote `upstream` = open-jarvis/OpenJarvis.
- Analytics PostHog : **désactivé** (`~/.openjarvis/config.toml`, `[analytics] enabled = false`).
- Minage « Pearl » : jamais installé ; commandes `mine` / `pearl` retirées de la CLI.
- Interface web : fenêtre « Win a Mac mini » et bloc « Leaderboard » retirés ; écran de chat
  en français ; le reste de l'interface est encore en anglais.
- Données perso dans `perso/` (ignoré par git) : profil.md, memoire.md, criteres.md,
  deja_postule.md, regles_ecriture.md, CV. Secrets dans `.env` (ignoré).
- Limites de dépense : crédit prépayé sans recharge automatique chez le fournisseur d'API.

## Personnalité et mémoire
- Prompt d'identité : `[agent] default_system_prompt` dans `~/.openjarvis/config.toml`
  (copie de référence : `src/sebtix/config.exemple.toml`).
- Raccourcis dans `~/.openjarvis/` lus par OpenJarvis à chaque message :
  `SOUL.md -> src/sebtix/persona/SOUL.md` (personnalité, public),
  `USER.md -> perso/profil.md`, `MEMORY.md -> perso/memoire.md` (privés).
- **Gemma 3 ne sait pas appeler d'outils** (capacités Ollama : completion, vision). Les outils
  `memory_manage` / `user_profile_manage` ont donné des résultats faux → désactivés.
  La mémoire est gérée par `src/sebtix/memoire.py`, **sans le modèle** : « retiens / note /
  souviens-toi … », « oublie … » (rien n'est effacé si > 3 lignes correspondent),
  « qu'est-ce que tu sais sur moi ? ». Branché au début de `chat_completions`
  (`src/openjarvis/server/routes.py`) ; une note interne dit au modèle ce qui a été fait.
  À réutiliser tel quel pour Telegram (étape 4). Pas encore branché sur `sebtix ask` / `chat`.
- Outils activés : `web_search` seulement. `shell_exec` et `code_interpreter` désactivés
  (exécution de commandes sur le Mac).

## Outlook (Microsoft Graph) — étape 3
- Compte Hotmail seul = refusé par le portail Microsoft (pas de tenant). Solution retenue :
  **compte Azure gratuit** (créé le 2026-11-25 avec le compte Hotmail ; limite de dépense par
  défaut, ne jamais passer au « paiement à l'utilisation » sans accord). Incertitude : rien ne
  garantit que l'app reste utilisable après la fin de l'offre gratuite ; plan de secours =
  paiement à l'utilisation sans aucune ressource (0 €) + alerte budget 1 €, avec accord.
  Ne PAS utiliser le compte de l'école (tenant géré par l'école).
- App Entra « Sebtix » : comptes Microsoft personnels uniquement, « Autoriser les flux clients
  publics » = Activé (sinon AADSTS70002), permissions déléguées Mail.Read, Calendars.Read,
  offline_access. Client ID dans `.env` (`SEBTIX_MS_CLIENT_ID`), modèle dans `.env.example`.
- `src/sebtix/outlook.py` : MSAL, autorité `consumers`, connexion par code (device flow),
  jetons chiffrés dans le Trousseau macOS (`msal-extensions`, fichier
  `~/.openjarvis/sebtix/outlook_jetons.bin`). **GET uniquement** (test AST qui l'impose).
  Droits vérifiés dans le cache : `Calendars.Read Mail.Read openid profile`.
- Commandes : `sebtix outlook connecter | statut | mails [-n N] | agenda | deconnecter`
  (déclarées dans `src/sebtix/cli.py`, branché à la fin de `openjarvis/cli/__init__.py`).
- La Sentinelle (étape 4) aura besoin de sa propre connexion (même app, jeton chiffré côté
  Cloudflare).

## Sentinelle (Cloudflare Workers, offre gratuite) — étape 4
- Dossier `sentinelle/` (JavaScript). Déployer : `cd sentinelle && npx wrangler deploy`.
  Tests : `npx vitest run`. Journaux en direct : `npx wrangler tail`.
  URL : https://sebtix-sentinelle.sebtix-sentinelle.workers.dev (compte Cloudflare via GitHub).
  Télémétrie wrangler désactivée.
- Base D1 `sebtix` (Europe de l'Ouest), schéma `sentinelle/schema.sql` : messages (30 j, purge
  cron 03:00 UTC), memoire, etat (surveillance, profil, jetons Outlook chiffrés, compteur Azure),
  deja_vu (anti-doublons), taches, conso.
- Secrets Cloudflare (`npx wrangler secret list`) : TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
  TELEGRAM_WEBHOOK_SECRET, SEBTIX_SYNC_KEY, AZURE_SPEECH_KEY, CHIFFREMENT_CLE.
  Le Mac n'a que SEBTIX_SENTINELLE_URL et SEBTIX_SYNC_KEY dans `.env` (jamais le jeton Telegram).
- Bot Telegram @sebtix_bot : ne répond qu'au chat privé du propriétaire ; webhook vérifié par
  secret ; anti-doublon par update_id. Installation : `sebtix telegram installer` (jeton saisi
  masqué, envoyé directement à Cloudflare). Commandes : /aide /etat /stop /reprendre /mac.
- Modèles : chat **Mistral Small 3.1** (`@cf/mistralai/mistral-small-3.1-24b-instruct`, ~0,7 s,
  tutoie). Gemma 4 écarté : modèle « qui réfléchit », réponses vides (si réutilisé :
  `chat_template_kwargs.enable_thinking=false`). Transcription : whisper-large-v3-turbo (FR).
  **Voix : Azure Speech F0** (ressource `sebtix-voix-jam`, France Central, voix fr-FR-HenriNeural,
  bulles vocales OGG/Opus) — MeloTTS de Cloudflare retiré le 2026-11-20, aucune voix FR chez
  Cloudflare. Garde-fou à 480 000 caractères/mois. ⚠️ L'essai Azure devra passer en « paiement à
  l'utilisation » (0 € avec F0) vers le 2026-12-25 pour garder la voix : demander l'accord avant.
- Coût réel par réponse lu dans `usage.neurons` → table conso → `sebtix budget`.
- API privée du Mac (`sentinelle/src/api.js`, Bearer SEBTIX_SYNC_KEY) : etat, budget, profil,
  memoire (+ /commande), messages, taches, notifier, outlook/jeton, outlook/test,
  diagnostic (webhook), essai (réponse brute du modèle + test voix, n'enregistre rien).
- Outlook côté Sentinelle (`sentinelle/src/outlook.js`) : refresh token obtenu par
  `sebtix outlook connecter-sentinelle` (connexion séparée de celle du Mac), chiffré AES-GCM
  (clé CHIFFREMENT_CLE) dans `etat`, renouvelé et tourné automatiquement ; GET uniquement.

## Synchronisation Mac ↔ Sentinelle
- La Sentinelle est la source de vérité (mémoire, conversations, tâches, surveillance).
  `perso/memoire.md` = miroir réécrit par la synchro ; « retiens » hors ligne → mis en attente
  (`~/.openjarvis/sebtix/memoire_en_attente.txt`) puis renvoyé.
- `src/sebtix/sentinelle.py` (client), `conversation.py` (nouvelle conversation sur le Mac =
  10 derniers messages < 12 h insérés ; chaque échange du Mac envoyé en arrière-plan, branché dans
  `_record_completed_exchange` de routes.py), `synchro.py` (`sebtix sync` : profil → Sentinelle,
  miroir mémoire, tâches traitées avec le modèle local puis notifiées sur Telegram).
- `sebtix sync installer` = LaunchAgent `com.sebtix.sync` (toutes les 5 min + au réveil).
  **Installé le 2026-11-26 avec l'accord de l'utilisateur.** Journal : `~/.openjarvis/sebtix/sync.log`.
- `sebtix stop` / `sebtix reprendre` / `sebtix budget` (Sentinelle). L'ancien `stop`
  d'OpenJarvis (arrêt du serveur local) s'appelle `sebtix serveur-stop`.
- Garde-fou : sous pytest, `sentinelle.configuree()` renvoie toujours False.

## Tests
- `uv run --extra dev --extra server pytest tests/server tests/cli tests/sebtix -n 6`
- `cd sentinelle && npx vitest run`
- 7 échecs connus, antérieurs à Sebtix : `tests/cli/test_memory_cmd.py` et
  `tests/cli/test_ask_context.py` (extension Rust `openjarvis_rust` non compilée).

## Environnement installé
Homebrew, uv 0.13, Python 3.13 (venv `.venv`), Ollama 0.40 (service brew au démarrage),
Node 26, gh. Dans le Terminal : `cd ~/Projets/Sebtix` puis `uv run sebtix …`.
Interface web : `uv run sebtix gui` → http://127.0.0.1:5173. Si « port 5173 unavailable » :
l'ancienne interface tourne encore (attendre quelques secondes ou fermer l'ancienne).

**Modèle local : `gemma3:12b`** (choisi par l'utilisateur après comparaison ; `default_model` dans
`~/.openjarvis/config.toml`). Plus fiable et meilleur ton en français, ~14 tokens/s, 8,2 Go.
Repli possible à l'oral (étape 9) : `qwen3:8b` (21 tokens/s, quelques fautes).
Écartés : qwen3.5:9b (a inventé un détail en résumant un mail), ministral-3:8b (trop bavard).

## Points d'attention pour la suite
- Étapes 5 et 6 : les tâches planifiées de la Sentinelle doivent vérifier `surveillanceActive()`
  (`sebtix stop`) avant toute notification ou brief. Limite Workers Free : 5 crons.

## Avancement
| # | Étape | État |
|---|-------|------|
| 0 | Prérequis (outils Apple, Homebrew, GitHub) | ✅ |
| 1 | Installation (fork, dépendances, Ollama, choix du modèle) | ✅ |
| 2 | Rebranding, personnalité, mémoire (profil.md) | ✅ |
| 3 | Connexion Outlook (Graph, lecture seule) | ✅ |
| 4 | Sentinelle Cloudflare + Telegram + synchro + `sebtix stop` / `sebtix budget` | ✅ |
| 5 | Brief du matin (8h) | ⏳ |
| 6 | Surveillance des mails | ⏳ |
| 7 | Veille emploi (9h) | ⏳ |
| 8 | Candidatures PDF | ⏳ |
| 9 | Voix sur le Mac | ⏳ |
| 10 | Guide d'utilisation + vérification des critères | ⏳ |

## Journal
- 2026-11-25 — Étape 1 : fork cloné, dépendances installées, analytics coupé, modèles testés :
  qwen3:8b, ministral-3:8b, gemma3:12b, qwen3.5:9b → **gemma3:12b retenu**, les autres supprimés.
  Interface web testée : réponse en français en ~6 s. Dossier `perso/` ignoré par git (dépôt public).
- 2026-11-25 — Étape 2 : commande `sebtix`, bannière et interface renommées, concours /
  leaderboard / minage retirés, personnalité FR (SOUL.md), profil + mémoire dans `perso/`,
  mémoire déterministe (`src/sebtix/memoire.py`, 13 tests). Testé dans l'interface web :
  identité, « retiens », « qu'est-ce que tu sais sur moi ? », « oublie » → OK. NOTICE ajouté.
- 2026-11-25 — Étape 3 : compte Azure gratuit + app Entra « Sebtix » (lecture seule),
  connecteur Graph `src/sebtix/outlook.py` (jetons dans le Trousseau), commandes
  `sebtix outlook …`. Testé sur la vraie boîte : 5 derniers mails + agenda du jour OK.
- 2026-11-26 — Étape 4 : Sentinelle Cloudflare (D1, Workers AI) + bot Telegram privé (texte,
  vocaux, réponses vocales Azure), mémoire/conversations partagées, file de tâches `/mac`,
  `sebtix sync | stop | reprendre | budget`, Outlook chiffré côté Sentinelle. Tout testé en réel.
