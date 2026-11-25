import { describe, expect, it } from "vitest";
import { analyser, correspondances, nettoyer } from "../src/memoire.js";
import { egaliteSure, estProprietaire } from "../src/telegram.js";

describe("mémoire : reconnaissance des commandes", () => {
  it.each([
    ["Retiens que je bois mon café noir", "retenir", "je bois mon café noir"],
    ["Sebtix, note que j'ai piscine le mardi", "retenir", "j'ai piscine le mardi"],
    ["souviens-toi que mon chat s'appelle Pixel", "retenir", "mon chat s'appelle Pixel"],
    ["Oublie que je bois du café", "oublier", "je bois du café"],
  ])("%s", (phrase, type, texte) => {
    const r = analyser(phrase);
    expect(r.type).toBe(type);
    expect(r.texte).toBe(texte);
  });

  it("reconnaît « qu'est-ce que tu sais sur moi »", () => {
    expect(analyser("Qu'est-ce que tu sais sur moi ?").type).toBe("savoir");
    expect(analyser("Que sais-tu de moi")).toEqual({ type: "savoir" });
  });

  it("ignore les messages normaux et « n'oublie pas »", () => {
    expect(analyser("Quel temps fait-il ?")).toBeNull();
    expect(analyser("N'oublie pas de me rappeler demain")).toBeNull();
  });

  it("nettoie l'entrée", () => {
    expect(nettoyer("  je bois   mon café.  ")).toBe("Je bois mon café");
  });
});

describe("mémoire : correspondances pour « oublie »", () => {
  const lignes = [
    { id: 1, texte: "[2026-11-25] Je bois mon café noir" },
    { id: 2, texte: "[2026-11-25] Mon chat s'appelle Pixel" },
  ];
  it("trouve la bonne ligne", () => {
    expect(correspondances("je bois du café noir", lignes).map((l) => l.id)).toEqual([1]);
  });
  it("ne trouve rien quand rien ne correspond", () => {
    expect(correspondances("mon numéro de passeport", lignes)).toEqual([]);
  });
  it("refuse une demande trop vague", () => {
    expect(correspondances("ça", lignes)).toBeNull();
  });
});

describe("sécurité Telegram", () => {
  const env = { TELEGRAM_CHAT_ID: "123456" };
  it("accepte uniquement le propriétaire, en privé", () => {
    expect(estProprietaire(env, { chat: { id: 123456, type: "private" } })).toBe(true);
    expect(estProprietaire(env, { chat: { id: 999, type: "private" } })).toBe(false);
    expect(estProprietaire(env, { chat: { id: 123456, type: "group" } })).toBe(false);
    expect(estProprietaire({}, { chat: { id: 123456, type: "private" } })).toBe(false);
    expect(estProprietaire(env, undefined)).toBe(false);
  });
  it("compare les secrets correctement", () => {
    expect(egaliteSure("abc", "abc")).toBe(true);
    expect(egaliteSure("abc", "abd")).toBe(false);
    expect(egaliteSure("abc", "ab")).toBe(false);
    expect(egaliteSure(undefined, "abc")).toBe(false);
  });
});

import { chiffrer, dechiffrer } from "../src/outlook.js";

describe("chiffrement du jeton Outlook", () => {
  const cle = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))));
  it("aller-retour", async () => {
    const env = { CHIFFREMENT_CLE: cle };
    const secret = "M.C123_jeton-de-renouvellement";
    const chiffre = await chiffrer(env, secret);
    expect(chiffre).not.toContain("jeton");
    expect(await dechiffrer(env, chiffre)).toBe(secret);
  });
  it("une autre clé ne peut pas déchiffrer", async () => {
    const chiffre = await chiffrer({ CHIFFREMENT_CLE: cle }, "secret");
    const autre = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))));
    await expect(dechiffrer({ CHIFFREMENT_CLE: autre }, chiffre)).rejects.toThrow();
  });
});
