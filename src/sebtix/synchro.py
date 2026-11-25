"""Synchronisation Mac ↔ Sentinelle et traitement des tâches lourdes (`sebtix sync`).

Lancée toutes les 5 minutes par macOS (LaunchAgent) tant que le Mac est allumé, et dès
son réveil : c'est ainsi que le Cerveau traite les tâches mises en file depuis le téléphone.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from sebtix import sentinelle
from sebtix.config import RACINE, dossier_donnees

OLLAMA = "http://127.0.0.1:11434"
LIBELLE = "com.sebtix.sync"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LIBELLE}.plist"


@dataclass
class Bilan:
    profil: bool = False
    souvenirs: int = 0
    taches_faites: list[int] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)


def _modele_local() -> str:
    from openjarvis.core.config import load_config

    return load_config().intelligence.default_model or "gemma3:12b"


def _profil_et_persona() -> tuple[str, str]:
    from openjarvis.core.paths import get_config_dir

    base = get_config_dir()
    lire = lambda nom: (base / nom).read_text(encoding="utf-8") if (base / nom).exists() else ""  # noqa: E731
    return lire("USER.md"), lire("SOUL.md")


def executer_tache(demande: str) -> str:
    """Traite une demande avec le modèle local (Ollama). Peut prendre plusieurs minutes."""
    profil, persona = _profil_et_persona()
    systeme = (
        f"{persona}\n\n## Contexte\nTu traites une tâche mise en attente depuis le téléphone, "
        "maintenant que le Mac est rallumé. Ta réponse lui sera envoyée sur Telegram : "
        "va droit au but, 3 500 caractères maximum.\n\n## Profil (USER)\n" + profil
    )
    r = httpx.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": _modele_local(),
            "stream": False,
            "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": demande}],
        },
        timeout=900,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()[:3500]


def synchroniser(traiter_taches: bool = True) -> Bilan:
    from sebtix.memoire import _chemins, synchroniser_memoire

    bilan = Bilan()
    profil = _chemins()[1]
    if profil.exists():
        sentinelle.pousser_profil(profil.read_text(encoding="utf-8"))
        bilan.profil = True
    bilan.souvenirs = synchroniser_memoire()

    if traiter_taches:
        for tache in sentinelle.taches_en_attente():
            sentinelle.maj_tache(tache["id"], "en_cours")
            try:
                resultat = executer_tache(tache["demande"])
                sentinelle.maj_tache(tache["id"], "faite", resultat)
                bilan.taches_faites.append(tache["id"])
            except Exception as e:  # noqa: BLE001
                sentinelle.maj_tache(tache["id"], "erreur", f"{type(e).__name__} : {e}"[:300])
                bilan.erreurs.append(f"tâche {tache['id']} : {e}")
    return bilan


# ------------------------------------------------------------------ automatisation macOS


def installer_automatisation() -> Path:
    """Installe un LaunchAgent : `sebtix sync` toutes les 5 min et à chaque ouverture de session."""
    journal = dossier_donnees() / "sync.log"
    contenu = {
        "Label": LIBELLE,
        "ProgramArguments": [str(RACINE / ".venv" / "bin" / "sebtix"), "--quiet", "sync"],
        "WorkingDirectory": str(RACINE),
        "StartInterval": 300,
        "RunAtLoad": True,
        "StandardOutPath": str(journal),
        "StandardErrorPath": str(journal),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/bin:/bin"},
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(contenu))
    domaine = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domaine, str(PLIST)], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domaine, str(PLIST)], check=True, capture_output=True)
    return PLIST


def desinstaller_automatisation() -> bool:
    if not PLIST.exists():
        return False
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
    PLIST.unlink()
    return True


def automatisation_installee() -> bool:
    return PLIST.exists()
