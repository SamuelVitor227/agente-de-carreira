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


def carregar_perfil() -> PerfilMestre:
    caminho = caminho_perfil()
    if not caminho.is_file():
        raise FileNotFoundError(
            f"Perfil-mestre não encontrado em {caminho}. Crie um com 'agente perfil criar'."
        )
    return PerfilMestre.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_perfil(perfil: PerfilMestre) -> Path:
    perfil.tocar()
    caminho = caminho_perfil()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    arquivar_versao(caminho)  # RF-PM-06: a versão anterior vai para o histórico
    caminho.write_text(
        perfil.model_dump_json(indent=2), encoding="utf-8"
    )
    return caminho
