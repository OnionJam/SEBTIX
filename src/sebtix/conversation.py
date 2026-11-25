"""Continuité des conversations entre le téléphone (Telegram) et le Mac.

- Nouvelle conversation sur le Mac → on y place d'abord les derniers échanges récents
  (Telegram ou Mac) gardés par la Sentinelle : tu continues sans répéter le contexte.
- Chaque échange fait sur le Mac est envoyé à la Sentinelle (en arrière-plan).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sebtix import sentinelle

journal = logging.getLogger("sebtix.conversation")

FENETRE = timedelta(hours=12)
NOMBRE = 10
MARQUE_NOTE = "\n\n[Note interne de Sebtix"


def _recents() -> list[dict]:
    limite = datetime.now(timezone.utc) - FENETRE
    gardes = []
    for m in sentinelle.messages_recents(NOMBRE):
        quand = datetime.fromisoformat(m["cree_le"].replace("Z", "+00:00"))
        if quand >= limite:
            gardes.append(m)
    # L'historique doit commencer par une question de l'utilisateur.
    while gardes and gardes[0]["role"] != "user":
        gardes.pop(0)
    return gardes


def reprendre_contexte(messages: list[Any], fabriquer: Callable[[str, str], Any]) -> int:
    """Si `messages` est une NOUVELLE conversation, y insère les échanges récents.

    `fabriquer(role, contenu)` crée un objet message du bon type. Renvoie le nombre inséré.
    """
    if not sentinelle.configuree():
        return 0
    roles = [getattr(m, "role", None) for m in messages]
    if roles.count("user") != 1 or "assistant" in roles:
        return 0
    try:
        recents = _recents()
    except sentinelle.SentinelleInjoignable:
        return 0
    if not recents:
        return 0
    position = roles.index("user")
    for decalage, m in enumerate(recents):
        messages.insert(position + decalage, fabriquer(m["role"], m["contenu"]))
    return len(recents)


def partager_echange(question: str, reponse: str) -> None:
    """Envoie un échange du Mac à la Sentinelle, sans la note interne de mémoire."""
    question = question.split(MARQUE_NOTE, 1)[0]
    sentinelle.envoyer_echange_en_arriere_plan(question, reponse)
