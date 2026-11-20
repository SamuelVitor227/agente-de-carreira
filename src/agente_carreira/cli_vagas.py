"""CLI do M4 — buscas salvas e radar de vagas (RF-VG-01 a RF-VG-13)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .radar.modelos import (
    CONTRATOS,
    MODELOS,
    NIVEIS,
    REGIAO_BH,
    SINONIMOS_POR_FOCO,
    BuscaSalva,
    EmpresaAlvo,
    VagaEncontrada,
    carregar_base,
    carregar_config,
    salvar_base,
    salvar_config,
)
from .storage import carregar_perfil, diretorio_dados

console = Console()
busca_app = typer.Typer(help="Buscas salvas do radar de vagas (RF-VG-01).", no_args_is_help=True)
vagas_app = typer.Typer(help="Radar de vagas: coleta, triagem, resumo diário e alertas (RF-VG-02 a RF-VG-13).",
                        no_args_is_help=True)


def _lista(texto: str | None) -> list[str]:
    return [p.strip() for p in (texto or "").split(",") if p.strip()]


def _validar(valores: list[str], permitidos: tuple[str, ...], rotulo: str) -> list[str]:
    invalidos = [v for v in valores if v not in permitidos]
    if invalidos:
        console.print(f"[red]{rotulo} inválido(s): {', '.join(invalidos)}. Use: {', '.join(permitidos)}.[/red]")
        raise typer.Exit(1)
    return valores


def _perfil():
    try:
        return carregar_perfil()
    except FileNotFoundError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)


def _vaga(base, id_: str) -> VagaEncontrada:
    try:
        return base.buscar(id_)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------- buscas (RF-VG-01)

@busca_app.command("criar")
def busca_criar(
    nome: str = typer.Option(..., "--nome"),
    foco: str | None = typer.Option(None, "--foco", help=f"Preenche cargos e sinônimos: {', '.join(SINONIMOS_POR_FOCO)}."),
    cargos: str | None = typer.Option(None, "--cargos", help="Cargos e sinônimos separados por vírgula (somados aos do foco)."),
    niveis: str = typer.Option("estagio,trainee,junior", "--niveis"),
    modelos: str = typer.Option("presencial,hibrido,remoto", "--modelos"),
    localidades: str | None = typer.Option(None, "--localidades", help="Cidades aceitas para presencial e híbrido; padrão: BH e região metropolitana."),
    raio: int = typer.Option(30, "--raio", help="Raio de referência em km (a região é definida pelas cidades)."),
    contratos: str = typer.Option("estagio,clt,pj", "--contratos"),
    salario_minimo: float | None = typer.Option(None, "--salario-minimo"),
    idiomas: str = typer.Option("pt,en", "--idiomas", help="Idiomas do anúncio aceitos (pt, en)."),
    sem_remoto: bool = typer.Option(False, "--sem-remoto", help="Não aceita vagas remotas."),
    limite_anos: int = typer.Option(2, "--limite-anos", help="Máximo de anos de experiência exigidos."),
) -> None:
    """Cria uma busca salva: cargos e sinônimos, nível, modelo, local, contrato, salário e idioma."""
    if foco and foco not in SINONIMOS_POR_FOCO:
        console.print(f"[red]Foco desconhecido: {escape(foco)}. Use: {', '.join(SINONIMOS_POR_FOCO)}.[/red]")
        raise typer.Exit(1)
    lista_cargos = list(dict.fromkeys(SINONIMOS_POR_FOCO.get(foco or "", []) + _lista(cargos)))
    if not lista_cargos:
        console.print("[red]Informe --foco ou --cargos.[/red]")
        raise typer.Exit(1)
    config = carregar_config()
    if any(b.nome == nome for b in config.buscas):
        console.print(f"[red]Já existe uma busca chamada {escape(nome)}.[/red]")
        raise typer.Exit(1)
    busca = BuscaSalva(
        nome=nome, cargos=lista_cargos,
        niveis=_validar(_lista(niveis), NIVEIS, "Nível"),
        modelos=_validar(_lista(modelos), MODELOS, "Modelo"),
        localidades=_lista(localidades) or list(REGIAO_BH), raio_km=raio, remoto_brasil=not sem_remoto,
        contratos=_validar(_lista(contratos), CONTRATOS, "Contrato"),
        salario_minimo=salario_minimo, idiomas=_validar(_lista(idiomas), ("pt", "en"), "Idioma"),
        limite_anos_experiencia=limite_anos,
    )
    config.buscas.append(busca)
    salvar_config(config)
    console.print(f"[green]Busca '{escape(nome)}' criada[/green] com {len(lista_cargos)} cargo(s)/sinônimo(s).")
    console.print("Adicione empresas-alvo com 'agente busca empresa' e rode 'agente vagas rodada'.")


@busca_app.command("listar")
def busca_listar() -> None:
    """Lista as buscas salvas."""
    config = carregar_config()
    if not config.buscas:
        console.print("Nenhuma busca salva. Crie com 'agente busca criar --nome X --foco backend-dotnet'.")
        return
    for b in config.buscas:
        alvo = ", ".join(e.nome + (" (página)" if e.pagina_carreira else "") for e in b.empresas_alvo) or "—"
        corpo = (
            f"[bold]Cargos ({len(b.cargos)}):[/bold] {escape(', '.join(b.cargos))}\n"
            f"[bold]Níveis:[/bold] {', '.join(b.niveis)} · [bold]Modelos:[/bold] {', '.join(b.modelos)}"
            f"{'' if b.remoto_brasil else ' (sem remoto)'}\n"
            f"[bold]Contratos:[/bold] {', '.join(b.contratos)} · [bold]Salário mínimo:[/bold] "
            f"{('R$ %.0f' % b.salario_minimo) if b.salario_minimo else '—'} · [bold]Idiomas:[/bold] {', '.join(b.idiomas)}\n"
            f"[bold]Localidades ({len(b.localidades)}, raio {b.raio_km} km):[/bold] {escape(', '.join(b.localidades))}\n"
            f"[bold]Limite de experiência:[/bold] {b.limite_anos_experiencia} ano(s)\n"
            f"[bold]Empresas-alvo:[/bold] {escape(alvo)}\n"
            f"[bold]Bloqueadas:[/bold] {escape(', '.join(b.empresas_bloqueadas) or '—')}"
        )
        console.print(Panel(corpo, title=f"Busca: {escape(b.nome)}", border_style="cyan"))


@busca_app.command("remover")
def busca_remover(nome: str = typer.Argument(...)) -> None:
    """Remove uma busca salva."""
    config = carregar_config()
    restantes = [b for b in config.buscas if b.nome != nome]
    if len(restantes) == len(config.buscas):
        console.print(f"[red]Busca {escape(nome)} não existe.[/red]")
        raise typer.Exit(1)
    config.buscas = restantes
    salvar_config(config)
    console.print(f"[green]Busca {escape(nome)} removida.[/green]")


@busca_app.command("empresa")
def busca_empresa(
    empresa: str = typer.Argument(..., help="Nome da empresa-alvo."),
    pagina: str | None = typer.Option(None, "--pagina", help="URL da página de carreira (lida respeitando o robots.txt)."),
    busca: str | None = typer.Option(None, "--busca", help="Busca que recebe a empresa; padrão: todas."),
) -> None:
    """Adiciona uma empresa-alvo, com a página de carreira opcional."""
    config = carregar_config()
    alvos = [b for b in config.buscas if busca is None or b.nome == busca]
    if not alvos:
        console.print("[red]Nenhuma busca encontrada. Crie uma com 'agente busca criar'.[/red]")
        raise typer.Exit(1)
    for b in alvos:
        b.empresas_alvo = [e for e in b.empresas_alvo if e.nome.lower() != empresa.lower()]
        b.empresas_alvo.append(EmpresaAlvo(nome=empresa, pagina_carreira=pagina))
    salvar_config(config)
    console.print(f"[green]{escape(empresa)} adicionada como empresa-alvo em {len(alvos)} busca(s).[/green]")


@busca_app.command("bloquear")
def busca_bloquear(
    empresa: str = typer.Argument(...),
    busca: str | None = typer.Option(None, "--busca", help="Padrão: todas as buscas."),
) -> None:
    """Bloqueia uma empresa: suas vagas são eliminadas da triagem."""
    config = carregar_config()
    alvos = [b for b in config.buscas if busca is None or b.nome == busca]
    if not alvos:
        console.print("[red]Nenhuma busca encontrada.[/red]")
        raise typer.Exit(1)
    for b in alvos:
        if empresa not in b.empresas_bloqueadas:
            b.empresas_bloqueadas.append(empresa)
    salvar_config(config)
    console.print(f"[green]{escape(empresa)} bloqueada em {len(alvos)} busca(s).[/green]")


# ---------------------------------------------------------------- rodada e coleta

def _mostrar_alertas(vagas: list[VagaEncontrada], arquivo: Path | None, limiar: int) -> None:
    if not vagas:
        return
    linhas = "\n".join(f"• {escape(v.titulo)} — {escape(v.empresa or '?')} ({v.nota}) · {escape(v.link or '')} · ID {v.id}" for v in vagas)
    console.print(Panel(linhas, title=f"Alerta: {len(vagas)} vaga(s) com aderência ≥ {limiar} (RF-VG-10)", border_style="bold green"))
    if arquivo:
        console.print(f"[dim]Alerta salvo em {arquivo}[/dim]")


@vagas_app.command("rodada")
def vagas_rodada(
    emails: Path | None = typer.Option(None, "--emails", help="Pasta com alertas .eml (padrão: data/caixa-alertas)."),
    sem_imap: bool = typer.Option(False, "--sem-imap", help="Não lê a caixa de e-mail por IMAP."),
    sem_paginas: bool = typer.Option(False, "--sem-paginas", help="Não lê as páginas de carreira das empresas-alvo."),
    sem_enriquecer: bool = typer.Option(False, "--sem-enriquecer", help="Não abre a página das vagas de domínios permitidos."),
    verificar_links: bool = typer.Option(False, "--verificar-links", help="Confere se vagas já vistas saíram do ar (domínios permitidos)."),
    forcar: bool = typer.Option(False, "--forcar", help="Roda mesmo com a rodada pausada."),
    sem_linkedin: bool = typer.Option(False, "--sem-linkedin", help="Não usa o navegador automático no LinkedIn nesta rodada."),
) -> None:
    """Rodada de vagas: coleta, deduplica, filtra, pontua e gera o resumo do dia (RF-VG-03, RF-VG-09)."""
    from .configuracao import carregar_configuracao, plataforma_permite_leitura
    from .operacao.notificacoes import notificar
    from .operacao.saude import carregar_saude, salvar_saude
    from .operacao.tarefas import carregar_tarefas, falhar, garantir_tarefa_rodada, salvar_tarefas
    from .radar.coleta import config_imap
    from .radar.rodada import executar_rodada

    from .operacao import andamento
    from .operacao.recursos import trabalhadores

    if (rodando := andamento.em_andamento("Busca de vagas")) is not None:
        console.print(f"[yellow]Já tem uma busca de vagas rodando ({escape(andamento.descrever(rodando))}). "
                      "Acompanhe com 'agente andamento' ou na faixa do app.[/yellow]")
        raise typer.Exit(0)
    tarefas = carregar_tarefas()
    tarefa = garantir_tarefa_rodada(tarefas)
    salvar_tarefas(tarefas)
    if tarefa.bloqueada and not forcar:
        console.print(f"[yellow]A rodada de vagas está {tarefa.status}.[/yellow] Retome com "
                      f"'agente tarefas retomar {tarefa.id}' ou rode uma vez com --forcar (RF-OP-03).")
        raise typer.Exit(0)

    perfil = _perfil()
    central = carregar_configuracao()
    config = central.vagas
    if not config.buscas:
        console.print("[red]Nenhuma busca salva. Crie uma com 'agente busca criar --nome X --foco backend-dotnet'.[/red]")
        raise typer.Exit(1)
    if central.somente_sugestao:
        console.print("[yellow]Modo somente sugestão: nenhuma página de plataforma é lida; só os alertas de e-mail (RF-OP-02).[/yellow]")
    pasta = emails or diretorio_dados() / "caixa-alertas"
    pasta.mkdir(parents=True, exist_ok=True)
    imap = None if sem_imap else config_imap()
    if not sem_imap and imap is None and not central.email_navegador.ativo:
        console.print(f"[dim]IMAP não configurado (variáveis AGENTE_IMAP_*); lendo os .eml de {pasta}.[/dim]")

    saude = carregar_saude()
    base = carregar_base()
    leitores = []
    if central.email_navegador.ativo and not sem_imap:
        from .radar.outlook_web import leitor_da_rodada

        console.print("[magenta]E-mail: lendo os alertas de vaga no Outlook, pelo navegador do agente.[/magenta]")
        leitores.append(leitor_da_rodada(central.email_navegador.consultas, saude,
                                         por_consulta=central.email_navegador.por_consulta))
    extras = []
    if central.sites.gupy_portal and not sem_paginas and not central.somente_sugestao             and central.modos_plataforma.get("gupy") != "desligado":
        from .radar.gupy_portal import coletor_da_rodada as coletor_gupy, termos_da_rodada
        from .radar.modelos import PESQUISAS_GERAIS_LINKEDIN

        termos = termos_da_rodada(config.buscas, PESQUISAS_GERAIS_LINKEDIN, central.sites.gupy_termos_por_rodada)
        console.print(f"[magenta]Gupy: buscando no portal de vagas ({len(termos)} termo(s)).[/magenta]")
        extras.append(coletor_gupy(config, termos, saude))
    if central.sites.glassdoor and not sem_paginas and not central.somente_sugestao:  # RF-EV-04
        from .operacao.aviso_windows import avisar_na_tela
        from .radar.glassdoor import coletor_da_rodada as coletor_glassdoor
        from .radar.gupy_portal import termos_da_rodada as termos_glassdoor
        from .radar.modelos import PESQUISAS_GERAIS_LINKEDIN as gerais

        automatica = os.environ.get("AGENTE_ORIGEM") == "agendada"  # sem ninguém por perto: não espera verificação
        minutos = 0 if automatica else central.sites.glassdoor_minutos_verificacao

        def avisar_glassdoor(texto: str) -> None:
            console.print(f"[yellow]{escape(texto)}[/yellow]")
            avisar_na_tela("Glassdoor pede verificação", texto)

        console.print("[magenta]Glassdoor: buscando no site, no navegador do agente.[/magenta]")
        extras.append(coletor_glassdoor(termos_glassdoor(config.buscas, gerais, central.sites.glassdoor_termos_por_rodada),
                                        "Belo Horizonte", saude, minutos_verificacao=minutos, avisar=avisar_glassdoor))
    auto = central.linkedin_automatico
    if auto.ativo and not sem_linkedin and not central.somente_sugestao             and central.modos_plataforma.get("linkedin") != "desligado":
        from .linkedin.automatico import coletor_da_rodada

        console.print("[magenta]LinkedIn: buscando vagas no navegador do agente (modo automático que você ligou).[/magenta]")
        extras.append(coletor_da_rodada(config, auto, saude))
    enriquecedores = []
    if auto.ativo and not central.somente_sugestao and central.modos_plataforma.get("linkedin") != "desligado":
        from .linkedin.automatico import enriquecedor_da_rodada

        enriquecedores.append(enriquecedor_da_rodada(auto, saude))
    try:
        with andamento.tarefa("Busca de vagas") as registro:
            resultado = executar_rodada(
                perfil, config, base, date.today(), pasta_emails=pasta, imap=imap,
                usar_paginas=not sem_paginas, enriquecer_links=not sem_enriquecer, verificar_links=verificar_links,
                motor_justificativa=central.motor_da_tarefa("justificativa-vagas"),
                saude=saude, pode_ler=lambda url: plataforma_permite_leitura(central, url), coletores_extras=extras,
                leitores_email=leitores, enriquecedores=enriquecedores,
                paralelo=trabalhadores(central.desempenho.memoria_max_percentual),
            )
            registro["resultado"] = (f"{len(resultado.processamento.adicionadas)} vaga(s) nova(s), "
                                     f"{len(resultado.resumo.itens)} recomendada(s)")
    except Exception as erro:  # noqa: BLE001 - a falha fica registrada na tarefa e é notificada
        salvar_saude(saude)
        falhar(tarefa, str(erro))
        salvar_tarefas(tarefas)
        notificar("falha_adaptador", "A rodada de vagas falhou", f"Erro: {erro}\n\nVeja 'agente tarefas' e 'agente saude'.", central)
        console.print(f"[red]A rodada falhou: {escape(str(erro))}[/red]")
        raise typer.Exit(1)
    # A busca é automática: se você mudou algo enquanto ela rodava (salvou, descartou...), a sua mudança vale.
    salvar_base(base, preferir="disco")
    salvar_config(config, preferir="disco")
    salvar_saude(saude)
    tarefa.erro = None
    tarefa.dados["ultima_execucao"] = f"{date.today():%d/%m/%Y}"
    salvar_tarefas(tarefas)

    proc = resultado.processamento
    console.print(
        f"[bold]Rodada concluída:[/bold] {resultado.coletadas} coletada(s) · {len(proc.adicionadas)} nova(s) · "
        f"{len(proc.mescladas)} duplicata(s) juntada(s) · {proc.abertas} página(s) aberta(s) · "
        f"{len(proc.eliminadas)} eliminada(s) · {len(proc.expiradas)} expirada(s)"
    )
    for erro in resultado.erros:
        console.print(f"[yellow]• {escape(erro)}[/yellow]")
    _mostrar_alertas(proc.alertas, proc.arquivo_alerta, config.limiar_alerta)
    _tabela_resumo(resultado.resumo.itens)
    if resultado.resumo.risco:
        console.print(f"[red]{len(resultado.resumo.risco)} vaga(s) com indícios de golpe ou risco, fora das recomendações (RN-12).[/red]")
    for falha in resultado.falhas_adaptadores:
        console.print(f"[red]Adaptador parado (RF-OP-07): {escape(falha)}[/red]")
    console.print(f"[green]Resumo salvo em[/green] {resultado.arquivo_resumo}")
    if resultado.pedido_ia and resultado.pedido_ia_autorizado:
        console.print(f"Prompt da justificativa por IA gerado pela autorização em lote (uso {resultado.pedido_ia}); veja 'agente ia log'.")
    elif resultado.pedido_ia:
        console.print(f"Justificativa escrita por IA na fila de aprovações: 'agente fila' (item ia:{resultado.pedido_ia}).")
    _notificar_rodada(resultado, central, config)
    try:  # RNF-15: o painel de execução é atualizado a cada rodada; falha aqui não derruba a rodada
        from .relatorios import salvar_painel_html

        console.print(f"Painel atualizado: {salvar_painel_html()}")
    except Exception as erro:  # noqa: BLE001
        console.print(f"[yellow]Painel não atualizado: {escape(str(erro))}[/yellow]")


def _notificar_rodada(resultado, central, config) -> None:
    """RF-OP-04: resumo diário, vagas acima do limiar, pedido de aprovação e falha de adaptador."""
    from .operacao.notificacoes import notificar
    from .radar.resumo import resumo_markdown

    envios = [notificar("resumo_diario", f"Resumo de vagas — {resultado.resumo.data:%d/%m/%Y}",
                        resumo_markdown(resultado.resumo, config), central)]
    alertas = resultado.processamento.alertas
    if alertas:
        envios.append(notificar(
            "vaga_acima_limiar", f"{len(alertas)} vaga(s) com aderência ≥ {config.limiar_alerta}",
            "\n".join(f"- {v.titulo} — {v.empresa or '?'} ({v.nota}): {v.link or 'sem link'}" for v in alertas), central,
        ))
    if resultado.pedido_ia and not resultado.pedido_ia_autorizado:
        envios.append(notificar(
            "pedido_aprovacao", "Pedido de aprovação na fila",
            f"A justificativa escrita das vagas de hoje espera sua autorização: agente fila (item ia:{resultado.pedido_ia}).",
            central,
        ))
    if resultado.falhas_adaptadores:
        envios.append(notificar(
            "falha_adaptador", "Adaptador parado",
            "\n".join(f"- {f}" for f in resultado.falhas_adaptadores) + "\n\nConfira com 'agente saude' e reative quando estiver ok.",
            central,
        ))
    from .funil import carregar_lembretes, vencidos

    if lembretes := vencidos(carregar_lembretes()):
        envios.append(notificar(
            "lembrete_funil", f"{len(lembretes)} lembrete(s) do funil",
            "\n".join(f"- {l.descricao} ({l.quando.astimezone():%d/%m %H:%M})" for l in lembretes)
            + "\n\nVeja 'agente funil lembretes'.", central,
        ))
    feitos = [e for e in envios if e]
    if not feitos:
        return
    console.print(f"[dim]{len(feitos)} notificação(ões) — canal: {', '.join(sorted({e.canal for e in feitos}))}.[/dim]")
    if erro := next((e.erro for e in feitos if e.erro), None):
        console.print(f"[yellow]Notificações ficaram só em arquivo: {escape(erro)}[/yellow]")


def _tabela_resumo(itens) -> None:
    if not itens:
        console.print("Nenhuma vaga nova recomendável nesta rodada.")
        return
    tabela = Table(title=f"Vagas novas por aderência ({len(itens)})")
    for col in ("ID", "Nota", "Ação", "Vaga", "Empresa", "Local"):
        tabela.add_column(col, overflow="fold")
    for i in itens:
        cor = "green" if i.acao == "candidatar" else "yellow" if i.acao == "salvar" else "dim"
        tabela.add_row(i.id, i.nota_texto, f"[{cor}]{i.acao}[/{cor}]", Text(i.titulo), Text(i.empresa or "?"),
                       Text(" · ".join(p for p in [i.local, i.modelo] if p)))
    console.print(tabela)


@vagas_app.command("link")
def vagas_link(
    url: str = typer.Argument(..., help="Link da vaga."),
    descricao: Path | None = typer.Option(None, "--descricao", exists=True, readable=True,
                                          help="Arquivo com a descrição copiada (obrigatório para LinkedIn, Indeed e afins)."),
    titulo: str | None = typer.Option(None, "--titulo"),
    empresa: str | None = typer.Option(None, "--empresa"),
    local: str | None = typer.Option(None, "--local"),
) -> None:
    """Adiciona uma vaga a partir de um link seu: lê a página se permitido, ou usa a descrição colada (RF-VG-02)."""
    from .radar.coleta import ColetaCopiloto, ColetaErro, baixar, canonizar_link, dominio, vaga_de_link
    from .radar.modelos import VagaBruta
    from .radar.rodada import processar

    perfil = _perfil()
    config = carregar_config()
    if descricao:
        if not titulo:
            titulo = typer.prompt("Título da vaga")
        bruta = VagaBruta(
            titulo=titulo, empresa=empresa, local=local, link=canonizar_link(url),
            descricao=descricao.read_text(encoding="utf-8"), fonte_tipo="link", fonte_origem=f"link:{dominio(url)}",
        )
    else:
        from .configuracao import carregar_configuracao, plataforma_permite_leitura

        central = carregar_configuracao()
        if not plataforma_permite_leitura(central, url):
            motivo = "o modo somente sugestão está ligado" if central.somente_sugestao else "essa plataforma está desligada"
            console.print(f"[yellow]A página não foi lida: {motivo} (RF-OP-02).[/yellow] Cole a descrição num arquivo e rode:\n"
                          "  agente vagas link URL --descricao vaga.txt --titulo \"...\" --empresa \"...\"")
            raise typer.Exit(1)
        try:
            bruta = vaga_de_link(url, baixar, config.dominios_copiloto)
        except ColetaCopiloto as erro:
            console.print(
                f"[yellow]Os termos de {escape(str(erro))} proíbem leitura automatizada (RN-04).[/yellow] Copie a descrição "
                "da vaga para um arquivo .txt e rode:\n  agente vagas link URL --descricao vaga.txt --titulo \"...\" --empresa \"...\""
            )
            raise typer.Exit(1)
        except ColetaErro as erro:
            console.print(f"[red]{escape(str(erro))}[/red]")
            raise typer.Exit(1)
        bruta.titulo = titulo or bruta.titulo
        bruta.empresa = empresa or bruta.empresa
        bruta.local = local or bruta.local

    base = carregar_base()
    proc = processar([bruta], base, perfil, config, date.today(), enriquecer_links=False)
    salvar_base(base)
    vaga = proc.destinos[0]
    if vaga not in proc.adicionadas:
        console.print("[cyan]Essa vaga já estava na base; a nova fonte foi juntada a ela (RF-VG-05).[/cyan]")
    _mostrar_alertas(proc.alertas, proc.arquivo_alerta, config.limiar_alerta)
    if proc.alertas:
        from .configuracao import carregar_configuracao
        from .operacao.notificacoes import notificar

        notificar("vaga_acima_limiar", f"Vaga com aderência ≥ {config.limiar_alerta}",
                  "\n".join(f"- {v.titulo} — {v.empresa or '?'} ({v.nota}): {v.link or 'sem link'}" for v in proc.alertas),
                  carregar_configuracao())
    _mostrar_vaga(vaga)


# ---------------------------------------------------------------- consulta

def _mostrar_vaga(v: VagaEncontrada) -> None:
    linhas = [
        f"[bold]{escape(v.titulo)}[/bold] — {escape(v.empresa or 'empresa não informada')}",
        f"Status: {v.status} · Nota: {v.nota} · Busca: {escape(v.busca or '—')}",
        f"Local: {escape(v.local or '—')} · Modelo: {v.modelo or '—'} · Contrato: {v.contrato or '—'} · Nível: {v.nivel or '—'}",
    ]
    if v.salario_min:
        faixa = f"R$ {v.salario_min:,.0f}".replace(",", ".")
        if v.salario_max and v.salario_max != v.salario_min:
            faixa += f" a R$ {v.salario_max:,.0f}".replace(",", ".")
        linhas.append(f"Salário: {faixa}")
    if v.horas_dia or v.horas_semana:
        linhas.append(f"Jornada: {v.horas_dia or '?'}h/dia · {v.horas_semana or '?'}h/semana")
    if v.publicada_em or v.valida_ate:
        linhas.append(f"Publicada: {v.publicada_em or '—'} · Válida até: {v.valida_ate or '—'}")
    linhas.append(f"Link: {escape(v.link or '—')}")
    linhas.append("Fontes: " + escape(", ".join(f"{f.origem} ({f.tipo})" for f in v.fontes)))
    from .ia import autoria

    if v.aderencia:
        linhas.append(f"\n[bold]Aderência {v.nota} ({autoria(None)}):[/bold] {escape(v.aderencia.justificativa)}")
    if v.justificativa_ia:
        linhas.append(f"[bold]Justificativa ({escape(autoria(v.motor_justificativa))}):[/bold] {escape(v.justificativa_ia)}")
    if v.requisitos_obrigatorios:
        linhas.append("[bold]Obrigatórios:[/bold] " + escape("; ".join(v.requisitos_obrigatorios)))
    if v.requisitos_desejaveis:
        linhas.append("[bold]Desejáveis:[/bold] " + escape("; ".join(v.requisitos_desejaveis)))
    for s in v.sinais:
        cor = "red" if s.gravidade == "forte" else "yellow"
        linhas.append(f"[{cor}]⚠ {escape(s.mensagem)}[/{cor}]")
    for m in v.motivos_eliminacao:
        linhas.append(f"[red]Eliminada: {escape(m)}[/red]")
    if v.motivo_expiracao and v.status == "expirada":
        linhas.append(f"[dim]Expirada: {escape(v.motivo_expiracao)}[/dim]")
    if v.feedback:
        linhas.append(f"Seu feedback: {'interessa' if v.feedback.interessa else 'não interessa'}"
                      + (f" ({escape(v.feedback.motivo)})" if v.feedback.motivo else ""))
    console.print(Panel("\n".join(linhas), title=f"Vaga {v.id}", border_style="cyan"))


@vagas_app.command("listar")
def vagas_listar(
    status: str | None = typer.Option(None, "--status", help="nova, no_resumo, salva, descartada, expirada ou eliminada."),
    minimo: int = typer.Option(0, "--minimo", help="Nota mínima."),
) -> None:
    """Lista as vagas encontradas."""
    base = carregar_base()
    vagas = [v for v in base.itens if (status is None or v.status == status) and v.nota >= minimo]
    if not vagas:
        console.print("Nenhuma vaga com esses critérios.")
        return
    tabela = Table(title=f"Vagas encontradas ({len(vagas)})")
    for col in ("ID", "Nota", "Status", "Vaga", "Empresa", "Local", "Fontes"):
        tabela.add_column(col, overflow="fold")
    for v in sorted(vagas, key=lambda x: -x.nota):
        tabela.add_row(v.id, str(v.nota), v.status + (" ⚠" if v.risco else ""), Text(v.titulo), Text(v.empresa or "?"),
                       Text(v.local or ""), str(len(v.fontes)))
    console.print(tabela)


@vagas_app.command("ver")
def vagas_ver(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Detalhes de uma vaga: campos extraídos, justificativa, sinais e fontes."""
    _mostrar_vaga(_vaga(carregar_base(), id_))


