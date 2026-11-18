"""Currículo: análise, otimização, revisão, versões sob medida e CV enviado (RF-CV-01 a RF-CV-14)."""

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

cv_app = typer.Typer(help="Otimização do currículo (RF-CV-01 a RF-CV-14).", no_args_is_help=True)
candidatura_app = typer.Typer(help="Candidaturas e CV enviado (RF-CV-10, RF-CV-14).", no_args_is_help=True)


# ---------------------------------------------------------------- otimização de CV

def _conjunto_ou_sai(foco: str | None, limite: int):
    conjunto = conjunto_de_analise(carregar_vagas(), foco=foco, limite=limite)
    if not conjunto:
        console.print("[yellow]Nenhuma vaga-alvo salva" + (f" para o foco {foco!r}" if foco else "") + ". Use 'agente vaga adicionar'.[/yellow]")
        raise typer.Exit(1)
    return conjunto


@cv_app.command("termos")
def cv_termos(
    foco: str | None = typer.Option(None, "--foco"),
    limite: int = typer.Option(30, "--limite", help="Tamanho do conjunto de vagas (padrão 30)."),
) -> None:
    """Extrai requisitos, competências e termos mais frequentes das vagas-alvo (RF-CV-01)."""
    from .analise.termos import extrair_termos

    conjunto = _conjunto_ou_sai(foco, limite)
    termos = extrair_termos(conjunto)
    tabela = Table(title=f"Termos mais frequentes em {len(conjunto)} vaga(s)" + (f" — foco {foco}" if foco else ""))
    tabela.add_column("Termo")
    tabela.add_column("Vagas")
    tabela.add_column("%")
    tabela.add_column("Tipo")
    for t in termos:
        tabela.add_row(t.termo, f"{t.vagas_em_que_aparece}/{t.total_de_vagas}", f"{t.percentual}%", "tecnologia" if t.e_tecnologia else "termo")
    console.print(tabela)


@cv_app.command("lacunas")
def cv_lacunas(
    foco: str | None = typer.Option(None, "--foco"),
    limite: int = typer.Option(30, "--limite"),
) -> None:
    """Relatório de lacunas em três grupos (RF-CV-02)."""
    from .analise.lacunas import gerar_relatorio
    from .analise.termos import extrair_termos

    perfil = carregar_perfil()
    conjunto = _conjunto_ou_sai(foco, limite)
    relatorio = gerar_relatorio(perfil, extrair_termos(conjunto))

    def _secao(titulo: str, cor: str, itens, dica: str) -> None:
        console.print(f"\n[bold {cor}]{titulo}[/bold {cor}] — {dica}")
        if not itens:
            console.print("  (nenhum)")
        for item in itens:
            extra = f" — encontrado em: {item.onde_encontrado}" if item.onde_encontrado else ""
            console.print(f"  • {escape(item.termo)} ({item.vagas_em_que_aparece} vaga(s), {item.percentual}%){escape(extra)}")
            mais = f" e mais {len(item.origens) - 3}" if len(item.origens) > 3 else ""
            console.print(f"    [dim]de: {escape('; '.join(item.origens[:3]))}{mais}[/dim]")

    console.print(f"[bold]Relatório de lacunas[/bold] — conjunto de {relatorio.total_de_vagas} vaga(s)")
    _secao("1. Você tem e já está no CV", "green", relatorio.ja_no_cv, "nada a fazer")
    _secao("2. Você tem, mas não aparece", "yellow", relatorio.tem_mas_nao_aparece, "basta destacar no CV")
    _secao("3. Você não tem (ou não registrou)", "red", relatorio.nao_tem, "fechar de verdade — nunca inventar (RN-02)")


@cv_app.command("ordenar")
def cv_ordenar(
    nivel: str = typer.Option("estagio", "--nivel", help="Nível-alvo: estagio, trainee, junior, pleno, senior."),
) -> None:
    """Mostra a ordem de seções e itens pelo peso no nível-alvo (RF-CV-04)."""
    from .analise.ordenacao import ordenar_cv

    perfil = carregar_perfil()
    estrutura = ordenar_cv(perfil, nivel=nivel)
    if not estrutura.secoes:
        console.print("[yellow]Perfil ainda sem conteúdo para ordenar.[/yellow]")
        raise typer.Exit(0)
    console.print(f"[bold]Ordem proposta para o CV — nível {nivel}[/bold]")
    for i, secao in enumerate(estrutura.secoes, 1):
        motivo = f" [dim]({secao.motivo})[/dim]" if secao.motivo else ""
        console.print(f"\n{i}. [bold cyan]{secao.titulo}[/bold cyan]{motivo}")
        for item in secao.itens:
            console.print(f"   • {item}")


