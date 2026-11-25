// Appels à Workers AI (modèles gratuits de Cloudflare) + suivi de consommation.

// Neurones par million de tokens (tarifs Cloudflare, nov. 2026) — pour `sebtix budget`.
const TARIFS = {
  "@cf/google/gemma-4-26b-a4b-it": { entree: 9091, sortie: 27273 },
  "@cf/mistralai/mistral-small-3.1-24b-instruct": { entree: 31876, sortie: 50488 },
};
const NEURONES_PAR_MINUTE = {
  "@cf/openai/whisper-large-v3-turbo": 46.63,
};

export async function compterNeurones(db, neurones) {
  if (!neurones) return;
  const jour = new Date().toISOString().slice(0, 10);
  await db
    .prepare(
      "INSERT INTO conso (jour, neurones) VALUES (?, ?) " +
        "ON CONFLICT(jour) DO UPDATE SET neurones = neurones + excluded.neurones",
    )
    .bind(jour, neurones)
    .run();
}

function estimerTokens(texte) {
  return Math.ceil((texte || "").length / 3.5);
}

/** Conversation avec le modèle. `messages` = [{role, content}]. Renvoie le texte. */
export async function discuter(env, messages, { maxTokens = 400 } = {}) {
  const modele = env.MODELE_CHAT;
  const options = { messages, max_tokens: maxTokens, temperature: 0.6 };
  // Les modèles « qui réfléchissent » (Gemma 4) épuisent sinon leur marge avant de répondre.
  if (modele.includes("gemma-4")) options.chat_template_kwargs = { enable_thinking: false };
  const r = await env.AI.run(modele, options);
  const texte = (r?.response ?? r?.choices?.[0]?.message?.content ?? "").trim();

  // Cloudflare renvoie le coût exact ; sinon, estimation d'après les tarifs.
  let neurones = r?.usage?.neurons;
  if (neurones == null) {
    const tarif = TARIFS[modele] || { entree: 30000, sortie: 60000 };
    const entree = r?.usage?.prompt_tokens ?? estimerTokens(messages.map((m) => m.content).join(" "));
    const sortie = r?.usage?.completion_tokens ?? estimerTokens(texte);
    neurones = (entree * tarif.entree + sortie * tarif.sortie) / 1e6;
  }
  await compterNeurones(env.DB, neurones);
  return texte;
}

function enBase64(octets) {
  let binaire = "";
  const morceau = 0x8000;
  for (let i = 0; i < octets.length; i += morceau) {
    binaire += String.fromCharCode.apply(null, octets.subarray(i, i + morceau));
  }
  return btoa(binaire);
}

/** Transcrit un message vocal (français). `duree` en secondes, pour le budget. */
export async function transcrire(env, octets, duree = 30) {
  const r = await env.AI.run(env.MODELE_TRANSCRIPTION, { audio: enBase64(octets), language: "fr" });
  await compterNeurones(env.DB, (duree / 60) * NEURONES_PAR_MINUTE[env.MODELE_TRANSCRIPTION]);
  return (r?.text || "").trim();
}

function echapperXml(texte) {
  return texte.replace(/[<>&'"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[c]);
}

/**
 * Synthèse vocale en français via Azure Speech (offre gratuite F0 : 500 000 caractères/mois).
 * Renvoie des octets OGG/Opus, le format des bulles vocales Telegram.
 */
export async function parler(env, texte) {
  if (!env.AZURE_SPEECH_KEY || !env.AZURE_SPEECH_REGION) throw new Error("Azure Speech non configuré");
  const extrait = texte.slice(0, 1500);

  // Garde-fou : on s'arrête avant la limite gratuite (500 000 caractères/mois).
  const mois = new Date().toISOString().slice(0, 7);
  const cle = `azure_caracteres:${mois}`;
  const deja = Number((await env.DB.prepare("SELECT valeur FROM etat WHERE cle = ?").bind(cle).first())?.valeur || 0);
  if (deja + extrait.length > 480000) throw new Error("Quota gratuit Azure Speech presque atteint ce mois-ci");

  const ssml =
    `<speak version="1.0" xml:lang="fr-FR"><voice name="${env.VOIX_AZURE}">` +
    `${echapperXml(extrait)}</voice></speak>`;
  const r = await fetch(`https://${env.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1`, {
    method: "POST",
    headers: {
      "Ocp-Apim-Subscription-Key": env.AZURE_SPEECH_KEY,
      "Content-Type": "application/ssml+xml",
      "X-Microsoft-OutputFormat": "ogg-48khz-16bit-mono-opus",
      "User-Agent": "sebtix",
    },
    body: ssml,
  });
  if (!r.ok) throw new Error(`Azure Speech : ${r.status} ${await r.text()}`);

  await env.DB.prepare(
    "INSERT INTO etat (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = " +
      "CAST(CAST(valeur AS INTEGER) + CAST(excluded.valeur AS INTEGER) AS TEXT)",
  )
    .bind(cle, String(extrait.length))
    .run();
  return new Uint8Array(await r.arrayBuffer());
}
