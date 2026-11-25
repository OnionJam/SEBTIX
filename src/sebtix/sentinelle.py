"""Client de la Sentinelle (Cloudflare) côté Mac : synchronisation de l'état partagé.

La Sentinelle est la source de vérité pour : mémoire, conversations, tâches en attente,
état de la surveillance. Le Mac lui envoie son profil (perso/profil.md) et ses conversations.
Adresse et clé : SEBTIX_SENTINELLE_URL et SEBTIX_SYNC_KEY dans .env.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

import httpx

from sebtix.config import reglage

journal = logging.getLogger("sebtix.sentinelle")


class SentinelleInjoignable(RuntimeError):
    """Pas d'Internet, Sentinelle non configurée, ou refus."""


def configuree() -> bool:
    # Garde-fou : les tests automatiques ne parlent jamais à la vraie Sentinelle.
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    return bool(reglage("SEBTIX_SENTINELLE_URL") and reglage("SEBTIX_SYNC_KEY"))


def _appel(methode: str, chemin: str, json: Any = None, timeout: float = 10) -> Any:
    if not configuree():
        raise SentinelleInjoignable("Sentinelle non configurée (sebtix telegram installer).")
    try:
        r = httpx.request(
            methode,
            reglage("SEBTIX_SENTINELLE_URL").rstrip("/") + chemin,
            json=json,
            headers={"Authorization": f"Bearer {reglage('SEBTIX_SYNC_KEY')}"},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise SentinelleInjoignable(f"Sentinelle injoignable : {e}") from e
    if r.status_code >= 400:
        raise SentinelleInjoignable(f"Sentinelle : erreur {r.status_code} ({r.text[:200]})")
    return r.json()


# ------------------------------------------------------------------ état et budget


def etat() -> str:
    return _appel("GET", "/api/etat")["surveillance"]


def definir_surveillance(active: bool) -> str:
    return _appel("POST", "/api/etat", {"surveillance": "on" if active else "off"})["surveillance"]


def budget() -> dict:
    return _appel("GET", "/api/budget")


def notifier(texte: str) -> None:
    _appel("POST", "/api/notifier", {"texte": texte})


# ------------------------------------------------------------------ profil et mémoire


def pousser_profil(texte: str) -> None:
    _appel("PUT", "/api/profil", {"texte": texte})


def memoire() -> list[dict]:
    return _appel("GET", "/api/memoire")["memoire"]


def commande_memoire(texte: str) -> Optional[str]:
    """Exécute « retiens / oublie / que sais-tu » côté Sentinelle. Renvoie la note, ou None."""
    return _appel("POST", "/api/memoire/commande", {"texte": texte})["note"]


# ------------------------------------------------------------------ conversations


def messages_recents(limite: int = 10) -> list[dict]:
    return _appel("GET", f"/api/messages?limite={limite}")["messages"]


def envoyer_echange(question: str, reponse: str) -> None:
    _appel(
        "POST",
        "/api/messages",
        {
            "messages": [
                {"canal": "mac", "role": "user", "contenu": question},
                {"canal": "mac", "role": "assistant", "contenu": reponse},
            ]
        },
    )


def envoyer_echange_en_arriere_plan(question: str, reponse: str) -> None:
    """Ne ralentit jamais une réponse : envoi dans un fil séparé, erreurs ignorées."""

    def _envoi() -> None:
        try:
            envoyer_echange(question, reponse)
        except Exception:  # noqa: BLE001
            journal.debug("Échange non synchronisé", exc_info=True)

    if configuree() and question.strip() and reponse.strip():
        threading.Thread(target=_envoi, daemon=True).start()


# ------------------------------------------------------------------ tâches


def taches_en_attente() -> list[dict]:
    return _appel("GET", "/api/taches")["taches"]


def maj_tache(identifiant: int, statut: str, resultat: Optional[str] = None) -> None:
    _appel("POST", f"/api/taches/{identifiant}", {"statut": statut, "resultat": resultat})
