"""Assistant d'installation du bot Telegram de Sebtix (`sebtix telegram installer`).

Le jeton du bot est saisi de façon masquée et envoyé directement à Cloudflare
(`wrangler secret put`) : il n'est jamais affiché, ni écrit dans un fichier du Mac.
"""

from __future__ import annotations

import getpass
import secrets
import shutil
import subprocess
from pathlib import Path

import click
import httpx

from sebtix.config import FICHIER_ENV, RACINE, reglage

DOSSIER_SENTINELLE = RACINE / "sentinelle"
URL_PAR_DEFAUT = "https://sebtix-sentinelle.sebtix-sentinelle.workers.dev"


def _telegram(jeton: str, methode: str, **params) -> dict:
    r = httpx.post(f"https://api.telegram.org/bot{jeton}/{methode}", json=params, timeout=60)
    donnees = r.json()
    if not donnees.get("ok"):
        raise click.ClickException(f"Telegram refuse ({methode}) : {donnees.get('description')}")
    return donnees["result"]


def _npx() -> str:
    chemin = shutil.which("npx") or "/opt/homebrew/bin/npx"
    if not Path(chemin).exists():
        raise click.ClickException("npx introuvable : Node n'est pas installé (brew install node).")
    return chemin


def _secret_cloudflare(nom: str, valeur: str) -> None:
    """Range un secret dans la Sentinelle (chiffré chez Cloudflare)."""
    resultat = subprocess.run(
        [_npx(), "wrangler", "secret", "put", nom],
        input=valeur,
        text=True,
        capture_output=True,
        cwd=DOSSIER_SENTINELLE,
    )
    if resultat.returncode != 0:
        raise click.ClickException(f"Cloudflare refuse le secret {nom} : {resultat.stderr[-500:]}")


def _ecrire_env(valeurs: dict[str, str]) -> None:
    """Ajoute/remplace des lignes CLE=valeur dans .env (privé, jamais commité)."""
    lignes = FICHIER_ENV.read_text(encoding="utf-8").splitlines() if FICHIER_ENV.exists() else []
    restantes = [l for l in lignes if l.split("=", 1)[0].strip() not in valeurs]
    if not any(l.startswith("# Sentinelle") for l in restantes):
        restantes.append("# Sentinelle (Cloudflare) et Telegram")
    restantes += [f"{cle}={val}" for cle, val in valeurs.items()]
    FICHIER_ENV.write_text("\n".join(restantes) + "\n", encoding="utf-8")
    FICHIER_ENV.chmod(0o600)


def installer() -> None:
    url = reglage("SEBTIX_SENTINELLE_URL", URL_PAR_DEFAUT).rstrip("/")

    click.echo("Colle le jeton donné par @BotFather (il ne s'affichera pas), puis Entrée :")
    jeton = getpass.getpass("Jeton : ").strip()
    jeton = jeton.split()[-1] if jeton else jeton  # ignore un éventuel texte collé avant
    if ":" not in jeton:
        raise click.ClickException("Ça ne ressemble pas à un jeton de bot (format 123456:ABC…).")

    try:
        bot = _telegram(jeton, "getMe")
    except click.ClickException:
        numero, _, reste = jeton.partition(":")
        raise click.ClickException(
            f"Telegram ne reconnaît pas ce jeton. Reçu : bot n°{numero}, {len(reste)} caractères "
            "après les deux-points (il en faut 35). Recopie-le depuis BotFather : /mybots → ton bot "
            "→ API Token, puis appuie sur le jeton pour le copier."
        )
    click.echo(f"✓ Bot trouvé : @{bot['username']}")

    # Le webhook doit être coupé pour lire les messages en attente.
    _telegram(jeton, "deleteWebhook", drop_pending_updates=False)
    def _lire_personnes(attente: int) -> dict:
        trouvees = {}
        for maj in _telegram(jeton, "getUpdates", allowed_updates=["message"], timeout=attente):
            chat = (maj.get("message") or {}).get("chat") or {}
            if chat.get("type") == "private":
                trouvees[chat["id"]] = chat.get("first_name", "") + (
                    f" (@{chat['username']})" if chat.get("username") else ""
                )
        return trouvees

    personnes = _lire_personnes(0)
    if not personnes:
        click.echo(
            f"\n👉 Maintenant, sur ton téléphone : ouvre t.me/{bot['username']} et envoie « salut ».\n"
            "J'attends ton message (2 minutes max)…"
        )
        for _ in range(3):
            personnes = _lire_personnes(40)
            if personnes:
                break
    if not personnes:
        raise click.ClickException(
            f"Aucun message reçu. Vérifie que tu écris bien à @{bot['username']}, puis relance."
        )
    if len(personnes) > 1:
        click.echo("Plusieurs personnes ont écrit au bot :")
        for i, (cid, nom) in enumerate(personnes.items(), 1):
            click.echo(f"  {i}. {nom}")
        choix = click.prompt("Lequel est TON compte ? (numéro)", type=click.IntRange(1, len(personnes)))
        chat_id, nom = list(personnes.items())[choix - 1]
    else:
        chat_id, nom = next(iter(personnes.items()))
        if not click.confirm(f"Le bot ne répondra qu'à : {nom}. C'est bien toi ?", default=True):
            raise click.ClickException("Installation annulée.")

    secret_webhook = secrets.token_urlsafe(32)
    cle_synchro = secrets.token_urlsafe(32)

    click.echo("Envoi des secrets à Cloudflare (chiffrés)…")
    _secret_cloudflare("TELEGRAM_TOKEN", jeton)
    _secret_cloudflare("TELEGRAM_CHAT_ID", str(chat_id))
    _secret_cloudflare("TELEGRAM_WEBHOOK_SECRET", secret_webhook)
    _secret_cloudflare("SEBTIX_SYNC_KEY", cle_synchro)

    _telegram(
        jeton,
        "setWebhook",
        url=f"{url}/telegram",
        secret_token=secret_webhook,
        allowed_updates=["message"],
        drop_pending_updates=True,
    )
    _telegram(
        jeton,
        "setMyCommands",
        commands=[
            {"command": "aide", "description": "Ce que je sais faire"},
            {"command": "etat", "description": "État de la surveillance"},
            {"command": "stop", "description": "Couper toute la surveillance"},
            {"command": "reprendre", "description": "Relancer la surveillance"},
        ],
    )

    # Le Mac n'a PAS besoin du jeton Telegram : il passe par la Sentinelle.
    _ecrire_env({"SEBTIX_SENTINELLE_URL": url, "SEBTIX_SYNC_KEY": cle_synchro})
    _telegram(jeton, "sendMessage", chat_id=chat_id, text="✅ Sebtix est en ligne. Écris-moi ou envoie un vocal !")
    click.echo(f"✅ Terminé. Le bot @{bot['username']} ne répond qu'à {nom}. Regarde ton téléphone !")
