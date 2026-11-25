// Outlook côté Sentinelle — Microsoft Graph en LECTURE SEULE (Mail.Read, Calendars.Read).
//
// Le jeton de renouvellement (refresh token) est chiffré en AES-GCM avant d'être stocké dans D1.
// La clé de chiffrement est un secret Cloudflare séparé (CHIFFREMENT_CLE) : une copie de la base
// seule ne suffit pas à lire tes mails.
// Comme sur le Mac, ce module ne fait que des requêtes GET vers Graph.

const AUTORITE = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token";
const DROITS = "Mail.Read Calendars.Read offline_access";
const GRAPH = "https://graph.microsoft.com/v1.0";

// ------------------------------------------------------------------ chiffrement

async function cle(env) {
  if (!env.CHIFFREMENT_CLE) throw new Error("CHIFFREMENT_CLE manquante");
  const brut = Uint8Array.from(atob(env.CHIFFREMENT_CLE), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey("raw", brut, "AES-GCM", false, ["encrypt", "decrypt"]);
}

export async function chiffrer(env, texte) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const chiffre = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await cle(env), new TextEncoder().encode(texte)),
  );
  const tout = new Uint8Array(iv.length + chiffre.length);
  tout.set(iv);
  tout.set(chiffre, iv.length);
  return btoa(String.fromCharCode(...tout));
}

export async function dechiffrer(env, b64) {
  const tout = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const clair = await crypto.subtle.decrypt({ name: "AES-GCM", iv: tout.slice(0, 12) }, await cle(env), tout.slice(12));
  return new TextDecoder().decode(clair);
}

// ------------------------------------------------------------------ jetons

async function lire(env, nom) {
  const r = await env.DB.prepare("SELECT valeur FROM etat WHERE cle = ?").bind(nom).first();
  return r ? r.valeur : null;
}

async function ecrire(env, nom, valeur) {
  await env.DB.prepare(
    "INSERT INTO etat (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, " +
      "modifie_le = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
  )
    .bind(nom, valeur)
    .run();
}

export async function enregistrerJeton(env, refreshToken) {
  await ecrire(env, "outlook_renouvellement", await chiffrer(env, refreshToken));
  await env.DB.prepare("DELETE FROM etat WHERE cle = 'outlook_acces'").run();
}

export async function connecte(env) {
  return Boolean(await lire(env, "outlook_renouvellement"));
}

/** Jeton d'accès valide (renouvelé si besoin ; le refresh token tourne à chaque renouvellement). */
async function jetonAcces(env) {
  const cache = await lire(env, "outlook_acces");
  if (cache) {
    const { jeton, expire } = JSON.parse(await dechiffrer(env, cache));
    if (Date.now() < expire - 120000) return jeton;
  }
  const renouvellement = await lire(env, "outlook_renouvellement");
  if (!renouvellement) throw new Error("Outlook non connecté côté Sentinelle");

  const r = await fetch(AUTORITE, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.MS_CLIENT_ID,
      grant_type: "refresh_token",
      refresh_token: await dechiffrer(env, renouvellement),
      scope: DROITS,
    }),
  });
  const json = await r.json();
  if (!json.access_token) throw new Error(`Microsoft refuse le renouvellement : ${json.error} ${json.error_description || ""}`);
  if (json.refresh_token) await ecrire(env, "outlook_renouvellement", await chiffrer(env, json.refresh_token));
  await ecrire(
    env,
    "outlook_acces",
    await chiffrer(env, JSON.stringify({ jeton: json.access_token, expire: Date.now() + json.expires_in * 1000 })),
  );
  return json.access_token;
}

/** Unique accès à Graph : GET. */
async function get(env, chemin, params = {}) {
  const url = new URL(GRAPH + chemin);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  const r = await fetch(url, {
    headers: { Authorization: `Bearer ${await jetonAcces(env)}`, Prefer: `outlook.timezone="${env.FUSEAU}"` },
  });
  if (!r.ok) throw new Error(`Graph ${chemin} : ${r.status}`);
  return r.json();
}

// ------------------------------------------------------------------ lecture

export async function derniersMails(env, nombre = 5, depuis = null) {
  const params = {
    $top: nombre,
    $orderby: "receivedDateTime desc",
    $select: "id,from,subject,receivedDateTime,isRead,bodyPreview",
  };
  if (depuis) params.$filter = `receivedDateTime ge ${depuis}`;
  const json = await get(env, "/me/mailFolders/inbox/messages", params);
  return (json.value || []).map((m) => ({
    id: m.id,
    expediteur: m.from?.emailAddress?.name || m.from?.emailAddress?.address || "?",
    adresse: m.from?.emailAddress?.address || "",
    objet: m.subject || "(sans objet)",
    recu_le: m.receivedDateTime,
    lu: Boolean(m.isRead),
    apercu: (m.bodyPreview || "").split(/\s+/).join(" ").slice(0, 300),
  }));
}

export async function agenda(env, jour = new Date()) {
  // Bornes de la journée à Paris, exprimées en UTC.
  const date = jour.toLocaleDateString("en-CA", { timeZone: env.FUSEAU }); // AAAA-MM-JJ
  const decalage = (d) => {
    const local = new Date(d.toLocaleString("en-US", { timeZone: env.FUSEAU }));
    return local.getTime() - new Date(d.toLocaleString("en-US", { timeZone: "UTC" })).getTime();
  };
  const minuitUtc = new Date(`${date}T00:00:00Z`);
  const debut = new Date(minuitUtc.getTime() - decalage(minuitUtc));
  const fin = new Date(debut.getTime() + 24 * 3600 * 1000);
  const json = await get(env, "/me/calendarView", {
    startDateTime: debut.toISOString(),
    endDateTime: fin.toISOString(),
    $orderby: "start/dateTime",
    $select: "subject,start,end,location,isAllDay",
    $top: 50,
  });
  return (json.value || []).map((e) => ({
    titre: e.subject || "(sans titre)",
    debut: e.start.dateTime,
    fin: e.end.dateTime,
    lieu: e.location?.displayName || "",
    journee_entiere: Boolean(e.isAllDay),
  }));
}
