"""Versionamento do perfil-mestre (RF-PM-06).

Cada salvamento arquiva a versão anterior em data/versoes/, com histórico de
mudanças (campos alterados entre versões) e restauração de qualquer versão.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from .models import PerfilMestre

DIR_VERSOES = "versoes"
PREFIXO = "perfil-mestre-"


def diretorio_versoes(diretorio_dados: Path) -> Path:
    return diretorio_dados / DIR_VERSOES


def arquivar_versao(caminho_perfil: Path) -> Path | None:
    """Copia o arquivo atual do perfil para o histórico antes de sobrescrever."""
    if not caminho_perfil.is_file():
        return None
    destino_dir = diretorio_versoes(caminho_perfil.parent)
    destino_dir.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destino = destino_dir / f"{PREFIXO}{carimbo}.json"
    shutil.copy2(caminho_perfil, destino)
    return destino


def listar_versoes(diretorio_dados: Path) -> list[Path]:
    """Versões arquivadas, da mais recente para a mais antiga."""
    pasta = diretorio_versoes(diretorio_dados)
    if not pasta.is_dir():
        return []
    return sorted(pasta.glob(f"{PREFIXO}*.json"), reverse=True)


def carregar_versao(caminho: Path) -> PerfilMestre:
    return PerfilMestre.model_validate_json(caminho.read_text(encoding="utf-8"))


def restaurar_versao(caminho_versao: Path, caminho_perfil: Path) -> PerfilMestre:
    """Restaura uma versão arquivada, preservando a atual no histórico."""
    perfil = carregar_versao(caminho_versao)  # valida antes de tocar em qualquer arquivo
    arquivar_versao(caminho_perfil)
    shutil.copy2(caminho_versao, caminho_perfil)
    return perfil


def resumo_diferencas(versao_a: Path, versao_b: Path) -> list[str]:
    """Campos de nível superior que mudaram entre duas versões (histórico de mudanças)."""
    a = json.loads(versao_a.read_text(encoding="utf-8"))
    b = json.loads(versao_b.read_text(encoding="utf-8"))
    mudancas: list[str] = []
    for campo in sorted(set(a) | set(b)):
        if campo == "atualizado_em":
            continue
        va, vb = a.get(campo), b.get(campo)
        if va == vb:
            continue
        if isinstance(va, list) or isinstance(vb, list):
            na, nb = len(va or []), len(vb or [])
            mudancas.append(f"{campo}: {na} → {nb} item(ns)")
        else:
            mudancas.append(f"{campo} alterado")
    return mudancas
