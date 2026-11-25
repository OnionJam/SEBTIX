"""Connexion Outlook de Sebtix via Microsoft Graph — LECTURE SEULE.

Garanties de sécurité, à deux niveaux :
1. Côté Microsoft : l'application « Sebtix » ne demande que Mail.Read et Calendars.Read
   (+ offline_access, ajouté automatiquement par MSAL). Avec ces droits, Microsoft refuse
   tout envoi, suppression ou déplacement de mail.
2. Côté code : ce module n'expose qu'une fonction HTTP, `_get` (requêtes GET). Il n'existe
   aucun chemin pour POST / PATCH / DELETE.

Connexion « par code » (device code flow) : aucun mot de passe ne transite par Sebtix.
La clé de connexion (jeton) est rangée chiffrée dans le Trousseau d'accès de macOS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import httpx

from sebtix.config import dossier_donnees, reglage

AUTORITE = "https://login.microsoftonline.com/consumers"  # comptes Microsoft personnels
DROITS = ["Mail.Read", "Calendars.Read"]  # offline_access est ajouté par MSAL
GRAPH = "https://graph.microsoft.com/v1.0"
FUSEAU = "Europe/Paris"


class OutlookNonConnecte(RuntimeError):
    """Aucun compte connecté (ou connexion expirée) : lancer `sebtix outlook connecter`."""


# ---------------------------------------------------------------- authentification


def _client_id() -> str:
    client_id = reglage("SEBTIX_MS_CLIENT_ID")
    if not client_id:
        raise RuntimeError(
            "SEBTIX_MS_CLIENT_ID manquant dans le fichier .env "
            "(ID d'application de l'app Sebtix sur portal.azure.com)."
        )
    return client_id


def _cache_jetons():
    from msal_extensions import PersistedTokenCache, build_encrypted_persistence

    persistance = build_encrypted_persistence(str(dossier_donnees() / "outlook_jetons.bin"))
    return PersistedTokenCache(persistance)


def _application():
    import msal

    return msal.PublicClientApplication(
        _client_id(), authority=AUTORITE, token_cache=_cache_jetons()
    )


def compte_connecte() -> Optional[str]:
    """Adresse du compte connecté, ou None."""
    comptes = _application().get_accounts()
    return comptes[0].get("username") if comptes else None


def connecter(afficher: Callable[[str], None] = print) -> str:
    """Connexion par code à usage unique. Renvoie l'adresse du compte connecté."""
    app = _application()
    flux = app.initiate_device_flow(scopes=DROITS)
    if "user_code" not in flux:
        raise RuntimeError(f"Microsoft a refusé de démarrer la connexion : {flux}")
    afficher(
        f"\n1. Ouvre {flux['verification_uri']}\n"
        f"2. Tape ce code : {flux['user_code']}\n"
        "3. Connecte-toi avec ton compte Hotmail et accepte les autorisations "
        "(lecture des mails et de l'agenda).\n"
        "J'attends que ce soit fait…\n"
    )
    resultat = app.acquire_token_by_device_flow(flux)  # bloque jusqu'à la fin
    if "access_token" not in resultat:
        raise RuntimeError(
            "Connexion refusée : "
            f"{resultat.get('error')} — {resultat.get('error_description', '')}"
        )
    return resultat.get("id_token_claims", {}).get("preferred_username", "compte inconnu")


def connecter_sentinelle(afficher: Callable[[str], None] = print) -> None:
    """Connexion par code dédiée à la Sentinelle : le jeton part chez elle, rien n'est gardé ici."""
    import msal

    from sebtix import sentinelle

    app = msal.PublicClientApplication(_client_id(), authority=AUTORITE)  # cache en mémoire
    flux = app.initiate_device_flow(scopes=DROITS)
    if "user_code" not in flux:
        raise RuntimeError(f"Microsoft a refusé de démarrer la connexion : {flux}")
    afficher(
        f"\n1. Ouvre {flux['verification_uri']}\n2. Tape ce code : {flux['user_code']}\n"
        "3. Connecte-toi avec ton compte Hotmail et accepte.\nJ'attends…\n"
    )
    resultat = app.acquire_token_by_device_flow(flux)
    jeton = resultat.get("refresh_token")
    if not jeton:
        raise RuntimeError(f"Connexion refusée : {resultat.get('error_description', resultat.get('error'))}")
    sentinelle._appel("POST", "/api/outlook/jeton", {"refresh_token": jeton})