@vagas_app.command("resumo")
def vagas_resumo(
    data: str | None = typer.Option(None, "--data", help="AAAA-MM-DD; padrão: o mais recente."),
    ia: bool = typer.Option(False, "--ia", help="Gera o prompt da justificativa escrita das vagas do último resumo (com autorização)."),
    motor: str | None = typer.Option(None, "--motor", help="claude, gemini ou local; padrão: o configurado."),
) -> None:
    """Mostra o resumo diário; com --ia, prepara a justificativa escrita por IA (RF-VG-09, RF-IA-02)."""
    if ia:
        from .cli import _usar_ia
        from .radar.resumo import dados_enviados_justificativa, prompt_justificativas

        base = carregar_base()
        vagas = [v for v in base.itens if v.id in base.ultimo_resumo_ids]
        if not vagas:
            console.print("[yellow]O último resumo não tem vagas recomendáveis.[/yellow]")
            raise typer.Exit(1)
        perfil = _perfil()
        dia = base.ultimo_resumo_data or date.today()
        uso = _usar_ia(
            perfil, "justificativa-vagas", motor, dados_enviados_justificativa(vagas),
            lambda m: prompt_justificativas(vagas, perfil, m),
            lambda m: f"prompt-justificativas-{dia:%Y-%m-%d}-{m}.md",
        )
        if uso:
            console.print(f"Cole no {uso.motor.capitalize()}, salve a resposta e rode: "
                          f"agente vagas justificativas <resposta.md> --motor {uso.motor}")
        return

    pasta = diretorio_dados() / "resumos"
    arquivos = sorted(pasta.glob("resumo-*.md")) if pasta.is_dir() else []
    if data:
        arquivos = [a for a in arquivos if a.stem == f"resumo-{data}"]
    if not arquivos:
        console.print("Nenhum resumo encontrado. Rode 'agente vagas rodada'.")
        raise typer.Exit(1)
    console.print(Markdown(arquivos[-1].read_text(encoding="utf-8")))


