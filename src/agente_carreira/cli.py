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

from .cli_comum import _checar_recusa, _usar_ia, app, console  # noqa: F401 - outros módulos importam daqui
from .cli_cv import candidatura_app, cv_app  # noqa: E402
from .cli_ia import ia_app  # noqa: E402
from .cli_linkedin import _auditar_linkedin, li_app  # noqa: E402,F401
from .cli_perfil import conquista_app, experiencia_app, perfil_app, vaga_app  # noqa: E402

app.add_typer(perfil_app, name="perfil")
app.add_typer(experiencia_app, name="experiencia")
app.add_typer(conquista_app, name="conquista")
app.add_typer(vaga_app, name="vaga")
app.add_typer(cv_app, name="cv")
app.add_typer(candidatura_app, name="candidatura")
app.add_typer(li_app, name="li")
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
from .cli_email import email_app  # noqa: E402

app.add_typer(email_app, name="email")
from .cli_vagas import andamento_cmd  # noqa: E402

app.command("andamento")(andamento_cmd)
from .cli_copias import copias_app  # noqa: E402

app.add_typer(copias_app, name="copias")
from .cli_dados import dados_app  # noqa: E402

app.add_typer(dados_app, name="dados")


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


def main() -> None:
    """Ponto de entrada do comando 'agente': sem perfil-mestre, orienta em vez de mostrar traceback."""
    from .copias import garantir_copia_do_dia
    from .operacao.credenciais import carregar_variaveis_do_usuario
    from .storage import PerfilAusente

    carregar_variaveis_do_usuario()  # ex.: a pasta dos dados mudou (AGENTE_CARREIRA_DATA) depois que o terminal abriu
    try:
        garantir_copia_do_dia()  # a primeira vez no dia guarda uma cópia dos dados (7 dias)
    except OSError:
        pass
    try:
        app()
    except PerfilAusente as erro:
        console.print(f"[yellow]{escape(str(erro))}[/yellow]")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
