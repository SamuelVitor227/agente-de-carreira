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
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.shared import Cm, Pt, RGBColor
from fpdf import FPDF

from .ordenacao import NIVEIS_INICIAIS
from .variantes import VarianteCV

FONTE_DOCX = "Calibri"      # fonte padrão amplamente aceita por ATS
FONTE_PDF = "Helvetica"     # fonte-base do PDF (sem download, sempre legível)
LINHAS_POR_PAGINA = 54      # estimativa para o aviso de tamanho do DOCX (A4, Calibri 10,5, margens de 1,3-1,5 cm)


def paginas_alvo_padrao(nivel: str) -> int:
    return 1 if nivel.lower() in NIVEIS_INICIAIS else 2


# ---------------------------------------------------------------- DOCX

AZUL = RGBColor(0x0F, 0x2B, 0x46)
CINZA = RGBColor(0x4A, 0x55, 0x60)


def _borda_inferior(paragrafo) -> None:
    """Linha fina embaixo do título da seção (como no PDF)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    propriedades = paragrafo._p.get_or_add_pPr()
    bordas = OxmlElement("w:pBdr")
    baixo = OxmlElement("w:bottom")
    for chave, valor in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "B9C6D3")):
        baixo.set(qn(chave), valor)
    bordas.append(baixo)
    propriedades.append(bordas)


def _espaco(paragrafo, antes: float = 0, depois: float = 1.5) -> None:
    formato = paragrafo.paragraph_format
    formato.space_before, formato.space_after, formato.line_spacing = Pt(antes), Pt(depois), 1.05


def exportar_docx(variante: VarianteCV, destino: Path) -> Path:
    """Word com o mesmo visual do PDF: nome em destaque, seções com linha, datas à direita, competências agrupadas."""
    from .cv_html import _contato, _rotulo_grupo, agrupar_competencias

    doc = docx.Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = FONTE_DOCX
    estilo.font.size = Pt(10.5)
    largura_util = None
    for secao_doc in doc.sections:  # A4, margens enxutas, uma coluna
        secao_doc.page_width, secao_doc.page_height = Cm(21), Cm(29.7)
        secao_doc.top_margin = secao_doc.bottom_margin = Cm(1.3)
        secao_doc.left_margin = secao_doc.right_margin = Cm(1.5)
        largura_util = secao_doc.page_width - secao_doc.left_margin - secao_doc.right_margin

    nome = doc.add_paragraph()
    _espaco(nome, depois=2)
    run = nome.add_run(variante.nome)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(20), AZUL
    for linha in variante.cabecalho:
        contato = doc.add_paragraph()
        _espaco(contato, depois=0)
        r = contato.add_run(_contato(linha).replace("&amp;", "&"))
        r.font.size, r.font.color.rgb = Pt(9.5), CINZA

    for secao in variante.secoes:
        if not secao.paragrafo and not secao.itens:
            continue
        titulo = doc.add_paragraph()
        _espaco(titulo, antes=8, depois=3)
        _borda_inferior(titulo)
        run = titulo.add_run(secao.titulo.upper())
        run.bold, run.font.size, run.font.color.rgb = True, Pt(10), AZUL

        if secao.paragrafo:
            if secao.titulo.lower() in ("competências", "skills") and len(agrupar_competencias(secao.paragrafo)) > 1:
                for grupo, itens in agrupar_competencias(secao.paragrafo):
                    p = doc.add_paragraph()
                    _espaco(p, depois=1)
                    p.add_run(f"{_rotulo_grupo(grupo, variante.idioma)}: ").bold = True
                    p.add_run(", ".join(itens))
            else:
                _espaco(doc.add_paragraph(secao.paragrafo), depois=2)
        compacta = secao.itens and all(not i.marcadores and not i.periodo for i in secao.itens) \
            and secao.titulo.lower() in ("idiomas", "languages")
        if compacta:
            p = doc.add_paragraph()
            for k, item in enumerate(secao.itens):
                if k:
                    p.add_run(" · ")
                p.add_run(item.titulo).bold = True
                if item.subtitulo:
                    p.add_run(f" ({item.subtitulo})")
            continue
        for item in secao.itens:
            cab = doc.add_paragraph()
            _espaco(cab, antes=2, depois=0.5)
            if largura_util is not None:
                cab.paragraph_format.tab_stops.add_tab_stop(largura_util, WD_TAB_ALIGNMENT.RIGHT)
            cab.add_run(item.titulo).bold = True
            if item.subtitulo:
                cab.add_run(f" — {item.subtitulo}")
            if item.periodo:
                r = cab.add_run(f"\t{item.periodo}")
                r.font.size, r.font.color.rgb = Pt(9.5), CINZA
            for marcador in item.marcadores:
                rotulo, sep, resto = marcador.partition(":")
                if sep and rotulo.strip().lower() in ("tecnologias", "technologies", "competências transferíveis",
                                                       "transferable skills"):
                    p = doc.add_paragraph()
                    _espaco(p, depois=0.5)
                    r1 = p.add_run(f"{rotulo.strip()}: ")
                    r1.bold, r1.font.size = True, Pt(9.5)
                    p.add_run(resto.strip()).font.size = Pt(9.5)
                else:
                    m = doc.add_paragraph(marcador, style="List Bullet")
                    _espaco(m, depois=0.5)

    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(destino))
    return destino


def estimar_paginas_docx(variante: VarianteCV) -> int:
    linhas = 1 + len(variante.cabecalho)
    for secao in variante.secoes:
        linhas += 2
        if secao.paragrafo:
            linhas += max(1, -(-len(secao.paragrafo) // 105))
        if secao.titulo.lower() in ("idiomas", "languages"):
            linhas += 1  # uma linha só
            continue
        for item in secao.itens:
            linhas += 1
            for marcador in item.marcadores:
                linhas += max(1, -(-len(marcador) // 105))
    return max(1, -(-linhas // LINHAS_POR_PAGINA))


# ---------------------------------------------------------------- PDF

_TROCAS_PDF = str.maketrans({
    "–": "-", "—": "-", "‒": "-", "•": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", " ": " ",
})


def _latin(texto: str) -> str:
    """A fonte-base do PDF é latin-1: troca a pontuação tipográfica por equivalentes legíveis por ATS."""
    return texto.translate(_TROCAS_PDF).encode("latin-1", "replace").decode("latin-1")


def exportar_pdf(variante: VarianteCV, destino: Path, paginas_alvo: int | None = None) -> tuple[Path, int]:
    """Gera o PDF e devolve (caminho, nº de páginas).

    Usa o modelo HTML/CSS impresso pelo Chromium (visual profissional, ainda legível por ATS); sem Chromium,
    cai para o motor simples (fpdf2).
    """
    from .cv_html import exportar_pdf_html

    try:
        return exportar_pdf_html(variante, destino, paginas_alvo or paginas_alvo_padrao(variante.nivel))
    except Exception:  # noqa: BLE001 - Playwright/Chromium indisponível: motor simples
        return exportar_pdf_simples(variante, destino)


def exportar_pdf_simples(variante: VarianteCV, destino: Path) -> tuple[Path, int]:
    """Motor de reserva, sem navegador (fpdf2)."""
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