@cv_app.command("nota")
def cv_nota(
    foco: str | None = typer.Option(None, "--foco"),
    limite: int = typer.Option(30, "--limite"),
    nivel: str = typer.Option("estagio", "--nivel"),
) -> None:
    """Calcula a nota de compatibilidade com ATS e mostra o que mudou (RF-CV-05)."""
    from .analise.ats import calcular_nota, comparar, registrar_nota
    from .analise.termos import extrair_termos

    perfil = carregar_perfil()
    conjunto = conjunto_de_analise(carregar_vagas(), foco=foco, limite=limite)
    termos = extrair_termos(conjunto)
    nota = calcular_nota(perfil, termos, foco=foco, nivel=nivel)
    anterior = registrar_nota(nota)

    tabela = Table(title=f"Nota ATS: {nota.total}/100" + (f" — foco {foco}" if foco else ""))
    tabela.add_column("Critério", overflow="fold")
    tabela.add_column("Pontos")
    tabela.add_column("Detalhe", overflow="fold")
    for item in nota.itens:
        tabela.add_row(item.criterio, f"{item.pontos}/{item.maximo}", item.detalhe or "")
    console.print(tabela)

    if anterior:
        console.print("[bold]O que mudou desde a última revisão:[/bold]")
        mudancas = comparar(anterior, nota)
        if len(mudancas) == 1:
            console.print(f"  • {mudancas[0]} — demais critérios sem mudança")
        else:
            for m in mudancas:
                console.print(f"  • {m}")
    else:
        console.print("[dim]Primeira revisão registrada; as próximas mostrarão o que mudou.[/dim]")


@cv_app.command("fechar-lacunas")
def cv_fechar_lacunas(
    foco: str | None = typer.Option(None, "--foco"),
    limite: int = typer.Option(30, "--limite"),
) -> None:
    """Sugere curso, certificação ou projeto para cada lacuna sem lastro (RF-CV-06)."""
    from .analise.fechamento import sugerir_fechamento
    from .analise.lacunas import gerar_relatorio
    from .analise.termos import extrair_termos

    perfil = carregar_perfil()
    conjunto = _conjunto_ou_sai(foco, limite)
    relatorio = gerar_relatorio(perfil, extrair_termos(conjunto))
    if not relatorio.nao_tem:
        console.print("[green]Nenhuma lacuna sem lastro: todos os termos das vagas têm base no perfil.[/green]")
        return

    console.print(
        f"[bold]Como fechar de verdade as {len(relatorio.nao_tem)} lacuna(s)[/bold] "
        "[dim](nunca inventar no CV — RN-02)[/dim]"
    )
    sugestoes = sugerir_fechamento(relatorio.nao_tem)
    termo_atual = None
    for s in sugestoes:
        if s.termo != termo_atual:
            termo_atual = s.termo
            peso = next((i for i in relatorio.nao_tem if i.termo == s.termo), None)
            info = f" — pedido em {peso.vagas_em_que_aparece} vaga(s) ({peso.percentual}%)" if peso else ""
            console.print(f"\n[bold red]{s.termo}[/bold red]{info}")
        rotulo = {"curso": "Curso", "certificacao": "Certificação", "projeto": "Projeto"}[s.tipo]
        origem = f" [{s.catalogo}]" if s.catalogo else ""
        console.print(f"  • {rotulo}{origem}: {s.descricao}")


