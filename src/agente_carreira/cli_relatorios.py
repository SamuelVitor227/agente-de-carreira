"""CLI do M7: painel, relatório semanal e exportação (RF-RL-01 a RF-RL-03)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .storage import diretorio_dados

console = Console()
relatorio_app = typer.Typer(help="Relatório semanal: o que funcionou, lacunas e próximas ações (RF-RL-02, UC-11).",
                            invoke_without_command=True)


def _tabela(titulo: str, linhas) -> None:
    if not linhas:
        return
    tabela = Table(title=titulo)
    for col in ("", "Vagas", "Candidaturas", "Retornos", "Taxa", "Entrevistas", "Propostas"):
        tabela.add_column(col, justify="left" if not col else "right", overflow="fold")
    for l in linhas:
        tabela.add_row(escape(l.grupo), str(l.vagas), str(l.candidaturas), str(l.retornos), f"{l.taxa_retorno}%",
                       str(l.entrevistas), str(l.propostas))
    console.print(tabela)


def painel(
    dias: int | None = typer.Option(None, "--dias", help="Só os últimos N dias (padrão: desde o início)."),
    html: bool = typer.Option(False, "--html", help="Também grava data/painel.html e mostra o caminho."),
) -> None:
    """Painel: vagas, candidaturas, taxa de retorno, entrevistas e propostas por fonte, foco e variante (RF-RL-01)."""
    from .relatorios import Dados, montar_painel, painel_html

    dados = Dados.carregar()
    desde = datetime.now(timezone.utc) - timedelta(days=dias) if dias else None
    p = montar_painel(dados.base, dados.candidaturas, usos_ia=dados.usos_ia, saude=dados.saude, desde=desde)
    t, e = p.total, p.execucao
    console.print(f"[bold]Painel{f' — últimos {dias} dias' if dias else ''}[/bold]: {t.vagas} vaga(s) encontrada(s) · "
                  f"{t.candidaturas} candidatura(s) · {t.taxa_retorno}% de retorno · {t.entrevistas} entrevista(s) · "
                  f"{t.propostas} proposta(s)")
    _tabela("Por fonte", p.por_fonte)
    _tabela("Por foco", p.por_foco)
    _tabela("Por variante de CV", p.por_variante)
    if p.funil:
        console.print("Funil agora: " + " · ".join(f"{escape(n)} {q}" for n, q in p.funil.items()))
    if p.motivos_saida:
        console.print("Motivos de saída: " + " · ".join(f"{escape(m)} ({q})" for m, q in p.motivos_saida))
    ultima = e.ultima.astimezone().strftime("%d/%m %H:%M") if e.ultima else "nunca"
    console.print(f"Execução: {e.rodadas} rodada(s), última {ultima}, média {e.duracao_media_s}s, {e.coletadas} coletada(s), "
                  f"{e.erros} erro(s) · IA: {', '.join(f'{m} {n}x' for m, n in sorted(e.uso_ia.items())) or 'nenhum uso'}"
                  + (f" · [red]parados: {', '.join(e.adaptadores_parados)}[/red]" if e.adaptadores_parados else ""))
    if html:
        destino = diretorio_dados() / "painel.html"
        destino.write_text(painel_html(p), encoding="utf-8")
        console.print(f"[green]Painel em HTML:[/green] {destino} (também é atualizado a cada rodada).")


@relatorio_app.callback()
def relatorio_principal(ctx: typer.Context) -> None:
    """Lista os relatórios semanais já gerados."""
    if ctx.invoked_subcommand is not None:
        return
    pasta = diretorio_dados() / "relatorios"
    arquivos = sorted(pasta.glob("semana-*.md"), reverse=True) if pasta.is_dir() else []
    if not arquivos:
        console.print("Nenhum relatório ainda. Gere com 'agente relatorio semanal' ou agende com 'agente relatorio agendar'.")
        return
    for arquivo in arquivos[:10]:
        console.print(f"- {arquivo}")


@relatorio_app.command("semanal")
def relatorio_semanal_cmd(
    notificar_: bool = typer.Option(False, "--notificar", help="Envia pelo canal de notificação configurado."),
) -> None:
    """Gera o relatório da semana: números, o que funcionou, lacunas e próximas ações (RF-RL-02)."""
    from .configuracao import carregar_configuracao
    from .operacao.notificacoes import notificar
    from .radar.modelos import carregar_config
    from .relatorios import Dados, relatorio_markdown, relatorio_semanal

    dados = Dados.carregar()
    central = carregar_configuracao()
    relatorio = relatorio_semanal(
        dados.base, dados.candidaturas, usos_ia=dados.usos_ia, saude=dados.saude, lembretes=dados.lembretes,
        contas=dados.contas, fila=dados.fila, followup_dias=central.limites.followup_dias,
        limiar=carregar_config().limiar_alerta, perfil=dados.perfil,
    )
    texto = relatorio_markdown(relatorio)
    destino = diretorio_dados() / "relatorios" / f"semana-{relatorio.fim.astimezone():%Y-%m-%d}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    console.print(texto, markup=False, highlight=False)
    console.print(f"[green]Salvo em[/green] {destino}")
    if notificar_:
        envio = notificar("relatorio_semanal", f"Relatório semanal — {relatorio.fim.astimezone():%d/%m}", texto, central)
        if envio is None:
            console.print("Evento 'relatorio_semanal' desligado nas notificações.")
        elif envio.erro:
            console.print(f"[yellow]{escape(envio.erro)}[/yellow]")
        else:
            console.print(f"Enviado por {envio.canal}.")


@relatorio_app.command("agendar")
def relatorio_agendar(
    quando: str | None = typer.Option(None, "--quando", help="Ex.: 'domingo 20:00' (padrão: horarios.relatorio_semanal)."),
    mostrar: bool = typer.Option(False, "--mostrar", help="Só mostra o comando, sem criar a tarefa."),
) -> None:
    """Agenda o relatório semanal no sistema (padrão: domingo 20:00) (UC-11)."""
    from .configuracao import carregar_configuracao, salvar_configuracao
    from .radar.agenda import (NOME_TAREFA_SEMANAL, comando_schtasks_semanal, linha_cron_semanal, script_windows,
                               validar_dia_hora)

    central = carregar_configuracao()
    texto = quando or central.horarios.relatorio_semanal
    try:
        dia, hora = validar_dia_hora(texto)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    uv = shutil.which("uv") or "uv"
    projeto = Path.cwd()
    if sys.platform != "win32":
        console.print("Adicione esta linha ao seu crontab ('crontab -e'):")
        console.print(linha_cron_semanal(projeto, uv, dia, hora), markup=False, highlight=False)
    else:
        script = diretorio_dados() / "relatorio-semanal.cmd"
        conteudo = script_windows(projeto, uv, os.environ.get("AGENTE_CARREIRA_DATA"),
                                  comando="relatorio semanal --notificar", log="relatorio.log")
        comando = comando_schtasks_semanal(script, dia, hora)
        if mostrar:
            console.print(conteudo, markup=False, highlight=False)
            console.print(" ".join(comando), markup=False, highlight=False)
            return
        if not typer.confirm(f"Criar a tarefa '{NOME_TAREFA_SEMANAL}' no Agendador do Windows ({texto})?"):
            raise typer.Exit(0)
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_bytes(conteudo.encode("utf-8"))
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0:
            console.print(f"[red]Falha ao criar a tarefa: {escape(resultado.stderr or resultado.stdout)}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]Relatório agendado ({texto}).[/green] Log em data/relatorio.log. O PC precisa estar ligado.")
    if quando:
        central.horarios.relatorio_semanal = texto
        salvar_configuracao(central)


def exportar_dados(
    pasta: Path | None = typer.Option(None, "--pasta", help="Destino (padrão: data/exportacoes/AAAA-MM-DD)."),
) -> None:
    """Exporta vagas, candidaturas, histórico do funil, log de ações, uso de IA e contatos em CSV (RF-RL-03)."""
    from .relatorios import Dados, exportar

    dados = Dados.carregar()
    destino = pasta or diretorio_dados() / "exportacoes" / f"{datetime.now():%Y-%m-%d}"
    arquivos = exportar(destino, base=dados.base, candidaturas=dados.candidaturas, acoes=dados.acoes,
                        usos_ia=dados.usos_ia, contatos=dados.contatos)
    console.print(f"[green]{len(arquivos)} arquivo(s) CSV em[/green] {destino} (separador ';', abre direto no Excel).")
    for arquivo in arquivos:
        console.print(f"- {arquivo.name}")
    if not str(destino.resolve()).startswith(str(diretorio_dados().resolve())):
        console.print("[yellow]Atenção: os arquivos têm seus dados pessoais; não os coloque em pasta versionada no git.[/yellow]")
