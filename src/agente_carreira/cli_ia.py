"""Uso de IA: motor por tarefa, fila de pedidos, autorização em lote e registro (RF-IA-01 a RF-IA-08)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .importadores import importar_arquivo
from .importadores.mesclar import aplicar_importacao
from .models import (
    Area,
    Conquista,
    Contato,
    Experiencia,
    ModeloTrabalho,
    Periodo,
    PerfilMestre,
    Vinculo,
)
from .storage import caminho_perfil, carregar_perfil, diretorio_dados, perfil_existe, salvar_perfil
from .vagas import Vaga, carregar_vagas, conjunto_de_analise, salvar_vagas
from .validacao import validar_perfil
from .versionamento import carregar_versao, listar_versoes, restaurar_versao, resumo_diferencas

from .cli_comum import (  # noqa: F401 - ajudantes comuns da linha de comando
    _bloquear_sem_lastro,
    _checar_recusa,
    _data,
    _lista,
    _perfil_ou_none,
    _perguntar_autorizacao,
    _prompt_multilinha,
    _tratar_recusa,
    _usar_ia,
    app,
    console,
)
from .cli_linkedin import _curto

ia_app = typer.Typer(help="Uso de IA: motor por tarefa, fila de pedidos e registro (RF-IA-01 a RF-IA-05).", no_args_is_help=True)


@ia_app.command("motores")
def ia_motores() -> None:
    """Mostra o motor configurado para cada tarefa (RF-IA-01)."""
    from .ia import TAREFAS, carregar_configuracao

    config = carregar_configuracao()
    tabela = Table(title="Motor por tarefa")
    tabela.add_column("Tarefa")
    tabela.add_column("Descrição", overflow="fold")
    tabela.add_column("Motor")
    for tarefa, descricao in TAREFAS.items():
        tabela.add_row(tarefa, descricao, config.motor_da_tarefa(tarefa))
    console.print(tabela)
    console.print("'perguntar' propõe o Claude e você pode trocar no pedido; 'local' não usa IA externa. "
                  "Mude com 'agente ia motor TAREFA MOTOR'.")


@ia_app.command("motor")
def ia_motor(
    tarefa: str = typer.Argument(..., help="Tarefa (veja 'agente ia motores')."),
    motor: str = typer.Argument(..., help="claude, gemini, local ou perguntar."),
) -> None:
    """Define o motor padrão de uma tarefa (RF-IA-01)."""
    from .ia import carregar_configuracao, definir_motor, salvar_configuracao

    config = carregar_configuracao()
    try:
        definir_motor(config, tarefa, motor)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_configuracao(config)
    console.print(f"[green]{escape(tarefa)} → {escape(motor)}.[/green] A autorização continua sendo pedida a cada uso (RN-14).")


@ia_app.command("fila")
def ia_fila() -> None:
    """Pedidos de IA negados, pendentes de decisão (RF-IA-03)."""
    from .ia import carregar_usos

    pendentes = carregar_usos().pendentes()
    if not pendentes:
        console.print("Nenhum pedido de IA pendente.")
        return
    tabela = Table(title=f"Pedidos de IA pendentes ({len(pendentes)})")
    for col in ("ID", "Pedido em", "Tarefa", "Motor", "Tamanho"):
        tabela.add_column(col)
    for u in pendentes:
        tabela.add_row(u.id, f"{u.pedido_em:%d/%m/%Y %H:%M}", u.tarefa, u.motor, f"{u.caracteres} caracteres")
    console.print(tabela)
    console.print("Autorize com 'agente ia autorizar ID' ou descarte com 'agente ia descartar ID'.")


@ia_app.command("autorizar")
def ia_autorizar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Autoriza um pedido pendente: gera o prompt agora, podendo trocar de motor (RF-IA-02, RF-IA-03)."""
    from .ia import autorizar_pendente, carregar_usos, outro_motor, salvar_usos

    usos = carregar_usos()
    try:
        uso = usos.buscar(id_)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    if uso.autorizacao != "pendente":
        console.print(f"[red]O uso {id_} não está pendente (status: {uso.autorizacao}).[/red]")
        raise typer.Exit(1)
    motor = uso.motor
    while True:
        escolha = _perguntar_autorizacao(motor, uso.descricao, uso.dados, uso.removidos, uso.caracteres)
        if escolha != "t":
            break
        motor = outro_motor(motor)
    if escolha == "n":
        console.print("Continua pendente; nada foi gerado.")
        raise typer.Exit(0)
    autorizar_pendente(usos, id_, motor=motor)
    salvar_usos(usos)
    console.print(f"[green]Prompt gerado em[/green] {uso.arquivo_prompt}  [dim](uso {uso.id}, motor {uso.motor})[/dim]")


