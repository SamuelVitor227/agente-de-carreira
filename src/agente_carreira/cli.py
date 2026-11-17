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
cv_app = typer.Typer(help="Otimização do currículo (RF-CV-01 a RF-CV-03).", no_args_is_help=True)
app.add_typer(perfil_app, name="perfil")
app.add_typer(experiencia_app, name="experiencia")
app.add_typer(conquista_app, name="conquista")
app.add_typer(vaga_app, name="vaga")
app.add_typer(cv_app, name="cv")

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


if __name__ == "__main__":
    app()
