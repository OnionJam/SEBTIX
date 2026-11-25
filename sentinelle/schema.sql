-- Base D1 de la Sentinelle : état partagé entre le téléphone (Telegram) et le Mac.
-- On ne stocke que le strict nécessaire.

-- Conversations (Telegram et Mac), gardées 30 jours.
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canal TEXT NOT NULL,            -- 'telegram' | 'mac'
  role TEXT NOT NULL,             -- 'user' | 'assistant'
  contenu TEXT NOT NULL,
  cree_le TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(cree_le);

-- Ce que Sebtix a retenu (« retiens… » / « oublie… »).
CREATE TABLE IF NOT EXISTS memoire (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  texte TEXT NOT NULL,
  cree_le TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Réglages et état : surveillance active, profil synchronisé depuis le Mac, etc.
CREATE TABLE IF NOT EXISTS etat (
  cle TEXT PRIMARY KEY,
  valeur TEXT NOT NULL,
  modifie_le TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Anti-doublons : chaque notification / mail signalé / offre vue n'est traité qu'une fois.
CREATE TABLE IF NOT EXISTS deja_vu (
  cle TEXT PRIMARY KEY,           -- ex. 'mail:<id>', 'offre:<id>', 'update:<id>'
  vu_le TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- File des tâches lourdes, traitées par le Mac quand il se rallume.
CREATE TABLE IF NOT EXISTS taches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  demande TEXT NOT NULL,
  statut TEXT NOT NULL DEFAULT 'en_attente',   -- en_attente | en_cours | faite | erreur
  resultat TEXT,
  cree_le TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  modifie_le TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Consommation Workers AI estimée (pour `sebtix budget`).
CREATE TABLE IF NOT EXISTS conso (
  jour TEXT PRIMARY KEY,          -- AAAA-MM-JJ (UTC)
  neurones REAL NOT NULL DEFAULT 0
);
