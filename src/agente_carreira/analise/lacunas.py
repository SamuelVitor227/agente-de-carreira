"""Relatório de lacunas entre o perfil-mestre e as vagas-alvo (RF-CV-02).

Três grupos:
1. Você tem e já aparece no CV (competências/tecnologias declaradas).
2. Você tem, mas não aparece (está só em textos: responsabilidades,
   conquistas, projetos, resumo) — basta destacar.
3. Você não tem (ou não registrou) — fechar de verdade, nunca inventar (RN-02).
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from ..models import PerfilMestre
from .termos import TermoFrequente


class ItemLacuna(BaseModel):
    termo: str
    vagas_em_que_aparece: int
    percentual: int
    onde_encontrado: str | None = None
    origens: list[str] = Field(default_factory=list)  # CA-04: vagas de onde o termo veio


class RelatorioLacunas(BaseModel):
    total_de_vagas: int
    ja_no_cv: list[ItemLacuna] = Field(default_factory=list)
    tem_mas_nao_aparece: list[ItemLacuna] = Field(default_factory=list)
    nao_tem: list[ItemLacuna] = Field(default_factory=list)


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _contem_termo(texto_norm: str, termo: str) -> bool:
    padrao = re.compile(rf"(?<![\w#+.]){re.escape(_norm(termo))}(?![\w#])")
    return bool(padrao.search(texto_norm))


def gerar_relatorio(perfil: PerfilMestre, termos: list[TermoFrequente]) -> RelatorioLacunas:
    declarados = [
        *perfil.competencias_tecnicas,
        *perfil.competencias_comportamentais,
        *(t for e in perfil.experiencias for t in e.tecnologias),
        *(t for p in perfil.projetos for t in p.tecnologias),
        *(t for c in perfil.banco_conquistas for t in c.tecnologias),
    ]
    texto_declarado = _norm(" | ".join(declarados))

    textos_livres: list[tuple[str, str]] = []
    if perfil.resumo:
        textos_livres.append(("resumo", perfil.resumo))
    if perfil.objetivo:
        textos_livres.append(("objetivo", perfil.objetivo))
    for exp in perfil.experiencias:
        origem = f"experiência {exp.cargo} ({exp.empresa})"
        for resp in exp.responsabilidades:
            textos_livres.append((origem, resp))
        textos_livres.extend((origem, ct) for ct in exp.competencias_transferiveis)
    for proj in perfil.projetos:
        if proj.descricao:
            textos_livres.append((f"projeto {proj.nome}", proj.descricao))
    for conq in perfil.banco_conquistas:
        trecho = " ".join(p for p in [conq.verbo_acao, conq.descricao, conq.resultado or ""] if p)
        textos_livres.append((f"conquista {conq.id}", trecho))
    for form in perfil.formacao:
        textos_livres.append((f"formação {form.curso}", f"{form.curso} {form.instituicao}"))
    for cert in perfil.certificacoes:
        textos_livres.append((f"certificação {cert.nome}", cert.nome))

    relatorio = RelatorioLacunas(total_de_vagas=termos[0].total_de_vagas if termos else 0)
    for termo in termos:
        item = ItemLacuna(
            termo=termo.termo,
            vagas_em_que_aparece=termo.vagas_em_que_aparece,
            percentual=termo.percentual,
            origens=list(termo.origens),
        )
        if _contem_termo(texto_declarado, termo.termo):
            relatorio.ja_no_cv.append(item)
            continue
        origem_encontrada = next(
            (origem for origem, texto in textos_livres if _contem_termo(_norm(texto), termo.termo)),
            None,
        )
        if origem_encontrada:
            item.onde_encontrado = origem_encontrada
            relatorio.tem_mas_nao_aparece.append(item)
        else:
            relatorio.nao_tem.append(item)
    return relatorio
