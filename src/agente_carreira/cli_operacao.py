"""CLI do M8 — operação (RF-OP-01 a RF-OP-07)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.columns import Columns
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

config_app = typer.Typer(help="Preferências centralizadas e modo somente sugestão (RF-OP-01, RF-OP-02).",
                         invoke_without_command=True)
tarefas_app = typer.Typer(help="Pausar, retomar e cancelar tarefas (RF-OP-03).", invoke_without_command=True)
fila_app = typer.Typer(help="Fila única de aprovações: aprovar, editar ou rejeitar item a item (RF-OP-05).",
                       invoke_without_command=True)
auditoria_app = typer.Typer(help="Log de auditoria das ações externas (RF-OP-06).", invoke_without_command=True)
saude_app = typer.Typer(help="Saúde dos adaptadores (RF-OP-07).", invoke_without_command=True)
notificacoes_app = typer.Typer(help="Notificações por e-mail ou push (RF-OP-04).", no_args_is_help=True)


def _sair_com_erro(erro: Exception) -> None:
    console.print(f"[red]{escape(str(erro))}[/red]")
    raise typer.Exit(1)


# ---------------------------------------------------------------- RF-OP-01 / RF-OP-02

def _mostrar_config() -> None:
    from .configuracao import carregar_configuracao
    from .ia import TAREFAS

    c = carregar_configuracao()
    v = c.vagas
    eventos = ", ".join(f"{e} {'✓' if ligado else '✗'}" for e, ligado in c.notificacao.eventos.items())
    linhas = [
        "[bold]Modo somente sugestão:[/bold] "
        + ("[red]LIGADO — nenhuma plataforma é tocada[/red]" if c.somente_sugestao else "desligado"),
        "",
        "[bold]Limites diários[/bold] (limites.*)",
        f"  candidaturas_por_dia: {c.limites.candidaturas_por_dia} · aderencia_minima_candidatura: "
        f"{c.limites.aderencia_minima_candidatura} · mensagens_por_dia: {c.limites.mensagens_por_dia}",
        f"  acoes_por_sessao: {c.limites.acoes_por_sessao} · intervalo_entre_acoes_segundos: "
        f"{c.limites.intervalo_entre_acoes_segundos} · reaplicar_mesma_empresa_dias: {c.limites.reaplicar_mesma_empresa_dias}",
        "",
        "[bold]Limiares de vagas[/bold] (vagas.*)",
        f"  limiar_alerta: {v.limiar_alerta} · limiar_candidatar: {v.limiar_candidatar} · limiar_salvar: "
        f"{v.limiar_salvar} · dias_validade: {v.dias_validade}",
        "",
        "[bold]Horários[/bold]",
        f"  vagas.hora_rodada: {v.hora_rodada} · horarios.resumo_ate: {c.horarios.resumo_ate} · "
        f"horarios.relatorio_semanal: {escape(c.horarios.relatorio_semanal)}",
        "",
        "[bold]Notificações[/bold] (notificacao.*)",
        f"  canal: {c.notificacao.canal} · email_para: {escape(c.notificacao.email_para or '—')}",
        f"  eventos: {eventos}",
        "",
        f"[bold]Buscas salvas:[/bold] {len(v.buscas)} (agente busca listar) · pesos aprendidos: {len(v.preferencias)}",
        "",
        "[bold]Motor de IA por tarefa[/bold] (motores.*)",
        *(f"  {t}: {c.motor_da_tarefa(t)}" for t in TAREFAS),
    ]
    console.print(Panel("\n".join(linhas), title="Preferências do agente (data/configuracao.json)", border_style="cyan"))
    tabela = Table(title="Modo por plataforma (modos_plataforma.*)")
    tabela.add_column("Plataforma")
    tabela.add_column("Modo")
    for plataforma, modo in c.modos_plataforma.items():
        cor = {"desligado": "red", "assistido": "yellow"}.get(modo, "")
        tabela.add_row(plataforma, f"[{cor}]{modo}[/{cor}]" if cor else modo)
    console.print(tabela)
    console.print("Altere com: agente config definir CAMINHO VALOR  (ex.: limites.candidaturas_por_dia 8)")


@config_app.callback()
def config_principal(ctx: typer.Context) -> None:
    """Mostra todas as preferências num só lugar."""
    if ctx.invoked_subcommand is None:
        _mostrar_config()


@config_app.command("definir")
def config_definir(
    caminho: str = typer.Argument(..., help="Ex.: limites.candidaturas_por_dia, notificacao.canal, modos_plataforma.gupy"),
    valor: str = typer.Argument(..., help="Novo valor (listas separadas por vírgula; true/false para ligar/desligar)."),
) -> None:
    """Altera uma preferência, com validação."""
    from .configuracao import carregar_configuracao, definir, salvar_configuracao
    from .ia import TAREFAS

    if caminho.startswith("motores.") and caminho.split(".", 1)[1] not in TAREFAS:
        _sair_com_erro(ValueError(f"Tarefa desconhecida. Válidas: {', '.join(TAREFAS)}."))
    if caminho == "modos_plataforma.linkedin" and valor.strip() == "assistido":
        console.print(Panel(
            "Os termos do LinkedIn proíbem automação. No modo assistido o agente preencheria o seu próprio perfil, "
            "uma alteração por vez e com você presente, mas a conta corre risco de restrição (RN-04).",
            title="Atenção", border_style="red",
        ))
        if not typer.confirm("Ligar o modo assistido no LinkedIn mesmo assim?", default=False):
            raise typer.Exit(0)
    try:
        nova = definir(carregar_configuracao(), caminho, valor)
    except ValueError as erro:
        _sair_com_erro(erro)
    salvar_configuracao(nova)
    console.print(f"[green]{escape(caminho)} atualizado.[/green]")


@config_app.command("sugestao")
def config_sugestao(ligar: bool = typer.Option(..., "--ligar/--desligar")) -> None:
    """Liga ou desliga o modo somente sugestão: com ele ligado, nenhuma plataforma é tocada (RF-OP-02)."""
    from .configuracao import carregar_configuracao, salvar_configuracao

    config = carregar_configuracao()
    config.somente_sugestao = ligar
    salvar_configuracao(config)
    if ligar:
        console.print("[yellow]Modo somente sugestão ligado:[/yellow] o agente só lê seus e-mails e arquivos e prepara "
                      "sugestões; páginas de vaga, páginas de carreira e GitHub não são acessados.")
    else:
        console.print("[green]Modo somente sugestão desligado.[/green] Cada plataforma volta ao modo configurado.")


# ---------------------------------------------------------------- RF-OP-03

@tarefas_app.callback()
def tarefas_principal(ctx: typer.Context) -> None:
    """Lista as tarefas."""
    if ctx.invoked_subcommand is not None:
        return
    from .operacao.tarefas import carregar_tarefas

    tarefas = [t for t in carregar_tarefas().itens if t.status != "concluida" or t.recorrente]
    if not tarefas:
        console.print("Nenhuma tarefa em andamento.")
        return
    tabela = Table(title="Tarefas")
    for col in ("ID", "Tipo", "Descrição", "Status", "Progresso", "Próximo passo / observação"):
        tabela.add_column(col, overflow="fold")
    for t in tarefas:
        proximo = t.proximo_passo()
        observacao = t.erro or t.dados.get("ultima_falha") or (proximo.descricao if proximo else t.dados.get("ultima_execucao", ""))
        cor = {"pausada": "yellow", "cancelada": "red", "falhou": "red"}.get(t.status, "green")
        tabela.add_row(t.id, t.tipo, Text(t.descricao), f"[{cor}]{t.status}[/{cor}]", t.progresso, Text(observacao or ""))
    console.print(tabela)
    console.print("Use 'agente tarefas pausar|retomar|cancelar ID'.")


def _com_tarefa(id_: str, acao) -> None:
    from .operacao.tarefas import carregar_tarefas, salvar_tarefas

    tarefas = carregar_tarefas()
    try:
        tarefa = tarefas.buscar(id_)
        resultado = acao(tarefa)
    except ValueError as erro:
        _sair_com_erro(erro)
    salvar_tarefas(tarefas)
    return tarefa, resultado


@tarefas_app.command("pausar")
def tarefas_pausar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Pausa uma tarefa (a rodada de vagas deixa de rodar até ser retomada)."""
    from .operacao.tarefas import pausar

    tarefa, _ = _com_tarefa(id_, pausar)
    console.print(f"[yellow]Tarefa {tarefa.id} pausada.[/yellow]")


