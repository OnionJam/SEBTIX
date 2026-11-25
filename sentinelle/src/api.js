// API privée de la Sentinelle, utilisée uniquement par le Mac (clé SEBTIX_SYNC_KEY obligatoire).
//
//   GET  /api/etat                 état de la surveillance
//   POST /api/etat                 {surveillance: "on"|"off"}
//   GET  /api/budget               consommation du mois (Workers AI, Azure Speech)
//   PUT  /api/profil               {texte}  profil.md du Mac
//   GET  /api/memoire              souvenirs
//   POST /api/memoire/commande     {texte}  « retiens / oublie / que sais-tu » → {note}
//   GET  /api/messages?limite=N    derniers messages (tous canaux)
//   POST /api/messages             {messages: [{canal, role, contenu}]}
//   GET  /api/taches               tâches en attente (pour le Mac)
//   POST /api/taches               {type, demande}  ajoute une tâche
//   POST /api/taches/<id>          {statut, resultat}  ; si « faite » → notification Telegram
//   POST /api/notifier             {texte}  envoie un message Telegram

import * as memoire from "./memoire.js";
import * as tg from "./telegram.js";
import * as outlook from "./outlook.js";

const LIMITE_GRATUITE_NEURONES = 10000;

export async function lireEtat(env, cle) {
  const r = await env.DB.prepare("SELECT valeur FROM etat WHERE cle = ?").bind(cle).first();
  return r ? r.valeur : null;
}

export async function ecrireEtat(env, cle, valeur) {
  await env.DB.prepare(
    "INSERT INTO etat (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, " +
      "modifie_le = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
  )
    .bind(cle, valeur)
    .run();
}

export async function surveillanceActive(env) {
  return (await lireEtat(env, "surveillance")) !== "off";
}

export async function ajouterTache(env, type, demande) {
  const r = await env.DB.prepare("INSERT INTO taches (type, demande) VALUES (?, ?) RETURNING id")
    .bind(type, demande)
    .first();
  return r.id;
}

async function budget(env) {
  const mois = new Date().toISOString().slice(0, 7);
  const { results } = await env.DB.prepare("SELECT jour, neurones FROM conso WHERE jour LIKE ? ORDER BY jour")
    .bind(`${mois}%`)
    .all();
  const aujourdhui = new Date().toISOString().slice(0, 10);
  const total = results.reduce((s, r) => s + r.neurones, 0);
  const jourMax = results.reduce((m, r) => (r.neurones > m.neurones ? r : m), { jour: null, neurones: 0 });
  return {
    mois,
    depense_euros: 0, // offres gratuites : Cloudflare bloque au lieu de facturer, Azure F0 idem
    workers_ai: {
      neurones_mois: Math.round(total * 10) / 10,
      neurones_aujourdhui: Math.round((results.find((r) => r.jour === aujourdhui)?.neurones || 0) * 10) / 10,
      jour_le_plus_charge: jourMax.jour ? { jour: jourMax.jour, neurones: Math.round(jourMax.neurones) } : null,
      limite_gratuite_par_jour: LIMITE_GRATUITE_NEURONES,
    },
    azure_speech: {
      caracteres_mois: Number((await lireEtat(env, `azure_caracteres:${mois}`)) || 0),
      limite_gratuite_par_mois: 500000,
    },
  };
}

