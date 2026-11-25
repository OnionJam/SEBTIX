"""Mémoire de Sebtix : « retiens… », « oublie… », « qu'est-ce que tu sais sur moi ? ».

Ces commandes sont traitées ici, de façon déterministe, AVANT d'appeler le modèle :
le modèle local (Gemma 3) ne sait pas appeler d'outils de façon fiable, et un
assistant qui répond « noté » sans rien noter est pire qu'inutile.

L'action est faite ici, puis une note interne est ajoutée au message de
l'utilisateur pour que le modèle confirme exactement ce qui a été fait.

Fichiers (raccourcis dans le dossier de config OpenJarvis) :
- MEMORY.md -> perso/memoire.md : ce que Sebtix a retenu (il peut écrire dedans)
- USER.md   -> perso/profil.md  : profil rédigé par l'utilisateur (« oublie » peut en retirer une ligne)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

# Au-delà de ce nombre de lignes correspondantes, on ne supprime rien (trop ambigu).
MAX_LIGNES_OUBLIEES = 3

_PREFIXE = r"^\s*(?:(?:hey|ok|dis)\s+)?(?:sebtix\s*[,!:.]?\s*)?"

_RE_RETENIR = re.compile(
    _PREFIXE
    + r"(?:retiens|r[ée]tiens|note|m[ée]morise|souviens[- ]toi|rappelle[- ]toi)\s+"
    + r"(?:bien\s+)?(?:(?:le\s+fait\s+)?que\s+|qu['’]\s*|[çc]a\s*:\s*|:\s*)?(?P<texte>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_RE_OUBLIER = re.compile(
    _PREFIXE
    + r"(?:oublie|efface\s+de\s+ta\s+m[ée]moire|supprime\s+de\s+ta\s+m[ée]moire)\s+"
    + r"(?:(?:le\s+fait\s+)?que\s+|qu['’]\s*|tout\s+ce\s+qui\s+concerne\s+|[çc]a\s*:\s*|:\s*)?(?P<texte>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_RE_SAVOIR = re.compile(
    r"(qu['’]est[- ]ce\s+que\s+tu\s+sais|que\s+sais[- ]tu|tu\s+sais\s+quoi|tu\s+connais\s+quoi)"
    r"\s+(sur|de)\s+moi",
    re.IGNORECASE,
)

_MOTS_VIDES = {
    "alors", "aussi", "avec", "dans", "elle", "elles", "est", "etait", "etre", "leur",
    "mais", "mes", "moi", "mon", "nous", "pour", "plus", "que", "quand", "qui", "sans",
    "ses", "son", "sont", "sur", "tes", "ton", "tous", "tout", "une", "des", "les",
    "the", "que", "jamais", "toujours", "fait", "faire", "suis", "ai", "as", "avoir",
}


@dataclass
class ResultatMemoire:
    """Ce qui a été fait (ou pas), et la note à transmettre au modèle."""

    action: str  # "ajout", "deja_connu", "oubli", "introuvable", "ambigu", "consultation"
    note: str
    lignes: list[str] = field(default_factory=list)


def _chemins() -> tuple[Path, Path]:
    from openjarvis.core.paths import get_config_dir

    base = get_config_dir()
    return base / "MEMORY.md", base / "USER.md"


def _normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in texte if not unicodedata.combining(c))


def _mots_cles(texte: str) -> set[str]:
    mots = re.findall(r"[a-z0-9]+", _normaliser(texte))
    return {m for m in mots if len(m) >= 3 and m not in _MOTS_VIDES}


def _nettoyer(texte: str) -> str:
    texte = " ".join(texte.split()).strip().rstrip(".!")
    return texte[:1].upper() + texte[1:] if texte else texte


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8") if chemin.exists() else ""


def retenir(texte: str, memoire: Path) -> ResultatMemoire:
    entree = _nettoyer(texte)
    contenu = _lire(memoire)
    if _normaliser(entree) in _normaliser(contenu):
        return ResultatMemoire(
            "deja_connu",
            f"C'était déjà dans ta mémoire : « {entree} ». Dis-le simplement.",
            [entree],
        )
    if not contenu.strip():
        contenu = "# Ce que Sebtix a retenu\n"
    ligne = f"- [{date.today().isoformat()}] {entree}"
    memoire.parent.mkdir(parents=True, exist_ok=True)
    memoire.write_text(contenu.rstrip() + "\n" + ligne + "\n", encoding="utf-8")
    return ResultatMemoire(
        "ajout",
        f"C'est fait : tu as ajouté à ta mémoire « {entree} ». Confirme-le en une phrase courte.",
        [entree],
    )


def oublier(texte: str, memoire: Path, profil: Path) -> ResultatMemoire:
    cles = _mots_cles(texte)
    if not cles:
        return ResultatMemoire(
            "introuvable",
            "La demande d'oubli était trop vague : rien n'a été effacé. "
            "Demande-lui de préciser ce qu'il faut oublier.",
        )
    seuil = max(1, (len(cles) + 1) // 2)  # au moins la moitié des mots-clés
    trouvees: list[tuple[Path, str]] = []
    for chemin in (memoire, profil):
        for ligne in _lire(chemin).splitlines():
            if ligne.lstrip().startswith("- ") and len(cles & _mots_cles(ligne)) >= seuil:
                trouvees.append((chemin, ligne))

    if not trouvees:
        return ResultatMemoire(
            "introuvable",
            f"Rien dans ta mémoire ni dans son profil ne correspond à « {texte.strip()} » : "
            "rien n'a été effacé. Dis-le-lui franchement.",
        )
    if len(trouvees) > MAX_LIGNES_OUBLIEES:
        lignes = [l.strip() for _, l in trouvees]
        return ResultatMemoire(
            "ambigu",
            f"{len(trouvees)} éléments correspondent, c'est trop vague : rien n'a été effacé. "
            "Montre-lui ces éléments et demande lequel oublier :\n" + "\n".join(lignes),
            lignes,
        )
    for chemin in {c for c, _ in trouvees}:
        a_retirer = {l for c, l in trouvees if c == chemin}
        restant = [l for l in _lire(chemin).splitlines() if l not in a_retirer]
        chemin.write_text("\n".join(restant).rstrip() + "\n", encoding="utf-8")
    lignes = [l.strip().removeprefix("- ") for _, l in trouvees]
    return ResultatMemoire(
        "oubli",
        "C'est fait, tu as oublié : " + " ; ".join(f"« {l} »" for l in lignes)
        + ". Confirme-le en une phrase courte.",
        lignes,
    )


def consulter(memoire: Path, profil: Path) -> ResultatMemoire:
    contenu_profil = _lire(profil).strip() or "(profil vide)"
    contenu_memoire = _lire(memoire).strip() or "(mémoire vide)"
    return ResultatMemoire(
        "consultation",
        "Il demande ce que tu sais sur lui. Résume fidèlement et brièvement UNIQUEMENT ceci, "
        "sans rien ajouter ni deviner, et rappelle qu'il peut te dire « oublie … » :\n\n"
        f"PROFIL :\n{contenu_profil}\n\nMÉMOIRE :\n{contenu_memoire}",
    )


def traiter(
    texte: str,
    memoire: Optional[Path] = None,
    profil: Optional[Path] = None,
) -> Optional[ResultatMemoire]:
    """Exécute la commande de mémoire contenue dans `texte`, s'il y en a une."""
    if memoire is None or profil is None:
        defaut_memoire, defaut_profil = _chemins()
        memoire = memoire or defaut_memoire
        profil = profil or defaut_profil

    if m := _RE_OUBLIER.match(texte):
        return oublier(m.group("texte"), memoire, profil)
    if m := _RE_RETENIR.match(texte):
        return retenir(m.group("texte"), memoire)
    if _RE_SAVOIR.search(texte):
        return consulter(memoire, profil)
    return None