@vagas_app.command("justificativas")
def vagas_justificativas(
    arquivo: Path = typer.Argument(..., exists=True, readable=True, help="Resposta do motor com as linhas '### VAGA: <id>'."),
    motor: str = typer.Option(..., "--motor", help="Motor que escreveu (claude ou gemini)."),
) -> None:
    """Anexa às vagas as justificativas escritas pela IA, identificando o motor (RF-IA-06)."""
    from .cli import _checar_recusa
    from .ia import carregar_usos, registrar_resultado, salvar_usos
    from .radar.resumo import ler_justificativas

    conteudo = arquivo.read_text(encoding="utf-8")
    if _checar_recusa(conteudo, "justificativa-vagas", motor):
        raise typer.Exit(0)
    textos = ler_justificativas(conteudo)
    if not textos:
        console.print("[red]Nenhuma justificativa reconhecida — a resposta precisa manter as linhas '### VAGA: <id>'.[/red]")
        raise typer.Exit(1)
    base = carregar_base()
    anexadas = 0
    for id_, texto in textos.items():
        try:
            vaga = base.buscar(id_)
        except ValueError:
            continue
        vaga.justificativa_ia, vaga.motor_justificativa = texto, motor
        anexadas += 1
    salvar_base(base)
    usos = carregar_usos()
    if registrar_resultado(usos, "justificativa-vagas", motor, f"resposta registrada: {anexadas} justificativa(s)"):
        salvar_usos(usos)
    console.print(f"[green]{anexadas} justificativa(s) anexada(s).[/green]")


