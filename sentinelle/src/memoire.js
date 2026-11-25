// Mémoire de Sebtix côté Sentinelle — même logique que src/sebtix/memoire.py sur le Mac.
// « retiens… », « oublie… », « qu'est-ce que tu sais sur moi ? » sont exécutés ici,
// sans dépendre du modèle ; une note interne dit ensuite au modèle ce qui a été fait.

export const MAX_LIGNES_OUBLIEES = 3;

const PREFIXE = String.raw`^\s*(?:(?:hey|ok|dis)\s+)?(?:sebtix\s*[,!:.]?\s*)?`;
const RE_RETENIR = new RegExp(
  PREFIXE +
    String.raw`(?:retiens|note|m[ée]morise|souviens[- ]toi|rappelle[- ]toi)\s+` +
    String.raw`(?:bien\s+)?(?:(?:le\s+fait\s+)?que\s+|qu['’]\s*|[çc]a\s*:\s*|:\s*)?([\s\S]+)$`,
  "i",
);
const RE_OUBLIER = new RegExp(
  PREFIXE +
    String.raw`(?:oublie|efface\s+de\s+ta\s+m[ée]moire|supprime\s+de\s+ta\s+m[ée]moire)\s+` +
    String.raw`(?:(?:le\s+fait\s+)?que\s+|qu['’]\s*|tout\s+ce\s+qui\s+concerne\s+|[çc]a\s*:\s*|:\s*)?([\s\S]+)$`,
  "i",
);
const RE_SAVOIR =
  /(qu['’]est[- ]ce\s+que\s+tu\s+sais|que\s+sais[- ]tu|tu\s+sais\s+quoi|tu\s+connais\s+quoi)\s+(sur|de)\s+moi/i;

const MOTS_VIDES = new Set(
  ("alors aussi avec dans elle elles est etait etre leur mais mes moi mon nous pour plus que " +
    "quand qui sans ses son sont sur tes ton tous tout une des les the jamais toujours fait faire " +
    "suis avoir").split(" "),
);

export function normaliser(texte) {
  return texte.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

export function motsCles(texte) {
  const mots = normaliser(texte).match(/[a-z0-9]+/g) || [];
  return new Set(mots.filter((m) => m.length >= 3 && !MOTS_VIDES.has(m)));
}

export function nettoyer(texte) {
  const t = texte.split(/\s+/).join(" ").trim().replace(/[.!]+$/, "");
  return t ? t[0].toUpperCase() + t.slice(1) : t;
}

/** Reconnaît une commande de mémoire. Renvoie {type, texte} ou null. */
export function analyser(texte) {
  let m;
  if ((m = RE_OUBLIER.exec(texte))) return { type: "oublier", texte: m[1] };
  if ((m = RE_RETENIR.exec(texte))) return { type: "retenir", texte: m[1] };
  if (RE_SAVOIR.test(texte)) return { type: "savoir" };
  return null;
}

/** Lignes (objets {id, texte}) qui partagent au moins la moitié des mots-clés de la demande. */
export function correspondances(demande, lignes) {
  const cles = motsCles(demande);
  if (cles.size === 0) return null; // trop vague
  const seuil = Math.max(1, Math.floor((cles.size + 1) / 2));
  return lignes.filter((l) => {
    const mots = motsCles(l.texte);
    let communs = 0;
    for (const c of cles) if (mots.has(c)) communs++;
    return communs >= seuil;
  });
}

// ------------------------------------------------------------------ accès D1

export async function lireMemoire(db) {
  const { results } = await db.prepare("SELECT id, texte, cree_le FROM memoire ORDER BY id").all();
  return results;
}

export async function lireProfil(db) {
  const r = await db.prepare("SELECT valeur FROM etat WHERE cle = 'profil'").first();
  return r ? r.valeur : "";
}

/** Exécute la commande éventuelle. Renvoie la note interne pour le modèle, ou null. */
export async function traiter(db, texte) {
  const cmd = analyser(texte);
  if (!cmd) return null;

  if (cmd.type === "retenir") {
    const entree = nettoyer(cmd.texte);
    const existantes = await lireMemoire(db);
    if (existantes.some((l) => normaliser(l.texte) === normaliser(entree))) {
      return `C'était déjà dans ta mémoire : « ${entree} ». Dis-le simplement.`;
    }
    const jour = new Date().toISOString().slice(0, 10);
    await db.prepare("INSERT INTO memoire (texte) VALUES (?)").bind(`[${jour}] ${entree}`).run();
    return `C'est fait : tu as ajouté à ta mémoire « ${entree} ». Confirme-le en une phrase courte.`;
  }

  if (cmd.type === "oublier") {
    const lignes = await lireMemoire(db);
    const trouvees = correspondances(cmd.texte, lignes);
    if (trouvees === null) {
      return "La demande d'oubli était trop vague : rien n'a été effacé. Demande-lui de préciser.";
    }
    if (trouvees.length === 0) {
      return `Rien dans ta mémoire ne correspond à « ${cmd.texte.trim()} » : rien n'a été effacé. Dis-le-lui franchement (si c'est dans son profil, il doit modifier perso/profil.md sur le Mac).`;
    }
    if (trouvees.length > MAX_LIGNES_OUBLIEES) {
      return `${trouvees.length} éléments correspondent, c'est trop vague : rien n'a été effacé. Montre-lui ces éléments et demande lequel oublier :\n${trouvees.map((l) => "- " + l.texte).join("\n")}`;
    }
    for (const l of trouvees) await db.prepare("DELETE FROM memoire WHERE id = ?").bind(l.id).run();
    return `C'est fait, tu as oublié : ${trouvees.map((l) => `« ${l.texte} »`).join(" ; ")}. Confirme-le en une phrase courte.`;
  }

  // savoir
  const profil = (await lireProfil(db)).trim() || "(profil pas encore synchronisé depuis le Mac)";
  const memoire = (await lireMemoire(db)).map((l) => "- " + l.texte).join("\n") || "(mémoire vide)";
  return (
    "Il demande ce que tu sais sur lui. Résume fidèlement et brièvement UNIQUEMENT ceci, sans rien " +
    `ajouter ni deviner, et rappelle qu'il peut te dire « oublie … » :\n\nPROFIL :\n${profil}\n\nMÉMOIRE :\n${memoire}`
  );
}
