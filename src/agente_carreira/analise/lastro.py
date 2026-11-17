"""Checagem automática de lastro (RN-02, RNF-09, CA-02).

Todo CV gerado — variante ou sob medida — só pode conter cargos, empresas,
datas, projetos, formações, certificações, idiomas e tecnologias que existem
no perfil-mestre confirmado. Rascunhos de importação não contam como lastro.
"""

from __future__ import annotations

import re
import unicodedata

from ..models import PerfilMestre
from ..radar.aderencia import documento_perfil, tecnologias_em
from .variantes import TITULOS, VarianteCV

_DATA = re.compile(r"\b(\d{2})/(\d{4})\b")
_CHAVE_POR_TITULO = {titulo: chave for por_idioma in TITULOS.values() for chave, titulo in por_idioma.items()}


def _norm(texto: str | None) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower().strip()


def _mes_ano(d) -> str:
    return f"{d.month:02d}/{d.year}"


def fatos_do_perfil(perfil: PerfilMestre) -> dict[str, set[str]]:
    datas = set()
    for exp in perfil.experiencias:
        datas.add(_mes_ano(exp.periodo.inicio))
        if exp.periodo.fim:
            datas.add(_mes_ano(exp.periodo.fim))
    return {
        "cargos": {_norm(e.cargo) for e in perfil.experiencias},
        "empresas": {_norm(e.empresa) for e in perfil.experiencias},
        "projetos": {_norm(p.nome) for p in perfil.projetos},
        "cursos": {_norm(f.curso) for f in perfil.formacao},
        "certificacoes": {_norm(c.nome) for c in perfil.certificacoes},
        "idiomas": {_norm(i.idioma) for i in perfil.idiomas},
        "datas": datas,
        # Nomes próprios registrados (emissor "AWS Academy", empresa, instituição) também são lastro.
        "tecnologias": {_norm(t) for t in tecnologias_em("\n".join([
            documento_perfil(perfil),
            *(c.emissor or "" for c in perfil.certificacoes),
            *(f.instituicao for f in perfil.formacao),
            *(e.empresa for e in perfil.experiencias),
        ]))},
    }


def verificar_lastro(variante: VarianteCV, perfil: PerfilMestre) -> list[str]:
    """Lista tudo no CV que não tem lastro no perfil-mestre (vazia = CV fiel ao perfil)."""
    fatos = fatos_do_perfil(perfil)
    problemas: list[str] = []

    def apontar(mensagem: str) -> None:
        if mensagem not in problemas:
            problemas.append(mensagem)

    for secao in variante.secoes:
        chave = _CHAVE_POR_TITULO.get(secao.titulo)
        if chave is None:
            apontar(f"seção fora do modelo: {secao.titulo}")
        for item in secao.itens:
            if chave in ("experiencia", "outras"):
                if _norm(item.titulo) not in fatos["cargos"]:
                    apontar(f"cargo sem lastro: {item.titulo}")
                empresa = (item.subtitulo or "").split(" — ")[0]
                if _norm(empresa) not in fatos["empresas"]:
                    apontar(f"empresa sem lastro: {empresa}")
                for mes, ano in _DATA.findall(item.periodo or ""):
                    if f"{mes}/{ano}" not in fatos["datas"]:
                        apontar(f"data sem lastro: {mes}/{ano} em {item.titulo}")
            elif chave == "projetos" and _norm(item.titulo) not in fatos["projetos"]:
                apontar(f"projeto sem lastro: {item.titulo}")
            elif chave == "formacao" and _norm(item.titulo) not in fatos["cursos"]:
                apontar(f"formação sem lastro: {item.titulo}")
            elif chave == "certificacoes" and _norm(item.titulo) not in fatos["certificacoes"]:
                apontar(f"certificação sem lastro: {item.titulo}")
            elif chave == "idiomas" and _norm(item.titulo) not in fatos["idiomas"]:
                apontar(f"idioma sem lastro: {item.titulo}")
        textos = [secao.paragrafo or ""] + [t for i in secao.itens for t in (i.titulo, i.subtitulo or "", *i.marcadores)]
        for texto in textos:
            for tecnologia in tecnologias_em(texto):
                if _norm(tecnologia) not in fatos["tecnologias"]:
                    apontar(f"tecnologia sem lastro: {tecnologia}")
    return problemas
