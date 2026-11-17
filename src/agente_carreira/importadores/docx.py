"""Importação de CV em DOCX (RF-PM-02)."""

from __future__ import annotations

from pathlib import Path

import docx

from .extrator import extrair_de_texto
from .resultado import ResultadoImportacao


def importar_docx(caminho: Path) -> ResultadoImportacao:
    documento = docx.Document(str(caminho))
    partes = [p.text for p in documento.paragraphs if p.text.strip()]
    for tabela in documento.tables:
        for linha in tabela.rows:
            for celula in linha.cells:
                if celula.text.strip():
                    partes.append(celula.text)
    return extrair_de_texto("\n".join(partes), origem=f"docx:{caminho.name}")
