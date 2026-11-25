"""Tests du connecteur Outlook (réponses Microsoft simulées, aucun appel réseau)."""

import ast
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sebtix import outlook as o


def test_droits_en_lecture_seule():
    assert o.DROITS == ["Mail.Read", "Calendars.Read"]
    assert not any("Write" in d or "Send" in d for d in o.DROITS)


def test_aucune_ecriture_possible_dans_le_code():
    """Le module ne doit appeler que httpx.get : jamais post/put/patch/delete/request."""
    arbre = ast.parse(Path(o.__file__).read_text(encoding="utf-8"))
    appels = {
        n.func.attr
        for n in ast.walk(arbre)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "httpx"
    }
    assert appels == {"get"}


def test_derniers_mails(monkeypatch):
    def faux_get(chemin, params=None):
        assert chemin == "/me/mailFolders/inbox/messages"
        assert params["$top"] == 2
        return {
            "value": [
                {
                    "id": "1",
                    "from": {"emailAddress": {"name": "Claire", "address": "c@x.com"}},
                    "subject": "Entretien demain ?",
                    "receivedDateTime": "2026-11-25T08:30:00Z",
                    "isRead": False,
                    "bodyPreview": "Bonjour,\r\n  dispo demain ?",
                },
                {"id": "2", "from": None, "subject": None,
                 "receivedDateTime": "2026-11-24T20:00:00Z", "isRead": True},
            ]
        }

    monkeypatch.setattr(o, "_get", faux_get)
    mails = o.derniers_mails(2)
    assert mails[0].expediteur == "Claire" and not mails[0].lu
    assert mails[0].recu_le.hour == 9  # 08:30 UTC = 09:30 à Paris en hiver
    assert mails[0].apercu == "Bonjour, dispo demain ?"
    assert mails[1].objet == "(sans objet)" and mails[1].expediteur == "?"


def test_agenda_du_jour(monkeypatch):
    vu = {}

    def faux_get(chemin, params=None):
        vu.update(params)
        return {
            "value": [
                {
                    "subject": "Entretien SDR",
                    "start": {"dateTime": "2026-11-25T11:30:00.0000000"},
                    "end": {"dateTime": "2026-11-25T12:00:00.0000000"},
                    "location": {"displayName": "Teams"},
                    "isAllDay": False,
                }
            ]
        }

    monkeypatch.setattr(o, "_get", faux_get)
    jour = datetime(2026, 11, 25, 15, 0, tzinfo=ZoneInfo("Europe/Paris"))
    evts = o.agenda(jour)
    assert vu["startDateTime"].startswith("2026-11-25T00:00:00")
    assert vu["endDateTime"].startswith("2026-11-26T00:00:00")
    assert evts[0].titre == "Entretien SDR" and evts[0].debut.hour == 11 and evts[0].lieu == "Teams"
