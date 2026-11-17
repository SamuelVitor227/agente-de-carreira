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
perfil_app = typer.Typer(help="Gerencia o perfil-mestre (RF-PM-01, RF-PM-06, RF-PM-07).", no_args_is_help=True)
experiencia_app = typer.Typer(help="Gerencia experiências (RF-PM-03, RF-PM-05).", no_args_is_help=True)
conquista_app = typer.Typer(help="Banco de conquistas reutilizáveis (RF-PM-04).", no_args_is_help=True)
vaga_app = typer.Typer(help="Vagas-alvo para a análise do CV (RF-CV-01).", no_args_is_help=True)
cv_app = typer.Typer(help="Otimização do currículo (RF-CV-01 a RF-CV-14).", no_args_is_help=True)
candidatura_app = typer.Typer(help="Candidaturas e CV enviado (RF-CV-10, RF-CV-14).", no_args_is_help=True)
li_app = typer.Typer(help="LinkedIn em modo copiloto (RF-LI-01 a RF-LI-15).", no_args_is_help=True)
ingles_app = typer.Typer(help="Perfil secundário em inglês (RF-LI-10).", no_args_is_help=True)
post_app = typer.Typer(help="Publicações sobre projetos, publicadas só com sua aprovação (RF-LI-12).", no_args_is_help=True)
li_app.add_typer(ingles_app, name="ingles")
li_app.add_typer(post_app, name="post")
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
    """Importa dados de CV mostrando tudo o que foi extraído; sem perfil, cria o perfil-mestre (RF-PM-02, CA-01)."""
    perfil = carregar_perfil() if perfil_existe() else None
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
        ("Cidade", ", ".join(p for p in [resultado.cidade, resultado.uf] if p) or None),
        ("Objetivo", resultado.objetivo),
    ]:
        if valor:
            tabela.add_row(campo, Text(valor))
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
    for proj in resultado.projetos:
        tabela.add_row("Projeto", Text(f"{proj.nome} ({', '.join(proj.tecnologias) or 'sem tecnologias'})"))
    for cert in resultado.certificacoes:
        tabela.add_row("Certificação", Text(f"{cert.nome} ({cert.emissor or '?'})"))
    console.print(tabela)

    if resultado.texto_bruto and not resultado.experiencias:
        console.print(Panel(resultado.texto_bruto[:2000], title="Texto extraído (para conferência)", border_style="dim"))

    if not confirmar and not typer.confirm("Aplicar esses dados ao perfil-mestre?"):
        console.print("Nada foi alterado.")
        raise typer.Exit(0)

    if perfil is None:
        nome = resultado.nome or typer.prompt("Nome completo (não encontrado no arquivo)")
        email = resultado.email or typer.prompt("E-mail (não encontrado no arquivo)")
        perfil = PerfilMestre(contato=Contato(nome=nome, email=email))
        console.print("[green]Perfil-mestre criado a partir do arquivo.[/green]")
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


# ---------------------------------------------------------------- uso de IA (RF-IA-01 a RF-IA-05)

ia_app = typer.Typer(help="Uso de IA: motor por tarefa, fila de pedidos e registro (RF-IA-01 a RF-IA-05).", no_args_is_help=True)
app.add_typer(ia_app, name="ia")

from .cli_operacao import (  # noqa: E402 - registrado junto dos demais grupos
    auditoria_app,
    config_app,
    fila_app,
    notificacoes_app,
    saude_app,
    tarefas_app,
)
from .cli_vagas import busca_app, vagas_app  # noqa: E402
from .cli_plataformas import plataformas_app  # noqa: E402
from .cli_candidatura import candidatar, contatos_app, funil_app, indicacao, respostas_app  # noqa: E402

app.add_typer(busca_app, name="busca")
app.add_typer(vagas_app, name="vagas")
app.add_typer(config_app, name="config")
app.add_typer(fila_app, name="fila")
app.add_typer(tarefas_app, name="tarefas")
app.add_typer(auditoria_app, name="auditoria")
app.add_typer(saude_app, name="saude")
app.add_typer(notificacoes_app, name="notificacoes")
app.add_typer(plataformas_app, name="plataformas")
app.add_typer(respostas_app, name="respostas")
app.add_typer(funil_app, name="funil")
app.add_typer(contatos_app, name="contatos")
app.command("candidatar")(candidatar)
app.command("indicacao")(indicacao)

from .cli_relatorios import exportar_dados, painel, relatorio_app  # noqa: E402

app.command("painel")(painel)
app.add_typer(relatorio_app, name="relatorio")
app.command("exportar")(exportar_dados)


@app.command("app")
def abrir_app() -> None:
    """Abre o app de janela, com botões para as ações do dia a dia."""
    from .app import abrir_em_segundo_plano

    abrir_em_segundo_plano()
    console.print("Abrindo o app do agente…")


@app.command("atalho")
def criar_atalho_cmd() -> None:
    """Cria o atalho "Agente de Carreira" na Área de Trabalho (Windows)."""
    from .app import criar_atalho

    try:
        caminho = criar_atalho()
    except RuntimeError as erro:
        console.print(f"[red]{escape(str(erro))}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Atalho criado:[/green] {caminho}. Dê dois cliques para abrir o agente.")


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


@app.command("aceite")
def aceite(
    fase: str = typer.Option("todas", "--fase", help="1 (MVP: CA-01 a CA-10), 2 (CA-11 e CA-12) ou todas."),
) -> None:
    """Confere os portões: MVP (CA-01 a CA-10) e fase 2 (CA-11 e CA-12) sobre os seus dados."""
    from .aceite import verificar_fase2, verificar_mvp

    if fase not in ("1", "2", "todas"):
        console.print("[red]Use --fase 1, 2 ou todas.[/red]")
        raise typer.Exit(1)
    portoes = []
    if fase in ("1", "todas"):
        portoes.append(("Portão do MVP — CA-01 a CA-10 (seção 14)", verificar_mvp()))
    if fase in ("2", "todas"):
        portoes.append(("Portão da fase 2 — CA-11 e CA-12", verificar_fase2()))
    cores = {"ok": "green", "pendente": "yellow", "falhou": "red", "manual": "cyan"}
    todos = []
    for titulo, criterios in portoes:
        tabela = Table(title=titulo)
        for col in ("CA", "Critério", "Status", "Detalhe"):
            tabela.add_column(col, overflow="fold")
        for c in criterios:
            tabela.add_row(c.codigo, Text(c.titulo), f"[{cores[c.status]}]{c.status}[/{cores[c.status]}]", Text(c.detalhe))
        console.print(tabela)
        todos += criterios
    ok = sum(1 for c in todos if c.status == "ok")
    console.print(f"[bold]{ok} de {len(todos)} ok[/bold] · pendente = falta uso real para comprovar · "
                  "manual = a parte automática passou, falta a conferência indicada.")
    if any(c.status == "falhou" for c in todos):
        raise typer.Exit(1)


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


def main() -> None:
    """Ponto de entrada do comando 'agente': sem perfil-mestre, orienta em vez de mostrar traceback."""
    from .storage import PerfilAusente

    try:
        app()
    except PerfilAusente as erro:
        console.print(f"[yellow]{escape(str(erro))}[/yellow]")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
