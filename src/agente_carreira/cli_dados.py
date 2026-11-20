"""Onde ficam os dados do agente ('agente dados') e como tirá-los da nuvem (RF-EV-19)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

console = Console()
dados_app = typer.Typer(help="Onde ficam os seus dados (perfil, currículos, candidaturas, logins do navegador).",
                        invoke_without_command=True)


@dados_app.callback()
def dados_onde(ctx: typer.Context) -> None:
    """Mostra a pasta dos dados e se ela sincroniza com a nuvem."""
    if ctx.invoked_subcommand:
        return
    from .operacao.local_dados import destino_padrao, local_atual

    local = local_atual()
    console.print(f"Seus dados: [bold]{escape(str(local.pasta))}[/bold] ({local.tamanho_mb} MB)")
    if local.na_nuvem:
        console.print(f"[yellow]Essa pasta sincroniza com o {local.na_nuvem}: perfil, currículos, candidaturas e os "
                      "logins do navegador do agente vão para a nuvem.[/yellow]")
        console.print(f"Para deixar só neste computador: [bold]agente dados mover[/bold] (vai para {escape(str(destino_padrao()))}).")
    else:
        console.print("[green]Só neste computador (não sincroniza com nuvem).[/green]")


@dados_app.command("mover")
def dados_mover(
    para: Path | None = typer.Option(None, "--para", help="Pasta de destino (padrão: %LOCALAPPDATA%\\AgenteCarreira\\data)."),
) -> None:
    """Move os dados para uma pasta só deste computador e passa a usar ela."""
    from .operacao.local_dados import NaoDaParaMover, destino_padrao, local_atual, mover_dados

    local = local_atual()
    destino = para or destino_padrao()
    if not typer.confirm(f"Mover {local.tamanho_mb} MB de {local.pasta} para {destino}? A pasta antiga é apagada "
                         "depois da cópia conferida", default=True):
        raise typer.Exit(0)
    try:
        novo = mover_dados(destino)
    except NaoDaParaMover as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Pronto: seus dados agora ficam em {escape(str(novo))}.[/green]")
    console.print("Feche e abra o app. Recrie o atalho (Configurações → Atalho na Área de Trabalho) e a busca "
                  "automática (Configurações → Busca automática todo dia → Agendar), que apontavam para a pasta antiga.")
