"""Tests de la continuité des conversations et de la synchro (Sentinelle simulée)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from sebtix import conversation, memoire, sentinelle, synchro


def _iso(delta):
    return (datetime.now(timezone.utc) - delta).isoformat().replace("+00:00", "Z")


@pytest.fixture
def fausse_sentinelle(monkeypatch):
    etat = {
        "messages": [
            {"canal": "telegram", "role": "assistant", "contenu": "vieux", "cree_le": _iso(timedelta(days=2))},
            {"canal": "telegram", "role": "user", "contenu": "J'ai un entretien demain", "cree_le": _iso(timedelta(hours=1))},
            {"canal": "telegram", "role": "assistant", "contenu": "Prépare ton pitch", "cree_le": _iso(timedelta(hours=1))},
        ],
        "memoire": [{"id": 1, "texte": "[2026-11-26] Je nage le mardi"}],
        "taches": [{"id": 7, "type": "demande", "demande": "Résume X"}],
        "maj": [],
        "profil": None,
    }
    monkeypatch.setattr(sentinelle, "configuree", lambda: True)
    monkeypatch.setattr(sentinelle, "messages_recents", lambda n: etat["messages"])
    monkeypatch.setattr(sentinelle, "memoire", lambda: etat["memoire"])
    monkeypatch.setattr(sentinelle, "taches_en_attente", lambda: etat["taches"])
    monkeypatch.setattr(sentinelle, "maj_tache", lambda i, s, r=None: etat["maj"].append((i, s, r)))
    monkeypatch.setattr(sentinelle, "pousser_profil", lambda t: etat.update(profil=t))
    monkeypatch.setattr(sentinelle, "commande_memoire", lambda t: None)
    return etat


def test_nouvelle_conversation_reprend_le_contexte_recent(fausse_sentinelle):
    messages = [SimpleNamespace(role="user", content="On en était où ?")]
    n = conversation.reprendre_contexte(messages, lambda r, c: SimpleNamespace(role=r, content=c))
    assert n == 2  # le message de plus de 12 h est ignoré
    assert [m.content for m in messages] == ["J'ai un entretien demain", "Prépare ton pitch", "On en était où ?"]


def test_conversation_en_cours_inchangee(fausse_sentinelle):
    messages = [
        SimpleNamespace(role="user", content="a"),
        SimpleNamespace(role="assistant", content="b"),
        SimpleNamespace(role="user", content="c"),
    ]
    assert conversation.reprendre_contexte(messages, lambda r, c: None) == 0
    assert len(messages) == 3


def test_partage_sans_note_interne(monkeypatch):
    envoyes = []
    monkeypatch.setattr(sentinelle, "envoyer_echange_en_arriere_plan", lambda q, r: envoyes.append((q, r)))
    conversation.partager_echange("Retiens X\n\n[Note interne de Sebtix — ...]", "Ok")
    assert envoyes == [("Retiens X", "Ok")]


def test_synchroniser(tmp_path, monkeypatch, fausse_sentinelle):
    mem, prof = tmp_path / "memoire.md", tmp_path / "profil.md"
    prof.write_text("# Profil\n- Paris\n", encoding="utf-8")
    monkeypatch.setattr(memoire, "_chemins", lambda: (mem, prof))
    monkeypatch.setattr(memoire, "_fichier_en_attente", lambda: tmp_path / "attente.txt")
    monkeypatch.setattr(synchro, "executer_tache", lambda d: f"Fait : {d}")

    bilan = synchro.synchroniser()

    assert fausse_sentinelle["profil"].startswith("# Profil")
    assert "Je nage le mardi" in mem.read_text(encoding="utf-8")
    assert bilan.taches_faites == [7]
    assert fausse_sentinelle["maj"] == [(7, "en_cours", None), (7, "faite", "Fait : Résume X")]


def test_tache_en_erreur_signalee(tmp_path, monkeypatch, fausse_sentinelle):
    monkeypatch.setattr(memoire, "_chemins", lambda: (tmp_path / "m.md", tmp_path / "p.md"))
    monkeypatch.setattr(memoire, "_fichier_en_attente", lambda: tmp_path / "attente.txt")

    def panne(_):
        raise RuntimeError("Ollama éteint")

    monkeypatch.setattr(synchro, "executer_tache", panne)
    bilan = synchro.synchroniser()
    assert bilan.erreurs and fausse_sentinelle["maj"][-1][1] == "erreur"


def test_garde_fou_tests_jamais_la_vraie_sentinelle():
    assert sentinelle.configuree() is False
