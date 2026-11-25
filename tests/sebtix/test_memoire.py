"""Tests du module de mémoire de Sebtix."""

from types import SimpleNamespace

import pytest

from sebtix import memoire as m


@pytest.fixture
def fichiers(tmp_path):
    mem = tmp_path / "memoire.md"
    prof = tmp_path / "profil.md"
    mem.write_text("# Ce que Sebtix a retenu\n", encoding="utf-8")
    prof.write_text("# Mon profil\n- Ville : Paris\n- Je parle français et anglais.\n", encoding="utf-8")
    return mem, prof


@pytest.mark.parametrize(
    "phrase",
    [
        "Retiens que je bois mon café noir, sans sucre.",
        "Sebtix, retiens que je bois mon café noir, sans sucre",
        "note que je bois mon café noir, sans sucre",
        "Souviens-toi que je bois mon café noir, sans sucre",
    ],
)
def test_retenir(fichiers, phrase):
    mem, prof = fichiers
    r = m.traiter(phrase, mem, prof)
    assert r is not None and r.action == "ajout"
    assert "Je bois mon café noir, sans sucre" in mem.read_text(encoding="utf-8")


def test_retenir_deux_fois_ne_duplique_pas(fichiers):
    mem, prof = fichiers
    m.traiter("Retiens que j'aime le thé vert", mem, prof)
    r = m.traiter("retiens que j'aime le thé vert", mem, prof)
    assert r.action == "deja_connu"
    assert mem.read_text(encoding="utf-8").count("thé vert") == 1


def test_oublier_dans_la_memoire(fichiers):
    mem, prof = fichiers
    m.traiter("Retiens que je bois mon café noir", mem, prof)
    m.traiter("Retiens que mon chat s'appelle Pixel", mem, prof)
    r = m.traiter("Oublie que je bois du café noir", mem, prof)
    assert r.action == "oubli"
    texte = mem.read_text(encoding="utf-8")
    assert "café" not in texte and "Pixel" in texte


def test_oublier_dans_le_profil(fichiers):
    mem, prof = fichiers
    r = m.traiter("Sebtix, oublie ma ville Paris", mem, prof)
    assert r.action == "oubli"
    assert "Paris" not in prof.read_text(encoding="utf-8")
    assert "français" in prof.read_text(encoding="utf-8")


def test_oublier_rien_ne_correspond(fichiers):
    mem, prof = fichiers
    avant = mem.read_text(encoding="utf-8"), prof.read_text(encoding="utf-8")
    r = m.traiter("oublie mon numéro de passeport", mem, prof)
    assert r.action == "introuvable"
    assert (mem.read_text(encoding="utf-8"), prof.read_text(encoding="utf-8")) == avant


def test_oublier_trop_vague_ne_supprime_rien(fichiers):
    mem, prof = fichiers
    for i in range(5):
        m.traiter(f"Retiens que le projet numéro {i} avance bien", mem, prof)
    avant = mem.read_text(encoding="utf-8")
    r = m.traiter("oublie le projet", mem, prof)
    assert r.action == "ambigu"
    assert mem.read_text(encoding="utf-8") == avant


def test_noublie_pas_n_est_pas_une_commande(fichiers):
    mem, prof = fichiers
    assert m.traiter("N'oublie pas de me rappeler demain", mem, prof) is None


def test_consulter(fichiers):
    mem, prof = fichiers
    r = m.traiter("Qu'est-ce que tu sais sur moi ?", mem, prof)
    assert r.action == "consultation" and "Paris" in r.note


def test_message_normal_ignore(fichiers):
    mem, prof = fichiers
    assert m.traiter("Quel temps fait-il à Paris ?", mem, prof) is None


def test_appliquer_aux_messages_ajoute_une_note(monkeypatch, fichiers):
    mem, prof = fichiers
    monkeypatch.setattr(m, "_chemins", lambda: (mem, prof))
    messages = [
        SimpleNamespace(role="user", content="Retiens que j'ai un chat"),
        SimpleNamespace(role="assistant", content="ok"),
        SimpleNamespace(role="user", content="Retiens que je fais du vélo"),
    ]
    r = m.appliquer_aux_messages(messages)
    assert r.action == "ajout"
    assert "Note interne de Sebtix" in messages[-1].content
    # Seul le DERNIER message est traité : l'ancien n'est pas ré-enregistré.
    assert "chat" not in mem.read_text(encoding="utf-8")
