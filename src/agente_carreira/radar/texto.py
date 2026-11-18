"""Utilitários de texto do radar: normalização, tokens, casamento de cargos e similaridade."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

STOPWORDS = {
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "para", "pra", "com", "por", "que",
    "ou", "ao", "aos", "os", "as", "um", "uma", "se", "sua", "seu", "suas", "seus", "mais", "como",
    "nao", "sao", "ser", "ter", "sobre", "entre", "sem", "ate", "ja", "voce", "nosso", "nossa",
    "the", "and", "of", "to", "in", "for", "with", "on", "is", "are", "be", "at", "an", "or", "we",
    "you", "our", "your", "will", "this", "that", "it", "by", "from", "as",
}

# Variações que devem casar entre si (gênero, abreviações e inglês → português).
STEM = {
    "estagiario": "estagio", "estagiaria": "estagio", "estagiarios": "estagio", "estagios": "estagio",
    "intern": "estagio", "internship": "estagio",
    "desenvolvedora": "desenvolvedor", "desenvolvedores": "desenvolvedor", "developer": "desenvolvedor",
    "dev": "desenvolvedor", "programadora": "programador", "programmer": "programador",
    "engenheira": "engenheiro", "engineer": "engenheiro", "analistas": "analista",
    "jr": "junior", "sr": "senior",
    "trainees": "trainee", "tecnologias": "tecnologia", "sistema": "sistemas", "tecnica": "tecnico",
    "tecnicos": "tecnico", "programadores": "programador", "estagiarias": "estagio", "desenvolvimentos": "desenvolvimento",
    "informatica": "informatica", "seguranca": "seguranca", "it": "ti",
}

_TOKEN = re.compile(r"(?:(?<![a-z0-9])\.)?[a-z0-9][a-z0-9#+]*(?:\.[a-z0-9]+)*")


def norm(texto: str | None) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def slug(texto: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(texto))


def tokens(texto: str | None) -> list[str]:
    saida: list[str] = []
    for token in _TOKEN.findall(norm(texto)):
        token = STEM.get(token, token)
        if len(token) > 1 and token not in STOPWORDS:
            saida.append(token)
    return saida


def casa_cargo(titulo: str, cargos: list[str]) -> bool:
    """O título contém todas as palavras de algum cargo (ou sinônimo) da busca."""
    do_titulo = set(tokens(titulo))
    for cargo in cargos:
        exigidos = set(tokens(cargo))
        if exigidos and exigidos <= do_titulo:
            return True
    return False


def jaccard(a: set[str], b: set[str]) -> float:
    uniao = a | b
    return len(a & b) / len(uniao) if uniao else 0.0


def cosseno_contagem(a: str, b: str) -> float:
    ca, cb = Counter(tokens(a)), Counter(tokens(b))
    if not ca or not cb:
        return 0.0
    produto = sum(ca[t] * cb[t] for t in ca.keys() & cb.keys())
    return produto / (math.sqrt(sum(v * v for v in ca.values())) * math.sqrt(sum(v * v for v in cb.values())))
