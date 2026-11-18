"""Comandos das cópias de segurança diárias dos dados ('agente copias')."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape

console = Console()
copias_app = typer.Typer(help="Cópias de segurança diárias dos seus dados (guardadas por 7 dias).",
                         invoke_without_command=True)


@copias_app.callback()
def copias_listar(ctx: typer.Context) -> None:
    """Mostra as cópias, da mais nova para a mais antiga."""
    if ctx.invoked_subcommand:
        return
    from .copias import garantir_copia_do_dia, listar_copias, pasta_copias

    garantir_copia_do_dia()
    lista = listar_copias()
    if not lista:
        console.print("Ainda não há cópias: a primeira é feita quando houver dados (perfil, vagas...).")
        return
    console.print(f"Cópias em {escape(str(pasta_copias()))}:")
    for c in lista:
        console.print(f"• [bold]{escape(c.nome)}[/bold] — {escape(c.rotulo)} · {c.arquivos} arquivo(s) · "
                      f"{c.tamanho / 1024:.0f} KB")
    console.print("Para voltar a uma delas: [bold]agente copias restaurar NOME[/bold] (o estado atual fica guardado antes).")


@copias_app.command("restaurar")
def copias_restaurar(nome: str = typer.Argument(..., help="O nome da cópia, como aparece em 'agente copias'.")) -> None:
    """Volta os dados para uma cópia. Antes, guarda o estado atual numa cópia 'antes-de-restaurar'."""
    from .copias import restaurar
    from .operacao import andamento

    if (estado := andamento.em_andamento()) is not None:
        console.print(f"[yellow]Espere esta tarefa terminar (ou pare-a) antes de restaurar: "
                      f"{escape(andamento.descrever(estado))}[/yellow]")
        raise typer.Exit(1)
    if not typer.confirm(f"Voltar os seus dados para a cópia {nome}? O estado atual fica guardado antes"):
        raise typer.Exit(0)
    try:
        restaurados = restaurar(nome)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Pronto: {len(restaurados)} arquivo(s) restaurado(s)[/green] ({escape(', '.join(restaurados))}).")
