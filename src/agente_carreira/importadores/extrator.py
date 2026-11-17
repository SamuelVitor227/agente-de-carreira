"""Heurísticas de extração sobre texto bruto de CV (RF-PM-02).

Extrai apenas o que está literalmente no texto — nada é inventado (RN-02).
A interpretação fina (experiências, datas) fica como rascunho para o usuário
confirmar e completar.
"""

from __future__ import annotations

import re

from .resultado import ResultadoImportacao

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
TELEFONE_RE = re.compile(r"(?:\+55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}[-\s]?\d{4}")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?[\w.-]+\.[a-z]{2,}(?:/[\w\-./%?=&#]*)?", re.IGNORECASE)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-./]+", re.IGNORECASE)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[\w\-./%]+", re.IGNORECASE)

# Vocabulário mínimo para detectar competências técnicas citadas no texto.
# É configuração, não código definitivo: cresce conforme o uso (RNF-14).
TECNOLOGIAS_CONHECIDAS = [
    ".NET", "C#", "ASP.NET", "Entity Framework", "Python", "Java", "JavaScript",
    "TypeScript", "React", "React Native", "Node.js", "SQL", "SQL Server",
    "PostgreSQL", "MySQL", "MongoDB", "AWS", "Azure", "Docker", "Kubernetes",
    "Git", "GitHub", "Linux", "REST", "GraphQL", "HTML", "CSS", "Angular",
    "Flutter", "Kotlin", "Swift", "PHP", "C++", "Go", "Scrum", "Kanban",
]


def extrair_de_texto(texto: str, origem: str) -> ResultadoImportacao:
    resultado = ResultadoImportacao(origem=origem, texto_bruto=texto.strip() or None)

    if m := EMAIL_RE.search(texto):
        resultado.email = m.group(0)

    if m := GITHUB_RE.search(texto):
        resultado.github = _normalizar_url(m.group(0))

    if m := LINKEDIN_RE.search(texto):
        resultado.linkedin = _normalizar_url(m.group(0))

    if m := TELEFONE_RE.search(texto):
        candidato = m.group(0).strip()
        # Evita confundir trechos de datas ou números soltos com telefone.
        if sum(c.isdigit() for c in candidato) >= 10:
            resultado.telefone = candidato

    resultado.outros_links = _outros_links(texto, excluir=[resultado.github, resultado.linkedin])
    _aplicar_secoes(resultado, texto)
    return resultado


def _aplicar_secoes(resultado: ResultadoImportacao, texto: str) -> None:
    """Completa a extração com o que as seções do CV dizem (objetivo, projetos, experiências...)."""
    from ..models import ExperienciaRascunho, FormacaoRascunho
    from .resultado import CertificacaoRascunho, IdiomaRascunho, ProjetoRascunho
    from .secoes import ler_secoes

    secoes = ler_secoes(texto)
    resultado.nome = secoes.nome
    resultado.cidade, resultado.uf = secoes.cidade, secoes.uf
    resultado.objetivo = secoes.objetivo
    resultado.resumo = secoes.resumo
    competencias = list(secoes.competencias)
    for tecnologia in _detectar_tecnologias(texto):
        # "HTML" já está em "HTML5", "AWS" em "AWS (fundamentos)"; "Java" não está em "JavaScript".
        coberta = re.compile(rf"(?<![a-z0-9]){re.escape(tecnologia.lower())}(?![a-z])")
        if not any(coberta.search(c.lower()) for c in competencias):
            competencias.append(tecnologia)
    resultado.competencias = competencias
    resultado.idiomas = [IdiomaRascunho(idioma=i, nivel=n) for i, n in secoes.idiomas]
    resultado.projetos = [ProjetoRascunho(nome=p.nome, tecnologias=p.tecnologias, descricao=p.descricao) for p in secoes.projetos]
    resultado.experiencias = [
        ExperienciaRascunho(cargo=e.cargo, empresa=e.empresa, periodo_texto=e.periodo, descricao=e.descricao,
                            origem=resultado.origem)
        for e in secoes.experiencias
    ]
    resultado.formacoes = [
        FormacaoRascunho(curso=f.curso, instituicao=f.instituicao, periodo_texto=f.periodo, observacoes=f.observacoes,
                         origem=resultado.origem)
        for f in secoes.formacoes
    ]
    resultado.certificacoes = [CertificacaoRascunho(nome=c.nome, emissor=c.emissor, data_texto=c.data) for c in secoes.certificacoes]


def _normalizar_url(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/.,;")


def _outros_links(texto: str, excluir: list[str | None]) -> list[str]:
    excluidos = {u.lower() for u in excluir if u}
    links: list[str] = []
    for m in URL_RE.finditer(texto):
        bruto = m.group(0)
        # Descarta e-mails capturados pelo padrão de URL e domínios sem caminho
        # que provavelmente são só texto (ex.: "empresa.com" dentro de frase).
        if "@" in texto[max(0, m.start() - 1) : m.end() + 1]:
            continue
        if not bruto.lower().startswith(("http", "www.")) and "/" not in bruto:
            continue
        url = _normalizar_url(bruto)
        chave = url.lower()
        if chave in excluidos or any(chave == l.lower() for l in links):
            continue
        if "linkedin.com" in chave or "github.com" in chave:
            continue
        links.append(url)
    return links


def _detectar_tecnologias(texto: str) -> list[str]:
    encontradas: list[str] = []
    for tec in TECNOLOGIAS_CONHECIDAS:
        padrao = re.compile(rf"(?<![\w#+.]){re.escape(tec)}(?![\w#])", re.IGNORECASE)
        if padrao.search(texto):
            encontradas.append(tec)
    return encontradas
