// Sentinelle de Sebtix — tourne 24h/24 sur Cloudflare Workers (offre gratuite).
//
// Routes :
//   POST /telegram  → messages du bot (vérifiés : secret Telegram + ton compte uniquement)
//   GET  /sante     → « ok » (vérification simple, ne révèle rien)
// Tâches planifiées (cron) : purge des conversations de plus de 30 jours.

import SOUL from "../../src/sebtix/persona/SOUL.md";
import * as memoire from "./memoire.js";
import * as tg from "./telegram.js";
import { discuter, parler, transcrire } from "./ia.js";
import { ajouterTache, ecrireEtat, lireEtat, routerApi } from "./api.js";

const HISTORIQUE = 20; // messages de contexte
const RE_AUDIO =
  /\b(en\s+(vocal|audio)|à\s+l['’]oral|r[ée]ponds?[- ]moi\s+(en\s+)?(vocal|audio)|lis[- ]le[- ]moi|dis[- ]le[- ]moi\s+[àa]\s+voix\s+haute)\b/i;

const AIDE = `Salut, c'est Sebtix 👋
Écris-moi ou envoie un vocal. Je réponds par écrit ; ajoute « en vocal » pour une réponse audio.

Mémoire : « retiens que… », « oublie… », « qu'est-ce que tu sais sur moi ? »
/stop — coupe toute la surveillance
/reprendre — la relance
/etat — état de la surveillance
/mac <demande> — tâche lourde, traitée par le Mac dès qu’il se rallume`;

export default {
  async fetch(requete, env, ctx) {
    const url = new URL(requete.url);

    if (url.pathname === "/sante") return new Response("ok");

    // API privée du Mac : clé de synchronisation obligatoire.
    if (url.pathname.startsWith("/api/")) {
      const cle = (requete.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
      if (!env.SEBTIX_SYNC_KEY || !tg.egaliteSure(cle, env.SEBTIX_SYNC_KEY)) {
        return new Response("interdit", { status: 403 });
      }
      if (url.pathname === "/api/diagnostic") {
        const webhook = await tg.infoWebhook(env);
        return Response.json({
          webhook_ok: webhook.url?.endsWith("/telegram") ?? false,
          messages_en_attente: webhook.pending_update_count,
          derniere_erreur: webhook.last_error_message || null,
          derniere_erreur_le: webhook.last_error_date
            ? new Date(webhook.last_error_date * 1000).toISOString()
            : null,
          proprietaire_configure: Boolean(env.TELEGRAM_CHAT_ID),
        });
      }
      if (url.pathname === "/api/essai" && requete.method === "POST") {
        // Diagnostic : réponse BRUTE du modèle et test de la voix, sans rien enregistrer.
        const { texte = "Salut", modele = env.MODELE_CHAT, options = {} } = await requete.json();
        const debut = Date.now();
        const brut = await env.AI.run(modele, {
          messages: [
            { role: "system", content: "Tu es Sebtix. Réponds en français, en deux phrases." },
            { role: "user", content: texte },
          ],
          max_tokens: 400,
          ...options,
        });
        brut.duree_ms = Date.now() - debut;
        let voix;
        try {
          const octets = await parler(env, "Salut, c'est Sebtix.");
          voix = { ok: true, taille_ogg: octets.length };
        } catch (e) {
          voix = { ok: false, erreur: String(e) };
        }
        return Response.json({ modele: env.MODELE_CHAT, brut, voix });
      }
      return routerApi(requete, env, url);
    }

    if (url.pathname === "/telegram" && requete.method === "POST") {
      // 1. Le message vient-il vraiment de Telegram ? (secret choisi à l'installation)
      const secret = requete.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
      if (!env.TELEGRAM_WEBHOOK_SECRET || !tg.egaliteSure(secret, env.TELEGRAM_WEBHOOK_SECRET)) {
        return new Response("interdit", { status: 403 });
      }
      const maj = await requete.json();
      // 2. Réponse immédiate à Telegram, traitement en arrière-plan.
      ctx.waitUntil(traiterMiseAJour(env, maj).catch((e) => signalerErreur(env, e)));
      return new Response("ok");
    }

    return new Response("introuvable", { status: 404 });
  },

  async scheduled(evenement, env, ctx) {
    // Purge quotidienne : on ne garde que 30 jours de conversation.
    ctx.waitUntil(
      env.DB.prepare("DELETE FROM messages WHERE cree_le < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-30 days')").run(),
    );
  },
};

async function signalerErreur(env, erreur) {
  console.error(erreur);
  try {
    await tg.envoyerMessage(env, "⚠️ Petit souci de mon côté, réessaie dans un instant.");
  } catch {}
}

async function dejaVu(env, cle) {
  const r = await env.DB.prepare("INSERT OR IGNORE INTO deja_vu (cle) VALUES (?)").bind(cle).run();
  return r.meta.changes === 0;
}

async function traiterMiseAJour(env, maj) {
  const message = maj.message;
  // 3. Seul TON compte, en privé, est écouté. Tout le reste est ignoré en silence.
  if (!tg.estProprietaire(env, message)) return;
  // 4. Telegram peut renvoyer un même message : on ne le traite qu'une fois.
  if (await dejaVu(env, `update:${maj.update_id}`)) return;

  let texte = (message.text || "").trim();
  let prefixe = "";

  if (message.voice || message.audio) {
    const audio = message.voice || message.audio;
    await tg.signalerFrappe(env, "typing");
    const octets = await tg.telecharger(env, audio.file_id);
    texte = await transcrire(env, octets, audio.duration || 30);
    if (!texte) {
      await tg.envoyerMessage(env, "Je n'ai rien compris à ce vocal. Tu peux répéter ?");
      return;
    }
    prefixe = `🎙️ « ${texte} »\n\n`;
  }

  if (!texte) {
    await tg.envoyerMessage(env, "Je sais lire du texte et écouter des vocaux. Le reste, pas encore.");
    return;
  }

  // Commandes simples
  const commande = texte.split(/\s+/)[0].toLowerCase().replace(/@.*$/, "");
  if (commande === "/start" || commande === "/aide") return tg.envoyerMessage(env, AIDE);
  if (commande === "/stop") {
    await ecrireEtat(env, "surveillance", "off");
    return tg.envoyerMessage(env, "🛑 Surveillance coupée. Plus aucune notification ni brief. /reprendre pour relancer.");
  }
  if (commande === "/reprendre") {
    await ecrireEtat(env, "surveillance", "on");
    return tg.envoyerMessage(env, "✅ Surveillance relancée.");
  }
  if (commande === "/mac") {
    const demande = texte.slice(texte.indexOf(" ") + 1).trim();
    if (!demande || demande.startsWith("/")) return tg.envoyerMessage(env, "Utilisation : /mac <ce que le Mac doit faire>");
    const id = await ajouterTache(env, "demande", demande);
    return tg.envoyerMessage(env, `📥 Noté (tâche n°${id}). Le Mac s’en occupe dès qu’il se rallume, je te préviens quand c’est prêt.`);
  }
  if (commande === "/etat") {
    const actif = (await lireEtat(env, "surveillance")) !== "off";
    return tg.envoyerMessage(env, actif ? "✅ Surveillance active." : "🛑 Surveillance coupée (/reprendre).");
  }

  await tg.signalerFrappe(env, "typing");
  const enAudio = RE_AUDIO.test(texte);
  const reponse = await repondre(env, texte, enAudio);

  await tg.envoyerMessage(env, prefixe + reponse);
  if (enAudio) {
    try {
      await tg.signalerFrappe(env, "upload_voice");
      await tg.envoyerVocal(env, await parler(env, reponse));
    } catch (e) {
      console.error("Voix indisponible", e);
      await tg.envoyerMessage(env, "🔇 Voix indisponible pour le moment : réponse écrite seulement.");
    }
  }
}

function maintenant(env) {
  return new Date().toLocaleString("fr-FR", {
    timeZone: env.FUSEAU,
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Construit le contexte (personnalité, profil, mémoire, historique) et interroge le modèle. */
export async function repondre(env, texte, enAudio = false) {
  const note = await memoire.traiter(env.DB, texte);

  const profil = (await memoire.lireProfil(env.DB)).trim();
  const souvenirs = (await memoire.lireMemoire(env.DB)).map((l) => "- " + l.texte).join("\n");
  const { results: historique } = await env.DB.prepare(
    "SELECT role, contenu FROM messages ORDER BY id DESC LIMIT ?",
  )
    .bind(HISTORIQUE)
    .all();

  const systeme = [
    SOUL,
    "## Contexte",
    `Nous sommes le ${maintenant(env)} (heure de Paris).`,
    "Tu réponds en ce moment depuis la Sentinelle (le cloud), via Telegram : le Mac est peut-être fermé. " +
      "Tu n'as pas encore accès à ses mails ni à son agenda d'ici. Ne prétends jamais avoir fait une action " +
      "que tu ne peux pas faire.",
    enAudio ? "Ta réponse sera lue à voix haute : deux phrases maximum, sans liste ni mise en forme." : "",
    "## Profil (USER)",
    profil || "(pas encore synchronisé depuis le Mac)",
    "## Mémoire (MEMORY)",
    souvenirs || "(vide)",
  ]
    .filter(Boolean)
    .join("\n\n");

  const messages = [
    { role: "system", content: systeme },
    ...historique.reverse().map((m) => ({ role: m.role, content: m.contenu })),
    {
      role: "user",
      content: note
        ? `${texte}\n\n[Note interne de Sebtix, invisible pour l'utilisateur — ${note}]`
        : texte,
    },
  ];

  const reponse = (await discuter(env, messages)) || "Je n'ai pas de réponse, reformule ?";

  await env.DB.batch([
    env.DB.prepare("INSERT INTO messages (canal, role, contenu) VALUES ('telegram', 'user', ?)").bind(texte),
    env.DB.prepare("INSERT INTO messages (canal, role, contenu) VALUES ('telegram', 'assistant', ?)").bind(reponse),
  ]);
  return reponse;
}
