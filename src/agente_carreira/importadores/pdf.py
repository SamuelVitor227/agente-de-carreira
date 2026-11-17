"""Importação de CV em PDF — inclui o PDF de perfil do LinkedIn (RF-PM-02)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .extrator import extrair_de_texto
from .resultado import ResultadoImportacao


def importar_pdf(caminho: Path) -> ResultadoImportacao:
    reader = PdfReader(str(caminho))
    texto = "\n".join(pagina.extract_text() or "" for pagina in reader.pages)
    return extrair_de_texto(texto, origem=f"pdf:{caminho.name}")
