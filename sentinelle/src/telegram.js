// Petites fonctions d'accès à l'API Telegram (bot privé de Sebtix).

const API = "https://api.telegram.org";

async function appel(env, methode, corps) {
  const r = await fetch(`${API}/bot${env.TELEGRAM_TOKEN}/${methode}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(corps),
  });
  const json = await r.json();
  if (!json.ok) throw new Error(`Telegram ${methode} : ${json.description}`);
  return json.result;
}

export async function infoWebhook(env) {
  const r = await fetch(`${API}/bot${env.TELEGRAM_TOKEN}/getWebhookInfo`);
  return (await r.json()).result || {};
}

/** Comparaison à durée constante (évite de deviner un secret caractère par caractère). */
export function egaliteSure(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Vrai seulement pour TON compte, en conversation privée. */
export function estProprietaire(env, message) {
  if (!message || !message.chat || !env.TELEGRAM_CHAT_ID) return false;
  return message.chat.type === "private" && String(message.chat.id) === String(env.TELEGRAM_CHAT_ID);
}

export function envoyerMessage(env, texte) {
  // Telegram limite un message à 4096 caractères.
  return appel(env, "sendMessage", {
    chat_id: env.TELEGRAM_CHAT_ID,
    text: texte.slice(0, 4000),
    link_preview_options: { is_disabled: true },
  });
}

export function signalerFrappe(env, action = "typing") {
  return appel(env, "sendChatAction", { chat_id: env.TELEGRAM_CHAT_ID, action }).catch(() => {});
}

/** Télécharge un fichier Telegram (ex. message vocal). */
export async function telecharger(env, fileId) {
  const fichier = await appel(env, "getFile", { file_id: fileId });
  const r = await fetch(`${API}/file/bot${env.TELEGRAM_TOKEN}/${fichier.file_path}`);
  if (!r.ok) throw new Error(`Téléchargement Telegram impossible (${r.status})`);
  return new Uint8Array(await r.arrayBuffer());
}

/** Envoie une bulle vocale (OGG/Opus). */
export async function envoyerVocal(env, octets) {
  const form = new FormData();
  form.append("chat_id", String(env.TELEGRAM_CHAT_ID));
  form.append("voice", new Blob([octets], { type: "audio/ogg" }), "sebtix.ogg");
  const r = await fetch(`${API}/bot${env.TELEGRAM_TOKEN}/sendVoice`, { method: "POST", body: form });
  const json = await r.json();
  if (!json.ok) throw new Error(`Telegram sendVoice : ${json.description}`);
}