@cv_app.command("variante")
def cv_variante(
    foco: str = typer.Option(..., "--foco", help="Foco: backend-dotnet, cloud-aws, mobile, dados ou suporte."),
    idioma: str = typer.Option("pt", "--idioma", help="pt ou en."),
    nivel: str = typer.Option("estagio", "--nivel"),
) -> None:
    """Gera uma variante do CV por foco e idioma, derivada da versão-base (RF-CV-07)."""
    from .analise.variantes import gerar_variante

    perfil = carregar_perfil()
    try:
        variante = gerar_variante(perfil, foco=foco, idioma=idioma, nivel=nivel)
    except ValueError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(1)

    destino = diretorio_dados() / "variantes" / f"{variante.nome_arquivo}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(variante.model_dump_json(indent=2), encoding="utf-8")

    console.print(f"[bold]{variante.nome}[/bold]")
    for linha in variante.cabecalho:
        console.print(f"[dim]{linha}[/dim]")
    for secao in variante.secoes:
        console.print(f"\n[bold cyan]{secao.titulo.upper()}[/bold cyan]")
        if secao.paragrafo:
            console.print(f"  {secao.paragrafo}")
        for item in secao.itens:
            detalhes = " — ".join(p for p in [item.subtitulo, item.periodo] if p)
            estrela = " [yellow]*[/yellow]" if item.relevancia else ""
            console.print(f"  [bold]{item.titulo}[/bold]" + (f" | {detalhes}" if detalhes else "") + estrela)
            for marcador in item.marcadores:
                console.print(f"    • {marcador}")
    console.print(f"\n[green]Variante salva em[/green] {destino}  [dim](* = item relevante ao foco)[/dim]")
    if idioma == "en":
        console.print("[yellow]Títulos e rótulos em inglês; os textos permanecem como registrados — traduza o conteúdo via 'agente cv reescrever' (RN-02).[/yellow]")


@cv_app.command("exportar")
def cv_exportar(
    foco: str = typer.Option(..., "--foco", help="Foco: backend-dotnet, cloud-aws, mobile, dados ou suporte."),
    idioma: str = typer.Option("pt", "--idioma", help="pt ou en."),
    nivel: str = typer.Option("estagio", "--nivel"),
    formato: str = typer.Option("ambos", "--formato", help="pdf, docx ou ambos."),
    paginas: int | None = typer.Option(None, "--paginas", help="Tamanho-alvo em páginas (padrão: 1 para estágio/júnior, 2 nos demais)."),
) -> None:
    """Exporta a variante em PDF/DOCX com layout compatível com ATS (RF-CV-08)."""
    from .analise.exportar import (
        aviso_de_tamanho,
        estimar_paginas_docx,
        exportar_docx,
        exportar_pdf,
        paginas_alvo_padrao,
    )
    from .analise.variantes import gerar_variante

    if formato not in {"pdf", "docx", "ambos"}:
        console.print(f"[red]Formato inválido: {formato}. Use pdf, docx ou ambos.[/red]")
        raise typer.Exit(1)
    perfil = carregar_perfil()
    try:
        variante = gerar_variante(perfil, foco=foco, idioma=idioma, nivel=nivel)
    except ValueError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(1)

    from .confirmacao import pendencias_na_variante

    pendencias = pendencias_na_variante(variante)
    if pendencias:
        console.print("[red]Exportação bloqueada (RF-CV-13): há frases [A CONFIRMAR] no material:[/red]")
        for p in pendencias:
            console.print(f"  • {p}")
        console.print("Revise com 'agente confirmar' e exporte de novo.")
        raise typer.Exit(1)
    _bloquear_sem_lastro(variante, perfil)

    alvo = paginas if paginas is not None else paginas_alvo_padrao(nivel)
    pasta = diretorio_dados() / "saidas"
    avisos: list[str] = []

    if formato in {"pdf", "ambos"}:
        caminho_pdf, n_paginas = exportar_pdf(variante, pasta / f"{variante.nome_arquivo}.pdf")
        console.print(f"[green]PDF gerado em[/green] {caminho_pdf} ({n_paginas} página(s))")
        if aviso := aviso_de_tamanho(n_paginas, alvo, "PDF"):
            avisos.append(aviso)
    if formato in {"docx", "ambos"}:
        caminho_docx = exportar_docx(variante, pasta / f"{variante.nome_arquivo}.docx")
        estimadas = estimar_paginas_docx(variante)
        console.print(f"[green]DOCX gerado em[/green] {caminho_docx} (~{estimadas} página(s) estimada(s))")
        if aviso := aviso_de_tamanho(estimadas, alvo, "DOCX"):
            avisos.append(aviso)

    for aviso in avisos:
        console.print(f"[yellow]{aviso}[/yellow]")
    console.print("[dim]Layout ATS: uma coluna, sem tabelas/imagens, fonte padrão, títulos convencionais, formato único de data.[/dim]")