@tarefas_app.command("retomar")
def tarefas_retomar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Retoma uma tarefa a partir do último passo confirmado."""
    from .operacao.tarefas import retomar

    tarefa, proximo = _com_tarefa(id_, retomar)
    console.print(f"[green]Tarefa {tarefa.id} retomada.[/green]")
    if tarefa.tipo == "linkedin-rodada" and proximo:
        console.print(f"Rode 'agente li propor' para continuar de '{escape(proximo.descricao)}'.")
    elif proximo:
        console.print(f"Próximo passo: {escape(proximo.descricao)}")


@tarefas_app.command("cancelar")
def tarefas_cancelar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Cancela uma tarefa."""
    from .operacao.tarefas import cancelar

    tarefa, _ = _com_tarefa(id_, cancelar)
    console.print(f"[red]Tarefa {tarefa.id} cancelada.[/red]")


# ---------------------------------------------------------------- RF-OP-05

def _mostrar_item(item, posicao: str = "") -> None:
    console.print(f"\n[bold]{posicao}{escape(item.titulo)}[/bold]  [dim]{item.id} · {item.tipo} · "
                  f"{item.criado_em:%d/%m/%Y %H:%M}[/dim]")
    depois = Panel(Text(item.depois), title="DEPOIS", border_style="yellow" if item.problemas else "green")
    if item.antes is not None:
        antes = Panel(Text(item.antes) if item.antes else Text("(vazio)", style="dim"), title="ANTES", border_style="red")
        console.print(Columns([antes, depois], equal=True, expand=True))
    else:
        console.print(depois)
    for detalhe in item.detalhes:
        console.print(f"  [dim]• {escape(detalhe)}[/dim]")
    for problema in item.problemas:
        console.print(f"  [red]• {escape(problema)}[/red]")


