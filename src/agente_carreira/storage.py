"""Armazenamento local do perfil-mestre em JSON.

Os dados ficam em armazenamento controlado pelo usuário (premissa 5 da
especificação): por padrão em ./data/perfil-mestre.json, configurável pela
variável de ambiente AGENTE_CARREIRA_DATA.
"""

from __future__ import annotations

import os
from pathlib import Path

from .models import PerfilMestre
from .versionamento import arquivar_versao

ARQUIVO_PERFIL = "perfil-mestre.json"


def diretorio_dados() -> Path:
    base = os.environ.get("AGENTE_CARREIRA_DATA")
    return Path(base) if base else Path.cwd() / "data"


def caminho_perfil() -> Path:
    return diretorio_dados() / ARQUIVO_PERFIL


def perfil_existe() -> bool:
    return caminho_perfil().is_file()


class PerfilAusente(FileNotFoundError):
    """Ainda não há perfil-mestre: a CLI e o app mostram como começar, sem traceback."""


COMO_COMECAR = (
    "Você ainda não tem perfil-mestre. Comece por um destes:\n"
    "  • seu currículo (PDF ou DOCX): botão \"Importar currículo…\" no app, ou 'agente importar ARQUIVO'\n"
    "  • seus dados do LinkedIn (ZIP da exportação oficial): botão \"Conectar LinkedIn (ZIP)…\", "
    "ou 'agente li conectar ARQUIVO.zip'\n"
    "  • do zero, respondendo perguntas: 'agente perfil criar'"
)


def carregar_perfil() -> PerfilMestre:
    caminho = caminho_perfil()
    if not caminho.is_file():
        raise PerfilAusente(f"{COMO_COMECAR}\n(procurado em {caminho})")
    from .arquivos import ler_modelo

    return ler_modelo(caminho, PerfilMestre)


def salvar_perfil(perfil: PerfilMestre) -> Path:
    from .arquivos import gravar_modelo

    perfil.tocar()
    caminho = caminho_perfil()
    # RF-PM-06: a versão anterior vai para o histórico (com o arquivo travado, logo antes da troca).
    return gravar_modelo(caminho, perfil, antes_de_trocar=lambda: arquivar_versao(caminho))