@cv_app.command("reescrever")
def cv_reescrever(
    foco: str | None = typer.Option(None, "--foco"),
    limite: int = typer.Option(30, "--limite"),
    motor: str | None = typer.Option(None, "--motor", help="claude, gemini ou local; padrão: o configurado para a tarefa ('agente ia motores')."),
) -> None:
    """Prepara a reescrita do resumo/experiências/projetos em modo copiloto (RF-CV-03, RF-IA-01 a RF-IA-05)."""
    from .analise.reescrita import dados_enviados, montar_prompt
    from .analise.termos import extrair_termos

    perfil = carregar_perfil()
    conjunto = _conjunto_ou_sai(foco, limite)
    termos = extrair_termos(conjunto)
    dados = dados_enviados(perfil)
    dados.insert(len(dados) - 1, f"termos mais frequentes de {len(conjunto)} vaga(s)-alvo")
    uso = _usar_ia(
        perfil, "reescrita-cv", motor, dados,
        lambda m: montar_prompt(perfil, termos, m),
        lambda m: f"prompt-reescrita-{foco or 'geral'}-{m}.md",
    )
    if uso is None:
        raise typer.Exit(0)
    console.print(
        f"Cole o conteúdo no {uso.motor.capitalize()}, revise a resposta e aplique no perfil só o que for verdadeiro "
        "(frases [A CONFIRMAR] exigem sua confirmação — RN-02)."
    )


# ---------------------------------------------------------------- revisão, desempenho e sob medida

@cv_app.command("revisar")
def cv_revisar(
    foco: str | None = typer.Option(None, "--foco"),
    limite: int = typer.Option(30, "--limite"),
    nivel: str = typer.Option("estagio", "--nivel"),
    verificar: bool = typer.Option(False, "--verificar", help="Só verifica se há revisão pendente (sai com 1 se houver)."),
) -> None:
    """Revisa a versão-base (mensal ou quando as vagas mudarem), com antes × depois (RF-CV-09)."""
    from .analise.ats import calcular_nota
    from .analise.lacunas import gerar_relatorio
    from .analise.revisao import comparar, instantaneo, registrar_revisao, revisao_pendente
    from .analise.termos import extrair_termos

    vagas = conjunto_de_analise(carregar_vagas(), foco=foco, limite=limite)
    if verificar:
        motivo = revisao_pendente(vagas)
        if motivo:
            console.print(f"[yellow]Revisão pendente:[/yellow] {motivo}. Rode 'agente cv revisar'.")
            raise typer.Exit(1)
        console.print("[green]Versão-base em dia.[/green]")
        raise typer.Exit(0)

    perfil = carregar_perfil()
    termos = extrair_termos(vagas)
    relatorio = gerar_relatorio(perfil, termos)
    nota = calcular_nota(perfil, termos, foco=foco, nivel=nivel)
    registro = instantaneo(perfil, vagas, nota.total, len(relatorio.ja_no_cv), len(termos))
    anterior = registrar_revisao(registro)

    console.print(f"[bold]Revisão da versão-base registrada[/bold] — nota ATS {nota.total}, "
                  f"{len(relatorio.ja_no_cv)}/{len(termos)} termos cobertos, {len(vagas)} vaga(s) no conjunto.")
    if anterior:
        mudancas = comparar(anterior, registro)
        if mudancas:
            console.print("[bold]Antes × depois da última revisão:[/bold]")
            for m in mudancas:
                console.print(f"  • {m}")
        else:
            console.print("Nada mudou desde a última revisão.")
    else:
        console.print("[dim]Primeira revisão; as próximas mostram o antes × depois.[/dim]")
    console.print("Próxima revisão: em até 30 dias ou quando o conjunto de vagas mudar.")


@cv_app.command("desempenho")
def cv_desempenho() -> None:
    """Desempenho por variante (candidaturas × retornos) e recomendação por foco (RF-CV-10)."""
    from .analise.desempenho import medir, recomendar_por_foco
    from .candidaturas import carregar_candidaturas

    colecao = carregar_candidaturas()
    desempenhos = medir(colecao)
    if not desempenhos:
        console.print("Nenhuma candidatura registrada. Use 'agente candidatura registrar'.")
        return
    tabela = Table(title="Desempenho por variante de CV")
    for col in ("Variante", "Foco", "Candidaturas", "Retornos", "Taxa"):
        tabela.add_column(col)
    for d in desempenhos:
        tabela.add_row(d.variante, d.foco, str(d.candidaturas), str(d.retornos), f"{round(d.taxa * 100)}%")
    console.print(tabela)
    console.print("[bold]Melhor variante por foco:[/bold]")
    for foco, d in recomendar_por_foco(desempenhos).items():
        console.print(f"  • {foco}: {d.variante} ({d.retornos}/{d.candidaturas} retornos)")


