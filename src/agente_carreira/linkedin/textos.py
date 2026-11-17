"""Textos do LinkedIn em modo copiloto (RF-LI-02 a RF-LI-05).

Tudo é montado só com dados registrados no perfil-mestre (RN-02); o usuário
revisa, copia e cola no LinkedIn. Polimento e tradução passam pelo fluxo de
reescrita com IA (RF-IA-02).
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from ..models import PerfilMestre
from ..analise.termos import TermoFrequente
from ..analise.variantes import FOCOS
from .limites import LIMITES


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _stack_do_foco(perfil: PerfilMestre, foco: str, maximo: int = 4) -> list[str]:
    chaves = [_norm(c) for c in FOCOS.get(foco, [])]
    do_foco = [
        c for c in perfil.competencias_tecnicas
        if any(re.search(rf"(?<![\w#+.]){re.escape(ch)}(?![\w#])", _norm(c)) or ch == _norm(c) for ch in chaves)
    ]
    resto = [c for c in perfil.competencias_tecnicas if c not in do_foco]
    return (do_foco + resto)[:maximo]


# ---------------------------------------------------------------- RF-LI-02

class OpcaoTitulo(BaseModel):
    texto: str
    caracteres: int
    dentro_do_limite: bool
    essencial_nos_primeiros_60: bool


def gerar_titulos(perfil: PerfilMestre, foco: str, cargo_alvo: str) -> list[OpcaoTitulo]:
    """3 opções de título: cargo-alvo + stack + diferencial (RF-LI-02)."""
    stack = " · ".join(_stack_do_foco(perfil, foco))
    formacao = perfil.formacao[0] if perfil.formacao else None
    diferencial_formacao = f"{formacao.curso} — {formacao.instituicao}" if formacao else None
    certificacao = perfil.certificacoes[0].nome if perfil.certificacoes else None

    candidatos = [
        " | ".join(p for p in [cargo_alvo, stack, diferencial_formacao] if p),
        " | ".join(p for p in [f"{cargo_alvo} em formação" if formacao else cargo_alvo, stack] if p),
        " | ".join(p for p in [cargo_alvo, stack, certificacao] if p)
        if certificacao
        else " | ".join(p for p in [diferencial_formacao, stack] if p),
    ]

    opcoes: list[OpcaoTitulo] = []
    for texto in candidatos:
        if not texto or any(texto == o.texto for o in opcoes):
            continue
        inicio = _norm(texto[: LIMITES["titulo_trecho_visivel"]])
        tem_essencial = _norm(cargo_alvo.split()[0]) in inicio or any(
            _norm(s) in inicio for s in _stack_do_foco(perfil, foco, maximo=2)
        )
        opcoes.append(OpcaoTitulo(
            texto=texto,
            caracteres=len(texto),
            dentro_do_limite=len(texto) <= LIMITES["titulo"],
            essencial_nos_primeiros_60=tem_essencial,
        ))
    return opcoes[:3]


# ---------------------------------------------------------------- RF-LI-03

class SecaoSobre(BaseModel):
    texto: str
    caracteres: int
    dentro_do_limite: bool
    abertura: str  # os ~300 primeiros caracteres (antes do "ver mais")


def gerar_sobre(perfil: PerfilMestre, foco: str) -> SecaoSobre:
    """Seção Sobre montada só com material registrado (RF-LI-03)."""
    blocos: list[str] = []
    if perfil.resumo:
        blocos.append(perfil.resumo)
    elif perfil.objetivo:
        blocos.append(perfil.objetivo)

    stack = _stack_do_foco(perfil, foco, maximo=8)
    if stack:
        blocos.append("Stack principal: " + ", ".join(stack) + ".")

    projetos = [p for p in perfil.projetos if p.tecnologias][:3]
    if projetos:
        linhas = [
            f"• {p.nome} ({', '.join(p.tecnologias)})" + (f" — {p.descricao}" if p.descricao else "")
            for p in projetos
        ]
        blocos.append("Projetos:\n" + "\n".join(linhas))

    conquistas = [c for c in perfil.banco_conquistas if c.numero][:2]
    if conquistas:
        blocos.append(
            "Resultados: " + "; ".join(f"{c.verbo_acao} {c.descricao} ({c.numero})" for c in conquistas) + "."
        )

    if perfil.formacao:
        f = perfil.formacao[0]
        frase = f"Formação: {f.curso} — {f.instituicao}"
        if f.conclusao_prevista:
            frase += f" (conclusão prevista em {f.conclusao_prevista})"
        blocos.append(frase + ".")

    contatos = [p for p in [perfil.links.github, perfil.links.portfolio] if p]
    if contatos:
        blocos.append("Contato e portfólio: " + " | ".join(contatos))

    texto = "\n\n".join(blocos)
    return SecaoSobre(
        texto=texto,
        caracteres=len(texto),
        dentro_do_limite=len(texto) <= LIMITES["sobre"],
        abertura=texto[: LIMITES["sobre_abertura"]],
    )


# ---------------------------------------------------------------- RF-LI-04

class ExperienciaLinkedIn(BaseModel):
    cargo: str
    empresa: str
    periodo: str  # mesmos dados do CV (RF-LI-04)
    texto: str
    caracteres: int
    dentro_do_limite: bool


def gerar_experiencias(perfil: PerfilMestre) -> list[ExperienciaLinkedIn]:
    conquistas = {c.id: c for c in perfil.banco_conquistas}
    resultado: list[ExperienciaLinkedIn] = []
    for exp in perfil.experiencias:
        linhas = [f"• {r}" for r in exp.responsabilidades]
        for cid in exp.conquista_ids:
            if c := conquistas.get(cid):
                frase = f"• {c.verbo_acao} {c.descricao}"
                if c.resultado:
                    frase += f" — {c.resultado}"
                if c.numero:
                    frase += f" ({c.numero})"
                linhas.append(frase)
        if exp.tecnologias:
            linhas.append("Tecnologias: " + ", ".join(exp.tecnologias))
        if exp.competencias_transferiveis:
            linhas.append("Competências: " + ", ".join(exp.competencias_transferiveis))
        texto = "\n".join(linhas)
        fim = f"{exp.periodo.fim.month:02d}/{exp.periodo.fim.year}" if exp.periodo.fim else "atual"
        resultado.append(ExperienciaLinkedIn(
            cargo=exp.cargo,
            empresa=exp.empresa,
            periodo=f"{exp.periodo.inicio.month:02d}/{exp.periodo.inicio.year} – {fim}",
            texto=texto,
            caracteres=len(texto),
            dentro_do_limite=len(texto) <= LIMITES["experiencia"],
        ))
    return resultado


# ---------------------------------------------------------------- RF-LI-05

class CompetenciaSugerida(BaseModel):
    nome: str
    vagas_em_que_aparece: int = 0
    vinculos: list[str] = Field(default_factory=list)  # experiência/projeto/formação onde foi usada


def sugerir_competencias(perfil: PerfilMestre, termos: list[TermoFrequente]) -> list[CompetenciaSugerida]:
    """Competências priorizadas pela frequência nas vagas-alvo, no limite da seção (RF-LI-05)."""
    frequencia = {_norm(t.termo): t.vagas_em_que_aparece for t in termos}

    def vinculos_de(nome: str) -> list[str]:
        alvo = _norm(nome)
        achados: list[str] = []
        for exp in perfil.experiencias:
            if any(_norm(t) == alvo for t in exp.tecnologias):
                achados.append(f"experiência: {exp.cargo} ({exp.empresa})")
        for proj in perfil.projetos:
            if any(_norm(t) == alvo for t in proj.tecnologias):
                achados.append(f"projeto: {proj.nome}")
        for form in perfil.formacao:
            if alvo in _norm(form.curso):
                achados.append(f"formação: {form.curso}")
        return achados

    sugeridas = [
        CompetenciaSugerida(
            nome=c,
            vagas_em_que_aparece=frequencia.get(_norm(c), 0),
            vinculos=vinculos_de(c),
        )
        for c in perfil.competencias_tecnicas + perfil.competencias_comportamentais
    ]
    sugeridas.sort(key=lambda s: (-s.vagas_em_que_aparece, s.nome.lower()))
    # As vinculadas a experiências não contam no limite da seção (RF-LI-05).
    limite = LIMITES["competencias"]
    resultado: list[CompetenciaSugerida] = []
    sem_vinculo_usadas = 0
    for s in sugeridas:
        if s.vinculos:
            resultado.append(s)
        elif sem_vinculo_usadas < limite:
            resultado.append(s)
            sem_vinculo_usadas += 1
    return resultado
