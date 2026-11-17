"""Reordenação de seções e itens pelo peso no nível-alvo (RF-CV-04).

Para estágio, trainee e júnior: formação, projetos e certificações vêm antes
de experiências fora da área. Para níveis plenos em diante, experiência
profissional lidera. A estrutura gerada aqui alimenta as variantes e a
exportação (RF-CV-07/08).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..models import Area, PerfilMestre

NIVEIS_INICIAIS = {"estagio", "trainee", "junior"}


class SecaoOrdenada(BaseModel):
    titulo: str  # títulos de seção padrão, amigáveis a ATS
    itens: list[str] = Field(default_factory=list)
    motivo: str | None = None


class EstruturaCV(BaseModel):
    nivel: str
    secoes: list[SecaoOrdenada] = Field(default_factory=list)


def _rotulo_experiencia(exp) -> str:
    fim = exp.periodo.fim.isoformat() if exp.periodo.fim else "atual"
    sufixo = " [fora da área]" if exp.area == Area.FORA_DE_TI else ""
    return f"{exp.cargo} — {exp.empresa} ({exp.periodo.inicio} a {fim}){sufixo}"


def ordenar_cv(perfil: PerfilMestre, nivel: str = "estagio") -> EstruturaCV:
    inicial = nivel.lower() in NIVEIS_INICIAIS
    estrutura = EstruturaCV(nivel=nivel)

    def adicionar(titulo: str, itens: list[str], motivo: str | None = None) -> None:
        if itens:
            estrutura.secoes.append(SecaoOrdenada(titulo=titulo, itens=itens, motivo=motivo))

    # Experiências: da área antes das fora da área; em cada grupo, a mais recente primeiro.
    dentro = [e for e in perfil.experiencias if e.area == Area.TI]
    fora = [e for e in perfil.experiencias if e.area == Area.FORA_DE_TI]
    dentro.sort(key=lambda e: (e.periodo.fim or date.max, e.periodo.inicio), reverse=True)
    fora.sort(key=lambda e: (e.periodo.fim or date.max, e.periodo.inicio), reverse=True)

    # Projetos: com tecnologias primeiro (mostram prática), depois os demais.
    projetos = sorted(perfil.projetos, key=lambda p: (not p.tecnologias, p.nome.lower()))
    itens_projetos = [
        p.nome + (f" ({', '.join(p.tecnologias)})" if p.tecnologias else "") for p in projetos
    ]

    # Formação: em andamento primeiro.
    formacao = sorted(perfil.formacao, key=lambda f: (f.status or "") != "cursando")
    itens_formacao = [
        f"{f.curso} — {f.instituicao}"
        + (f" (conclusão prevista {f.conclusao_prevista})" if f.conclusao_prevista else "")
        for f in formacao
    ]
    itens_certificacoes = [c.nome + (f" — {c.emissor}" if c.emissor else "") for c in perfil.certificacoes]
    itens_competencias = (
        [", ".join(perfil.competencias_tecnicas)] if perfil.competencias_tecnicas else []
    ) + ([", ".join(perfil.competencias_comportamentais)] if perfil.competencias_comportamentais else [])
    itens_idiomas = [f"{i.idioma} — {i.nivel}" for i in perfil.idiomas]

    if inicial:
        adicionar("Resumo", [perfil.resumo] if perfil.resumo else [])
        adicionar(
            "Formação Acadêmica", itens_formacao,
            motivo="nível inicial: formação pesa mais que experiência fora da área",
        )
        adicionar("Projetos", itens_projetos, motivo="projetos mostram prática no nível inicial")
        adicionar("Certificações", itens_certificacoes)
        adicionar("Experiência Profissional", [_rotulo_experiencia(e) for e in dentro])
        adicionar(
            "Outras Experiências", [_rotulo_experiencia(e) for e in fora],
            motivo="fora da área vem depois de formação, projetos e certificações",
        )
    else:
        adicionar("Resumo", [perfil.resumo] if perfil.resumo else [])
        adicionar(
            "Experiência Profissional",
            [_rotulo_experiencia(e) for e in dentro + fora],
            motivo="a partir do pleno, experiência lidera",
        )
        adicionar("Projetos", itens_projetos)
        adicionar("Formação Acadêmica", itens_formacao)
        adicionar("Certificações", itens_certificacoes)

    adicionar("Competências", itens_competencias)
    adicionar("Idiomas", itens_idiomas)
    return estrutura