@cv_app.command("sob-medida")
def cv_sob_medida(
    vaga: int = typer.Option(..., "--vaga", help="Número da vaga em 'agente vaga listar'."),
    foco: str | None = typer.Option(None, "--foco", help="Padrão: o foco registrado na vaga."),
    idioma: str = typer.Option("pt", "--idioma"),
    nivel: str = typer.Option("estagio", "--nivel"),
    exportar: bool = typer.Option(False, "--exportar", help="Também exporta PDF e DOCX."),
) -> None:
    """Versão sob medida para uma vaga, com cobertura e antes × depois (RF-CV-11, RF-CV-12)."""
    from .analise.sob_medida import gerar_sob_medida
    from .confirmacao import pendencias_na_variante

    colecao = carregar_vagas()
    if not 1 <= vaga <= len(colecao.vagas):
        console.print(f"[red]Vaga {vaga} não existe ({len(colecao.vagas)} salva(s)).[/red]")
        raise typer.Exit(1)
    alvo = colecao.vagas[vaga - 1]
    perfil = carregar_perfil()
    try:
        resultado = gerar_sob_medida(perfil, alvo, foco=foco or alvo.foco, idioma=idioma, nivel=nivel)
    except ValueError as erro:
        console.print(f"[red]{erro}[/red]")
        raise typer.Exit(1)

    destino = diretorio_dados() / "variantes" / f"cv-vaga-{alvo.id}-{idioma}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(resultado.model_dump_json(indent=2), encoding="utf-8")

    console.print(f"[bold]CV sob medida para:[/bold] {alvo.titulo}" + (f" — {alvo.empresa}" if alvo.empresa else ""))
    console.print("\n[bold]Antes × depois (vs variante-base):[/bold]")
    for m in resultado.mudancas or ["sem mudanças de ordem — a base já estava alinhada à vaga"]:
        console.print(f"  • {m}")
    cob = resultado.cobertura
    console.print("\n[bold]Cobertura da vaga (RF-CV-12):[/bold]")
    console.print(f"  [green]Requisitos atendidos ({len(cob.atendidos)}):[/green] " + (", ".join(cob.atendidos) or "—"))
    console.print(f"  [cyan]Termos incluídos no CV ({len(cob.incluidos)}):[/cyan] " + (", ".join(cob.incluidos) or "—"))
    console.print(f"  [red]Sem lastro ({len(cob.sem_lastro)}):[/red] " + (", ".join(cob.sem_lastro) or "—")
                  + ("  → feche com 'agente cv fechar-lacunas'" if cob.sem_lastro else ""))
    console.print(f"\n[green]Salvo em[/green] {destino}")

    if exportar:
        pendencias = pendencias_na_variante(resultado.variante)
        if pendencias:
            console.print("[red]Exportação bloqueada (RF-CV-13): há frases [A CONFIRMAR] no material:[/red]")
            for p in pendencias:
                console.print(f"  • {p}")
            console.print("Confirme com 'agente confirmar' e exporte de novo.")
            raise typer.Exit(1)
        _bloquear_sem_lastro(resultado.variante, perfil)
        from .analise.exportar import exportar_docx, exportar_pdf

        pasta = diretorio_dados() / "saidas"
        caminho_pdf, paginas = exportar_pdf(resultado.variante, pasta / f"cv-vaga-{alvo.id}-{idioma}.pdf")
        caminho_docx = exportar_docx(resultado.variante, pasta / f"cv-vaga-{alvo.id}-{idioma}.docx")
        console.print(f"[green]Exportado:[/green] {caminho_pdf} ({paginas} pág.) e {caminho_docx}")


@app.command("confirmar")
def confirmar() -> None:
    """Revisa frases marcadas [A CONFIRMAR] e libera a exportação (RF-CV-13)."""
    from .confirmacao import MARCADOR, confirmar_frase, frases_pendentes

    perfil = carregar_perfil()
    pendentes = frases_pendentes(perfil)
    if not pendentes:
        console.print("[green]Nenhuma frase pendente de confirmação.[/green]")
        return
    console.print(f"{len(pendentes)} frase(s) com {MARCADOR}:")
    confirmadas = 0
    for pendente in pendentes:
        console.print(f"\n[bold]{pendente.local}[/bold]\n  {pendente.texto}")
        if typer.confirm("Esta frase é verdadeira e pode ficar?"):
            confirmar_frase(perfil, pendente)
            confirmadas += 1
    if confirmadas:
        salvar_perfil(perfil)
    console.print(f"[green]{confirmadas} confirmada(s);[/green] {len(pendentes) - confirmadas} mantida(s) como pendente(s).")