def note_interne(resultat: ResultatMemoire) -> str:
    return f"\n\n[Note interne de Sebtix, invisible pour l'utilisateur — {resultat.note}]"


# ------------------------------------------------------------------ mémoire partagée (Sentinelle)


def _fichier_en_attente() -> Path:
    from sebtix.config import dossier_donnees

    return dossier_donnees() / "memoire_en_attente.txt"


def ecrire_miroir(souvenirs: list[dict], memoire: Optional[Path] = None) -> None:
    """Réécrit perso/memoire.md à partir de la mémoire de la Sentinelle (source de vérité)."""
    memoire = memoire or _chemins()[0]
    lignes = ["# Ce que Sebtix a retenu"] + [f"- {s['texte']}" for s in souvenirs]
    memoire.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def synchroniser_memoire() -> int:
    """Envoie les « retiens » faits hors ligne, puis met le miroir local à jour.

    Renvoie le nombre de souvenirs. Lève SentinelleInjoignable si la Sentinelle ne répond pas.
    """
    from sebtix import sentinelle

    attente = _fichier_en_attente()
    if attente.exists():
        for ligne in attente.read_text(encoding="utf-8").splitlines():
            if ligne.strip():
                sentinelle.commande_memoire(ligne)
        attente.unlink()
    souvenirs = sentinelle.memoire()
    ecrire_miroir(souvenirs)
    return len(souvenirs)


def traiter_partage(texte: str) -> Optional[ResultatMemoire]:
    """Comme `traiter`, mais via la mémoire partagée de la Sentinelle quand elle est joignable."""
    from sebtix import sentinelle

    commande = _RE_OUBLIER.match(texte) or _RE_RETENIR.match(texte) or _RE_SAVOIR.search(texte)
    if commande is None:
        return None
    if not sentinelle.configuree():
        return traiter(texte)

    try:
        note = sentinelle.commande_memoire(texte)
        synchroniser_memoire()
    except sentinelle.SentinelleInjoignable:
        resultat = traiter(texte)  # hors ligne : en local, envoyé à la prochaine synchro
        if resultat and resultat.action == "ajout":
            with _fichier_en_attente().open("a", encoding="utf-8") as f:
                f.write(texte.replace("\n", " ") + "\n")
        return resultat

    if note is None:
        return None
    # « oublie » : la mémoire partagée n'a rien trouvé → peut-être une ligne du profil (local).
    if (m := _RE_OUBLIER.match(texte)) and note.startswith("Rien dans ta mémoire"):
        local = oublier(m.group("texte"), Path("/sebtix-inexistant"), _chemins()[1])
        if local.action in ("oubli", "ambigu"):
            return local
    if _RE_SAVOIR.search(texte) and not _RE_OUBLIER.match(texte) and not _RE_RETENIR.match(texte):
        # Le profil fait foi côté Mac (fichier local, toujours à jour).
        return consulter(*_chemins())
    return ResultatMemoire("partage", note)


def appliquer_aux_messages(messages: list[Any]) -> Optional[ResultatMemoire]:
    """Traite le DERNIER message utilisateur d'une requête de chat (objets avec .role/.content).

    Ajoute la note interne au message pour que le modèle confirme ce qui a été fait.
    """
    for message in reversed(messages):
        if getattr(message, "role", None) != "user":
            continue
        contenu = getattr(message, "content", None)
        if not isinstance(contenu, str) or "[Note interne de Sebtix" in contenu:
            return None
        resultat = traiter_partage(contenu)
        if resultat is not None:
            message.content = contenu + note_interne(resultat)
        return resultat
    return None
