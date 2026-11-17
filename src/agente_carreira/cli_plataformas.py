"""CLI do M3 — cadastro e sincronização em outras plataformas (RF-PL-01 a RF-PL-11)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .storage import carregar_perfil, diretorio_dados

console = Console()
plataformas_app = typer.Typer(help="Catálogo e cadastro em outras plataformas (RF-PL-01 a RF-PL-11).",
                              invoke_without_command=True)

PASSOS_DO_USUARIO = [
    ("conta", "Crie a conta (uma só por plataforma — RN-10) e confirme o e-mail. Isso é seu (RN-03)."),
    ("login", "Faça login, 2FA e CAPTCHA. Isso é seu (RN-03)."),
    ("termos", "Leia e aceite os termos de uso. Isso é seu (RN-03)."),
]


def _sair(erro: Exception | str) -> None:
    console.print(f"[red]{escape(str(erro))}[/red]")
    raise typer.Exit(1)


def _pasta(plataforma_id: str) -> Path:
    pasta = diretorio_dados() / "plataformas" / plataforma_id.replace(".", "-")
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _exportar_cv(perfil, plataforma) -> str:
    """RF-PL-06: a variante adequada à plataforma, com as travas de veracidade (RN-02)."""
    from .analise.exportar import exportar_pdf
    from .analise.lastro import verificar_lastro
    from .analise.variantes import gerar_variante
    from .confirmacao import pendencias_na_variante

    alvo = plataforma.variante
    variante = gerar_variante(perfil, foco=alvo.foco, idioma=alvo.idioma, nivel=alvo.nivel)
    if pendencias := pendencias_na_variante(variante):
        raise ValueError(f"CV com frases [A CONFIRMAR] ({len(pendencias)}); rode 'agente confirmar'.")
    if problemas := verificar_lastro(variante, perfil):
        raise ValueError(f"CV com itens sem lastro: {'; '.join(problemas[:3])}.")
    caminho, _ = exportar_pdf(variante, _pasta(plataforma.id) / f"{variante.nome_arquivo}-{alvo.nivel}.pdf")
    return str(caminho)


def _montar_pacote(plataforma, exportar_cv: bool = True):
    from .analise.termos import extrair_termos
    from .linkedin.textos import sugerir_competencias
    from .plataformas.pacote import gerar_pacote
    from .respostas import carregar_respostas
    from .vagas import carregar_vagas

    perfil = carregar_perfil()
    termos = extrair_termos(carregar_vagas().vagas)
    ordem = [s.nome for s in sugerir_competencias(perfil, termos)]
    cv = _exportar_cv(perfil, plataforma) if exportar_cv else None
    return gerar_pacote(perfil, plataforma, banco=carregar_respostas(), ordem_habilidades=ordem, cv_arquivo=cv)


def _salvar_pacote(pacote, plataforma) -> Path:
    from .plataformas.pacote import pacote_markdown

    pasta = _pasta(plataforma.id)
    (pasta / "pacote.json").write_text(pacote.model_dump_json(indent=2), encoding="utf-8")
    destino = pasta / "pacote.md"
    destino.write_text(pacote_markdown(pacote, plataforma), encoding="utf-8")
    return destino


def _pacote_salvo(plataforma):
    from .plataformas.pacote import PacoteCadastro

    caminho = _pasta(plataforma.id) / "pacote.json"
    return PacoteCadastro.model_validate_json(caminho.read_text(encoding="utf-8")) if caminho.is_file() else None


def _modo(plataforma) -> str:
    from .configuracao import carregar_configuracao

    return carregar_configuracao().modos_plataforma.get(plataforma.id, plataforma.modo_padrao)


# ---------------------------------------------------------------- RF-PL-01 / RF-PL-09

@plataformas_app.callback()
def plataformas_principal(ctx: typer.Context) -> None:
    """Catálogo de plataformas com modo, prioridade e status da sua conta em cada uma."""
    if ctx.invoked_subcommand is not None:
        return
    from .plataformas.catalogo import catalogo, termos_vencidos
    from .plataformas.contas import carregar_contas, status_efetivo
    from .storage import perfil_existe

    contas = carregar_contas()
    tabela = Table(title="Plataformas (Anexo B)")
    for col in ("ID", "Plataforma", "Prior.", "Modo", "Conta", "Completude", "Termos", "Observação"):
        tabela.add_column(col, overflow="fold")
    for p in catalogo():
        conta = contas.obter(p.id)
        assinatura = None
        if p.cadastravel and conta.pacote and perfil_existe():
            try:
                assinatura = _montar_pacote(p, exportar_cv=False).assinatura
            except ValueError:
                assinatura = None
        status = status_efetivo(conta, assinatura) if p.cadastravel else "—"
        cor = {"completo": "green", "em_andamento": "yellow", "desatualizado": "red"}.get(status, "dim")
        termos = "revisar" if termos_vencidos(p) else f"{p.termos_revisados_em:%d/%m/%Y}"
        tabela.add_row(
            p.id, p.nome, p.prioridade, _modo(p), f"[{cor}]{status}[/{cor}]",
            f"{conta.completude}%" if conta.completude is not None else "—", termos, Text(p.observacao),
        )
    console.print(tabela)
    console.print("Cadastre com 'agente plataformas cadastrar ID'. Termos 'revisar': confira e registre com "
                  "'agente plataformas termos ID --revisado-em AAAA-MM-DD' (RNF-06).")


@plataformas_app.command("ver")
def plataformas_ver(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Detalhes de uma plataforma: campos, limites, formatos e regras."""
    from .plataformas.catalogo import buscar_plataforma

    try:
        p = buscar_plataforma(id_)
    except ValueError as erro:
        _sair(erro)
    linhas = [
        f"[bold]{escape(p.nome)}[/bold] — {escape(p.url)}", f"Foco: {escape(p.foco)} · Prioridade: {p.prioridade} · Modo: {_modo(p)}",
        f"CV: {', '.join(p.formatos_cv)}" + (f" até {p.tamanho_max_mb} MB" if p.tamanho_max_mb else " (tamanho máximo não conferido)"),
        f"Variante enviada: foco {p.variante.foco}, {p.variante.idioma}, {p.variante.nivel} (RF-PL-06)",
        f"Termos revisados em: {p.termos_revisados_em or 'nunca — revisar'}",
    ]
    if p.cobra_candidato:
        linhas.append(f"[red]Cobra do candidato: {escape(p.etapas_pagas or '')} — o agente não contrata nada (RF-PL-10).[/red]")
    if p.testes_tecnicos:
        linhas.append("[yellow]Tem testes técnicos: são seus (RN-13); material de estudo em 'agente plataformas estudo'.[/yellow]")
    if p.so_estagio:
        linhas.append("[yellow]Só estágio: vale enquanto houver matrícula ativa (RN-07).[/yellow]")
    linhas.append(escape(p.observacao))
    console.print(Panel("\n".join(linhas), title=f"Plataforma {p.id}", border_style="cyan"))
    if p.campos:
        tabela = Table(title="Campos do cadastro")
        for col in ("Campo", "Rótulo", "Origem", "Obrigatório", "Limite"):
            tabela.add_column(col)
        for c in p.campos:
            tabela.add_row(c.id, c.rotulo, c.origem, "sim" if c.obrigatorio else "", str(c.limite) if c.limite else "—")
        console.print(tabela)