# ---------------------------------------------------------------- decisões e feedback (RF-VG-11)

@vagas_app.command("feedback")
def vagas_feedback(
    id_: str = typer.Argument(..., metavar="ID"),
    interessa: bool = typer.Option(..., "--interessa/--nao-interessa"),
    motivo: str | None = typer.Option(None, "--motivo", help="area, requisitos, nivel, modelo, local, salario, empresa ou outro."),
) -> None:
    """Registra se a vaga interessa e por quê; o agente ajusta pesos e sugere filtros (RF-VG-11)."""
    from .radar.acoes import aceitar_sugestoes, registrar_feedback

    try:
        sugestoes = registrar_feedback(id_, interessa, motivo)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    console.print("[green]Feedback registrado.[/green] Pesos ajustados para as próximas rodadas.")
    aceitas = [s for s in sugestoes if typer.confirm(f"Ajustar o filtro: {s.descricao}?", default=False)]
    aceitar_sugestoes(aceitas)
    for sugestao in aceitas:
        console.print(f"[green]Filtro ajustado: {escape(sugestao.descricao)}.[/green]")


@vagas_app.command("salvar")
def vagas_salvar(
    id_: str = typer.Argument(..., metavar="ID"),
    foco: str | None = typer.Option(None, "--foco", help="Foco da vaga-alvo; padrão: a busca da vaga, se for um foco."),
) -> None:
    """Salva a vaga: entra nas vagas-alvo que alimentam a otimização do CV (RF-CV-01)."""
    from .radar.acoes import FocoNecessario, salvar_vaga

    _vaga(carregar_base(), id_)  # vaga inexistente: mensagem clara
    try:
        foco_final = salvar_vaga(id_, foco)
    except FocoNecessario:
        foco_final = salvar_vaga(id_, typer.prompt(f"Foco da vaga-alvo ({', '.join(SINONIMOS_POR_FOCO)})"))
    console.print(f"[green]Vaga salva e adicionada às vagas-alvo (foco {escape(foco_final)}).[/green]")