def _mostrar_decisao(decisao) -> None:
    console.print(f"[green]{escape(decisao.mensagem)}[/green]")
    if decisao.arquivo:
        console.print(f"Arquivo: {decisao.arquivo}")
    if decisao.texto_para_copiar:
        console.print("Texto para copiar:")
        console.print(decisao.texto_para_copiar, markup=False, highlight=False)
    if decisao.proximo_passo:
        console.print(escape(decisao.proximo_passo))


@fila_app.callback()
def fila_principal(ctx: typer.Context) -> None:
    """Lista tudo o que espera sua aprovação."""
    if ctx.invoked_subcommand is not None:
        return
    from .operacao.fila import listar_fila

    itens = listar_fila()
    if not itens:
        console.print("[green]Nada esperando aprovação.[/green]")
        return
    tabela = Table(title=f"Fila de aprovações ({len(itens)})")
    for col in ("ID", "Tipo", "Item", "Criado em", "Avisos"):
        tabela.add_column(col, overflow="fold")
    for item in itens:
        tabela.add_row(item.id, item.tipo, Text(item.titulo), f"{item.criado_em:%d/%m %H:%M}",
                       Text("; ".join(item.problemas)) if item.problemas else "")
    console.print(tabela)
    console.print("Revise um a um com 'agente fila revisar', ou use 'agente fila aprovar|editar|rejeitar ID'.")


@fila_app.command("revisar")
def fila_revisar() -> None:
    """Revisa a fila item a item, com antes × depois lado a lado (RNF-13)."""
    from .operacao import fila

    itens = fila.listar_fila()
    if not itens:
        console.print("[green]Nada esperando aprovação.[/green]")
        return
    try:
        for n, item in enumerate(itens, 1):
            _mostrar_item(item, f"{n}/{len(itens)} · ")
            while True:
                escolha = typer.prompt("[a]provar, [e]ditar, [r]ejeitar ou [p]ular").lstrip("﻿").strip().lower()[:1]
                try:
                    if escolha == "a":
                        decisao = fila.aprovar(item.id)
                        _mostrar_decisao(decisao)
                        if decisao.entrada_log:
                            _talvez_aplicar(decisao.entrada_log)
                    elif escolha == "r":
                        _mostrar_decisao(fila.rejeitar(item.id))
                    elif escolha == "e":
                        _editar_interativo(item)
                        item = next((i for i in fila.listar_fila() if i.id == item.id), None)
                        if item is None:
                            break
                        _mostrar_item(item)
                        continue
                    elif escolha != "p":
                        console.print("Opção inválida.")
                        continue
                except ValueError as erro:
                    console.print(f"[red]{escape(str(erro))}[/red]")
                    continue
                break
    except (KeyboardInterrupt, typer.Abort):
        console.print("\n[yellow]Revisão interrompida; os itens restantes continuam na fila.[/yellow]")


def _editar_interativo(item) -> None:
    from .operacao import fila

    if item.id.startswith("ia:"):
        motor = typer.prompt("Trocar para qual motor (claude ou gemini)?").strip().lower()
        _mostrar_decisao(fila.editar(item.id, motor=motor))
        return
    resposta = typer.prompt("Novo texto (ou caminho de um arquivo .txt/.md)")
    caminho = Path(resposta.strip().strip('"'))
    texto = caminho.read_text(encoding="utf-8") if caminho.suffix.lower() in {".txt", ".md"} and caminho.is_file() else resposta
    _mostrar_decisao(fila.editar(item.id, texto=texto))


def _talvez_aplicar(entrada_id: str) -> None:
    """Depois de aprovar uma alteração do LinkedIn, registra a aplicação se o usuário já colou."""
    from .cli import _auditar_linkedin
    from .linkedin.estado import carregar_estado, carregar_log, marcar_aplicado, salvar_estado, salvar_log

    if not typer.confirm("Já colou e salvou no LinkedIn?", default=False):
        return
    estado, log = carregar_estado(), carregar_log()
    entrada = marcar_aplicado(log, estado, entrada_id)
    salvar_log(log)
    salvar_estado(estado)
    _auditar_linkedin(entrada)
    console.print("[green]Aplicação registrada e auditada.[/green]")


@fila_app.command("aprovar")
def fila_aprovar(
    id_: str = typer.Argument(..., metavar="ID"),
    motor: str | None = typer.Option(None, "--motor", help="Só para uso de IA: autorizar já trocando de motor."),
) -> None:
    """Aprova um item da fila."""
    from .operacao import fila

    try:
        _mostrar_decisao(fila.aprovar(id_, motor=motor))
    except ValueError as erro:
        _sair_com_erro(erro)


@fila_app.command("rejeitar")
def fila_rejeitar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Rejeita um item da fila: nada é gerado, publicado ou alterado."""
    from .operacao import fila

    try:
        _mostrar_decisao(fila.rejeitar(id_))
    except ValueError as erro:
        _sair_com_erro(erro)


@fila_app.command("editar")
def fila_editar(
    id_: str = typer.Argument(..., metavar="ID"),
    texto: str | None = typer.Option(None, "--texto"),
    arquivo: Path | None = typer.Option(None, "--arquivo", exists=True, readable=True),
    motor: str | None = typer.Option(None, "--motor", help="Uso de IA: trocar o motor. Texto: motor que o escreveu."),
) -> None:
    """Edita um item; ele continua na fila esperando aprovação."""
    from .operacao import fila

    novo = arquivo.read_text(encoding="utf-8") if arquivo else texto
    try:
        _mostrar_decisao(fila.editar(id_, texto=novo, motor=motor))
    except ValueError as erro:
        _sair_com_erro(erro)


# ---------------------------------------------------------------- RF-OP-06

@auditoria_app.callback()
def auditoria_principal(
    ctx: typer.Context,
    plataforma: str | None = typer.Option(None, "--plataforma"),
) -> None:
    """Lista as ações externas registradas."""
    if ctx.invoked_subcommand is not None:
        return
    from .operacao.auditoria import listar_acoes

    acoes = listar_acoes(plataforma)
    if not acoes:
        console.print("Nenhuma ação externa registrada.")
        return
    tabela = Table(title=f"Auditoria de ações externas ({len(acoes)})")
    for col in ("ID", "Quando", "Plataforma", "Ação", "Alvo", "Modo", "Aprovação", "Captura"):
        tabela.add_column(col, overflow="fold")
    for a in reversed(acoes):
        tabela.add_row(a.id, f"{a.quando:%d/%m/%Y %H:%M}", a.plataforma, a.acao, Text(a.alvo), a.modo,
                       Text(a.origem_aprovacao), "sim" if a.captura else "—")
    console.print(tabela)
    console.print("Detalhes com antes e depois: 'agente auditoria ver ID'.")


@auditoria_app.command("ver")
def auditoria_ver(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Mostra uma ação com antes, depois, aprovação e captura."""
    from .operacao.auditoria import listar_acoes

    acao = next((a for a in listar_acoes() if a.id == id_), None)
    if acao is None:
        _sair_com_erro(ValueError(f"Ação {id_!r} não existe na auditoria."))
    console.print(f"[bold]{escape(acao.acao)}[/bold] em {acao.plataforma} — {escape(acao.alvo)}  "
                  f"[dim]{acao.quando:%d/%m/%Y %H:%M} · modo {acao.modo} · {acao.resultado}[/dim]")
    console.print(f"Aprovação: {escape(acao.origem_aprovacao)}"
                  + (f" em {acao.aprovado_em:%d/%m/%Y %H:%M}" if acao.aprovado_em else ""))
    paineis = []
    if acao.antes is not None:
        paineis.append(Panel(Text(acao.antes or "(vazio)"), title="ANTES", border_style="red"))
    paineis.append(Panel(Text(acao.depois or "(vazio)"), title="DEPOIS", border_style="green"))
    console.print(Columns(paineis, equal=True, expand=True))
    if acao.captura:
        console.print(f"Captura de tela: {acao.captura}")


# ---------------------------------------------------------------- RF-OP-07

@saude_app.callback()
def saude_principal(ctx: typer.Context) -> None:
    """Mostra a saúde de cada adaptador."""
    if ctx.invoked_subcommand is not None:
        return
    from .operacao.saude import LIMITE_FALHAS, carregar_saude

    registro = carregar_saude()
    if not registro.adaptadores:
        console.print("Nenhum adaptador usado ainda.")
        return
    tabela = Table(title="Saúde dos adaptadores")
    for col in ("Adaptador", "Status", "Falhas seguidas", "Último sucesso", "Último erro"):
        tabela.add_column(col, overflow="fold")
    for a in registro.adaptadores.values():
        cor = {"ok": "green", "degradado": "yellow", "parado": "red"}[a.status]
        tabela.add_row(
            a.nome, f"[{cor}]{a.status}[/{cor}]", f"{a.falhas_seguidas}/{LIMITE_FALHAS}",
            f"{a.ultimo_sucesso:%d/%m/%Y %H:%M}" if a.ultimo_sucesso else "—", Text(a.ultimo_erro or ""),
        )
    console.print(tabela)
    console.print("Adaptadores parados não rodam até você conferir e reativar: 'agente saude reativar NOME'.")


@saude_app.command("reativar")
def saude_reativar(nome: str = typer.Argument(...)) -> None:
    """Reativa um adaptador parado (depois de conferir a fonte ou atualizar o agente)."""
    from .operacao.saude import carregar_saude, salvar_saude

    registro = carregar_saude()
    try:
        registro.reativar(nome)
    except ValueError as erro:
        _sair_com_erro(erro)
    salvar_saude(registro)
    console.print(f"[green]{escape(nome)} reativado.[/green] E-mails guardados serão relidos na próxima rodada.")


# ---------------------------------------------------------------- RF-OP-04

@notificacoes_app.command("teste")
def notificacoes_teste() -> None:
    """Envia uma notificação de teste pelo canal configurado."""
    from .configuracao import carregar_configuracao
    from .operacao.notificacoes import notificar

    config = carregar_configuracao()
    config.notificacao.eventos["teste"] = True
    resultado = notificar("teste", "Teste de notificação", "Se você recebeu isto, as notificações estão funcionando.", config)
    if resultado.erro:
        console.print(f"[yellow]Não enviada por {config.notificacao.canal}: {escape(resultado.erro)}[/yellow]")
    else:
        console.print(f"[green]Enviada por {resultado.canal}.[/green]")
    console.print(f"[dim]Cópia em {resultado.arquivo}[/dim]")
