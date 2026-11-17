"""Extração de requisitos, competências e termos frequentes das vagas-alvo (RF-CV-01).

Roda no motor local (sem IA externa): dicionário de tecnologias + frequência
de palavras relevantes nas descrições das vagas.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from ..importadores.extrator import TECNOLOGIAS_CONHECIDAS
from ..vagas import Vaga

STOPWORDS_PT = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "em", "um", "uma", "para", "com",
    "que", "ou", "na", "no", "nas", "nos", "por", "se", "ao", "as", "os", "ser",
    "mais", "como", "sua", "seu", "suas", "seus", "entre", "sobre", "pela", "pelo",
    "nossa", "nosso", "voce", "você", "sera", "será", "temos", "ter", "area", "área",
    "vaga", "vagas", "empresa", "trabalho", "atuar", "atividades", "requisitos",
    "conhecimento", "conhecimentos", "experiencia", "experiência", "desejavel",
    "desejável", "diferencial", "beneficios", "benefícios", "ensino", "nivel", "nível",
}

MINIMO_DE_VAGAS = 2  # termo genérico só conta se aparecer em pelo menos N vagas


class TermoFrequente(BaseModel):
    termo: str
    vagas_em_que_aparece: int
    total_de_vagas: int
    e_tecnologia: bool
    origens: list[str] = Field(default_factory=list)  # CA-04: vagas de onde o termo veio

    @property
    def percentual(self) -> int:
        if not self.total_de_vagas:
            return 0
        return round(100 * self.vagas_em_que_aparece / self.total_de_vagas)


def _normalizar(palavra: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", palavra).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def extrair_termos(vagas: list[Vaga], limite: int = 30) -> list[TermoFrequente]:
    """Termos mais frequentes do conjunto, ordenados por nº de vagas em que aparecem."""
    total = len(vagas)
    if not total:
        return []

    origens: dict[tuple[str, bool], list[str]] = {}

    def anotar(termo: str, tecnologia: bool, vaga: Vaga) -> None:
        rotulo = f"{vaga.titulo} ({vaga.empresa})" if vaga.empresa else vaga.titulo
        origens.setdefault((termo, tecnologia), []).append(rotulo)

    for vaga in vagas:
        texto = f"{vaga.titulo}\n{vaga.descricao}"
        for tec in TECNOLOGIAS_CONHECIDAS:
            padrao = re.compile(rf"(?<![\w#+.]){re.escape(tec)}(?![\w#])", re.IGNORECASE)
            if padrao.search(texto):
                anotar(tec, True, vaga)

    cobertas = {_normalizar(t) for t, tecnologia in origens if tecnologia}
    for vaga in vagas:
        texto = f"{vaga.titulo}\n{vaga.descricao}"
        palavras = {
            _normalizar(p.rstrip(".-"))
            for p in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ+#.-]{2,}", texto)
        }
        for palavra in palavras:
            if len(palavra) < 3 or palavra in STOPWORDS_PT or palavra in cobertas:
                continue
            anotar(palavra, False, vaga)

    termos = [
        TermoFrequente(termo=termo, vagas_em_que_aparece=len(lista), total_de_vagas=total,
                       e_tecnologia=tecnologia, origens=lista)
        for (termo, tecnologia), lista in origens.items()
        if tecnologia or len(lista) >= min(MINIMO_DE_VAGAS, total)
    ]
    termos.sort(key=lambda t: (-t.vagas_em_que_aparece, not t.e_tecnologia, t.termo))
    return termos[:limite]
