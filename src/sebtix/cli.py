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


def enregistrer(cli: click.Group) -> None:
    """Ajoute toutes les commandes Sebtix à la CLI."""
    cli.add_command(outlook, "outlook")