@plataformas_app.command("termos")
def plataformas_termos(
    id_: str = typer.Argument(..., metavar="ID"),
    revisado_em: str = typer.Option(..., "--revisado-em", help="AAAA-MM-DD"),
) -> None:
    """Registra a data em que você revisou os termos de uso da plataforma (RF-PL-01, RNF-06)."""
    from .plataformas.catalogo import buscar_plataforma, carregar_ajustes, salvar_ajustes

    try:
        buscar_plataforma(id_)
        data = date.fromisoformat(revisado_em)
    except ValueError as erro:
        _sair(erro)
    ajustes = carregar_ajustes()
    ajustes.termos_revisados_em[id_] = data
    salvar_ajustes(ajustes)
    console.print(f"[green]Termos de {id_} revisados em {data:%d/%m/%Y}.[/green]")


@plataformas_app.command("limite")
def plataformas_limite(
    id_: str = typer.Argument(..., metavar="ID"),
    campo: str = typer.Argument(...),
    caracteres: int = typer.Argument(...),
) -> None:
    """Define o limite de caracteres de um campo, conferido na plataforma (RNF-14: é configuração)."""
    from .plataformas.catalogo import buscar_plataforma, carregar_ajustes, salvar_ajustes

    try:
        buscar_plataforma(id_).campo(campo)
    except ValueError as erro:
        _sair(erro)
    ajustes = carregar_ajustes()
    ajustes.limites.setdefault(id_, {})[campo] = caracteres
    salvar_ajustes(ajustes)
    console.print(f"[green]{id_}.{campo}: limite de {caracteres} caracteres.[/green]")


