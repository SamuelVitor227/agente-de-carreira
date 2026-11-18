"""Variantes de CV por foco e idioma, derivadas da versão-base (RF-CV-07).

Cada variante seleciona e prioriza conteúdo do perfil-mestre para um foco
(backend .NET, cloud AWS, mobile, dados, suporte) e um idioma (pt/en), sem
acrescentar nada (RN-02): títulos de seção e rótulos são traduzidos, mas os
textos registrados permanecem como estão — tradução de conteúdo passa pelo
fluxo de reescrita com IA (RF-CV-03/RF-IA-02).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from ..models import Area, Experiencia, PerfilMestre, Projeto
from .ordenacao import NIVEIS_INICIAIS

# Palavras-chave que definem a relevância de cada foco (configuração, não código).
FOCOS: dict[str, list[str]] = {
    "backend-dotnet": ["c#", ".net", "asp.net", "entity framework", "sql server", "rest", "api", "backend"],
    "cloud-aws": ["aws", "cloud", "docker", "kubernetes", "linux", "lambda", "ec2", "s3"],
    "mobile": ["react native", "flutter", "kotlin", "swift", "mobile", "android", "ios"],
    "dados": ["sql", "python", "dados", "etl", "power bi", "analytics", "postgresql"],
    "suporte": ["suporte", "atendimento", "windows", "linux", "redes", "chamados", "help desk"],
}

IDIOMAS_SUPORTADOS = ("pt", "en")

TITULOS = {
    "pt": {
        "resumo": "Resumo", "formacao": "Formação Acadêmica", "projetos": "Projetos",
        "certificacoes": "Certificações", "experiencia": "Experiência Profissional",
        "outras": "Outras Experiências", "competencias": "Competências", "idiomas": "Idiomas",
    },
    "en": {
        "resumo": "Summary", "formacao": "Education", "projetos": "Projects",
        "certificacoes": "Certifications", "experiencia": "Professional Experience",
        "outras": "Additional Experience", "competencias": "Skills", "idiomas": "Languages",
    },
}

ROTULOS = {
    "pt": {"atual": "atual", "tecnologias": "Tecnologias", "transferiveis": "Competências transferíveis",
           "conclusao": "conclusão prevista", "cursando": "cursando", "concluido": "concluído"},
    "en": {"atual": "Present", "tecnologias": "Technologies", "transferiveis": "Transferable skills",
           "conclusao": "expected graduation", "cursando": "in progress", "concluido": "completed"},
}


class ItemCV(BaseModel):
    titulo: str
    subtitulo: str | None = None
    periodo: str | None = None
    marcadores: list[str] = Field(default_factory=list)
    relevancia: int = 0  # nº de termos do foco encontrados


class SecaoCV(BaseModel):
    titulo: str
    paragrafo: str | None = None
    itens: list[ItemCV] = Field(default_factory=list)


class VarianteCV(BaseModel):
    foco: str
    idioma: str
    nivel: str
    gerada_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    nome: str
    cabecalho: list[str] = Field(default_factory=list)  # contato em linhas de texto puro
    secoes: list[SecaoCV] = Field(default_factory=list)

    @property
    def nome_arquivo(self) -> str:
        return f"cv-{self.foco}-{self.idioma}"


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _relevancia(texto: str, foco: str) -> int:
    base = _norm(texto)
    pontos = 0
    for chave in FOCOS[foco]:
        if re.search(rf"(?<![\w#+.]){re.escape(_norm(chave))}(?![\w#])", base):
            pontos += 1
    return pontos


def _fmt_data(d: date) -> str:
    return f"{d.month:02d}/{d.year}"  # formato único de data (RF-CV-08)


def _fmt_periodo(exp: Experiencia, idioma: str) -> str:
    formatar = (lambda d: str(d.year)) if exp.periodo.so_ano else _fmt_data
    fim = formatar(exp.periodo.fim) if exp.periodo.fim else ROTULOS[idioma]["atual"]
    return f"{formatar(exp.periodo.inicio)} – {fim}"


def _item_experiencia(exp: Experiencia, perfil: PerfilMestre, foco: str, idioma: str) -> ItemCV:
    rot = ROTULOS[idioma]
    marcadores = list(exp.responsabilidades)
    conquistas = {c.id: c for c in perfil.banco_conquistas}
    for cid in exp.conquista_ids:
        if c := conquistas.get(cid):
            frase = f"{c.verbo_acao} {c.descricao}"
            if c.resultado:
                frase += f" — {c.resultado}"
            if c.numero:
                frase += f" ({c.numero})"
            marcadores.append(frase)
    if exp.tecnologias:
        marcadores.append(f"{rot['tecnologias']}: {', '.join(exp.tecnologias)}")
    if exp.competencias_transferiveis:
        marcadores.append(f"{rot['transferiveis']}: {', '.join(exp.competencias_transferiveis)}")
    texto_total = " ".join([exp.cargo, *exp.responsabilidades, *exp.tecnologias])
    return ItemCV(
        titulo=exp.cargo,
        subtitulo=exp.empresa + (f" — {exp.local}" if exp.local else ""),
        periodo=_fmt_periodo(exp, idioma),
        marcadores=marcadores,
        relevancia=_relevancia(texto_total, foco),
    )


def _item_projeto(proj: Projeto, foco: str, idioma: str) -> ItemCV:
    marcadores = []
    if proj.descricao:
        marcadores.append(proj.descricao)
    if proj.url:
        marcadores.append(proj.url)
    if proj.tecnologias:
        marcadores.append(f"{ROTULOS[idioma]['tecnologias']}: {', '.join(proj.tecnologias)}")
    texto_total = " ".join([proj.nome, proj.descricao or "", *proj.tecnologias])
    return ItemCV(titulo=proj.nome, marcadores=marcadores, relevancia=_relevancia(texto_total, foco))


def gerar_variante(
    perfil: PerfilMestre, foco: str, idioma: str = "pt", nivel: str = "estagio"
) -> VarianteCV:
    if foco not in FOCOS:
        raise ValueError(f"Foco desconhecido: {foco!r}. Válidos: {', '.join(FOCOS)}.")
    if idioma not in IDIOMAS_SUPORTADOS:
        raise ValueError(f"Idioma não suportado: {idioma!r}. Válidos: {', '.join(IDIOMAS_SUPORTADOS)}.")

    titulos = TITULOS[idioma]
    rot = ROTULOS[idioma]
    variante = VarianteCV(foco=foco, idioma=idioma, nivel=nivel, nome=perfil.contato.nome)

    local = ", ".join(p for p in [perfil.contato.cidade, perfil.contato.uf] if p)
    contatos = " | ".join(p for p in [perfil.contato.email, perfil.contato.telefone, local] if p)
    links = " | ".join(
        p for p in [perfil.links.github, perfil.links.linkedin, perfil.links.portfolio] if p
    )
    variante.cabecalho = [linha for linha in [contatos, links] if linha]

    secoes: list[SecaoCV] = []

    if perfil.resumo:
        secoes.append(SecaoCV(titulo=titulos["resumo"], paragrafo=perfil.resumo))

    # Itens ordenados pela relevância ao foco; empates ficam na ordem registrada.
    dentro = sorted(
        (_item_experiencia(e, perfil, foco, idioma) for e in perfil.experiencias if e.area == Area.TI),
        key=lambda i: -i.relevancia,
    )
    fora = sorted(
        (_item_experiencia(e, perfil, foco, idioma) for e in perfil.experiencias if e.area == Area.FORA_DE_TI),
        key=lambda i: -i.relevancia,
    )
    projetos = sorted((_item_projeto(p, foco, idioma) for p in perfil.projetos), key=lambda i: -i.relevancia)

    formacao = SecaoCV(
        titulo=titulos["formacao"],
        itens=[
            ItemCV(
                titulo=f.curso,
                subtitulo=f.instituicao,
                periodo=" — ".join(
                    p for p in [
                        rot.get(_norm(f.status or ""), f.status),
                        f"{rot['conclusao']} {f.conclusao_prevista}" if f.conclusao_prevista else None,
                    ] if p
                ) or None,
            )
            for f in perfil.formacao
        ],
    )
    certificacoes = SecaoCV(
        titulo=titulos["certificacoes"],
        itens=[ItemCV(titulo=c.nome, subtitulo=c.emissor) for c in perfil.certificacoes],
    )
    secao_projetos = SecaoCV(titulo=titulos["projetos"], itens=projetos)
    secao_dentro = SecaoCV(titulo=titulos["experiencia"], itens=dentro)
    secao_fora = SecaoCV(titulo=titulos["outras"], itens=fora)

    # Competências com as relevantes ao foco primeiro.
    tecnicas = sorted(perfil.competencias_tecnicas, key=lambda c: -_relevancia(c, foco))
    competencias = SecaoCV(
        titulo=titulos["competencias"],
        paragrafo=" | ".join(x for x in [", ".join(tecnicas), ", ".join(perfil.competencias_comportamentais)] if x) or None,
    )
    idiomas_secao = SecaoCV(
        titulo=titulos["idiomas"],
        itens=[ItemCV(titulo=i.idioma, subtitulo=i.nivel) for i in perfil.idiomas],
    )

    # Competências logo no começo: é o que o recrutador de TI procura primeiro.
    if nivel.lower() in NIVEIS_INICIAIS:
        ordem = [formacao, competencias, secao_projetos, secao_dentro, secao_fora, certificacoes]
    else:
        secao_dentro.itens = dentro + fora
        ordem = [secao_dentro, competencias, secao_projetos, formacao, certificacoes]

    secoes += ordem + [idiomas_secao]
    variante.secoes = [s for s in secoes if s.itens or s.paragrafo]
    return variante
