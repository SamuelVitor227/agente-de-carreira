"""Peças comuns da linha de comando: o app raiz, o console e ajudantes (datas, listas, uso de IA)."""

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

app = typer.Typer(help="Agente de Carreira — perfil-mestre e otimização de currículo.", no_args_is_help=True)

console = Console()


def _data(texto: str) -> date:
    """Aceita AAAA-MM, AAAA-MM-DD ou MM/AAAA."""
    texto = texto.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", texto):
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
    if m := re.fullmatch(r"(\d{2})/(\d{4})", texto):
        return date(int(m.group(2)), int(m.group(1)), 1)
    raise typer.BadParameter(f"Data inválida: {texto!r}. Use AAAA-MM, AAAA-MM-DD ou MM/AAAA.")


def _lista(texto: str) -> list[str]:
    return [item.strip() for item in texto.split(",") if item.strip()]


def _prompt_multilinha(rotulo: str) -> list[str]:
    console.print(f"[bold]{rotulo}[/bold] (uma por linha; linha vazia encerra)")
    itens: list[str] = []
    while True:
        linha = input("> ").strip()
        if not linha:
            return itens
        itens.append(linha)


def _perguntar_autorizacao(motor: str, descricao: str, dados: list[str], removidos: dict[str, int], caracteres: int,
                           permitir_troca: bool = True) -> str:
    """Aviso do motor, da tarefa e dos dados; devolve 's' (aprovar), 't' (trocar motor) ou 'n' (negar) — RF-IA-02."""
    from .ia import outro_motor

    corpo = (
        f"[bold]Motor:[/bold] {escape(motor)} (sua assinatura; você cola o prompt manualmente)\n"
        f"[bold]Tarefa:[/bold] {escape(descricao)}\n"
        "[bold]Dados que vão no prompt:[/bold]\n" + "\n".join(f"  • {escape(d)}" for d in dados)
    )
    if removidos:
        corpo += "\n[bold]Removidos automaticamente (RF-IA-04):[/bold] " + ", ".join(
            f"{escape(tipo)} ({qtd})" for tipo, qtd in removidos.items()
        )
    corpo += f"\n[dim]Tamanho do prompt: {caracteres} caracteres[/dim]"
    console.print(Panel(corpo, title="Autorização de uso de IA (RF-IA-02)", border_style="magenta"))
    pergunta = f"Autoriza? [s]im, [t]rocar para {outro_motor(motor)} ou [n]ão" if permitir_troca else "Autoriza? [s]im ou [n]ão"
    validas = {"s", "t", "n"} if permitir_troca else {"s", "n"}
    while True:
        escolha = typer.prompt(pergunta).lstrip("﻿").strip().lower()[:1]
        if escolha in validas:
            return escolha
        console.print("Opção inválida.")


def _bloquear_sem_lastro(variante, perfil: PerfilMestre) -> None:
    """RN-02 / RNF-09: nada sem lastro no perfil-mestre sai num CV exportado."""
    from .analise.lastro import verificar_lastro

    if problemas := verificar_lastro(variante, perfil):
        console.print("[red]Exportação bloqueada (RN-02): o CV tem itens sem lastro no perfil-mestre:[/red]")
        for problema in problemas:
            console.print(f"  • {escape(problema)}")
        raise typer.Exit(1)


def _perfil_ou_none() -> PerfilMestre | None:
    """Perfil para o filtro de dados sensíveis, quando existir (comandos que não dependem dele)."""
    return carregar_perfil() if perfil_existe() else None


