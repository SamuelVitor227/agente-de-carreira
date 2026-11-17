"""Exportação da variante de CV em PDF e DOCX compatíveis com ATS (RF-CV-08).

Regras do requisito: uma coluna; sem tabelas, imagens ou ícones no lugar de
texto; fonte padrão; títulos convencionais (vêm da variante); formato único
de data (aplicado na variante); tamanho-alvo configurável, padrão 1 página
para estágio e júnior.
"""

from __future__ import annotations

from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from fpdf import FPDF

from .ordenacao import NIVEIS_INICIAIS
from .variantes import VarianteCV

FONTE_DOCX = "Calibri"      # fonte padrão amplamente aceita por ATS
FONTE_PDF = "Helvetica"     # fonte-base do PDF (sem download, sempre legível)
LINHAS_POR_PAGINA = 46      # estimativa para o aviso de tamanho do DOCX


def paginas_alvo_padrao(nivel: str) -> int:
    return 1 if nivel.lower() in NIVEIS_INICIAIS else 2


# ---------------------------------------------------------------- DOCX

def exportar_docx(variante: VarianteCV, destino: Path) -> Path:
    doc = docx.Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = FONTE_DOCX
    estilo.font.size = Pt(11)
    for secao_doc in doc.sections:  # margens enxutas, uma coluna
        secao_doc.top_margin = secao_doc.bottom_margin = Pt(36)
        secao_doc.left_margin = secao_doc.right_margin = Pt(42)

    nome = doc.add_paragraph()
    nome.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = nome.add_run(variante.nome)
    run.bold = True
    run.font.size = Pt(16)
    for linha in variante.cabecalho:
        p = doc.add_paragraph(linha)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)

    for secao in variante.secoes:
        titulo = doc.add_paragraph()
        titulo.paragraph_format.space_before = Pt(10)
        titulo.paragraph_format.space_after = Pt(4)
        run = titulo.add_run(secao.titulo.upper())
        run.bold = True
        run.font.size = Pt(12)

        if secao.paragrafo:
            doc.add_paragraph(secao.paragrafo)
        for item in secao.itens:
            cab = doc.add_paragraph()
            cab.paragraph_format.space_after = Pt(1)
            r = cab.add_run(item.titulo)
            r.bold = True
            detalhes = " — ".join(p for p in [item.subtitulo, item.periodo] if p)
            if detalhes:
                cab.add_run(f" | {detalhes}")
            for marcador in item.marcadores:
                m = doc.add_paragraph(marcador, style="List Bullet")
                m.paragraph_format.space_after = Pt(1)

    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(destino))
    return destino


def estimar_paginas_docx(variante: VarianteCV) -> int:
    linhas = 1 + len(variante.cabecalho)
    for secao in variante.secoes:
        linhas += 2
        if secao.paragrafo:
            linhas += max(1, len(secao.paragrafo) // 90)
        for item in secao.itens:
            linhas += 1
            for marcador in item.marcadores:
                linhas += max(1, len(marcador) // 90)
    return max(1, -(-linhas // LINHAS_POR_PAGINA))


# ---------------------------------------------------------------- PDF

def _latin(texto: str) -> str:
    return texto.encode("latin-1", "replace").decode("latin-1")


def exportar_pdf(variante: VarianteCV, destino: Path) -> tuple[Path, int]:
    """Gera o PDF e devolve (caminho, nº de páginas)."""
    pdf = FPDF(format="A4")
    pdf.set_margins(left=15, top=13, right=15)
    pdf.set_auto_page_break(auto=True, margin=13)
    pdf.add_page()
    largura = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font(FONTE_PDF, style="B", size=16)
    pdf.cell(largura, 8, _latin(variante.nome), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONTE_PDF, size=10)
    for linha in variante.cabecalho:
        pdf.cell(largura, 5, _latin(linha), align="C", new_x="LMARGIN", new_y="NEXT")

    for secao in variante.secoes:
        pdf.ln(3)
        pdf.set_font(FONTE_PDF, style="B", size=12)
        pdf.cell(largura, 6, _latin(secao.titulo.upper()), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(FONTE_PDF, size=11)
        if secao.paragrafo:
            pdf.multi_cell(largura, 5, _latin(secao.paragrafo), new_x="LMARGIN", new_y="NEXT")
        for item in secao.itens:
            pdf.set_font(FONTE_PDF, style="B", size=11)
            cab = item.titulo
            detalhes = " — ".join(p for p in [item.subtitulo, item.periodo] if p)
            if detalhes:
                cab += f" | {detalhes}"
            pdf.multi_cell(largura, 5, _latin(cab), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(FONTE_PDF, size=11)
            for marcador in item.marcadores:
                pdf.multi_cell(largura, 5, _latin(f"- {marcador}"), new_x="LMARGIN", new_y="NEXT")

    destino.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(destino))
    return destino, pdf.page_no()


def aviso_de_tamanho(paginas: int, alvo: int, formato: str) -> str | None:
    if paginas <= alvo:
        return None
    return (
        f"{formato}: ficou com {paginas} página(s) para um alvo de {alvo}. "
        "Enxugue marcadores ou remova itens menos relevantes ao foco (os últimos de cada seção)."
    )
