"""Commandes Sebtix ajoutées à la CLI `sebtix`.

Pour ajouter les commandes d'un nouveau module : créer un groupe click ci-dessous
et l'ajouter dans `enregistrer()`. Rien d'autre à toucher dans OpenJarvis.
"""

from __future__ import annotations

import click


@click.group(help="Outlook (Microsoft Graph, lecture seule) : connexion, mails, agenda.")
def outlook() -> None:
    pass


@outlook.command("connecter", help="Connecte ton compte Outlook (code à usage unique).")
def outlook_connecter() -> None:
    from sebtix import outlook as o

    deja = o.compte_connecte()
    if deja:
        click.echo(f"Déjà connecté : {deja}. (Pour changer : sebtix outlook deconnecter)")
        return
    adresse = o.connecter(lambda texte: click.echo(texte))
    click.echo(f"✅ Connecté en lecture seule : {adresse}")


@outlook.command(
    "connecter-sentinelle",
    help="Donne à la Sentinelle son propre accès Outlook en lecture seule (code à usage unique).",
)
def outlook_connecter_sentinelle() -> None:
    from sebtix import outlook as o

    o.connecter_sentinelle(lambda texte: click.echo(texte))
    click.echo("✅ La Sentinelle peut lire tes mails et ton agenda (lecture seule, jeton chiffré chez elle).")


@outlook.command("deconnecter", help="Oublie la connexion Outlook sur ce Mac.")
def outlook_deconnecter() -> None:
    from sebtix import outlook as o

    o.deconnecter()
    click.echo("Connexion Outlook supprimée de ce Mac.")


@outlook.command("statut", help="Indique si Outlook est connecté.")
def outlook_statut() -> None:
    from sebtix import outlook as o

    compte = o.compte_connecte()
    click.echo(f"Connecté : {compte}" if compte else "Non connecté (sebtix outlook connecter).")


@outlook.command("mails", help="Affiche tes derniers mails reçus.")
@click.option("-n", "--nombre", default=5, show_default=True, help="Nombre de mails.")
def outlook_mails(nombre: int) -> None:
    from sebtix import outlook as o

    try:
        mails = o.derniers_mails(nombre)
    except o.OutlookNonConnecte as e:
        raise click.ClickException(str(e))
    if not mails:
        click.echo("Boîte de réception vide.")
    for m in mails:
        pastille = " " if m.lu else "●"
        click.echo(f"{pastille} {m.recu_le:%d/%m %H:%M}  {m.expediteur} — {m.objet}")


@outlook.command("agenda", help="Affiche ton agenda du jour.")
def outlook_agenda() -> None:
    from sebtix import outlook as o

    try:
        evenements = o.agenda()
    except o.OutlookNonConnecte as e:
        raise click.ClickException(str(e))
    if not evenements:
        click.echo("Rien dans ton agenda aujourd'hui.")
    for e in evenements:
        heure = "Toute la journée" if e.journee_entiere else f"{e.debut:%H:%M}–{e.fin:%H:%M}"
        lieu = f" ({e.lieu})" if e.lieu else ""
        click.echo(f"{heure}  {e.titre}{lieu}")


@click.group(help="Bot Telegram de Sebtix (canal téléphone).")
def telegram() -> None:
    pass


@telegram.command("installer", help="Branche ton bot Telegram sur la Sentinelle (jeton saisi masqué).")
def telegram_installer() -> None:
    from sebtix.telegram_installation import installer

    installer()


def _sentinelle_ou_erreur(action):
    from sebtix import sentinelle

    try:
        return action(sentinelle)
    except sentinelle.SentinelleInjoignable as e:
        raise click.ClickException(str(e))


@click.group(
    "sync",
    invoke_without_command=True,
    help="Synchronise le Mac avec la Sentinelle et traite les tâches en attente.",
)
@click.pass_context
def sync(ctx: click.Context) -> None:
    if ctx.invoked_subcommand:
        return
    from sebtix import synchro

    bilan = _sentinelle_ou_erreur(lambda _s: synchro.synchroniser())
    taches = f", {len(bilan.taches_faites)} tâche(s) traitée(s)" if bilan.taches_faites else ""
    click.echo(f"✅ Synchronisé : profil envoyé, {bilan.souvenirs} souvenir(s){taches}.")
    for erreur in bilan.erreurs:
        click.echo(f"⚠️ {erreur}")


@sync.command("installer", help="Synchronise automatiquement toutes les 5 min (et au réveil du Mac).")
def sync_installer() -> None:
    from sebtix import synchro

    chemin = synchro.installer_automatisation()
    click.echo(f"✅ Synchronisation automatique installée ({chemin}).")


@sync.command("desinstaller", help="Retire la synchronisation automatique.")
def sync_desinstaller() -> None:
    from sebtix import synchro

    click.echo("Retirée." if synchro.desinstaller_automatisation() else "Elle n'était pas installée.")


@click.command("stop", help="Coupe TOUTE la surveillance d'un coup (mails, notifications, briefs).")
def stop() -> None:
    _sentinelle_ou_erreur(lambda s: s.definir_surveillance(False))
    click.echo("🛑 Surveillance coupée : plus aucune notification ni brief. (sebtix reprendre pour relancer)")


@click.command("reprendre", help="Relance la surveillance.")
def reprendre() -> None:
    _sentinelle_ou_erreur(lambda s: s.definir_surveillance(True))
    click.echo("✅ Surveillance relancée.")


@click.command("budget", help="Affiche ce que Sebtix a consommé et dépensé ce mois-ci.")
def budget() -> None:
    b = _sentinelle_ou_erreur(lambda s: s.budget())
    ia, voix = b["workers_ai"], b["azure_speech"]
    click.echo(f"💶 Dépensé en {b['mois']} : {b['depense_euros']:.2f} € (plafond fixé : 10 €/mois)")
    click.echo(
        f"🧠 IA de la Sentinelle (Cloudflare, gratuit) : {ia['neurones_aujourdhui']:.0f} / "
        f"{ia['limite_gratuite_par_jour']} neurones aujourd'hui, {ia['neurones_mois']:.0f} ce mois-ci"
    )
    click.echo(
        f"🔊 Voix (Azure, gratuit) : {voix['caracteres_mois']} / {voix['limite_gratuite_par_mois']} "
        "caractères ce mois-ci"
    )
    click.echo("   Au-delà des limites gratuites, le service se bloque : il ne facture jamais.")


def enregistrer(cli: click.Group) -> None:
    """Ajoute toutes les commandes Sebtix à la CLI."""
    cli.add_command(outlook, "outlook")
    cli.add_command(telegram, "telegram")
    cli.add_command(sync, "sync")
    # `stop` d'OpenJarvis (arrêt du serveur local) reste disponible sous un autre nom.
    if "stop" in cli.commands:
        cli.add_command(cli.commands["stop"], "serveur-stop")
    cli.add_command(stop, "stop")
    cli.add_command(reprendre, "reprendre")
    cli.add_command(budget, "budget")
