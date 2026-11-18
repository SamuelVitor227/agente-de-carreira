"""App de janela do agente, feito para quem não é de TI.

Navegação lateral (Início, Vagas, Candidaturas, Perfil, LinkedIn, Aprovações,
Relatórios, Configurações), próximo passo sugerido e primeiros passos. As ações
rodam os comandos da CLI dentro da janela: as perguntas viram botões e campos,
sem console. Abra pelo atalho da Área de Trabalho ('agente atalho'),
com 'agente app' ou com 'uv run agente-app'.
"""

from __future__ import annotations

import os
import subprocess
import sys

from .atalho import NOME_APP, criar_atalho, criar_icone, raiz_do_projeto, script_atalho

__all__ = ["NOME_APP", "abrir_em_segundo_plano", "criar_atalho", "criar_icone", "main", "raiz_do_projeto", "script_atalho"]

LARGURA_SAIDA = "112"  # colunas das tabelas na janela de execução


def preparar_ambiente() -> None:
    """Antes de importar a CLI: cores do rich (viram cores na janela), largura e a pasta data/ do projeto."""
    from ..operacao.credenciais import carregar_variaveis_do_usuario

    os.environ.setdefault("FORCE_COLOR", "1")
    os.environ["COLUMNS"] = LARGURA_SAIDA
    carregar_variaveis_do_usuario()  # e-mail configurado pelo app, mesmo que o Windows não tenha repassado ainda
    if os.environ.get("AGENTE_CARREIRA_DATA") is None:
        os.chdir(raiz_do_projeto())


def main() -> None:
    preparar_ambiente()
    from .janela import abrir_janela

    abrir_janela()


def abrir_em_segundo_plano() -> subprocess.Popen:
    """Abre a janela num processo próprio (sem console), para não herdar o terminal de quem chamou."""
    from .atalho import lancador

    try:
        alvo, argumentos = lancador()
        comando = [str(alvo), *argumentos.split()]
    except RuntimeError:
        comando = [sys.executable, "-m", "agente_carreira.app"]
    criacao = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(comando, cwd=raiz_do_projeto(), creationflags=criacao, close_fds=True)