export async function routerApi(requete, env, url) {
  const chemin = url.pathname;
  const methode = requete.method;
  const corps = methode === "GET" ? {} : await requete.json().catch(() => ({}));

  if (chemin === "/api/etat" && methode === "GET") {
    return Response.json({ surveillance: (await surveillanceActive(env)) ? "on" : "off" });
  }
  if (chemin === "/api/etat" && methode === "POST") {
    if (!["on", "off"].includes(corps.surveillance)) return new Response("valeur invalide", { status: 400 });
    await ecrireEtat(env, "surveillance", corps.surveillance);
    return Response.json({ surveillance: corps.surveillance });
  }
  if (chemin === "/api/budget") return Response.json(await budget(env));

  if (chemin === "/api/profil" && methode === "PUT") {
    await ecrireEtat(env, "profil", String(corps.texte || "").slice(0, 8000));
    return Response.json({ ok: true });
  }

  if (chemin === "/api/memoire" && methode === "GET") {
    return Response.json({ memoire: await memoire.lireMemoire(env.DB) });
  }
  if (chemin === "/api/memoire/commande" && methode === "POST") {
    return Response.json({ note: await memoire.traiter(env.DB, String(corps.texte || "")) });
  }

  if (chemin === "/api/messages" && methode === "GET") {
    const limite = Math.min(Number(url.searchParams.get("limite") || 20), 100);
    const { results } = await env.DB.prepare(
      "SELECT canal, role, contenu, cree_le FROM messages ORDER BY id DESC LIMIT ?",
    )
      .bind(limite)
      .all();
    return Response.json({ messages: results.reverse() });
  }
  if (chemin === "/api/messages" && methode === "POST") {
    const valides = (corps.messages || []).filter(
      (m) => ["user", "assistant"].includes(m.role) && typeof m.contenu === "string" && m.contenu.trim(),
    );
    if (valides.length) {
      await env.DB.batch(
        valides.map((m) =>
          env.DB.prepare("INSERT INTO messages (canal, role, contenu) VALUES (?, ?, ?)").bind(
            m.canal === "telegram" ? "telegram" : "mac",
            m.role,
            m.contenu.slice(0, 8000),
          ),
        ),
      );
    }
    return Response.json({ ajoutes: valides.length });
  }

  if (chemin === "/api/taches" && methode === "GET") {
    const { results } = await env.DB.prepare(
      "SELECT id, type, demande, cree_le FROM taches WHERE statut = 'en_attente' ORDER BY id",
    ).all();
    return Response.json({ taches: results });
  }
  if (chemin === "/api/taches" && methode === "POST") {
    if (!corps.type || !corps.demande) return new Response("type et demande requis", { status: 400 });
    return Response.json({ id: await ajouterTache(env, String(corps.type), String(corps.demande)) });
  }
  const tache = chemin.match(/^\/api\/taches\/(\d+)$/);
  if (tache && methode === "POST") {
    const statut = corps.statut;
    if (!["en_cours", "faite", "erreur"].includes(statut)) return new Response("statut invalide", { status: 400 });
    await env.DB.prepare(
      "UPDATE taches SET statut = ?, resultat = ?, modifie_le = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
    )
      .bind(statut, corps.resultat ?? null, Number(tache[1]))
      .run();
    if (statut === "faite" && corps.resultat) {
      await tg.envoyerMessage(env, `✅ Tâche prête (le Mac s'est rallumé) :\n\n${corps.resultat}`);
    } else if (statut === "erreur") {
      await tg.envoyerMessage(env, `⚠️ Le Mac n'a pas pu terminer une tâche : ${corps.resultat || "erreur inconnue"}`);
    }
    return Response.json({ ok: true });
  }

  if (chemin === "/api/outlook/jeton" && methode === "POST") {
    if (!corps.refresh_token) return new Response("refresh_token requis", { status: 400 });
    await outlook.enregistrerJeton(env, String(corps.refresh_token));
    return Response.json({ ok: true });
  }
  if (chemin === "/api/outlook/test" && methode === "GET") {
    if (!(await outlook.connecte(env))) return Response.json({ connecte: false });
    return Response.json({ connecte: true, mails: await outlook.derniersMails(env, 5), agenda: await outlook.agenda(env) });
  }

  if (chemin === "/api/notifier" && methode === "POST") {
    if (!corps.texte) return new Response("texte requis", { status: 400 });
    await tg.envoyerMessage(env, String(corps.texte));
    return Response.json({ ok: true });
  }

  return new Response("introuvable", { status: 404 });
}
