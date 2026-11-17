"""Importação de texto livre (RF-PM-02)."""

from __future__ import annotations

from pathlib import Path

from .extrator import extrair_de_texto
from .resultado import ResultadoImportacao


def importar_texto(caminho: Path) -> ResultadoImportacao:
    texto = caminho.read_text(encoding="utf-8")
    return extrair_de_texto(texto, origem=f"texto:{caminho.name}")