def _usar_ia(perfil, tarefa: str, motor_cli: str | None, dados: list[str], gerar_prompt, nome_arquivo):
    """Motor da tarefa, autorização, dados mínimos e registro do uso (RF-IA-01 a RF-IA-05).

    gerar_prompt(motor) e nome_arquivo(motor) montam o prompt e o arquivo para o motor escolhido.
    Devolve o UsoIA aprovado, ou None se o motor é local ou o pedido foi negado (fica na fila).
    """
    from .ia import (
        TAREFAS,
        carregar_configuracao,
        carregar_usos,
        lote_que_cobre,
        outro_motor,
        registrar_pedido,
        resolver_motor,
        salvar_usos,
        sanitizar,
        sugerir_motor,
        valores_sensiveis,
    )

    try:
        motor = resolver_motor(tarefa, motor_cli, carregar_configuracao())
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    if motor == "local":
        console.print(
            f"[yellow]A tarefa '{tarefa}' está no motor local: nenhuma IA externa é usada e nenhum prompt foi gerado.[/yellow] "
            f"Para usar IA nela: 'agente ia motor {tarefa} perguntar'."
        )
        return None
    # RF-IA-07: se o motor recusou por limite há pouco, avisa e propõe o outro.
    sugerido, aviso = sugerir_motor(carregar_usos(), motor)
    if aviso:
        console.print(f"[yellow]{escape(aviso)}[/yellow]")
        if not motor_cli:
            motor = sugerido

    sensiveis = valores_sensiveis(perfil)
    usos = carregar_usos()
    lote = lote_que_cobre(usos, tarefa, motor)
    if lote is not None:
        # RF-IA-08: autorizado em lote — o aviso de motor, tarefa e dados continua sendo mostrado (RF-IA-02).
        prompt, removidos = sanitizar(gerar_prompt(motor), sensiveis)
        corpo = (
            f"[bold]Motor:[/bold] {escape(motor)} · [bold]Tarefa:[/bold] {escape(TAREFAS[tarefa])}\n"
            "[bold]Dados que vão no prompt:[/bold]\n" + "\n".join(f"  • {escape(d)}" for d in dados)
            + (f"\n[bold]Removidos automaticamente:[/bold] {escape(', '.join(f'{t} ({q})' for t, q in removidos.items()))}"
               if removidos else "")
        )
        console.print(Panel(corpo, title=f"Autorizado em lote {lote.id} até {lote.valida_ate.astimezone():%d/%m %H:%M} (RF-IA-08)",
                            border_style="magenta"))
        escolha = "s"
    else:
        while True:
            prompt, removidos = sanitizar(gerar_prompt(motor), sensiveis)
            escolha = _perguntar_autorizacao(motor, TAREFAS[tarefa], dados, removidos, len(prompt))
            if escolha != "t":
                break
            motor = outro_motor(motor)
        usos = carregar_usos()

    uso = registrar_pedido(
        usos, tarefa=tarefa, descricao=TAREFAS[tarefa], motor=motor, dados=dados, prompt=prompt,
        removidos=removidos, nome_arquivo=nome_arquivo(motor), autorizado=escolha == "s",
        lote=lote.id if lote is not None else None,
    )
    salvar_usos(usos)
    if escolha == "n":
        console.print(
            f"Nada foi gerado nem enviado (RF-IA-03). O pedido [bold]{uso.id}[/bold] ficou pendente: "
            "veja 'agente ia fila' para autorizar depois ou descartar."
        )
        return None
    console.print(f"[green]Prompt gerado em[/green] {uso.arquivo_prompt}  [dim](uso de IA {uso.id} registrado)[/dim]")
    console.print(f"[dim]Se o {uso.motor.capitalize()} recusar por limite de uso, rode 'agente ia recusado {uso.id}'.[/dim]")
    return uso


def _tratar_recusa(uso_id: str) -> None:
    """RF-IA-07: registra a recusa por limite e oferece o outro motor ou o motor local, com nova autorização."""
    from .ia import (
        carregar_usos,
        outro_motor,
        prompt_para_outro_motor,
        registrar_pedido,
        registrar_recusa,
        salvar_usos,
    )

    usos = carregar_usos()
    try:
        uso = registrar_recusa(usos, uso_id)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_usos(usos)
    outro = outro_motor(uso.motor)
    console.print(Panel(
        f"O {uso.motor.capitalize()} recusou o pedido {uso.id} ({escape(uso.tarefa)}) por limite de uso da assinatura.\n"
        f"Dá para refazer no {outro.capitalize()}, com nova autorização, ou seguir no motor local, sem IA.",
        title="Motor recusou por limite (RF-IA-07)", border_style="yellow",
    ))
    while True:
        escolha = typer.prompt(f"[o]utro motor ({outro}), [l]ocal (sem IA) ou [n]ada agora").lstrip("﻿").strip().lower()[:1]
        if escolha in {"o", "l", "n"}:
            break
        console.print("Opção inválida.")
    if escolha == "l":
        console.print("Seguindo no motor local: nenhuma IA externa é usada; o texto do agente continua valendo.")
        return
    if escolha == "n":
        console.print(f"Nada feito. Para decidir depois: 'agente ia recusado {uso.id}'.")
        return
    try:
        prompt, nome_arquivo = prompt_para_outro_motor(usos, uso.id, outro)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    decisao = _perguntar_autorizacao(outro, uso.descricao, uso.dados, uso.removidos, len(prompt), permitir_troca=False)
    novo = registrar_pedido(
        usos, tarefa=uso.tarefa, descricao=uso.descricao, motor=outro, dados=uso.dados, prompt=prompt,
        removidos=uso.removidos, nome_arquivo=nome_arquivo, autorizado=decisao == "s", substitui=uso.id,
    )
    salvar_usos(usos)
    if decisao == "s":
        console.print(f"[green]Prompt gerado para o {outro.capitalize()} em[/green] {novo.arquivo_prompt}  [dim](uso {novo.id})[/dim]")
    else:
        console.print(f"Nada foi gerado. O pedido {novo.id} ficou na fila de aprovações.")


def _checar_recusa(texto: str, tarefa: str, motor: str | None) -> bool:
    """Se a 'resposta' trazida for uma recusa por limite, trata a recusa e devolve True."""
    from .ia import carregar_usos, resposta_e_recusa_por_limite, ultimo_aprovado

    if not motor or not resposta_e_recusa_por_limite(texto):
        return False
    console.print("[yellow]O arquivo traz uma recusa por limite de uso do motor, não uma resposta.[/yellow]")
    uso = ultimo_aprovado(carregar_usos(), tarefa, motor)
    if uso is None:
        console.print(f"Nenhum pedido de '{tarefa}' enviado ao {motor} foi encontrado no registro.")
        return True
    _tratar_recusa(uso.id)
    return True
