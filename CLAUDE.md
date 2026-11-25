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
  tout ce qui est visible est renommé Sebtix ; modules perso dans un paquet `sebtix/` séparé.
- Remote `upstream` = open-jarvis/OpenJarvis.
- Analytics PostHog : **désactivé** (`~/.openjarvis/config.toml`, `[analytics] enabled = false`).
- Module de minage « Pearl » : jamais installé (extra optionnel), à retirer de la CLI.
- Données perso dans `perso/` (ignoré par git) : profil.md, criteres.md, deja_postule.md,
  regles_ecriture.md, CV. Secrets dans `.env` (ignoré).
- Limites de dépense : crédit prépayé sans recharge automatique chez le fournisseur d'API.

## Environnement installé
Homebrew, uv 0.13, Python 3.13 (venv `.venv`), Ollama 0.40 (service brew au démarrage),
Node 26, gh. Lancer OpenJarvis : `uv run jarvis …` depuis le dossier du projet.
Interface web : `uv run jarvis gui` → http://127.0.0.1:5173.

**Modèle local : `gemma3:12b`** (choisi par l'utilisateur après comparaison ; `default_model` dans
`~/.openjarvis/config.toml`). Plus fiable et meilleur ton en français, ~14 tokens/s, 8,2 Go.
Repli possible à l'oral (étape 9) : `qwen3:8b` (21 tokens/s, quelques fautes).
Écartés : qwen3.5:9b (a inventé un détail en résumant un mail), ministral-3:8b (trop bavard).

## À faire à l'étape 2 (repéré à l'étape 1)
- Supprimer la fenêtre « Win a Mac mini » (concours + analytics + e-mail vers Supabase) et le
  bloc « Leaderboard / Share your savings » de l'interface.
- Retirer les commandes `mine` et `pearl` de la CLI.

## Avancement
| # | Étape | État |
|---|-------|------|
| 0 | Prérequis (outils Apple, Homebrew, GitHub) | ✅ |
| 1 | Installation (fork, dépendances, Ollama, choix du modèle) | ✅ |
| 2 | Rebranding, personnalité, mémoire (profil.md) | ⏳ |
| 3 | Connexion Outlook (Graph, lecture seule) | ⏳ |
| 4 | Sentinelle Cloudflare + Telegram + synchro + `sebtix stop` / `sebtix budget` | ⏳ |
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