# ---------------------------------------------------------------- candidaturas

@candidatura_app.command("registrar")
def candidatura_registrar(
    vaga: int | None = typer.Option(None, "--vaga", help="Número da vaga em 'agente vaga listar'."),
    foco: str = typer.Option(..., "--foco"),
    idioma: str = typer.Option("pt", "--idioma"),
) -> None:
    """Registra uma candidatura e guarda a versão de CV enviada (RF-CV-14)."""
    from .candidaturas import Candidatura, carregar_candidaturas, guardar_cv_enviado, salvar_candidaturas

    vagas = carregar_vagas()
    vaga_obj = None
    if vaga is not None:
        if not 1 <= vaga <= len(vagas.vagas):
            console.print(f"[red]Vaga {vaga} não existe.[/red]")
            raise typer.Exit(1)
        vaga_obj = vagas.vagas[vaga - 1]
    titulo = vaga_obj.titulo if vaga_obj else typer.prompt("Título da vaga")
    empresa = vaga_obj.empresa if vaga_obj else (typer.prompt("Empresa (opcional)", default="", show_default=False) or None)

    nome_variante = (
        f"cv-vaga-{vaga_obj.id}-{idioma}" if vaga_obj
        and (diretorio_dados() / "saidas" / f"cv-vaga-{vaga_obj.id}-{idioma}.pdf").is_file()
        else f"cv-{foco}-{idioma}"
    )
    candidatos = [
        diretorio_dados() / "saidas" / f"{nome_variante}.pdf",
        diretorio_dados() / "saidas" / f"{nome_variante}.docx",
    ]
    arquivos = [c for c in candidatos if c.is_file()]

    cand = Candidatura(
        vaga_id=vaga_obj.id if vaga_obj else None,
        vaga_titulo=titulo,
        empresa=empresa,
        foco=foco,
        variante=nome_variante,
        idioma=idioma,
    )
    if arquivos:
        guardar_cv_enviado(cand, arquivos)  # RF-CV-14
        console.print(f"CV guardado junto da candidatura: {', '.join(a.name for a in arquivos)}")
    else:
        console.print("[yellow]Nenhum CV exportado encontrado para guardar — exporte antes com 'agente cv exportar' ou 'cv sob-medida --exportar'.[/yellow]")

    colecao = carregar_candidaturas()
    colecao.itens.append(cand)
    salvar_candidaturas(colecao)
    console.print(f"[green]Candidatura registrada:[/green] {cand.id} — {titulo} (variante {nome_variante})")


@candidatura_app.command("listar")
def candidatura_listar() -> None:
    """Lista as candidaturas registradas."""
    from .candidaturas import carregar_candidaturas

    colecao = carregar_candidaturas()
    if not colecao.itens:
        console.print("Nenhuma candidatura registrada.")
        return
    tabela = Table(title=f"Candidaturas ({len(colecao.itens)})")
    for col in ("#", "Vaga", "Empresa", "Foco", "Variante", "Status", "CV guardado"):
        tabela.add_column(col)
    for i, c in enumerate(colecao.itens, 1):
        tabela.add_row(str(i), c.vaga_titulo, c.empresa or "", c.foco, c.variante, c.status.value,
                       "sim" if c.cv_enviado else "não")
    console.print(tabela)


@candidatura_app.command("status")
def candidatura_status(
    numero: int = typer.Argument(..., help="Número em 'agente candidatura listar'."),
    novo: str = typer.Argument(..., help="Etapa do funil (veja 'agente funil'); o funil completo está em 'agente funil mover'."),
) -> None:
    """Atualiza a etapa de uma candidatura (alimenta o desempenho, RF-CV-10). Para datas e motivos, use 'agente funil mover'."""
    from .candidaturas import StatusCandidatura, carregar_candidaturas, salvar_candidaturas

    colecao = carregar_candidaturas()
    if not 1 <= numero <= len(colecao.itens):
        console.print(f"[red]Candidatura {numero} não existe.[/red]")
        raise typer.Exit(1)
    try:
        status = StatusCandidatura(novo)
        cand = colecao.itens[numero - 1]
        cand.mudar_status(status)
    except ValueError as erro:
        console.print(f"[red]{escape(str(erro)) if 'funil' in str(erro) or 'encerrada' in str(erro) else f'Etapa inválida: {escape(novo)}.'}[/red]")
        raise typer.Exit(1)
    salvar_candidaturas(colecao)
    console.print(f"[green]{cand.vaga_titulo}: etapa → {status.value}[/green]")