# ---------------------------------------------------------------- RF-PL-02 / RF-PL-05 / RF-PL-06

@plataformas_app.command("pacote")
def plataformas_pacote(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Gera o pacote de cadastro: cada campo da plataforma a partir do perfil-mestre, já no limite (RF-PL-02)."""
    from .plataformas.catalogo import buscar_plataforma

    try:
        p = buscar_plataforma(id_)
        if not p.cadastravel:
            _sair(f"{p.nome} não tem cadastro pelo agente: {p.observacao}")
        pacote = _montar_pacote(p)
    except ValueError as erro:
        _sair(erro)
    destino = _salvar_pacote(pacote, p)
    _mostrar_pacote(pacote)
    console.print(f"[green]Pacote salvo em[/green] {destino}")


def _mostrar_pacote(pacote) -> None:
    tabela = Table(title=f"Pacote de cadastro — {pacote.plataforma} (variante {pacote.variante})")
    for col in ("Campo", "Valor", "Observação"):
        tabela.add_column(col, overflow="fold")
    for c in pacote.campos:
        obs = []
        if c.manual:
            obs.append(c.instrucao or "preencha você")
        if c.cortado:
            obs.append(f"ajustado ao limite de {c.limite}")
        if c.obrigatorio and not c.valor and not c.manual:
            obs.append("obrigatório e vazio no perfil-mestre")
        valor = c.valor if c.valor and len(c.valor) <= 300 else (c.valor[:300] + "…" if c.valor else "—")
        tabela.add_row(c.rotulo, Text(valor), Text("; ".join(obs)))
    console.print(tabela)


# ---------------------------------------------------------------- RF-PL-03 (copiloto e assistido)

def _passos_cadastro(pacote) -> list[tuple[str, str]]:
    passos = list(PASSOS_DO_USUARIO)
    passos.append(("cv", f"Envie o currículo ({Path(pacote.cv_arquivo).name if pacote.cv_arquivo else 'exporte antes'})"))
    passos += [(f"campo:{c.id}", c.rotulo) for c in pacote.campos if c.id != "cv"]
    passos += [
        ("revisar", "Confira o que a plataforma preencheu sozinha a partir do CV (RF-PL-04)"),
        ("salvar", "Salve o cadastro na plataforma — clique você"),
    ]
    return passos


def _executar_passos(tarefa, tarefas, pacote, plataforma, modo_usado: str, captura: Path | None = None) -> None:
    from .operacao.auditoria import registrar_acao
    from .operacao.tarefas import confirmar_passo, pausar, salvar_tarefas
    from .plataformas.contas import carregar_contas, registrar_gravacao, salvar_contas

    try:
        for passo in [p for p in tarefa.passos if p.status == "pendente"]:
            console.print(f"\n[bold]{escape(passo.descricao)}[/bold]")
            if passo.nome == "cv" and pacote.cv_arquivo:
                console.print(f"Arquivo: {pacote.cv_arquivo}")
            if passo.nome.startswith("campo:"):
                campo = pacote.campo(passo.nome.split(":", 1)[1])
                if campo.manual:
                    console.print(f"[yellow]Preencha você: {escape(campo.instrucao or '')}[/yellow]")
                else:
                    console.print(campo.valor or "(vazio no perfil-mestre — deixe em branco ou complete o perfil)",
                                  markup=False, highlight=False)
            if passo.nome == "revisar":
                console.print(f"Se a plataforma preencheu campos sozinha, compare com 'agente plataformas conferir {plataforma.id} --antes-de-salvar'.")
            escolha = ""
            while escolha not in {"o", "s", "p"}:
                escolha = typer.prompt("[o]k, [s]altar ou [p]ausar").lstrip("﻿").strip().lower()[:1]
            if escolha == "p":
                raise typer.Abort()
            confirmar_passo(tarefa, passo.nome, pulado=escolha == "s")
            salvar_tarefas(tarefas)
            if passo.nome == "salvar" and escolha == "o":
                registrar_acao(
                    plataforma=plataforma.id, acao="salvar cadastro", alvo="perfil do candidato",
                    depois=f"pacote {pacote.assinatura} ({len(pacote.campos)} campos, CV {pacote.variante})",
                    modo=modo_usado, aprovado_em=datetime.now(timezone.utc),
                    origem_aprovacao=f"tarefa {tarefa.id} (campo a campo)", captura=captura,
                )
                contas = carregar_contas()
                registrar_gravacao(contas.obter(plataforma.id), pacote, completude=None, completo=False)
                salvar_contas(contas)
                console.print(f"[green]Cadastro registrado e auditado.[/green] Agora confira o que ficou gravado: "
                              f"'agente plataformas conferir {plataforma.id}' (RF-PL-07).")
    except (KeyboardInterrupt, typer.Abort):
        if tarefa.status == "ativa":
            pausar(tarefa)
            salvar_tarefas(tarefas)
        proximo = tarefa.proximo_passo()
        console.print(f"\n[yellow]Cadastro pausado{f' em {escape(proximo.descricao)!s}' if proximo else ''}.[/yellow] "
                      f"Continue com 'agente plataformas cadastrar {plataforma.id}'.")
        raise typer.Exit(0)


def _cadastro_assistido(plataforma, pacote, tarefa, tarefas) -> Path | None:
    """Abre o navegador, espera o login (RN-03), confere o layout (RNF-08) e preenche sem salvar."""
    from .configuracao import carregar_configuracao
    from .navegador import CampoParaPreencher, SessaoNavegador, preencher
    from .operacao.notificacoes import notificar
    from .operacao.saude import LayoutMudou, carregar_saude, salvar_saude
    from .operacao.tarefas import confirmar_passo, salvar_tarefas

    central = carregar_configuracao()
    saude = carregar_saude()
    nome = f"assistido:{plataforma.id}"
    if not saude.pode_usar(nome):
        console.print(f"[yellow]O preenchimento assistido em {plataforma.nome} está parado (layout mudou); seguindo em copiloto. "
                      f"Reative com 'agente saude reativar {nome}'.[/yellow]")
        return None
    campos = [CampoParaPreencher(id=c.id, rotulo=c.rotulo, valor=c.valor, obrigatorio=c.obrigatorio, arquivo=c.id == "cv")
              for c in pacote.campos if not c.manual]
    with SessaoNavegador() as sessao:
        sessao.pagina.goto(plataforma.url)
        console.print(Panel(
            "No navegador que abriu: crie a conta ou faça login, 2FA e CAPTCHA, aceite os termos e abra o formulário "
            "do seu perfil/currículo. Isso é seu (RN-03). Depois volte aqui.",
            title=f"Modo assistido — {plataforma.nome}", border_style="magenta",
        ))
        typer.prompt("Tecle Enter quando o formulário estiver aberto", default="", show_default=False)
        try:
            resultado = preencher(
                sessao.pagina, campos, limite_acoes=central.limites.acoes_por_sessao,
                intervalo_segundos=central.limites.intervalo_entre_acoes_segundos,
                pasta_capturas=diretorio_dados() / "auditoria" / "capturas",
            )
        except LayoutMudou as erro:
            saude.falha(nome, str(erro), parar=True)
            salvar_saude(saude)
            notificar("falha_adaptador", f"Preenchimento assistido parado em {plataforma.nome}", str(erro), central)
            console.print(f"[red]Parei sem preencher nada: {escape(str(erro))}.[/red] Seguindo em copiloto (RNF-08).")
            return None
        saude.sucesso(nome)
        salvar_saude(saude)
        for passo, _ in PASSOS_DO_USUARIO:
            confirmar_passo(tarefa, passo)
        rotulo_para_passo = {c.rotulo: ("cv" if c.id == "cv" else f"campo:{c.id}") for c in pacote.campos}
        for rotulo in resultado.preenchidos:
            confirmar_passo(tarefa, rotulo_para_passo[rotulo])
        salvar_tarefas(tarefas)
        console.print(f"[green]Preenchidos pelo agente ({len(resultado.preenchidos)}):[/green] {escape(', '.join(resultado.preenchidos))}")
        if resultado.para_copiloto:
            console.print(f"[yellow]Ficam com você ({len(resultado.para_copiloto)}):[/yellow] {escape(', '.join(resultado.para_copiloto))}")
        if resultado.parou_no_limite:
            console.print(f"[yellow]Parei no limite de {central.limites.acoes_por_sessao} ações por sessão (RN-05).[/yellow]")
        console.print("[bold]O agente não salva nada: complete os campos restantes abaixo, revise a tela e clique você em salvar.[/bold]")
        _executar_passos(tarefa, tarefas, pacote, plataforma, "assistido", captura=resultado.captura)
        typer.prompt("Tecle Enter para fechar o navegador", default="", show_default=False)
    return resultado.captura


@plataformas_app.command("cadastrar")
def plataformas_cadastrar(
    id_: str = typer.Argument(..., metavar="ID"),
    copiloto: bool = typer.Option(False, "--copiloto", help="Não abrir o navegador, mesmo em plataforma assistida."),
) -> None:
    """Conduz o cadastro (ou a atualização) no modo da plataforma; pausa e retoma do último campo (RF-PL-03)."""
    from .configuracao import carregar_configuracao
    from .navegador import playwright_disponivel
    from .operacao.tarefas import carregar_tarefas, criar_tarefa, retomar, salvar_tarefas
    from .plataformas.catalogo import buscar_plataforma, termos_vencidos
    from .plataformas.contas import carregar_contas, salvar_contas
    from .radar.filtros import matricula_ativa

    try:
        p = buscar_plataforma(id_)
    except ValueError as erro:
        _sair(erro)
    if not p.cadastravel:
        _sair(f"{p.nome} não tem cadastro pelo agente: {p.observacao}")
    central = carregar_configuracao()
    modo = central.modos_plataforma.get(p.id, p.modo_padrao)
    if modo == "desligado":
        _sair(f"{p.nome} está desligada nas preferências (modos_plataforma.{p.id}).")
    perfil = carregar_perfil()
    if p.so_estagio and not matricula_ativa(perfil, date.today()):
        _sair(f"{p.nome} é só para estágio e não há matrícula ativa no perfil-mestre (RN-07).")
    if p.cobra_candidato:
        console.print(Panel(f"{p.nome} oferece etapas pagas: {escape(p.etapas_pagas or '')}. O agente não contrata nada; "
                            "ignore ofertas de plano ou destaque (RF-PL-10).", title="Atenção: etapas pagas", border_style="red"))
        if not typer.confirm("Seguir com o cadastro gratuito?", default=False):
            raise typer.Exit(0)
    if p.testes_tecnicos:
        console.print(f"[yellow]{p.nome} aplica testes técnicos: eles são seus (RN-13). Material de estudo: "
                      f"'agente plataformas estudo {p.id}'.[/yellow]")
    if termos_vencidos(p):
        console.print(f"[yellow]Termos de uso de {p.nome} não revisados nos últimos 6 meses (RNF-06).[/yellow]")

    tarefas = carregar_tarefas()
    atualizacao = tarefas.aberta_do_tipo(f"atualizar-{p.id}")
    try:
        pacote = _montar_pacote(p)
    except ValueError as erro:
        _sair(erro)
    _salvar_pacote(pacote, p)

    tarefa = atualizacao or tarefas.aberta_do_tipo(f"cadastro-{p.id}")
    if tarefa is not None:
        if tarefa.status != "ativa":
            retomar(tarefa)
        console.print(f"[cyan]Continuando {escape(tarefa.descricao)} ({tarefa.progresso}).[/cyan]")
    else:
        tarefa = criar_tarefa(tarefas, f"cadastro-{p.id}", f"Cadastro em {p.nome}", _passos_cadastro(pacote))
    salvar_tarefas(tarefas)
    contas = carregar_contas()
    conta = contas.obter(p.id)
    if conta.status == "nao_iniciado":
        conta.status, conta.iniciado_em = "em_andamento", datetime.now(timezone.utc)
    conta.tarefa_id = tarefa.id
    salvar_contas(contas)

    usar_assistido = modo == "assistido" and not copiloto and atualizacao is None
    if usar_assistido and central.somente_sugestao:
        console.print("[yellow]Modo somente sugestão ligado: nada é aberto no navegador; seguindo em copiloto (RF-OP-02).[/yellow]")
        usar_assistido = False
    if usar_assistido and not playwright_disponivel():
        console.print("[yellow]Playwright indisponível; seguindo em copiloto ('uv sync' e 'uv run playwright install chromium').[/yellow]")
        usar_assistido = False
    if usar_assistido:
        _cadastro_assistido(p, pacote, tarefa, tarefas)
        return
    console.print(f"[bold]Cadastro em {p.nome} — modo copiloto:[/bold] copie cada valor e cole na plataforma; o agente não toca nela.")
    _executar_passos(tarefa, tarefas, pacote, p, "copiloto")


# ---------------------------------------------------------------- RF-PL-04 / RF-PL-07

@plataformas_app.command("conferir")
def plataformas_conferir(
    id_: str = typer.Argument(..., metavar="ID"),
    arquivo: Path | None = typer.Option(None, "--arquivo", exists=True, readable=True,
                                        help="O que a plataforma mostra, em linhas 'Rótulo: valor' ou blocos '### CAMPO: id'."),
    antes_de_salvar: bool = typer.Option(False, "--antes-de-salvar", help="Revisa o preenchimento automático pelo CV (RF-PL-04)."),
) -> None:
    """Compara o que a plataforma gravou com o pacote e registra a completude (RF-PL-04, RF-PL-07)."""
    from .plataformas.catalogo import buscar_plataforma
    from .plataformas.contas import carregar_contas, registrar_gravacao, salvar_contas
    from .plataformas.pacote import comparar, completude, ler_campos

    try:
        p = buscar_plataforma(id_)
    except ValueError as erro:
        _sair(erro)
    pacote = _pacote_salvo(p)
    if pacote is None:
        _sair(f"Gere o pacote antes: 'agente plataformas pacote {p.id}'.")
    if arquivo:
        lidos = ler_campos(arquivo.read_text(encoding="utf-8"), pacote)
    else:
        lidos = {}
        console.print("Digite o que a plataforma mostra em cada campo (Enter = vazio; '-' = não conferi).")
        for c in pacote.campos:
            if c.id == "cv":
                continue
            valor = typer.prompt(c.rotulo, default="", show_default=False)
            if valor.strip() != "-":
                lidos[c.id] = valor
    comparacoes = comparar(pacote, lidos)
    tabela = Table(title=f"Conferência — {p.nome}")
    for col in ("Campo", "Status", "No pacote", "Na plataforma"):
        tabela.add_column(col, overflow="fold")
    cores = {"ok": "green", "diferente": "red", "faltando": "red", "manual": "yellow", "nao_conferido": "dim"}
    for c in comparacoes:
        tabela.add_row(c.rotulo, f"[{cores[c.status]}]{c.status}[/{cores[c.status]}]",
                       Text((c.esperado or "—")[:120]), Text((c.encontrado or "—")[:120]))
    console.print(tabela)
    pct = completude(comparacoes)
    divergentes = [c for c in comparacoes if c.status in ("diferente", "faltando")]
    if antes_de_salvar:
        if divergentes:
            console.print(f"[red]Corrija {len(divergentes)} campo(s) antes de salvar[/red] — o valor certo é o do pacote (RF-PL-04).")
        else:
            console.print("[green]O preenchimento automático bate com o pacote.[/green]")
        return
    obrigatorios = {c.id for c in pacote.campos if c.obrigatorio}
    completo = not [c for c in comparacoes if c.campo in obrigatorios and c.status in ("diferente", "faltando", "nao_conferido")]
    contas = carregar_contas()
    registrar_gravacao(contas.obter(p.id), pacote, completude=pct, completo=completo)
    salvar_contas(contas)
    console.print(f"[bold]Completude: {pct}%[/bold] — conta {'completa' if completo else 'em andamento'} (RF-PL-07, RF-PL-09).")


# ---------------------------------------------------------------- RF-PL-08

@plataformas_app.command("propagar")
def plataformas_propagar() -> None:
    """Lista as plataformas desatualizadas pelo perfil-mestre e cria uma tarefa de atualização para cada (RF-PL-08)."""
    from .operacao.tarefas import carregar_tarefas, criar_tarefa, salvar_tarefas
    from .plataformas.catalogo import buscar_plataforma
    from .plataformas.contas import carregar_contas, salvar_contas
    from .plataformas.pacote import campos_alterados

    contas, tarefas = carregar_contas(), carregar_tarefas()
    criadas = 0
    for conta in contas.itens.values():
        if not conta.pacote or conta.status == "nao_iniciado":
            continue
        p = buscar_plataforma(conta.plataforma)
        atual = _montar_pacote(p, exportar_cv=False)
        if atual.assinatura == conta.pacote.assinatura:
            continue
        alterados = campos_alterados(conta.pacote, atual)
        conta.status = "desatualizado"
        rotulos = ", ".join(atual.campo(c).rotulo for c in alterados)
        console.print(f"[red]{p.nome}[/red]: mudaram {escape(rotulos)}")
        if tarefas.aberta_do_tipo(f"atualizar-{p.id}") is None:
            criar_tarefa(tarefas, f"atualizar-{p.id}", f"Atualizar {p.nome}",
                         [(f"campo:{c}", atual.campo(c).rotulo) for c in alterados] + [("salvar", "Salve na plataforma — clique você")])
            criadas += 1
    salvar_contas(contas)
    salvar_tarefas(tarefas)
    if not criadas and not any(c.status == "desatualizado" for c in contas.itens.values()):
        console.print("[green]Todas as plataformas cadastradas estão em dia com o perfil-mestre.[/green]")
    else:
        console.print(f"{criadas} tarefa(s) de atualização criada(s). Rode 'agente plataformas cadastrar ID' para cada uma.")


# ---------------------------------------------------------------- RF-PL-11

@plataformas_app.command("estudo")
def plataformas_estudo(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Material de estudo para os testes técnicos da plataforma — que são seus (RF-PL-11, RN-13)."""
    from .analise.fechamento import sugerir_fechamento
    from .analise.lacunas import gerar_relatorio
    from .analise.termos import extrair_termos
    from .plataformas.catalogo import buscar_plataforma
    from .vagas import carregar_vagas

    try:
        p = buscar_plataforma(id_)
    except ValueError as erro:
        _sair(erro)
    perfil = carregar_perfil()
    termos = [t for t in extrair_termos(carregar_vagas().vagas) if t.e_tecnologia]
    relatorio = gerar_relatorio(perfil, termos)
    linhas = [f"# Material de estudo — {p.nome}", "",
              "Os testes técnicos e questionários são seus: o agente não responde por você (RN-13).", "",
              "## O que as suas vagas-alvo mais pedem", ""]
    linhas += [f"- {t.termo} ({t.vagas_em_que_aparece} vaga[s])" for t in termos[:12]] or ["- (salve vagas-alvo para priorizar)"]
    linhas += ["", "## Revise o que você já usa", ""]
    linhas += [f"- {i.termo}: refaça um exercício curto e explique em voz alta o que cada parte faz" for i in relatorio.ja_no_cv[:8]]
    linhas += ["", "## Estude o que falta", ""]
    for s in sugerir_fechamento(relatorio.nao_tem[:6]):
        linhas.append(f"- {s.termo} — {s.tipo}: {s.descricao}" + (f" [{s.catalogo}]" if s.catalogo else ""))
    linhas += ["", "## No dia do teste", "",
               "- Leia o enunciado inteiro antes de codar e anote as restrições.",
               "- Comece pela solução simples que passa nos casos dados; depois melhore.",
               "- Escreva testes ou casos de borda e explique suas decisões no README ou nos comentários pedidos."]
    destino = _pasta(p.id) / "estudo.md"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    console.print("\n".join(linhas), markup=False, highlight=False)
    console.print(f"\n[green]Salvo em[/green] {destino}")