@vagas_app.command("descartar")
def vagas_descartar(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Descarta a vaga (some dos próximos resumos)."""
    from .radar.acoes import descartar_vaga

    _vaga(carregar_base(), id_)  # vaga inexistente: mensagem clara
    descartar_vaga(id_)
    console.print("[green]Vaga descartada.[/green] Dica: 'agente vagas feedback ID --nao-interessa --motivo ...' ensina o agente.")


@vagas_app.command("config")
def vagas_config(
    limiar_alerta: int | None = typer.Option(None, "--limiar-alerta"),
    limiar_candidatar: int | None = typer.Option(None, "--limiar-candidatar"),
    limiar_salvar: int | None = typer.Option(None, "--limiar-salvar"),
    dias_validade: int | None = typer.Option(None, "--dias-validade"),
    permitir_dominio: str | None = typer.Option(None, "--permitir-dominio", help="Domínio cujas páginas de vaga podem ser lidas."),
    remoto: str | None = typer.Option(None, "--remoto", help="Vagas remotas: qualquer (de qualquer lugar), brasil "
                                      "(só de empresas no Brasil) ou nao (nenhuma)."),
) -> None:
    """Mostra ou ajusta limiares, validade das vagas, vagas remotas e domínios permitidos."""
    config = carregar_config()
    if remoto is not None and remoto not in ("qualquer", "brasil", "nao"):
        console.print("[red]Use --remoto qualquer, brasil ou nao.[/red]")
        raise typer.Exit(1)
    for campo, valor in (("limiar_alerta", limiar_alerta), ("limiar_candidatar", limiar_candidatar),
                         ("limiar_salvar", limiar_salvar), ("dias_validade", dias_validade), ("remoto", remoto)):
        if valor is not None:
            setattr(config, campo, valor)
    if permitir_dominio and permitir_dominio not in config.dominios_permitidos:
        config.dominios_permitidos.append(permitir_dominio)
    salvar_config(config)
    console.print(
        f"Limiar de alerta: {config.limiar_alerta} · candidatar: {config.limiar_candidatar} · salvar: {config.limiar_salvar}\n"
        f"Validade: {config.dias_validade} dias · Rodada: {config.hora_rodada} · Remotas: {config.remoto}\n"
        f"Domínios permitidos: {', '.join(config.dominios_permitidos)}\n"
        f"Só copiloto (termos proíbem leitura automatizada): {', '.join(config.dominios_copiloto)}\n"
        f"Pesos aprendidos: {len(config.preferencias)}"
    )


@vagas_app.command("agendar")
def vagas_agendar(
    hora: str = typer.Option("07:00", "--hora", help="Horário diário da rodada (HH:MM)."),
    mostrar: bool = typer.Option(False, "--mostrar", help="Só mostra o comando, sem criar a tarefa."),
) -> None:
    """Agenda a rodada diária no sistema (padrão: 7h, para o resumo sair antes das 8h) (RF-VG-03).

    No Windows a busca roda sem janela; se o PC estiver desligado ou suspenso no horário, ela roda assim que
    ele voltar.
    """
    from .operacao import agendada
    from .radar.agenda import NOME_TAREFA, linha_cron, validar_hora

    try:
        hora = validar_hora(hora)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    config = carregar_config()
    config.hora_rodada = hora

    if sys.platform != "win32":
        console.print("Adicione esta linha ao seu crontab ('crontab -e'):")
        console.print(linha_cron(Path.cwd(), shutil.which("uv") or "uv", hora), markup=False, highlight=False)
        salvar_config(config)
        return

    if mostrar:
        xml, comando = agendada.preparar(NOME_TAREFA, ["vagas", "rodada"], hora)
        console.print(xml.read_text(encoding="utf-16"), markup=False, highlight=False)
        console.print(" ".join(comando), markup=False, highlight=False)
        return
    if not typer.confirm(f"Criar a tarefa '{NOME_TAREFA}' no Agendador do Windows, todo dia às {hora}?"):
        raise typer.Exit(0)
    try:
        agendada.instalar(NOME_TAREFA, ["vagas", "rodada"], hora)
    except RuntimeError as erro:
        console.print(f"[red]Falha ao criar a tarefa: {escape(str(erro))}[/red]")
        raise typer.Exit(1)
    salvar_config(config)
    console.print(f"[green]Busca agendada para {hora} todos os dias, sem janela.[/green] Se o PC estiver desligado "
                  "ou suspenso nesse horário, ela roda assim que ele voltar. Registro em data/rodada.log.")


@vagas_app.command("gupy")
def vagas_gupy(termo: str = typer.Argument("estágio ti", help="O que pesquisar no portal da Gupy.")) -> None:
    """Pesquisa agora no portal da Gupy e mostra as vagas (não salva nada)."""
    from .radar.gupy_portal import NavegadorPublico, buscar

    with NavegadorPublico() as abrir:
        vagas, avisos = buscar(abrir, [termo])
    console.print(f"[green]{len(vagas)} vaga(s) na Gupy para '{escape(termo)}':[/green]")
    for v in vagas[:25]:
        detalhes = " · ".join(x for x in (v.local, v.modelo, v.contrato, f"{v.publicada_em:%d/%m}" if v.publicada_em else None) if x)
        console.print(f"• {escape(v.titulo)} — {escape(v.empresa or '?')} [dim]({escape(detalhes)})[/dim]")
    for aviso in avisos:
        console.print(f"[dim]{escape(aviso)}[/dim]")


def andamento_cmd() -> None:
    """Mostra o que o agente está fazendo agora (ou o resultado da última tarefa longa)."""
    from .operacao import andamento

    estado = andamento.ler()
    if estado is None:
        console.print("Nenhuma tarefa longa registrada ainda.")
        return
    cor = "magenta" if estado.get("rodando") else "green" if estado.get("situacao") == "concluida" else "yellow"
    console.print(f"[{cor}]{escape(andamento.descrever(estado))}[/{cor}]")
    for linha in andamento.ultimas_linhas(15):
        console.print(f"[dim]{escape(linha)}[/dim]")


def caminho_cv_da_vaga(vaga_id: str, idioma: str = "pt") -> Path:
    return diretorio_dados() / "saidas" / f"cv-vaga-{vaga_id}-{idioma}.pdf"


@vagas_app.command("curriculo")
def vagas_curriculo(
    id_: str = typer.Argument(..., metavar="ID"),
    idioma: str | None = typer.Option(None, "--idioma", help="pt ou en; padrão: o idioma do anúncio (RF-EV-10)."),
) -> None:
    """Gera o currículo sob medida desta vaga (PDF) e mostra o que mudou em relação ao currículo-base (RF-EV-09)."""
    from .analise.exportar import exportar_pdf
    from .analise.sob_medida import gerar_sob_medida
    from .cli_comum import _bloquear_sem_lastro
    from .confirmacao import pendencias_na_variante
    from .vagas import Vaga

    vaga = _vaga(carregar_base(), id_)
    perfil = _perfil()
    idioma = idioma or ("en" if vaga.idioma == "en" else "pt")
    foco = vaga.busca if vaga.busca in SINONIMOS_POR_FOCO else next(iter(SINONIMOS_POR_FOCO))
    nivel = vaga.nivel if vaga.nivel in ("estagio", "trainee", "junior") else "estagio"
    alvo = Vaga(titulo=vaga.titulo, empresa=vaga.empresa, foco=foco, url=vaga.link,
                descricao=vaga.descricao or vaga.titulo)
    try:
        resultado = gerar_sob_medida(perfil, alvo, foco=foco, idioma=idioma, nivel=nivel)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    console.print(f"[bold]Currículo sob medida para:[/bold] {escape(vaga.titulo)}"
                  + (f" — {escape(vaga.empresa)}" if vaga.empresa else ""))
    if not vaga.descricao:
        console.print("[yellow]A descrição da vaga ainda não foi lida: o ajuste usou só o título.[/yellow]")
    console.print("\n[bold]O que mudou em relação ao currículo-base:[/bold]")
    for mudanca in resultado.mudancas or ["nada de ordem: o currículo-base já estava alinhado a esta vaga"]:
        console.print(f"  • {escape(mudanca)}")
    # As tecnologias reconhecidas na nota (os termos soltos do anúncio incluem "café", "almoço"...).
    atendidos = vaga.aderencia.atendidos if vaga.aderencia else []
    lacunas = vaga.aderencia.lacunas if vaga.aderencia else []
    console.print(f"\n[green]Tecnologias da vaga que você tem ({len(atendidos)}):[/green] " + escape(", ".join(atendidos) or "—"))
    console.print(f"[red]Que ela pede e não estão no seu perfil ({len(lacunas)}):[/red] " + escape(", ".join(lacunas) or "—"))
    pendencias = pendencias_na_variante(resultado.variante)
    if pendencias:
        console.print("[red]O PDF não foi gerado: há frases [A CONFIRMAR] no seu perfil. Confirme em 'agente confirmar'.[/red]")
        raise typer.Exit(1)
    _bloquear_sem_lastro(resultado.variante, perfil)
    caminho, paginas = exportar_pdf(resultado.variante, caminho_cv_da_vaga(vaga.id, idioma))
    console.print(f"\n[green]PDF pronto[/green] ({paginas} pág.): {caminho}")


@vagas_app.command("conferir")
def vagas_conferir(
    limite: int = typer.Option(20, "--limite", help="Quantas vagas do LinkedIn abrir no máximo."),
) -> None:
    """Abre as vagas recomendadas e salvas para ver se ainda aceitam candidaturas; as fechadas saem da lista.

    A busca diária já confere algumas por dia; este comando confere agora. LinkedIn: pelo navegador do agente, com a
    automação ligada. Gupy e outros sites permitidos: pelo link, respeitando o robots.txt.
    """
    from .configuracao import carregar_configuracao
    from .operacao import andamento
    from .operacao.saude import carregar_saude, salvar_saude
    from .radar.coleta import baixar
    from .radar.rodada import ABERTAS, expirar

    from datetime import datetime, timedelta, timezone

    central = carregar_configuracao()
    base, config = carregar_base(), carregar_config()
    recente = datetime.now(timezone.utc) - timedelta(hours=6)  # conferida há pouco: não abre de novo
    abertas = [v for v in base.itens if v.status in ABERTAS and not v.risco
               and (v.conferida_em is None or v.conferida_em < recente)]
    with andamento.tarefa("Conferir vagas") as registro:
        lidas = 0
        if central.linkedin_automatico.ativo:
            from .linkedin.automatico import enriquecedor_da_rodada

            saude = carregar_saude()
            lidas = enriquecedor_da_rodada(central.linkedin_automatico, saude, limite=limite)(abertas, conferir_todas=True)
            salvar_saude(saude)
        else:
            console.print("[yellow]A automação do LinkedIn está desligada: as vagas do LinkedIn não foram abertas.[/yellow]")
        andamento.etapa("Conferindo os links dos outros sites")
        expiradas = expirar(base, date.today(), config, baixar_fn=baixar, verificar_links=True)
        if lidas:  # descrições novas mudam a nota (e podem mostrar que a vaga não serve)
            from .radar.rodada import reavaliar_base

            reavaliar_base(base, _perfil(), config, date.today())
        salvar_base(base, preferir="disco")
        registro["resultado"] = f"{len(expiradas)} vaga(s) encerrada(s)"
    console.print(f"{lidas} vaga(s) do LinkedIn abertas e conferidas.")
    if not expiradas:
        console.print("[green]Todas as vagas conferidas continuam abertas.[/green]")
        return
    console.print(f"[yellow]{len(expiradas)} vaga(s) não aceitam mais candidaturas e saíram da lista:[/yellow]")
    for v in expiradas:
        console.print(f"• {escape(v.titulo)} — {escape(v.empresa or '?')} [dim]({escape(v.motivo_expiracao or '')})[/dim]")


@vagas_app.command("reavaliar")
def vagas_reavaliar(
    ler_descricoes: int = typer.Option(0, "--ler-descricoes", help="Antes, lê a descrição de até N vagas do LinkedIn "
                                       "sem descrição (navegador do agente; precisa da automação ligada)."),
) -> None:
    """Dá nota de novo às vagas guardadas com o perfil atual e refaz o resumo do dia (não busca nada)."""
    from .configuracao import carregar_configuracao
    from .operacao.saude import carregar_saude, salvar_saude
    from .radar.rodada import REAVALIAVEIS, reavaliar_base

    perfil, config, base = _perfil(), carregar_config(), carregar_base()
    central = carregar_configuracao()
    if ler_descricoes and central.linkedin_automatico.ativo:
        from .linkedin.automatico import enriquecedor_da_rodada

        saude = carregar_saude()
        alvo = [v for v in base.itens if v.status in (*REAVALIAVEIS, "eliminada") and (not v.descricao or not v.local)]
        lidas = enriquecedor_da_rodada(central.linkedin_automatico, saude, limite=ler_descricoes)(alvo)
        salvar_saude(saude)
        console.print(f"LinkedIn: {lidas} descrição(ões) lida(s).")
    liberadas, resumo, arquivo = reavaliar_base(base, perfil, config, date.today())
    salvar_base(base, preferir="disco")
    console.print(f"[green]{liberadas} vaga(s) voltaram a valer[/green] · {len(resumo.itens)} recomendada(s) no resumo.")
    _tabela_resumo(resumo.itens)
    console.print(f"Resumo salvo em {arquivo}")
