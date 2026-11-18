"""CLI da leitura de alertas pelo Outlook na web, no navegador do agente."""

from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.markup import escape

console = Console()
email_app = typer.Typer(help="Alertas de vaga lidos pelo Outlook na web, no navegador do agente (só leitura).",
                        invoke_without_command=True)


@email_app.callback()
def email_status(ctx: typer.Context) -> None:
    """Mostra como o agente lê os alertas de vaga."""
    if ctx.invoked_subcommand is not None:
        return
    from .configuracao import carregar_configuracao
    from .operacao.credenciais import email_configurado

    central = carregar_configuracao()
    if central.email_navegador.ativo:
        console.print("[green]Lendo pelo Outlook na web[/green], no navegador do agente: "
                      f"{len(central.email_navegador.consultas)} remetente(s) de alerta, Prioritário e Outros.")
    elif email_configurado():
        console.print(f"[green]Lendo por IMAP[/green] ({escape(email_configurado())}).")
    else:
        console.print("Nenhuma leitura de e-mail ligada. Para o Outlook: 'agente email entrar' e 'agente email ligar'.")


@email_app.command("ligar")
def email_ligar() -> None:
    """Liga a leitura dos alertas pelo Outlook na web em cada busca de vagas."""
    from .configuracao import carregar_configuracao, salvar_configuracao

    central = carregar_configuracao()
    central.email_navegador.ativo = True
    salvar_configuracao(central)
    console.print("[green]Leitura pelo Outlook ligada.[/green] Cada busca de vagas lê os alertas novos (só leitura).")


@email_app.command("desligar")
def email_desligar() -> None:
    """Desliga a leitura pelo Outlook na web."""
    from .configuracao import carregar_configuracao, salvar_configuracao

    central = carregar_configuracao()
    central.email_navegador.ativo = False
    salvar_configuracao(central)
    console.print("[green]Leitura pelo Outlook desligada.[/green]")


@email_app.command("entrar")
def email_entrar() -> None:
    """Abre o Outlook no navegador do agente e espera você entrar (login e 2FA são seus)."""
    from .navegador import NavegadorOcupado, SessaoNavegador, playwright_disponivel
    from .radar.outlook_web import DOMINIOS_CAIXA, SELETOR_PESQUISA, LoginOutlook, caixa_aberta

    if not playwright_disponivel():
        console.print("[red]O navegador do agente precisa do Playwright ('uv sync').[/red]")
        raise typer.Exit(1)
    try:
        with SessaoNavegador() as sessao:
            try:
                caixa_aberta(sessao.pagina, espera_s=20)
                console.print("[green]O navegador do agente já está logado no Outlook. Pode fechar esta janela.[/green]")
                return
            except LoginOutlook:
                pass
            console.print("Entre na sua conta da Microsoft no navegador que abriu. O agente espera até 10 minutos.")
            for _ in range(200):
                time.sleep(3)
                try:
                    abertas = [p for p in sessao.pagina.context.pages if not p.is_closed()]
                    if not abertas:
                        break
                    if any(any(d in p.url.lower() for d in DOMINIOS_CAIXA) and p.locator(SELETOR_PESQUISA).count()
                           for p in abertas):
                        console.print("[green]Pronto: login feito. O navegador do agente lembra dele.[/green]")
                        return
                except Exception:  # noqa: BLE001 - página trocando durante o login
                    continue
            console.print("[yellow]Não detectei o login. Tente de novo quando quiser.[/yellow]")
            raise typer.Exit(1)
    except NavegadorOcupado as erro:
        console.print(f"[yellow]{escape(str(erro))}[/yellow]")
        raise typer.Exit(1)


@email_app.command("testar")
def email_testar() -> None:
    """Lê os alertas agora e mostra as vagas encontradas, sem salvar nada."""
    from .configuracao import carregar_configuracao
    from .navegador import NavegadorOcupado, SessaoNavegador
    from .radar.coleta import diagnostico_email, vagas_de_email
    from .radar.outlook_web import LoginOutlook, ler_alertas

    central = carregar_configuracao()
    try:
        with SessaoNavegador() as sessao:
            mensagens, avisos = ler_alertas(sessao.pagina, central.email_navegador.consultas, set(), por_consulta=3)
    except (NavegadorOcupado, LoginOutlook) as erro:
        console.print(f"[yellow]{escape(str(erro))}[/yellow]")
        raise typer.Exit(1)
    total = 0
    for _, msg in mensagens:
        plataforma, links, _ = diagnostico_email(msg)
        vagas = vagas_de_email(msg)
        total += len(vagas)
        console.print(f"• {escape(str(msg['Subject'])[:70])} — {plataforma or '?'}: {len(vagas)} vaga(s)")
        for vaga in vagas[:3]:
            console.print(f"    {escape(vaga.titulo)} — {escape(vaga.empresa or '?')}")
    console.print(f"[green]{len(mensagens)} alerta(s) lido(s), {total} vaga(s) encontrada(s).[/green] Nada foi salvo.")
    for aviso in avisos:
        console.print(f"[dim]{escape(aviso)}[/dim]")