def deconnecter() -> None:
    app = _application()
    for compte in app.get_accounts():
        app.remove_account(compte)


def _jeton() -> str:
    app = _application()
    comptes = app.get_accounts()
    if not comptes:
        raise OutlookNonConnecte("Outlook n'est pas connecté : lance `sebtix outlook connecter`.")
    resultat = app.acquire_token_silent(DROITS, account=comptes[0])
    if not resultat or "access_token" not in resultat:
        raise OutlookNonConnecte(
            "La connexion Outlook a expiré : relance `sebtix outlook connecter`."
        )
    return resultat["access_token"]


# ---------------------------------------------------------------- lecture (GET uniquement)


def _get(chemin: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Unique accès à Graph : une requête GET. Aucune écriture n'est possible ici."""
    reponse = httpx.get(
        f"{GRAPH}{chemin}",
        params=params,
        headers={
            "Authorization": f"Bearer {_jeton()}",
            "Prefer": f'outlook.timezone="{FUSEAU}"',
        },
        timeout=30,
    )
    if reponse.status_code == 401:
        raise OutlookNonConnecte("Microsoft refuse l'accès : relance `sebtix outlook connecter`.")
    reponse.raise_for_status()
    return reponse.json()


@dataclass
class Mail:
    id: str
    expediteur: str
    adresse: str
    objet: str
    recu_le: datetime
    lu: bool
    apercu: str


@dataclass
class Evenement:
    titre: str
    debut: datetime
    fin: datetime
    lieu: str
    journee_entiere: bool


def _date(valeur: str) -> datetime:
    """Graph renvoie '2026-11-25T08:30:00Z' (mails) ou '2026-11-25T09:00:00.0000000' (agenda)."""
    valeur = valeur.rstrip("Z").split(".")[0]
    return datetime.fromisoformat(valeur)


def derniers_mails(nombre: int = 5) -> list[Mail]:
    donnees = _get(
        "/me/mailFolders/inbox/messages",
        {
            "$top": nombre,
            "$orderby": "receivedDateTime desc",
            "$select": "id,from,subject,receivedDateTime,isRead,bodyPreview",
        },
    )
    mails = []
    for m in donnees.get("value", []):
        exp = (m.get("from") or {}).get("emailAddress") or {}
        recu = _date(m["receivedDateTime"]).replace(tzinfo=ZoneInfo("UTC"))
        mails.append(
            Mail(
                id=m["id"],
                expediteur=exp.get("name") or exp.get("address", "?"),
                adresse=exp.get("address", ""),
                objet=m.get("subject") or "(sans objet)",
                recu_le=recu.astimezone(ZoneInfo(FUSEAU)),
                lu=bool(m.get("isRead")),
                apercu=" ".join((m.get("bodyPreview") or "").split())[:200],
            )
        )
    return mails


def agenda(jour: Optional[datetime] = None) -> list[Evenement]:
    """Événements du jour (heure de Paris), triés par heure de début."""
    tz = ZoneInfo(FUSEAU)
    jour = (jour or datetime.now(tz)).astimezone(tz)
    debut = datetime.combine(jour.date(), time.min, tz)
    fin = debut + timedelta(days=1)
    donnees = _get(
        "/me/calendarView",
        {
            "startDateTime": debut.isoformat(),
            "endDateTime": fin.isoformat(),
            "$orderby": "start/dateTime",
            "$select": "subject,start,end,location,isAllDay",
            "$top": 50,
        },
    )
    evenements = []
    for e in donnees.get("value", []):
        evenements.append(
            Evenement(
                titre=e.get("subject") or "(sans titre)",
                debut=_date(e["start"]["dateTime"]),
                fin=_date(e["end"]["dateTime"]),
                lieu=((e.get("location") or {}).get("displayName") or "").strip(),
                journee_entiere=bool(e.get("isAllDay")),
            )
        )
    return evenements