@ia_app.command("descartar")
def ia_descartar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Descarta um pedido pendente; nada é gerado nem enviado."""
    from .ia import carregar_usos, descartar_pendente, salvar_usos

    usos = carregar_usos()
    try:
        descartar_pendente(usos, id_)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_usos(usos)
    console.print(f"[green]Pedido {id_} descartado.[/green]")


@ia_app.command("recusado")
def ia_recusado(id_: str = typer.Argument(..., metavar="ID", help="ID do uso de IA (veja 'agente ia log').")) -> None:
    """Registra que o motor recusou por limite de uso e oferece o outro motor ou o local (RF-IA-07)."""
    _tratar_recusa(id_)


lote_app = typer.Typer(help="Autorização em lote: desligada por padrão, com prazo e revogável (RF-IA-08).",
                       invoke_without_command=True)
ia_app.add_typer(lote_app, name="lote")


@lote_app.callback()
def lote_listar(ctx: typer.Context) -> None:
    """Lista as autorizações em lote."""
    if ctx.invoked_subcommand is not None:
        return
    from .ia import carregar_usos

    lotes = carregar_usos().lotes
    if not lotes:
        console.print("Nenhuma autorização em lote — cada uso de IA pede autorização (padrão). "
                      "Crie uma com 'agente ia lote criar --tarefa justificativa-vagas'.")
        return
    tabela = Table(title="Autorizações em lote")
    for col in ("ID", "Situação", "Tarefas", "Motor", "Válida até", "Usos"):
        tabela.add_column(col, overflow="fold")
    for l in reversed(lotes):
        situacao = "revogada" if l.revogada_em else ("ativa" if l.ativa() else "vencida")
        cor = {"ativa": "green", "revogada": "red", "vencida": "dim"}[situacao]
        tabela.add_row(l.id, f"[{cor}]{situacao}[/{cor}]", ", ".join(l.tarefas), l.motor or "claude ou gemini",
                       f"{l.valida_ate.astimezone():%d/%m %H:%M}", str(len(l.usos)))
    console.print(tabela)


@lote_app.command("criar")
def lote_criar(
    tarefa: list[str] = typer.Option(..., "--tarefa", help="Tarefa coberta (repita para mais de uma)."),
    motor: str | None = typer.Option(None, "--motor", help="claude ou gemini; sem isso, vale para os dois."),
    ate: str | None = typer.Option(None, "--ate", help="Hora de hoje em que o lote vence (HH:MM)."),
    horas: float | None = typer.Option(None, "--horas", help="Duração em horas (máximo 24)."),
) -> None:
    """Cria uma autorização em lote — por exemplo, 'toda a rodada de hoje' (RF-IA-08)."""
    import re as _re
    from datetime import datetime, timedelta, timezone

    from .ia import TAREFAS, carregar_usos, criar_lote, fim_do_dia, salvar_usos

    agora = datetime.now(timezone.utc)
    if horas is not None:
        valida_ate = agora + timedelta(hours=horas)
    elif ate:
        m = _re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", ate.strip())
        if not m:
            console.print("[red]Use --ate HH:MM.[/red]")
            raise typer.Exit(1)
        valida_ate = agora.astimezone().replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0,
                                                 microsecond=0).astimezone(timezone.utc)
    else:
        valida_ate = fim_do_dia(agora)
    descricoes = "\n".join(f"  • {escape(t)}: {escape(TAREFAS.get(t, 'tarefa desconhecida'))}" for t in tarefa)
    console.print(Panel(
        f"Enquanto o lote valer, estes usos de IA geram o prompt sem perguntar a cada vez:\n{descricoes}\n"
        f"Motor: {motor or 'Claude ou Gemini'} · válido até {valida_ate.astimezone():%d/%m %H:%M}\n"
        "Cada uso continua mostrando motor, tarefa e dados, e fica no registro com o ID do lote. "
        "Revogue quando quiser com 'agente ia lote revogar ID'.",
        title="Autorização em lote (RF-IA-08)", border_style="magenta",
    ))
    if not typer.confirm("Criar esta autorização em lote?", default=False):
        raise typer.Exit(0)
    usos = carregar_usos()
    try:
        lote = criar_lote(usos, tarefa, valida_ate, motor=motor, agora=agora)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_usos(usos)
    console.print(f"[green]Autorização em lote {lote.id} criada.[/green]")


@lote_app.command("revogar")
def lote_revogar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Revoga uma autorização em lote na hora: os próximos usos voltam a pedir autorização."""
    from .ia import carregar_usos, revogar_lote, salvar_usos

    usos = carregar_usos()
    try:
        revogar_lote(usos, id_)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_usos(usos)
    console.print(f"[green]Lote {id_} revogado.[/green] Cada uso de IA volta a pedir autorização.")


@ia_app.command("log")
def ia_log(tarefa: str | None = typer.Option(None, "--tarefa", help="Filtra por tarefa.")) -> None:
    """Registro de cada uso de IA: data, motor, tarefa, dados, autorização e resultado (RF-IA-05)."""
    from .ia import carregar_usos

    usos = [u for u in carregar_usos().itens if tarefa is None or u.tarefa == tarefa]
    if not usos:
        console.print("Nenhum uso de IA registrado.")
        return
    tabela = Table(title=f"Registro de uso de IA ({len(usos)})")
    for col in ("ID", "Pedido em", "Tarefa", "Motor", "Autorização", "Dados enviados", "Removidos", "Resultado"):
        tabela.add_column(col, overflow="fold")
    for u in reversed(usos):
        removidos = ", ".join(f"{t} ({q})" for t, q in u.removidos.items()) or "—"
        enviados = "; ".join(d.split(":")[0] for d in u.dados if not d.startswith("NÃO"))
        tabela.add_row(
            u.id, f"{u.pedido_em:%d/%m/%Y %H:%M}", u.tarefa, u.motor, u.autorizacao,
            Text(_curto(enviados, 60)), Text(removidos), Text(u.resultado or ""),
        )
    console.print(tabela)
    console.print("[dim]Os dados completos de cada pedido ficam em data/uso-ia.json.[/dim]")
