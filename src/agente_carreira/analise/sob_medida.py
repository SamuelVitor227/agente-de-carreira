"""Versão de CV sob medida por vaga (RF-CV-11) com cobertura e antes × depois (RF-CV-12).

A versão sob medida só usa itens do perfil-mestre (RN-02): seleciona e
reordena conquistas, experiências, projetos e competências pelos requisitos
daquela vaga; nada novo é escrito aqui.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from ..models import PerfilMestre
from ..vagas import Vaga
from .lacunas import gerar_relatorio
from .termos import extrair_termos
from .variantes import ItemCV, VarianteCV, gerar_variante

TERMOS_POR_VAGA = 20


class CoberturaVaga(BaseModel):
    """RF-CV-12: o que a vaga pede × o que o CV cobre."""

    atendidos: list[str] = Field(default_factory=list)       # com lastro no perfil
    incluidos: list[str] = Field(default_factory=list)       # presentes no texto da variante
    sem_lastro: list[str] = Field(default_factory=list)      # a vaga pede e o perfil não tem


class ResultadoSobMedida(BaseModel):
    vaga_id: str
    vaga_titulo: str
    variante: VarianteCV
    cobertura: CoberturaVaga
    mudancas: list[str] = Field(default_factory=list)  # antes × depois vs variante-base


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _contem(texto_norm: str, termo: str) -> bool:
    return bool(re.search(rf"(?<![\w#+.]){re.escape(_norm(termo))}(?![\w#])", texto_norm))


def _texto_do_item(item: ItemCV) -> str:
    return " ".join([item.titulo, item.subtitulo or "", *item.marcadores])


def _texto_da_variante(variante: VarianteCV) -> str:
    partes: list[str] = []
    for secao in variante.secoes:
        if secao.paragrafo:
            partes.append(secao.paragrafo)
        partes.extend(_texto_do_item(i) for i in secao.itens)
    return _norm(" ".join(partes))


def _relevancia_para_vaga(item: ItemCV, termos_vaga: list[str]) -> int:
    texto = _norm(_texto_do_item(item))
    return sum(1 for termo in termos_vaga if _contem(texto, termo))


def gerar_sob_medida(
    perfil: PerfilMestre, vaga: Vaga, foco: str, idioma: str = "pt", nivel: str = "estagio"
) -> ResultadoSobMedida:
    termos = extrair_termos([vaga], limite=TERMOS_POR_VAGA)
    nomes_termos = [t.termo for t in termos]

    base = gerar_variante(perfil, foco=foco, idioma=idioma, nivel=nivel)
    variante = base.model_copy(deep=True)
    mudancas: list[str] = []

    for secao, secao_base in zip(variante.secoes, base.secoes):
        if len(secao.itens) < 2:
            continue
        ordem_anterior = [i.titulo for i in secao_base.itens]
        secao.itens.sort(key=lambda i: -_relevancia_para_vaga(i, nomes_termos))
        for posicao, item in enumerate(secao.itens, 1):
            anterior = ordem_anterior.index(item.titulo) + 1
            if anterior != posicao:
                mudancas.append(
                    f"{secao.titulo}: {item.titulo!r} foi de {anterior}º para {posicao}º "
                    f"(requisitos da vaga)"
                )
        # Dentro de cada item, as conquistas/marcadores que citam termos da vaga sobem.
        for item in secao.itens:
            antes = list(item.marcadores)
            item.marcadores.sort(
                key=lambda m: -sum(1 for termo in nomes_termos if _contem(_norm(m), termo))
            )
            if item.marcadores != antes:
                mudancas.append(f"{secao.titulo} › {item.titulo}: marcadores reordenados pela vaga")

    # Competências: as pedidas pela vaga vêm primeiro (ajuste só com itens do perfil).
    for secao in variante.secoes:
        if secao.titulo in {"Competências", "Skills"} and secao.paragrafo:
            partes = [p.strip() for p in secao.paragrafo.replace("|", ",").split(",") if p.strip()]
            if len(partes) > 1:
                partes.sort(key=lambda c: not any(_contem(_norm(c), t) for t in nomes_termos))
                novo = ", ".join(partes)
                if novo != secao.paragrafo:
                    secao.paragrafo = novo
                    mudancas.append(f"{secao.titulo}: reordenadas pelos requisitos da vaga")

    relatorio = gerar_relatorio(perfil, termos)
    texto_final = _texto_da_variante(variante)
    cobertura = CoberturaVaga(
        atendidos=[i.termo for i in relatorio.ja_no_cv + relatorio.tem_mas_nao_aparece],
        incluidos=[t for t in nomes_termos if _contem(texto_final, t)],
        sem_lastro=[i.termo for i in relatorio.nao_tem],
    )
    return ResultadoSobMedida(
        vaga_id=vaga.id,
        vaga_titulo=vaga.titulo,
        variante=variante,
        cobertura=cobertura,
        mudancas=mudancas,
    )
