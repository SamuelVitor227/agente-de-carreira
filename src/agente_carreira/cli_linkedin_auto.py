"""CLI do navegador automático no LinkedIn (RN-04: só por opção do usuário, ciente do risco)."""

from __future__ import annotations

from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

console = Console()
auto_app = typer.Typer(help="Navegador automático no LinkedIn: buscar vagas e preencher a Candidatura Simplificada "
                            "(desligado por padrão; o envio é sempre seu).", invoke_without_command=True)

RISCO = (
    "Os termos de uso do LinkedIn proíbem automação. Com este modo ligado, o agente usa o navegador dele, "
    "com a SUA conta, para pesquisar vagas e preencher a Candidatura Simplificada, devagar e com pausas. "
    "Mesmo assim, o LinkedIn pode restringir ou bloquear a conta. O agente nunca clica em 'Enviar "
    "candidatura', nunca faz login por você e para em qualquer verificação de segurança."
)


@auto_app.callback()
def auto_status(ctx: typer.Context) -> None:
    """Mostra se o modo automático está ligado e se o navegador do agente está logado."""
    if ctx.invoked_subcommand is not None:
        return
    from .configuracao import carregar_configuracao

    cfg = carregar_configuracao().linkedin_automatico
    if cfg.ativo:
        quando = cfg.aceito_risco_em.astimezone().strftime("%d/%m/%Y %H:%M") if cfg.aceito_risco_em else "?"
        console.print(f"[magenta]Ligado[/magenta] (risco aceito em {quando}). Por rodada: até {cfg.consultas_por_rodada} "
                      f"buscas e {cfg.detalhes_por_rodada} vagas abertas, com pausas de {cfg.intervalo_min_s:g} a "
                      f"{cfg.intervalo_max_s:g} s.")
    else:
        console.print("Desligado. O LinkedIn entra só pelos alertas de e-mail e no modo copiloto.")
    console.print("Comandos: 'agente li automatico entrar' (login no navegador do agente), 'ligar --aceito-o-risco', "
                  "'desligar' e 'testar'.")


@auto_app.command("ligar")
def auto_ligar(
    aceito_o_risco: bool = typer.Option(False, "--aceito-o-risco", help="Confirma que você leu e aceita o risco para a conta."),
) -> None:
    """Liga o modo automático no LinkedIn (exige --aceito-o-risco)."""
    from .configuracao import carregar_configuracao, salvar_configuracao

    console.print(Panel(RISCO, title="Antes de ligar", border_style="red"))
    if not aceito_o_risco:
        console.print("[yellow]Nada mudou. Para ligar: 'agente li automatico ligar --aceito-o-risco'.[/yellow]")
        raise typer.Exit(1)
    central = carregar_configuracao()
    central.linkedin_automatico.ativo = True
    central.linkedin_automatico.aceito_risco_em = datetime.now(timezone.utc)
    salvar_configuracao(central)
    console.print("[green]Modo automático no LinkedIn ligado.[/green] Se ainda não entrou na conta pelo navegador do "
                  "agente, rode 'agente li automatico entrar'.")


@auto_app.command("desligar")
def auto_desligar() -> None:
    """Desliga o modo automático: o LinkedIn volta a ser só alertas de e-mail e copiloto."""
    from .configuracao import carregar_configuracao, salvar_configuracao

    central = carregar_configuracao()
    central.linkedin_automatico.ativo = False
    salvar_configuracao(central)
    console.print("[green]Modo automático no LinkedIn desligado.[/green]")


@auto_app.command("entrar")
def auto_entrar() -> None:
    """Abre o navegador do agente na tela de login do LinkedIn e espera você entrar (login, 2FA e CAPTCHA são seus)."""
    from .linkedin.automatico import esperar_login, esta_logado
    from .navegador import SessaoNavegador, playwright_disponivel

    if not playwright_disponivel():
        console.print("[red]O navegador do agente precisa do Playwright: rode 'uv sync' e 'uv run playwright install chromium'.[/red]")
        raise typer.Exit(1)
    with SessaoNavegador() as sessao:
        if esta_logado(sessao.pagina):
            console.print("[green]O navegador do agente já está logado no LinkedIn.[/green]")
            return
        console.print("Entre na sua conta no navegador que abriu. O agente espera até 10 minutos e não vê sua senha.")
        if esperar_login(sessao.pagina):
            console.print("[green]Pronto: login feito. O navegador do agente lembra dele nas próximas vezes.[/green]")
        else:
            console.print("[yellow]Não detectei o login. Tente de novo quando quiser.[/yellow]")
            raise typer.Exit(1)


@auto_app.command("testar")
def auto_testar() -> None:
    """Faz uma busca agora, só para ver o que o agente encontra (não salva nada)."""
    from .configuracao import carregar_configuracao
    from .linkedin.automatico import LoginNecessario, buscar_vagas
    from .navegador import SessaoNavegador, playwright_disponivel
    from .operacao.saude import LayoutMudou

    central = carregar_configuracao()
    if not central.vagas.buscas:
        console.print("[red]Crie uma busca de vagas antes ('Que vagas você procura?' no app).[/red]")
        raise typer.Exit(1)
    if not playwright_disponivel():
        console.print("[red]O navegador do agente precisa do Playwright ('uv sync').[/red]")
        raise typer.Exit(1)
    cfg = central.linkedin_automatico.model_copy(update={"detalhes_por_rodada": 3, "consultas_por_rodada": 2})
    try:
        with SessaoNavegador() as sessao:
            resultado = buscar_vagas(sessao.pagina, central.vagas, cfg, set())
    except LoginNecessario as erro:
        console.print(f"[yellow]{escape(str(erro))}[/yellow]")
        raise typer.Exit(1)
    except LayoutMudou as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]{len(resultado.vagas)} vaga(s) em {resultado.consultas} busca(s):[/green]")
    for vaga in resultado.vagas[:20]:
        descricao = "com descrição" if vaga.descricao else "só título"
        console.print(f"• {escape(vaga.titulo)} — {escape(vaga.empresa or '?')} ({escape(vaga.local or '?')}) · {descricao}")
    for aviso in resultado.avisos:
        console.print(f"[dim]{escape(aviso)}[/dim]")
