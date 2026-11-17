"""Importadores de dados de CV (RF-PM-02).

Fontes aceitas: CV em PDF ou DOCX, PDF do perfil do LinkedIn, exportação de
dados do LinkedIn (ZIP) e texto livre. Tudo o que for extraído é mostrado ao
usuário para confirmação antes de entrar no perfil-mestre (RN-01, RN-02).
"""

from __future__ import annotations

from pathlib import Path

from .resultado import ResultadoImportacao


def importar_arquivo(caminho: Path) -> ResultadoImportacao:
    """Detecta o tipo do arquivo pela extensão e extrai os dados."""
    sufixo = caminho.suffix.lower()
    if sufixo == ".pdf":
        from .pdf import importar_pdf

        return importar_pdf(caminho)
    if sufixo == ".docx":
        from .docx import importar_docx

        return importar_docx(caminho)
    if sufixo == ".zip":
        from .linkedin import importar_exportacao_linkedin

        return importar_exportacao_linkedin(caminho)
    if sufixo in {".txt", ".md"}:
        from .texto import importar_texto

        return importar_texto(caminho)
    raise ValueError(
        f"Formato não suportado: {sufixo!r}. Aceitos: .pdf, .docx, .zip (exportação do LinkedIn), .txt, .md"
    )
