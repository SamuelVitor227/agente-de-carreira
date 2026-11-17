"""CLI do Agente de Carreira (fase M1 — perfil-mestre).

Toda importação é mostrada por completo antes de entrar no perfil (RF-PM-02,
RN-01) e nada é inventado: o que não veio de fonte confirmada fica como
rascunho (RN-02).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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
perfil_app = typer.Typer(help="Gerencia o perfil-mestre (RF-PM-01, RF-PM-06, RF-PM-07).", no_args_is_help=True)
experiencia_app = typer.Typer(help="Gerencia experiências (RF-PM-03, RF-PM-05).", no_args_is_help=True)
conquista_app = typer.Typer(help="Banco de conquistas reutilizáveis (RF-PM-04).", no_args_is_help=True)
vaga_app = typer.Typer(help="Vagas-alvo para análise (RF-CV-01).", no_args_is_help=True)
cv_app = typer.Typer(help="Otimização do currículo (RF-CV-01 a RF-CV-14).", no_args_is_help=True)
candidatura_app = typer.Typer(help="Candidaturas e CV enviado (RF-CV-10, RF-CV-14).", no_args_is_help=True)
li_app = typer.Typer(help="LinkedIn em modo copiloto (RF-LI-01 a RF-LI-09).", no_args_is_help=True)
app.add_typer(perfil_app, name="perfil")
app.add_typer(experiencia_app, name="experiencia")
app.add_typer(conquista_app, name="conquista")
app.add_typer(vaga_app, name="vaga")
app.add_typer(cv_app, name="cv")
app.add_typer(candidatura_app, name="candidatura")
app.add_typer(li_app, name="li")

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


# ---------------------------------------------------------------- perfil

@perfil_app.command("criar")
def perfil_criar(
    sobrescrever: bool = typer.Option(False, "--sobrescrever", help="Substitui um perfil existente."),
) -> None:
    """Cria o perfil-mestre (RF-PM-01)."""
    if perfil_existe() and not sobrescrever:
        console.print(f"[red]Já existe um perfil em {caminho_perfil()}.[/red] Use --sobrescrever para substituir.")
        raise typer.Exit(1)
    nome = typer.prompt("Nome completo")
    email = typer.prompt("E-mail")
    objetivo = typer.prompt("Objetivo profissional (opcional)", default="", show_default=False)
    perfil = PerfilMestre(contato=Contato(nome=nome, email=email), objetivo=objetivo or None)
    caminho = salvar_perfil(perfil)
    console.print(f"[green]Perfil-mestre criado em[/green] {caminho}")


@perfil_app.command("mostrar")
def perfil_mostrar() -> None:
    """Mostra o perfil-mestre completo."""
    perfil = carregar_perfil()

    corpo = [f"[bold]{perfil.contato.nome}[/bold]  <{perfil.contato.email}>"]
    if perfil.contato.telefone:
        corpo.append(f"Telefone: {perfil.contato.telefone}")
    local = ", ".join(p for p in [perfil.contato.cidade, perfil.contato.uf, perfil.contato.pais] if p)
    if local:
        corpo.append(f"Local: {local}")
    for rotulo, valor in [("GitHub", perfil.links.github), ("LinkedIn", perfil.links.linkedin), ("Portfólio", perfil.links.portfolio)]:
        if valor:
            corpo.append(f"{rotulo}: {valor}")
    if perfil.objetivo:
        corpo.append(f"\n[bold]Objetivo:[/bold] {perfil.objetivo}")
    if perfil.resumo:
        corpo.append(f"\n[bold]Resumo:[/bold] {perfil.resumo}")
    console.print(Panel("\n".join(corpo), title="Perfil-mestre", border_style="cyan"))

    if perfil.experiencias:
        tabela = Table(title=f"Experiências ({len(perfil.experiencias)})")
        for col in ("#", "Cargo", "Empresa", "Vínculo", "Período", "Área", "Tecnologias"):
            tabela.add_column(col)
        for i, exp in enumerate(perfil.experiencias, 1):
            fim = exp.periodo.fim.isoformat() if exp.periodo.fim else "atual"
            tabela.add_row(
                str(i), exp.cargo, exp.empresa, exp.vinculo.value,
                f"{exp.periodo.inicio.isoformat()} – {fim}",
                exp.area.value, ", ".join(exp.tecnologias),
            )
        console.print(tabela)

    if perfil.formacao:
        tabela = Table(title="Formação")
        for col in ("Curso", "Instituição", "Status", "Conclusão prevista"):
            tabela.add_column(col)
        for f in perfil.formacao:
            tabela.add_row(f.curso, f.instituicao, f.status or "", f.conclusao_prevista or "")
        console.print(tabela)

    if perfil.banco_conquistas:
        console.print(f"[bold]Banco de conquistas:[/bold] {len(perfil.banco_conquistas)} (use 'agente conquista listar')")
    if perfil.competencias_tecnicas:
        console.print(f"[bold]Competências técnicas:[/bold] {', '.join(perfil.competencias_tecnicas)}")
    if perfil.competencias_comportamentais:
        console.print(f"[bold]Competências comportamentais:[/bold] {', '.join(perfil.competencias_comportamentais)}")
    if perfil.idiomas:
        console.print(f"[bold]Idiomas:[/bold] {', '.join(f'{i.idioma} ({i.nivel})' for i in perfil.idiomas)}")
    if perfil.certificacoes:
        console.print(f"[bold]Certificações:[/bold] {', '.join(c.nome for c in perfil.certificacoes)}")
    pend = len(perfil.rascunhos.experiencias) + len(perfil.rascunhos.formacoes)
    if pend:
        console.print(f"[yellow]{pend} rascunho(s) de importação pendentes — veja 'agente rascunhos'.[/yellow]")
    console.print(f"[dim]Atualizado em {perfil.atualizado_em:%d/%m/%Y %H:%M} UTC — {caminho_perfil()}[/dim]")


@perfil_app.command("validar")
def perfil_validar() -> None:
    """Valida completude e consistência do perfil (RF-PM-07)."""
    perfil = carregar_perfil()
    problemas = validar_perfil(perfil)
    if not problemas:
        console.print("[green]Nenhum problema encontrado: perfil completo e consistente.[/green]")
        return
    cores = {"erro": "red", "aviso": "yellow", "info": "cyan"}
    tabela = Table(title=f"Validação do perfil-mestre — {len(problemas)} apontamento(s)")
    tabela.add_column("Nível")
    tabela.add_column("Código")
    tabela.add_column("Mensagem", overflow="fold")
    for p in problemas:
        tabela.add_row(f"[{cores[p.nivel]}]{p.nivel}[/{cores[p.nivel]}]", p.codigo, p.mensagem)
    console.print(tabela)
    if any(p.nivel == "erro" for p in problemas):
        raise typer.Exit(1)


@perfil_app.command("versoes")
def perfil_versoes() -> None:
    """Lista o histórico de versões do perfil (RF-PM-06)."""
    versoes = listar_versoes(diretorio_dados())
    if not versoes:
        console.print("Nenhuma versão arquivada ainda (o histórico começa no segundo salvamento).")
        return
    tabela = Table(title=f"Histórico do perfil-mestre ({len(versoes)} versão(ões))")
    tabela.add_column("#")
    tabela.add_column("Arquivada em")
    tabela.add_column("Mudanças em relação à anterior", overflow="fold")
    for i, versao in enumerate(versoes, 1):
        carimbo = versao.stem.removeprefix("perfil-mestre-")
        quando = f"{carimbo[6:8]}/{carimbo[4:6]}/{carimbo[:4]} {carimbo[9:11]}:{carimbo[11:13]}"
        anterior = versoes[i] if i < len(versoes) else None
        mudancas = ", ".join(resumo_diferencas(anterior, versao)) if anterior else "(primeira versão)"
        tabela.add_row(str(i), quando, mudancas or "sem mudanças de conteúdo")
    console.print(tabela)
    console.print("Restaure com 'agente perfil restaurar N'.")


@perfil_app.command("restaurar")
def perfil_restaurar(numero: int = typer.Argument(..., help="Número da versão em 'agente perfil versoes'.")) -> None:
    """Restaura uma versão arquivada do perfil (RF-PM-06)."""
    versoes = listar_versoes(diretorio_dados())
    if not 1 <= numero <= len(versoes):
        console.print(f"[red]Versão {numero} não existe (há {len(versoes)} arquivada(s)).[/red]")
        raise typer.Exit(1)
    alvo = versoes[numero - 1]
    perfil_antigo = carregar_versao(alvo)
    console.print(f"Versão {numero}: {perfil_antigo.contato.nome}, atualizada em {perfil_antigo.atualizado_em:%d/%m/%Y %H:%M} UTC.")
    if not typer.confirm("Restaurar esta versão? (a atual vai para o histórico)"):
        console.print("Nada foi alterado.")
        raise typer.Exit(0)
    restaurar_versao(alvo, caminho_perfil())
    console.print("[green]Versão restaurada.[/green]")


# ---------------------------------------------------------------- importar

@app.command("importar")
def importar(
    arquivo: Path = typer.Argument(..., exists=True, readable=True, help="CV em .pdf/.docx, exportação do LinkedIn (.zip) ou texto (.txt/.md)."),
    confirmar: bool = typer.Option(False, "--sim", help="Aplica sem perguntar (use com cautela)."),
) -> None:
    """Importa dados de CV mostrando tudo o que foi extraído (RF-PM-02)."""
    perfil = carregar_perfil()
    resultado = importar_arquivo(arquivo)

    if resultado.vazio():
        console.print("[yellow]Nada foi extraído desse arquivo.[/yellow]")
        raise typer.Exit(0)

    tabela = Table(title=f"Dados extraídos de {resultado.origem}", show_lines=False)
    tabela.add_column("Campo", style="bold")
    tabela.add_column("Valor")
    for campo, valor in [
        ("Nome", resultado.nome), ("E-mail", resultado.email), ("Telefone", resultado.telefone),
        ("GitHub", resultado.github), ("LinkedIn", resultado.linkedin),
    ]:
        if valor:
            tabela.add_row(campo, valor)
    if resultado.outros_links:
        tabela.add_row("Outros links", "\n".join(resultado.outros_links))
    if resultado.resumo:
        tabela.add_row("Resumo", resultado.resumo[:500])
    if resultado.competencias:
        tabela.add_row("Competências", ", ".join(resultado.competencias))
    if resultado.idiomas:
        tabela.add_row("Idiomas", ", ".join(f"{i.idioma} ({i.nivel or '?'})" for i in resultado.idiomas))
    for exp in resultado.experiencias:
        tabela.add_row("Experiência (rascunho)", f"{exp.cargo or '?'} — {exp.empresa or '?'} ({exp.periodo_texto or 'período ?'})")
    for form in resultado.formacoes:
        tabela.add_row("Formação (rascunho)", f"{form.curso or '?'} — {form.instituicao or '?'}")
    for cert in resultado.certificacoes:
        tabela.add_row("Certificação", f"{cert.nome} ({cert.emissor or '?'})")
    console.print(tabela)

    if resultado.texto_bruto and not resultado.experiencias:
        console.print(Panel(resultado.texto_bruto[:2000], title="Texto extraído (para conferência)", border_style="dim"))

    if not confirmar and not typer.confirm("Aplicar esses dados ao perfil-mestre?"):
        console.print("Nada foi alterado.")
        raise typer.Exit(0)

    alteracoes = aplicar_importacao(perfil, resultado)
    if not alteracoes:
        console.print("[yellow]Nenhuma alteração: os campos já estavam preenchidos.[/yellow]")
        raise typer.Exit(0)
    salvar_perfil(perfil)
    console.print("[green]Alterações aplicadas:[/green]")
    for alt in alteracoes:
        console.print(f"  • {alt}")


@app.command("rascunhos")
def rascunhos() -> None:
    """Lista rascunhos importados pendentes de confirmação (RN-02)."""
    perfil = carregar_perfil()
    if not perfil.rascunhos.experiencias and not perfil.rascunhos.formacoes:
        console.print("Nenhum rascunho pendente.")
        return
    for i, exp in enumerate(perfil.rascunhos.experiencias, 1):
        console.print(f"[bold]Experiência {i}:[/bold] {exp.cargo or '?'} — {exp.empresa or '?'} ({exp.periodo_texto or 'período ?'}) [dim]{exp.origem or ''}[/dim]")
        if exp.descricao:
            console.print(f"  {exp.descricao[:300]}")
    for i, form in enumerate(perfil.rascunhos.formacoes, 1):
        console.print(f"[bold]Formação {i}:[/bold] {form.curso or '?'} — {form.instituicao or '?'} ({form.periodo_texto or 'período ?'})")
    console.print("\nComplete cada rascunho com 'agente experiencia adicionar' e remova-o depois com 'agente experiencia adicionar --do-rascunho N'.")


# ---------------------------------------------------------------- experiência

@experiencia_app.command("adicionar")
def experiencia_adicionar(
    do_rascunho: int | None = typer.Option(None, "--do-rascunho", help="Número do rascunho de experiência a converter (ver 'agente rascunhos')."),
) -> None:
    """Adiciona uma experiência completa (RF-PM-03); aceita fora de TI e projetos acadêmicos (RF-PM-05)."""
    perfil = carregar_perfil()

    rascunho = None
    if do_rascunho is not None:
        if not 1 <= do_rascunho <= len(perfil.rascunhos.experiencias):
            console.print(f"[red]Rascunho {do_rascunho} não existe.[/red]")
            raise typer.Exit(1)
        rascunho = perfil.rascunhos.experiencias[do_rascunho - 1]
        console.print(Panel(
            f"{rascunho.cargo or '?'} — {rascunho.empresa or '?'}\n{rascunho.periodo_texto or ''}\n{rascunho.descricao or ''}",
            title="Rascunho de origem", border_style="yellow",
        ))

    cargo = typer.prompt("Cargo", default=rascunho.cargo if rascunho and rascunho.cargo else None)
    empresa = typer.prompt("Empresa/organização", default=rascunho.empresa if rascunho and rascunho.empresa else None)
    vinculo = typer.prompt(
        f"Vínculo ({', '.join(v.value for v in Vinculo)})", default=Vinculo.OUTRO.value
    )
    inicio = _data(typer.prompt("Início (AAAA-MM)"))
    fim_texto = typer.prompt("Fim (AAAA-MM, vazio = atual)", default="", show_default=False)
    local = typer.prompt("Local (opcional)", default=rascunho.local if rascunho and rascunho.local else "", show_default=False)
    modelo = typer.prompt(
        f"Modelo de trabalho ({', '.join(m.value for m in ModeloTrabalho)}, vazio = não se aplica)",
        default="", show_default=False,
    )
    area = typer.prompt(f"Área ({Area.TI.value} ou {Area.FORA_DE_TI.value})", default=Area.TI.value)
    responsabilidades = _prompt_multilinha("Responsabilidades")
    tecnologias = _lista(typer.prompt("Tecnologias (separadas por vírgula)", default="", show_default=False))
    transferiveis: list[str] = []
    if area == Area.FORA_DE_TI.value:
        transferiveis = _lista(typer.prompt(
            "Competências transferíveis (ex.: atendimento, compras e estoque, escala de equipe)",
            default="", show_default=False,
        ))

    experiencia = Experiencia(
        cargo=cargo,
        empresa=empresa,
        vinculo=Vinculo(vinculo),
        periodo=Periodo(inicio=inicio, fim=_data(fim_texto) if fim_texto.strip() else None),
        local=local or None,
        modelo_trabalho=ModeloTrabalho(modelo) if modelo.strip() else None,
        area=Area(area),
        responsabilidades=responsabilidades,
        tecnologias=tecnologias,
        competencias_transferiveis=transferiveis,
    )
    perfil.experiencias.append(experiencia)
    if rascunho is not None:
        perfil.rascunhos.experiencias.remove(rascunho)
    salvar_perfil(perfil)
    console.print(f"[green]Experiência adicionada:[/green] {cargo} — {empresa}")


@experiencia_app.command("listar")
def experiencia_listar() -> None:
    """Lista as experiências registradas."""
    perfil = carregar_perfil()
    if not perfil.experiencias:
        console.print("Nenhuma experiência registrada. Use 'agente experiencia adicionar'.")
        return
    for i, exp in enumerate(perfil.experiencias, 1):
        fim = exp.periodo.fim.isoformat() if exp.periodo.fim else "atual"
        console.print(f"[bold]{i}. {exp.cargo}[/bold] — {exp.empresa} ({exp.vinculo.value}, {exp.periodo.inicio} – {fim}, {exp.area.value})")
        for r in exp.responsabilidades:
            console.print(f"   • {r}")
        if exp.tecnologias:
            console.print(f"   Tecnologias: {', '.join(exp.tecnologias)}")
        if exp.competencias_transferiveis:
            console.print(f"   Transferíveis: {', '.join(exp.competencias_transferiveis)}")
        if exp.conquista_ids:
            console.print(f"   Conquistas vinculadas: {', '.join(exp.conquista_ids)}")


# ---------------------------------------------------------------- conquistas

@conquista_app.command("adicionar")
def conquista_adicionar() -> None:
    """Adiciona uma conquista ao banco de conquistas (RF-PM-04)."""
    perfil = carregar_perfil()
    verbo = typer.prompt("Verbo de ação (ex.: Reduzi, Automatizei, Organizei)")
    descricao = typer.prompt("Descrição da conquista")
    resultado = typer.prompt("Resultado (opcional)", default="", show_default=False)
    numero = typer.prompt("Número que quantifica (ex.: 30%, 1.200 itens; opcional)", default="", show_default=False)
    tecnologias = _lista(typer.prompt("Tecnologias (vírgula; opcional)", default="", show_default=False))
    competencias = _lista(typer.prompt("Competências (vírgula; opcional)", default="", show_default=False))
    evidencia = typer.prompt("Evidência que sustenta (link, documento, pessoa; opcional)", default="", show_default=False)

    conquista = Conquista(
        verbo_acao=verbo,
        descricao=descricao,
        resultado=resultado or None,
        numero=numero or None,
        tecnologias=tecnologias,
        competencias=competencias,
        evidencia=evidencia or None,
    )
    perfil.banco_conquistas.append(conquista)

    if perfil.experiencias:
        for i, exp in enumerate(perfil.experiencias, 1):
            console.print(f"  {i}. {exp.cargo} — {exp.empresa}")
        escolha = typer.prompt("Vincular a qual experiência? (número, vazio = nenhuma)", default="", show_default=False)
        if escolha.strip():
            indice = int(escolha) - 1
            if not 0 <= indice < len(perfil.experiencias):
                console.print("[red]Experiência inválida; conquista salva sem vínculo.[/red]")
            else:
                perfil.experiencias[indice].conquista_ids.append(conquista.id)

    salvar_perfil(perfil)
    console.print(f"[green]Conquista adicionada ao banco:[/green] {conquista.id} — {verbo} …")


@conquista_app.command("listar")
def conquista_listar() -> None:
    """Lista o banco de conquistas (RF-PM-04)."""
    perfil = carregar_perfil()
    if not perfil.banco_conquistas:
        console.print("Banco de conquistas vazio. Use 'agente conquista adicionar'.")
        return
    tabela = Table(title=f"Banco de conquistas ({len(perfil.banco_conquistas)})")
    for col in ("ID", "Verbo", "Descrição", "Resultado", "Número", "Tecnologias", "Evidência"):
        tabela.add_column(col)
    for c in perfil.banco_conquistas:
        tabela.add_row(
            c.id, c.verbo_acao, c.descricao, c.resultado or "", c.numero or "",
            ", ".join(c.tecnologias), c.evidencia or "",
        )
    console.print(tabela)


# ---------------------------------------------------------------- vagas-alvo

@vaga_app.command("adicionar")
def vaga_adicionar(
    arquivo: Path | None = typer.Option(None, "--arquivo", exists=True, readable=True, help="Arquivo .txt/.md com a descrição da vaga."),
) -> None:
    """Salva uma vaga-alvo para o conjunto de análise (RF-CV-01)."""
    colecao = carregar_vagas()
    titulo = typer.prompt("Título da vaga")
    empresa = typer.prompt("Empresa (opcional)", default="", show_default=False)
    foco = typer.prompt("Foco (ex.: backend-dotnet, cloud-aws, mobile, dados, suporte)")
    url = typer.prompt("URL (opcional)", default="", show_default=False)
    fonte = typer.prompt("Fonte (ex.: linkedin, gupy, site da empresa; opcional)", default="", show_default=False)
    if arquivo is not None:
        descricao = arquivo.read_text(encoding="utf-8")
    else:
        descricao = "\n".join(_prompt_multilinha("Descrição/requisitos da vaga"))
    if not descricao.strip():
        console.print("[red]A descrição é obrigatória: é dela que saem os termos.[/red]")
        raise typer.Exit(1)
    vaga = Vaga(
        titulo=titulo, empresa=empresa or None, foco=foco,
        url=url or None, fonte=fonte or None, descricao=descricao,
    )
    colecao.vagas.append(vaga)
    salvar_vagas(colecao)
    console.print(f"[green]Vaga salva:[/green] {titulo} (foco {foco}) — {len(colecao.vagas)} vaga(s) no total.")


@vaga_app.command("listar")
def vaga_listar(foco: str | None = typer.Option(None, "--foco", help="Filtra por foco.")) -> None:
    """Lista as vagas-alvo salvas."""
    colecao = carregar_vagas()
    vagas = [v for v in colecao.vagas if foco is None or v.foco == foco]
    if not vagas:
        console.print("Nenhuma vaga salva. Use 'agente vaga adicionar'.")
        return
    tabela = Table(title=f"Vagas-alvo ({len(vagas)})")
    for col in ("#", "Título", "Empresa", "Foco", "Fonte", "Salva em"):
        tabela.add_column(col)
    for i, v in enumerate(vagas, 1):
        tabela.add_row(str(i), v.titulo, v.empresa or "", v.foco, v.fonte or "", f"{v.salva_em:%d/%m/%Y}")
    console.print(tabela)


@vaga_app.command("remover")
def vaga_remover(numero: int = typer.Argument(..., help="Número da vaga em 'agente vaga listar'.")) -> None:
    """Remove uma vaga-alvo."""
    colecao = carregar_vagas()
    if not 1 <= numero <= len(colecao.vagas):
        console.print(f"[red]Vaga {numero} não existe.[/red]")
        raise typer.Exit(1)
    removida = colecao.vagas.pop(numero - 1)
    salvar_vagas(colecao)
    console.print(f"[green]Removida:[/green] {removida.titulo}")


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
            console.print(f"  • {item.termo} ({item.vagas_em_que_aparece} vaga(s), {item.percentual}%){extra}")

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
    motor: str = typer.Option("claude", "--motor", help="Motor de IA: claude ou gemini."),
) -> None:
    """Prepara a reescrita do resumo/experiências/projetos em modo copiloto (RF-CV-03, RF-IA-02)."""
    from .analise.reescrita import MOTORES, dados_enviados, montar_prompt
    from .analise.termos import extrair_termos

    if motor not in MOTORES:
        console.print(f"[red]Motor desconhecido: {motor}. Use um de: {', '.join(MOTORES)}.[/red]")
        raise typer.Exit(1)
    perfil = carregar_perfil()
    conjunto = _conjunto_ou_sai(foco, limite)
    termos = extrair_termos(conjunto)

    # RF-IA-02 / RN-14: aviso do motor, da tarefa e dos dados, com autorização a cada uso.
    console.print(Panel(
        f"[bold]Motor:[/bold] {motor} (sua assinatura; você cola o prompt manualmente)\n"
        f"[bold]Tarefa:[/bold] reescrever resumo, experiências e projetos no padrão "
        f"verbo de ação + feito + resultado + tecnologia, usando termos de {len(conjunto)} vaga(s)\n"
        "[bold]Dados que vão no prompt:[/bold]\n" + "\n".join(f"  • {d}" for d in dados_enviados(perfil)),
        title="Autorização de uso de IA (RF-IA-02)", border_style="magenta",
    ))
    if not typer.confirm("Autorizar e gerar o prompt?"):
        console.print("Uso de IA não autorizado; nada foi gerado.")
        raise typer.Exit(0)

    prompt = montar_prompt(perfil, termos, motor)
    destino = diretorio_dados() / "saidas" / f"prompt-reescrita-{foco or 'geral'}-{motor}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(prompt, encoding="utf-8")
    console.print(f"[green]Prompt gerado em[/green] {destino}")
    console.print(
        "Cole o conteúdo no "
        + ("Claude" if motor == "claude" else "Gemini")
        + ", revise a resposta e aplique no perfil só o que for verdadeiro "
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
    novo: str = typer.Argument(..., help="preparada, enviada, retorno, entrevista, proposta, recusada, sem_resposta"),
) -> None:
    """Atualiza o status de uma candidatura (alimenta o desempenho, RF-CV-10)."""
    from .candidaturas import StatusCandidatura, carregar_candidaturas, salvar_candidaturas

    colecao = carregar_candidaturas()
    if not 1 <= numero <= len(colecao.itens):
        console.print(f"[red]Candidatura {numero} não existe.[/red]")
        raise typer.Exit(1)
    try:
        status = StatusCandidatura(novo)
    except ValueError:
        console.print(f"[red]Status inválido: {novo}.[/red]")
        raise typer.Exit(1)
    cand = colecao.itens[numero - 1]
    cand.mudar_status(status)
    salvar_candidaturas(colecao)
    console.print(f"[green]{cand.vaga_titulo}: status → {status.value}[/green]")


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


if __name__ == "__main__":
    app()
