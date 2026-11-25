"""Réglages de Sebtix : lecture du fichier .env (jamais commité) et chemins communs."""

from __future__ import annotations

import os
from pathlib import Path

# Racine du dépôt : src/sebtix/config.py -> ../../
RACINE = Path(__file__).resolve().parents[2]
FICHIER_ENV = RACINE / ".env"


def _lire_env(chemin: Path = FICHIER_ENV) -> dict[str, str]:
    valeurs: dict[str, str] = {}
    if not chemin.exists():
        return valeurs
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        valeurs[cle.strip()] = valeur.strip().strip('"').strip("'")
    return valeurs


def reglage(cle: str, defaut: str = "") -> str:
    """Variable d'environnement si définie, sinon valeur du fichier .env, sinon `defaut`."""
    return os.environ.get(cle) or _lire_env().get(cle) or defaut


def dossier_donnees() -> Path:
    """Dossier privé où Sebtix range ses données techniques (hors dépôt git)."""
    from openjarvis.core.paths import get_config_dir

    dossier = get_config_dir() / "sebtix"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier
