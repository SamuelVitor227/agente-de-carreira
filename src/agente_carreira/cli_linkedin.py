"""LinkedIn em modo copiloto: perfil, aprovação, inglês, recomendações e publicações (RF-LI-01 a RF-LI-15)."""

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
from .cli_perfil import importar

li_app = typer.Typer(help="LinkedIn em modo copiloto (RF-LI-01 a RF-LI-15).", no_args_is_help=True)
ingles_app = typer.Typer(help="Perfil secundário em inglês (RF-LI-10).", no_args_is_help=True)
post_app = typer.Typer(help="Publicações sobre projetos, publicadas só com sua aprovação (RF-LI-12).", no_args_is_help=True)
li_app.add_typer(ingles_app, name="ingles")
li_app.add_typer(post_app, name="post")
from .cli_linkedin_auto import auto_app  # noqa: E402

li_app.add_typer(auto_app, name="automatico")


# ---------------------------------------------------------------- LinkedIn (M2, copiloto)

@li_app.command("auditar")
def li_auditar() -> None:
    """Audita o perfil contra o checklist do Anexo A, pendências por impacto (RF-LI-01)."""
    from .linkedin.auditoria import auditar

    perfil = carregar_perfil()
    itens = auditar(perfil)
    pendentes = [i for i in itens if i.status == "pendente"]
    cores = {"alto": "red", "medio": "yellow", "baixo": "cyan"}
    tabela = Table(title=f"Auditoria do LinkedIn — {len(pendentes)} pendência(s) de {len(itens)} itens")
    for col in ("#", "Item", "Impacto", "Status", "Verificação do agente"):
        tabela.add_column(col, overflow="fold")
    for i in itens:
        cor = cores[i.impacto]
        tabela.add_row(str(i.numero), i.titulo, f"[{cor}]{i.impacto}[/{cor}]", i.status, i.verificacao or "")
    console.print(tabela)
    console.print("Marque itens aplicados com 'agente li marcar N' (ou 'agente li marcar N --status nao_se_aplica').")


@li_app.command("marcar")
def li_marcar(
    numero: int = typer.Argument(...),
    status: str = typer.Option("feito", "--status", help="feito, pendente ou nao_se_aplica"),
) -> None:
    """Atualiza o status de um item do checklist do Anexo A."""
    from .linkedin.auditoria import marcar

    if status not in {"feito", "pendente", "nao_se_aplica"}:
        console.print(f"[red]Status inválido: {status}.[/red]")
        raise typer.Exit(1)
    try:
        marcar(numero, status)  # type: ignore[arg-type]
    except ValueError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Item {numero} → {status}.[/green]")


@li_app.command("titulo")
def li_titulo(
    foco: str = typer.Option("backend-dotnet", "--foco"),
    cargo: str | None = typer.Option(None, "--cargo", help="Cargo-alvo; padrão: pergunta com base no objetivo."),
) -> None:
    """Gera 3 opções de título de até 220 caracteres (RF-LI-02)."""
    from .linkedin.textos import gerar_titulos

    perfil = carregar_perfil()
    cargo_alvo = cargo or typer.prompt("Cargo-alvo do título", default=perfil.objetivo or "")
    if not cargo_alvo.strip():
        console.print("[red]Informe o cargo-alvo.[/red]")
        raise typer.Exit(1)
    for i, opcao in enumerate(gerar_titulos(perfil, foco, cargo_alvo.strip()), 1):
        ok_limite = "[green]ok[/green]" if opcao.dentro_do_limite else "[red]estourou[/red]"
        ok_60 = "[green]sim[/green]" if opcao.essencial_nos_primeiros_60 else "[yellow]não[/yellow]"
        console.print(f"\n[bold]Opção {i}[/bold] ({opcao.caracteres}/220 {ok_limite}; essencial nos 60 primeiros: {ok_60})")
        console.print(f"  {opcao.texto}")
    console.print("\nCopie a opção escolhida e cole no título do LinkedIn (copiloto, RN-04).")


@li_app.command("sobre")
def li_sobre(foco: str = typer.Option("backend-dotnet", "--foco")) -> None:
    """Gera a seção Sobre com até 2.600 caracteres (RF-LI-03)."""
    from .linkedin.textos import gerar_sobre

    perfil = carregar_perfil()
    sobre = gerar_sobre(perfil, foco)
    if not sobre.texto:
        console.print("[yellow]Perfil sem material para o Sobre (preencha resumo, projetos, formação).[/yellow]")
        raise typer.Exit(1)
    console.print(Panel(sobre.texto, title=f"Sobre — {sobre.caracteres}/2600 caracteres", border_style="cyan"))
    console.print(f"[bold]Abertura (antes do 'ver mais', ~300):[/bold] {sobre.abertura}")
    if not sobre.dentro_do_limite:
        console.print("[red]Acima do limite — enxugue o resumo ou os projetos.[/red]")
    console.print("Versão em inglês: gere o prompt de tradução com 'agente cv reescrever --motor claude' e revise (RF-IA-02).")


@li_app.command("experiencias")
def li_experiencias() -> None:
    """Gera o texto de cada cargo (até 2.000 caracteres), mesmos cargos e datas do CV (RF-LI-04)."""
    from .linkedin.textos import gerar_experiencias

    perfil = carregar_perfil()
    blocos = gerar_experiencias(perfil)
    if not blocos:
        console.print("Nenhuma experiência registrada.")
        return
    for b in blocos:
        ok = "[green]ok[/green]" if b.dentro_do_limite else "[red]estourou[/red]"
        console.print(Panel(b.texto, title=f"{b.cargo} — {b.empresa} ({b.periodo}) · {b.caracteres}/2000 {ok}",
                            border_style="cyan"))
    console.print("Cole cada bloco no cargo correspondente; cargos e datas devem bater com o CV (RF-LI-04).")


@li_app.command("competencias")
def li_competencias(
    foco: str | None = typer.Option(None, "--foco"),
    limite: int = typer.Option(30, "--limite"),
) -> None:
    """Sugere competências priorizadas pelas vagas-alvo, com vínculos (RF-LI-05)."""
    from .analise.termos import extrair_termos
    from .linkedin.textos import sugerir_competencias

    perfil = carregar_perfil()
    vagas = conjunto_de_analise(carregar_vagas(), foco=foco, limite=limite)
    termos = extrair_termos(vagas)
    sugeridas = sugerir_competencias(perfil, termos)
    if not sugeridas:
        console.print("Nenhuma competência registrada no perfil.")
        return
    tabela = Table(title=f"Competências para o LinkedIn (limite da seção: 100; vinculadas não contam)")
    for col in ("Competência", "Vagas", "Vincular a"):
        tabela.add_column(col, overflow="fold")
    for s in sugeridas:
        tabela.add_row(s.nome, str(s.vagas_em_que_aparece) if s.vagas_em_que_aparece else "", "; ".join(s.vinculos))
    console.print(tabela)


@li_app.command("open-to-work")
def li_open_to_work() -> None:
    """Prepara o pacote do Open to Work (RF-LI-06)."""
    from .linkedin.configuracoes import (
        ARQUIVO_OPEN_TO_WORK,
        CARGOS_POR_FOCO,
        montar_open_to_work,
        passos_open_to_work,
        salvar_pacote,
    )

    perfil = carregar_perfil()
    sugestao = ", ".join(CARGOS_POR_FOCO["backend-dotnet"])
    cargos = _lista(typer.prompt(f"Cargos (até 5, separados por vírgula)", default=sugestao))
    visibilidade = typer.prompt(
        "Visibilidade (so_recrutadores, todos_os_membros ou decidir_ao_aplicar)",
        default="decidir_ao_aplicar",
    )
    try:
        pacote = montar_open_to_work(perfil, cargos, visibilidade)
    except Exception as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(1)
    caminho = salvar_pacote(pacote, ARQUIVO_OPEN_TO_WORK)
    console.print("[bold]Passo a passo (você aplica — copiloto):[/bold]")
    for i, passo in enumerate(passos_open_to_work(pacote), 1):
        console.print(f"  {i}. {passo}")
    console.print(f"[green]Pacote salvo em[/green] {caminho}")


@li_app.command("ajustes")
def li_ajustes() -> None:
    """Pacote de ajustes de perfil: localização, URL, contato, Em destaque, certificações, idiomas (RF-LI-07)."""
    from .linkedin.configuracoes import pacote_ajustes

    perfil = carregar_perfil()
    tabela = Table(title="Ajustes de perfil preparados (RF-LI-07)")
    tabela.add_column("Campo")
    tabela.add_column("Valor preparado", overflow="fold")
    for campo, valor in pacote_ajustes(perfil):
        tabela.add_row(campo, valor)
    console.print(tabela)
    console.print("Aplique campo a campo no LinkedIn; itens PENDENTES pedem dado no perfil-mestre.")


@li_app.command("alertas")
def li_alertas(
    focos: str = typer.Option("backend-dotnet", "--focos", help="Focos separados por vírgula."),
) -> None:
    """Gera até 20 alertas de vagas diários por e-mail (RF-LI-09)."""
    from .linkedin.configuracoes import ARQUIVO_ALERTAS, gerar_alertas, salvar_pacote

    perfil = carregar_perfil()
    pacote = gerar_alertas(perfil, _lista(focos))
    if not pacote.alertas:
        console.print("[yellow]Nenhum alerta gerado — confira os focos e a cidade do perfil.[/yellow]")
        raise typer.Exit(1)
    caminho = salvar_pacote(pacote, ARQUIVO_ALERTAS)
    tabela = Table(title=f"Alertas de vagas ({len(pacote.alertas)}/20) — diários, por e-mail")
    for col in ("#", "Busca", "Local"):
        tabela.add_column(col)
    for i, a in enumerate(pacote.alertas, 1):
        tabela.add_row(str(i), a.termos, a.local)
    console.print(tabela)
    console.print(f"Crie cada alerta na busca de vagas do LinkedIn (sino > criar alerta). [green]Pacote salvo em[/green] {caminho}")
    console.print("Os e-mails desses alertas alimentam o resumo diário do M4 (RF-LI-09 → RF-VG).")


@li_app.command("rodada")
def li_rodada() -> None:
    """Roteiro de uma rodada de edições, com o desligar/religar do compartilhamento (RF-LI-08)."""
    from .linkedin.auditoria import auditar
    from .linkedin.configuracoes import passos_rodada

    perfil = carregar_perfil()
    pendentes_altas = [
        f"{i.numero}. {i.titulo}" for i in auditar(perfil) if i.status == "pendente" and i.impacto == "alto"
    ]
    console.print("[bold]Rodada de edições do LinkedIn (copiloto):[/bold]")
    for i, passo in enumerate(passos_rodada(pendentes_altas), 1):
        console.print(f"  {i}. {passo}")


# ---------------------------------------------------------------- LinkedIn: aprovação, log e reauditoria

def _cargo_alvo(perfil: PerfilMestre, cargo: str | None) -> str:
    cargo_alvo = (cargo or typer.prompt("Cargo-alvo do título", default=perfil.objetivo or "")).strip()
    if not cargo_alvo:
        console.print("[red]Informe o cargo-alvo.[/red]")
        raise typer.Exit(1)
    return cargo_alvo


def _ler_texto_editado(resposta: str) -> str:
    """Aceita o texto digitado ou o caminho de um arquivo .txt/.md com o texto."""
    caminho = Path(resposta.strip().strip('"'))
    try:
        if caminho.suffix.lower() in {".txt", ".md"} and caminho.is_file():
            return caminho.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return resposta.strip()


def _curto(texto: str | None, tamanho: int = 40) -> str:
    texto = (texto or "").replace("\n", " ")
    return texto if len(texto) <= tamanho else texto[: tamanho - 1] + "…"


def _auditar_linkedin(entrada, captura: Path | None = None) -> None:
    """RF-OP-06: toda alteração aplicada no LinkedIn vai para o log de auditoria, com a autoria do texto (RF-IA-06)."""
    from .ia import autoria
    from .linkedin.propostas import rotulo_do_campo
    from .operacao.auditoria import registrar_acao

    registrar_acao(
        plataforma="linkedin",
        acao="reverter campo" if entrada.tipo == "reversao" else "alterar campo",
        alvo=rotulo_do_campo(entrada.campo), antes=entrada.anterior, depois=entrada.novo, modo="copiloto",
        aprovado_em=entrada.aprovado_em, origem_aprovacao=f"log LinkedIn {entrada.id}", captura=captura,
        autoria=autoria(entrada.motor),
    )


def _fluxo_aprovacao(propostas, motor: str | None = None, tarefa_id: str | None = None) -> None:
    """Antes × depois com contagem de caracteres; aprovar, editar, rejeitar ou pular campo a campo (RF-LI-13).

    Com tarefa_id, cada decisão confirma um passo da tarefa: interromper (Ctrl+C) pausa a rodada,
    que depois continua do primeiro campo ainda sem decisão (RF-OP-03).
    """
    from .linkedin.estado import (
        carregar_estado,
        carregar_log,
        marcar_aplicado,
        registrar_aprovacao,
        salvar_estado,
        salvar_log,
    )
    from .ia import autoria
    from .linkedin.propostas import limite_do_campo, validar_texto
    from .operacao.tarefas import carregar_tarefas, confirmar_passo, pausar, salvar_tarefas

    estado = carregar_estado()
    log = carregar_log()
    tarefas = carregar_tarefas() if tarefa_id else None
    tarefa = tarefas.buscar(tarefa_id) if tarefas and tarefa_id else None

    def concluir_passo(campo: str, pulado: bool = False) -> None:
        if tarefa is not None:
            confirmar_passo(tarefa, campo, pulado=pulado)
            salvar_tarefas(tarefas)

    aprovadas = aplicadas = rejeitadas = 0
    try:
        for i, p in enumerate(propostas, 1):
            limite = limite_do_campo(p.campo)
            sufixo = f"/{limite}" if limite else ""
            antes = p.anterior or ""
            console.print(Panel(
                Text(antes) if antes else Text("(vazio ou desconhecido)", style="dim"),
                title=f"{i}/{len(propostas)} · {escape(p.rotulo)} — ANTES · {len(antes)}{sufixo} caracteres",
                border_style="red",
            ))
            novo, autor = p.novo, motor
            while True:
                problemas = validar_texto(p.campo, novo)
                console.print(Panel(
                    Text(novo), title=f"DEPOIS · {len(novo)}{sufixo} caracteres · escrito por: {autoria(autor)}",
                    border_style="yellow" if problemas else "green",
                ))
                for problema in problemas:
                    console.print(f"  [red]• {escape(problema)}[/red]")
                escolha = typer.prompt("[a]provar, [e]ditar, [r]ejeitar ou [p]ular").lstrip("﻿").strip().lower()[:1]
                if escolha not in {"a", "e", "r", "p"}:
                    console.print("Opção inválida.")
                    continue
                if escolha == "e":
                    novo = _ler_texto_editado(typer.prompt("Novo texto (ou caminho de um arquivo .txt/.md)"))
                    autor = "usuario"  # RF-IA-06: o texto editado passa a ser seu
                    continue
                if escolha == "a" and problemas:
                    console.print("[red]Não dá para aprovar com problemas pendentes — edite o texto.[/red]")
                    continue
                break

            if escolha == "r":
                rejeitadas += 1
                concluir_passo(p.campo)
                continue
            if escolha == "p":
                concluir_passo(p.campo, pulado=True)
                continue

            entrada = registrar_aprovacao(log, p.campo, p.anterior, novo, motor=autor)
            salvar_log(log)
            aprovadas += 1
            concluir_passo(p.campo)
            console.print(f"[green]Aprovado (log {entrada.id}).[/green] Copie o texto abaixo e cole no LinkedIn:")
            console.print(novo, markup=False, highlight=False)
            if typer.confirm("Já colou e salvou este campo no LinkedIn?", default=False):
                marcar_aplicado(log, estado, entrada.id)
                salvar_log(log)
                salvar_estado(estado)
                _auditar_linkedin(entrada)
                aplicadas += 1
    except (KeyboardInterrupt, typer.Abort):
        if tarefa is not None and tarefa.status == "ativa":
            pausar(tarefa)
            salvar_tarefas(tarefas)
            proximo = tarefa.proximo_passo()
            onde = f" em '{escape(proximo.descricao)}'" if proximo else ""
            console.print(f"\n[yellow]Rodada pausada{onde}.[/yellow] Rode 'agente li propor' para continuar de onde parou.")
        else:
            console.print("\n[yellow]Interrompido.[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[bold]Resumo:[/bold] {aprovadas} aprovada(s), {aplicadas} aplicada(s), {rejeitadas} rejeitada(s).")
    if aprovadas > aplicadas:
        console.print(
            f"{aprovadas - aplicadas} aprovada(s) aguardando aplicação: depois de colar no LinkedIn, rode "
            "'agente li aplicado <id>' (lista em 'agente li log --pendentes')."
        )


@li_app.command("sincronizar")
def li_sincronizar(
    arquivo: Path = typer.Argument(..., exists=True, readable=True, help="ZIP de 'Obter uma cópia dos seus dados' do LinkedIn."),
) -> None:
    """Atualiza o estado conhecido do LinkedIn pela exportação oficial (base do antes × depois)."""
    import zipfile

    from .linkedin.estado import carregar_estado, salvar_estado, sincronizar_exportacao
    from .linkedin.propostas import rotulo_do_campo

    estado = carregar_estado()
    try:
        lidos = sincronizar_exportacao(estado, arquivo)
    except zipfile.BadZipFile:
        console.print("[red]O arquivo não é um ZIP válido da exportação do LinkedIn.[/red]")
        raise typer.Exit(1)
    salvar_estado(estado)
    console.print(f"[green]Estado do LinkedIn sincronizado:[/green] {len(lidos)} campo(s) lido(s).")
    for campo in lidos:
        console.print(f"  • {escape(rotulo_do_campo(campo))}")


@li_app.command("conectar")
def li_conectar(
    arquivo: Path = typer.Argument(..., exists=True, readable=True, help="ZIP de 'Obter uma cópia dos seus dados' do LinkedIn."),
) -> None:
    """Traz seus dados do LinkedIn pela exportação oficial: perfil-mestre (com confirmação) e estado atual do LinkedIn.

    O agente não faz login no LinkedIn (RN-04): tudo vem do ZIP que você baixa.
    """
    if arquivo.suffix.lower() != ".zip":
        console.print("[red]Use o ZIP da exportação do LinkedIn (Configurações e privacidade → Privacidade de dados → "
                      "Obter uma cópia dos seus dados).[/red]")
        raise typer.Exit(1)
    console.print("[bold]1/2 · Dados do perfil[/bold] (confira tudo antes de aplicar)")
    try:
        importar(arquivo, confirmar=False)
    except typer.Exit:
        pass  # recusou ou não havia nada novo: o estado do LinkedIn ainda vale a pena registrar
    console.print("\n[bold]2/2 · Estado atual do LinkedIn[/bold] (base para o antes × depois das propostas)")
    li_sincronizar(arquivo)
    console.print("\nPronto. Próximos passos: 'agente li auditar' e 'agente li propor'.")


@li_app.command("propor")
def li_propor(
    foco: str = typer.Option("backend-dotnet", "--foco"),
    cargo: str | None = typer.Option(None, "--cargo", help="Cargo-alvo do título."),
    opcao: int = typer.Option(1, "--opcao", help="Qual das opções de 'agente li titulo' usar."),
    fila: bool = typer.Option(False, "--fila", help="Manda as alterações para a fila de aprovações em vez de decidir agora (RF-OP-05)."),
) -> None:
    """Propõe as alterações com antes × depois e aprovação campo a campo (RF-LI-13, RF-LI-14, RF-OP-03)."""
    from .linkedin.estado import carregar_estado, carregar_log, pendentes_de_aplicacao
    from .linkedin.pendentes import carregar_pendentes, enfileirar, salvar_pendentes
    from .linkedin.propostas import gerar_propostas
    from .operacao.tarefas import cancelar, carregar_tarefas, confirmar_passo, criar_tarefa, retomar, salvar_tarefas

    perfil = carregar_perfil()
    estado = carregar_estado()
    cargo_alvo = _cargo_alvo(perfil, cargo)
    try:
        propostas = gerar_propostas(perfil, estado, foco, cargo_alvo, opcao_titulo=opcao)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)

    # Campos já aprovados (aguardando aplicação) ou já na fila não são propostos de novo.
    pendentes = carregar_pendentes()
    em_andamento = {e.campo for e in pendentes_de_aplicacao(carregar_log())} | pendentes.campos()
    ja_tratados = [p for p in propostas if p.campo in em_andamento]
    propostas = [p for p in propostas if p.campo not in em_andamento]
    if ja_tratados:
        console.print(f"[dim]{len(ja_tratados)} campo(s) já aprovados ou na fila ficaram de fora.[/dim]")
    if not propostas:
        console.print("[green]Nada a propor: o LinkedIn conhecido já bate com o perfil-mestre.[/green]")
        return

    if fila:
        novas = enfileirar(pendentes, propostas)
        salvar_pendentes(pendentes)
        console.print(f"[green]{novas} alteração(ões) enviadas para a fila de aprovações.[/green] Revise com 'agente fila revisar'.")
        return

    tarefas = carregar_tarefas()
    tarefa = tarefas.aberta_do_tipo("linkedin-rodada")
    if tarefa is not None:
        proximo = tarefa.proximo_passo()
        continuar = proximo is not None and typer.confirm(
            f"Há uma rodada de edições {tarefa.status} ({tarefa.progresso}). Continuar a partir de '{proximo.descricao}'?",
            default=True,
        )
        if continuar:
            if tarefa.status != "ativa":
                retomar(tarefa)
            restantes = set(tarefa.pendentes())
            propostas = [p for p in propostas if p.campo in restantes]
            for campo in restantes - {p.campo for p in propostas}:
                confirmar_passo(tarefa, campo, pulado=True)  # já não difere do LinkedIn
        else:
            cancelar(tarefa)
            tarefa = None
    if tarefa is None:
        tarefa = criar_tarefa(
            tarefas, "linkedin-rodada", f"Rodada de edições do LinkedIn ({len(propostas)} campo(s))",
            [(p.campo, p.rotulo) for p in propostas],
        )
    salvar_tarefas(tarefas)
    if not propostas:
        console.print("[green]Nada restante nesta rodada.[/green]")
        return

    if estado.sincronizado_em is None:
        console.print("[yellow]Estado do LinkedIn nunca sincronizado: o 'antes' pode estar vazio. "
                      "Para o antes real, rode 'agente li sincronizar <exportação.zip>'.[/yellow]")
    console.print("[yellow]Lembrete (RF-LI-08): desligue 'Compartilhar atualizações do perfil' antes de uma rodada grande de edições.[/yellow]")
    _fluxo_aprovacao(propostas, tarefa_id=tarefa.id)


@li_app.command("log")
def li_log(
    pendentes: bool = typer.Option(False, "--pendentes", help="Só as aprovadas que ainda não foram aplicadas."),
) -> None:
    """Log de alterações do LinkedIn: data, campo, valor anterior e novo (RF-LI-14)."""
    from .linkedin.estado import carregar_log
    from .linkedin.propostas import rotulo_do_campo

    entradas = [e for e in carregar_log().entradas if not pendentes or e.status == "aprovado"]
    if not entradas:
        console.print("Nenhuma entrada no log." if not pendentes else "Nenhuma alteração aguardando aplicação.")
        return
    tabela = Table(title=f"Log do LinkedIn ({len(entradas)})")
    for col in ("ID", "Aprovado em", "Campo", "Tipo", "Status", "Antes → depois"):
        tabela.add_column(col, overflow="fold")
    from .ia import autoria

    for e in reversed(entradas):
        status = f"{e.status} · {autoria(e.motor)}"
        tabela.add_row(
            e.id, f"{e.aprovado_em:%d/%m/%Y %H:%M}", Text(rotulo_do_campo(e.campo)), e.tipo, status,
            Text(f"{_curto(e.anterior) or '(vazio)'} → {_curto(e.novo) or '(vazio)'}"),
        )
    console.print(tabela)
    console.print("Reverta uma alteração aplicada com 'agente li reverter <id>'.")


@li_app.command("aplicado")
def li_aplicado(
    id_: str = typer.Argument(..., metavar="ID"),
    captura: Path | None = typer.Option(None, "--captura", exists=True, readable=True,
                                        help="Captura de tela do campo salvo (vai para a auditoria)."),
) -> None:
    """Marca como aplicada uma alteração aprovada que você já colou no LinkedIn (RF-LI-14, RF-OP-06)."""
    from .linkedin.estado import carregar_estado, carregar_log, marcar_aplicado, salvar_estado, salvar_log

    estado, log = carregar_estado(), carregar_log()
    try:
        entrada = marcar_aplicado(log, estado, id_)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_log(log)
    salvar_estado(estado)
    _auditar_linkedin(entrada, captura)
    console.print(f"[green]Aplicada:[/green] {escape(entrada.campo)} ({entrada.id}). Registrada na auditoria.")


@li_app.command("reverter")
def li_reverter(
    id_: str = typer.Argument(..., metavar="ID"),
    captura: Path | None = typer.Option(None, "--captura", exists=True, readable=True,
                                        help="Captura de tela do campo revertido (vai para a auditoria)."),
) -> None:
    """Reverte uma alteração aplicada, com nova aprovação (RF-LI-14)."""
    from .linkedin.estado import carregar_estado, carregar_log, marcar_aplicado, preparar_reversao, salvar_estado, salvar_log
    from .linkedin.propostas import rotulo_do_campo

    estado, log = carregar_estado(), carregar_log()
    try:
        reversao = preparar_reversao(log, id_)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    rotulo = rotulo_do_campo(reversao.campo)
    console.print(Panel(Text(reversao.anterior or ""), title=f"{escape(rotulo)} — ATUAL · {len(reversao.anterior or '')} caracteres", border_style="red"))
    console.print(Panel(Text(reversao.novo) if reversao.novo else Text("(campo vazio)", style="dim"),
                        title=f"VOLTA PARA · {len(reversao.novo)} caracteres", border_style="green"))
    if not typer.confirm("Aprovar a reversão?"):
        console.print("Nada foi alterado.")
        raise typer.Exit(0)
    salvar_log(log)
    if reversao.novo:
        console.print("Cole o valor abaixo no LinkedIn:")
        console.print(reversao.novo, markup=False, highlight=False)
    else:
        console.print("Apague o conteúdo deste campo no LinkedIn.")
    if typer.confirm("Já aplicou a reversão no LinkedIn?", default=False):
        marcar_aplicado(log, estado, reversao.id)
        salvar_log(log)
        salvar_estado(estado)
        _auditar_linkedin(reversao, captura)
        console.print(f"[green]Reversão aplicada (log {reversao.id}).[/green]")
    else:
        console.print(f"Reversão aprovada; marque depois com 'agente li aplicado {reversao.id}'.")


@li_app.command("reauditar")
def li_reauditar(
    verificar: bool = typer.Option(False, "--verificar", help="Só verifica se a reauditoria está pendente (sai com 1 se estiver)."),
) -> None:
    """Reauditoria a cada 30 dias ou quando o perfil-mestre mudar, com divergências LinkedIn × CV (RF-LI-15)."""
    from .linkedin.auditoria import auditar
    from .linkedin.estado import (
        carregar_estado,
        divergencias,
        reauditoria_pendente,
        registrar_auditoria,
        salvar_estado,
    )

    perfil = carregar_perfil()
    estado = carregar_estado()
    motivo = reauditoria_pendente(estado, perfil)
    if verificar:
        if motivo:
            console.print(f"[yellow]Reauditoria pendente:[/yellow] {escape(motivo)}. Rode 'agente li reauditar'.")
            raise typer.Exit(1)
        console.print("[green]Auditoria do LinkedIn em dia.[/green]")
        raise typer.Exit(0)

    if motivo:
        console.print(f"[yellow]Motivo da reauditoria:[/yellow] {escape(motivo)}.")
    achados = divergencias(estado, perfil)
    if achados:
        tabela = Table(title=f"Divergências LinkedIn × CV ({len(achados)})")
        tabela.add_column("Tipo")
        tabela.add_column("Divergência", overflow="fold")
        for d in achados:
            tabela.add_row(d.tipo, Text(d.mensagem))
        console.print(tabela)
    else:
        console.print("[green]Nenhuma divergência entre o LinkedIn conhecido e o CV.[/green]")
    if estado.sincronizado_em:
        console.print(f"[dim]Estado do LinkedIn sincronizado em {estado.sincronizado_em:%d/%m/%Y}.[/dim]")
    pendentes = [i for i in auditar(perfil) if i.status == "pendente"]
    console.print(f"Checklist do Anexo A: {len(pendentes)} pendência(s) — detalhes em 'agente li auditar'.")
    registrar_auditoria(estado, perfil)
    salvar_estado(estado)
    console.print("[green]Auditoria registrada.[/green] Próxima: em até 30 dias ou quando o perfil-mestre mudar.")


# ---------------------------------------------------------------- LinkedIn: perfil em inglês (RF-LI-10)

@ingles_app.command("preparar")
def ingles_preparar(
    foco: str = typer.Option("backend-dotnet", "--foco"),
    cargo: str | None = typer.Option(None, "--cargo", help="Cargo-alvo do título."),
    opcao: int = typer.Option(1, "--opcao", help="Qual das opções de 'agente li titulo' traduzir."),
    motor: str | None = typer.Option(None, "--motor", help="claude, gemini ou local; padrão: o configurado para a tarefa."),
) -> None:
    """Monta o pacote de tradução do perfil para inglês, com autorização de IA (RF-LI-10, RF-IA-01 a RF-IA-05)."""
    from .linkedin.ingles import dados_enviados, montar_prompt, textos_fonte

    perfil = carregar_perfil()
    fontes = textos_fonte(perfil, foco, _cargo_alvo(perfil, cargo), opcao_titulo=opcao)
    if not fontes:
        console.print("[yellow]Perfil sem material para traduzir (título, Sobre ou experiências).[/yellow]")
        raise typer.Exit(1)
    uso = _usar_ia(
        perfil, "traducao-linkedin", motor, dados_enviados(fontes),
        lambda m: montar_prompt(fontes, m),
        lambda m: f"prompt-linkedin-en-{m}.md",
    )
    if uso is None:
        raise typer.Exit(0)
    console.print(
        f"Cole no {uso.motor.capitalize()}, salve a resposta num arquivo .md e rode: "
        f"agente li ingles registrar <resposta.md> --motor {uso.motor}"
    )


@ingles_app.command("registrar")
def ingles_registrar(
    arquivo: Path = typer.Argument(..., exists=True, readable=True, help="Resposta do motor com as linhas '### CAMPO: en:...'."),
    motor: str = typer.Option(..., "--motor", help="Motor que fez a tradução (claude ou gemini)."),
) -> None:
    """Traz a tradução de volta e aprova campo a campo antes de colar no perfil em inglês (RF-LI-10, RF-LI-13)."""
    from .linkedin.estado import carregar_estado
    from .linkedin.ingles import PASSOS_PERFIL_INGLES, ler_resposta
    from .linkedin.propostas import propostas_de_textos

    from .ia import carregar_usos, registrar_resultado, salvar_usos

    conteudo = arquivo.read_text(encoding="utf-8")
    if _checar_recusa(conteudo, "traducao-linkedin", motor):
        raise typer.Exit(0)
    textos = ler_resposta(conteudo)
    if not textos:
        console.print("[red]Nenhum campo reconhecido — a resposta precisa manter as linhas '### CAMPO: en:...'.[/red]")
        raise typer.Exit(1)
    usos = carregar_usos()
    if registrar_resultado(usos, "traducao-linkedin", motor, f"resposta registrada: {len(textos)} campo(s) traduzido(s)"):
        salvar_usos(usos)
    propostas = propostas_de_textos(carregar_estado(), textos)
    if not propostas:
        console.print("[green]Todos os campos já estão iguais ao perfil em inglês conhecido.[/green]")
        return
    console.print("[bold]Como criar ou atualizar o perfil em inglês:[/bold]")
    for i, passo in enumerate(PASSOS_PERFIL_INGLES, 1):
        console.print(f"  {i}. {passo}")
    _fluxo_aprovacao(propostas, motor=motor)


# ---------------------------------------------------------------- LinkedIn: recomendação e convite (RF-LI-11)

@li_app.command("recomendacao")
def li_recomendacao(
    nome: str = typer.Option(..., "--nome", help="Como chamar a pessoa (fica só na tela, não é salvo)."),
    relacao: str = typer.Option(..., "--relacao", help="orientador, professor ou colega"),
    contexto: str = typer.Option(..., "--contexto", help="Ex.: 'o TCC sobre recomendação de vagas'"),
) -> None:
    """Rascunho de pedido de recomendação; o envio é manual (RF-LI-11)."""
    from .linkedin.mensagens import FRASE_RELACAO, rascunho_recomendacao

    if relacao not in FRASE_RELACAO:
        console.print(f"[red]Relação inválida: {escape(relacao)}. Use: {', '.join(FRASE_RELACAO)}.[/red]")
        raise typer.Exit(1)
    perfil = carregar_perfil()
    pontos: list[str] = []
    if perfil.projetos:
        for i, p in enumerate(perfil.projetos, 1):
            console.print(f"  {i}. {escape(p.nome)}")
        escolha = typer.prompt("Projetos que a pessoa acompanhou (números separados por vírgula; vazio = nenhum)",
                               default="", show_default=False)
        for parte in _lista(escolha):
            if not parte.isdigit() or not 1 <= int(parte) <= len(perfil.projetos):
                console.print(f"[red]Projeto {escape(parte)} não existe.[/red]")
                raise typer.Exit(1)
            proj = perfil.projetos[int(parte) - 1]
            pontos.append(proj.nome + (f": {proj.descricao}" if proj.descricao else ""))
    texto = rascunho_recomendacao(perfil, nome, relacao, contexto, pontos)  # type: ignore[arg-type]
    console.print(Panel(Text(texto), title=f"Pedido de recomendação · {len(texto)} caracteres", border_style="cyan"))
    console.print("Revise, personalize e envie você mesmo pelo LinkedIn (RN-04, RN-11). O rascunho não é salvo.")


@li_app.command("convite")
def li_convite(
    nome: str = typer.Option(..., "--nome", help="Como chamar a pessoa (não é salvo)."),
    motivo: str = typer.Option(..., "--motivo", help="Por que conectar, em uma frase."),
) -> None:
    """Nota de convite com até 300 caracteres; o envio é manual (RF-LI-11)."""
    from .linkedin.mensagens import rascunho_convite, validar_convite

    texto = rascunho_convite(carregar_perfil(), nome, motivo)
    problemas = validar_convite(texto)
    console.print(Panel(Text(texto), title=f"Nota de convite · {len(texto)}/300 caracteres",
                        border_style="red" if problemas else "cyan"))
    for problema in problemas:
        console.print(f"[red]{escape(problema)}[/red]")
    if problemas:
        raise typer.Exit(1)
    console.print("Copie e envie você mesmo junto do convite (RN-04, RN-11). A nota não é salva.")


# ---------------------------------------------------------------- LinkedIn: publicações (RF-LI-12)

@li_app.command("pauta")
def li_pauta(
    sem_github: bool = typer.Option(False, "--sem-github", help="Usa só os projetos do perfil-mestre."),
) -> None:
    """Pauta de publicações a partir dos projetos do perfil e dos repositórios públicos do GitHub (RF-LI-12)."""
    from .configuracao import carregar_configuracao
    from .linkedin.github import GitHubIndisponivel, listar_repositorios
    from .linkedin.publicacoes import montar_pauta, salvar_pauta
    from .operacao.saude import carregar_saude, salvar_saude

    perfil = carregar_perfil()
    central = carregar_configuracao()
    if not sem_github and (central.somente_sugestao or central.modos_plataforma.get("github") == "desligado"):
        console.print("[yellow]Modo somente sugestão ou GitHub desligado: pauta só com o perfil-mestre (RF-OP-02).[/yellow]")
        sem_github = True
    repos = []
    if not sem_github:
        saude = carregar_saude()
        if not saude.pode_usar("github"):
            console.print("[yellow]Leitor do GitHub parado após falhas (agente saude reativar github); pauta só com o perfil-mestre.[/yellow]")
        else:
            try:
                repos = listar_repositorios()
                saude.sucesso("github")
            except GitHubIndisponivel as erro:
                saude.falha("github", str(erro))
                console.print(f"[yellow]GitHub indisponível ({escape(str(erro))}); pauta só com o perfil-mestre.[/yellow]")
            salvar_saude(saude)
    pauta = montar_pauta(perfil, repos)
    if not pauta.itens:
        console.print("[yellow]Nenhum projeto no perfil-mestre nem repositório público no GitHub.[/yellow]")
        raise typer.Exit(1)
    salvar_pauta(pauta)
    tabela = Table(title=f"Pauta de publicações ({len(pauta.itens)})")
    for col in ("#", "Projeto", "Tipo", "Origem", "Tecnologias", "Atualizado"):
        tabela.add_column(col, overflow="fold")
    for i, item in enumerate(pauta.itens, 1):
        tabela.add_row(
            str(i), Text(item.titulo), item.tipo, item.origem, Text(", ".join(item.tecnologias)),
            f"{item.atualizado_em:%d/%m/%Y}" if item.atualizado_em else "",
        )
    console.print(tabela)
    console.print("Gere um rascunho com 'agente li post rascunho N'. Repositórios privados e forks ficam de fora.")


@post_app.command("rascunho")
def post_rascunho(
    numero: int = typer.Argument(..., help="Número do item em 'agente li pauta'."),
    ia: bool = typer.Option(False, "--ia", help="Gera também o prompt de polimento com IA (com autorização)."),
    motor: str | None = typer.Option(None, "--motor", help="claude, gemini ou local; padrão: o configurado para a tarefa."),
) -> None:
    """Rascunho de publicação só com fatos registrados; polimento opcional com IA (RF-LI-12)."""
    from .linkedin.github import ler_readme
    from .linkedin.publicacoes import (
        Publicacao,
        carregar_pauta,
        carregar_publicacoes,
        dados_enviados_polimento,
        prompt_polimento,
        rascunho_publicacao,
        salvar_publicacoes,
    )

    pauta = carregar_pauta()
    if not pauta.itens:
        console.print("[red]Pauta vazia — rode 'agente li pauta' primeiro.[/red]")
        raise typer.Exit(1)
    if not 1 <= numero <= len(pauta.itens):
        console.print(f"[red]Item {numero} não existe na pauta ({len(pauta.itens)} itens).[/red]")
        raise typer.Exit(1)
    item = pauta.itens[numero - 1]
    texto = rascunho_publicacao(item)
    colecao = carregar_publicacoes()
    pub = Publicacao(titulo=item.titulo, texto=texto)
    colecao.itens.append(pub)
    salvar_publicacoes(colecao)
    console.print(Panel(Text(texto), title=f"Rascunho {pub.id} · {len(texto)}/3000 caracteres", border_style="cyan"))

    if ia:
        readme = ler_readme(item.url) if item.url else None
        uso = _usar_ia(
            _perfil_ou_none(), "polimento-post", motor, dados_enviados_polimento(item, readme is not None),
            lambda m: prompt_polimento(item, texto, readme, m),
            lambda m: f"posts/prompt-post-{pub.id}-{m}.md",
        )
        if uso:
            console.print(f"Salve a resposta e rode: agente li post editar {pub.id} --arquivo <resposta.md> --motor {uso.motor}")
        else:
            console.print("Fica o rascunho local, sem IA.")
    console.print(f"Para publicar: revise, aprove com 'agente li post aprovar {pub.id}' e publique você mesmo no LinkedIn.")


@post_app.command("editar")
def post_editar(
    id_: str = typer.Argument(..., metavar="ID"),
    arquivo: Path = typer.Option(..., "--arquivo", exists=True, readable=True, help="Arquivo com o novo texto do post."),
    motor: str | None = typer.Option(None, "--motor", help="Motor que escreveu o texto (claude/gemini), se houver."),
) -> None:
    """Substitui o texto do rascunho (ex.: versão polida pela IA); volta a exigir aprovação."""
    from .ia import autoria
    from .linkedin.publicacoes import carregar_publicacoes, editar_publicacao, salvar_publicacoes, validar_publicacao

    texto = arquivo.read_text(encoding="utf-8")
    if _checar_recusa(texto, "polimento-post", motor):
        raise typer.Exit(0)
    colecao = carregar_publicacoes()
    try:
        pub = colecao.buscar(id_)
        editar_publicacao(pub, texto, motor=motor or "usuario")  # sem --motor, o texto é seu (RF-IA-06)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_publicacoes(colecao)
    if motor:
        from .ia import carregar_usos, registrar_resultado, salvar_usos

        usos = carregar_usos()
        if registrar_resultado(usos, "polimento-post", motor, f"resposta registrada no post {pub.id}"):
            salvar_usos(usos)
    problemas = validar_publicacao(pub.texto)
    console.print(Panel(Text(pub.texto), title=f"{pub.id} · {len(pub.texto)}/3000 caracteres · escrito por: {autoria(pub.motor)}",
                        border_style="yellow" if problemas else "cyan"))
    for problema in problemas:
        console.print(f"[red]• {escape(problema)}[/red]")
    console.print(f"Texto atualizado (rascunho). Aprove com 'agente li post aprovar {pub.id}'.")


@post_app.command("listar")
def post_listar() -> None:
    """Lista os rascunhos e publicações, com quem escreveu cada uma (RF-IA-06)."""
    from .ia import autoria
    from .linkedin.publicacoes import carregar_publicacoes

    colecao = carregar_publicacoes()
    if not colecao.itens:
        console.print("Nenhuma publicação. Comece com 'agente li pauta'.")
        return
    tabela = Table(title=f"Publicações ({len(colecao.itens)})")
    for col in ("ID", "Projeto", "Status", "Escrito por", "Caracteres", "Criada em"):
        tabela.add_column(col)
    for p in colecao.itens:
        tabela.add_row(p.id, Text(p.titulo), p.status, autoria(p.motor), str(len(p.texto)), f"{p.criada_em:%d/%m/%Y}")
    console.print(tabela)


@post_app.command("aprovar")
def post_aprovar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Aprova uma publicação para você publicar manualmente (RN-01)."""
    from .ia import autoria
    from .linkedin.publicacoes import aprovar_publicacao, carregar_publicacoes, salvar_publicacoes, validar_publicacao

    colecao = carregar_publicacoes()
    try:
        pub = colecao.buscar(id_)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    console.print(Panel(Text(pub.texto), title=f"{escape(pub.titulo)} · {len(pub.texto)}/3000 · escrito por: {autoria(pub.motor)}",
                        border_style="cyan"))
    if problemas := validar_publicacao(pub.texto):
        for problema in problemas:
            console.print(f"[red]• {escape(problema)}[/red]")
        console.print(f"Corrija com 'agente li post editar {pub.id} --arquivo <texto.md>'.")
        raise typer.Exit(1)
    if not typer.confirm("Você aprova esta publicação para publicar no LinkedIn?"):
        console.print("Não aprovada; continua como rascunho.")
        raise typer.Exit(0)
    try:
        aprovar_publicacao(pub)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_publicacoes(colecao)
    console.print(f"[green]Aprovada.[/green] Copie o texto abaixo, publique você mesmo no LinkedIn e depois rode "
                  f"'agente li post publicado {pub.id}'.")
    console.print(pub.texto, markup=False, highlight=False)


@post_app.command("publicado")
def post_publicado(
    id_: str = typer.Argument(..., metavar="ID"),
    captura: Path | None = typer.Option(None, "--captura", exists=True, readable=True,
                                        help="Captura de tela do post publicado (vai para a auditoria)."),
) -> None:
    """Registra que você publicou uma publicação aprovada (RF-OP-06)."""
    from .linkedin.publicacoes import carregar_publicacoes, marcar_publicada, salvar_publicacoes
    from .operacao.auditoria import registrar_acao

    colecao = carregar_publicacoes()
    try:
        pub = colecao.buscar(id_)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    if not typer.confirm(f"Confirma que publicou '{pub.titulo}' no LinkedIn?"):
        raise typer.Exit(0)
    try:
        marcar_publicada(pub)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_publicacoes(colecao)
    from .ia import autoria

    registrar_acao(
        plataforma="linkedin", acao="publicar post", alvo=pub.titulo, depois=pub.texto, modo="copiloto",
        aprovado_em=pub.aprovado_em, origem_aprovacao=f"publicação {pub.id}", captura=captura,
        autoria=autoria(pub.motor),
    )
    console.print("[green]Registrada como publicada e na auditoria.[/green]")
