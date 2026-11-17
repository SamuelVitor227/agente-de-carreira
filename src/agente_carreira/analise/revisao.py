"""Revisão periódica da versão-base (RF-CV-09).

A versão-base deve ser revisada todo mês ou quando o conjunto de vagas-alvo
mudar. Cada revisão registra um instantâneo (nota ATS, cobertura de termos e
volumes do perfil) e a seguinte mostra o antes × depois.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ..models import PerfilMestre
from ..storage import diretorio_dados
from ..vagas import Vaga

ARQUIVO_REVISOES = "revisoes-cv.json"
DIAS_ENTRE_REVISOES = 30


class RegistroRevisao(BaseModel):
    quando: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hash_vagas: str
    nota_total: float
    termos_cobertos: int
    total_termos: int
    experiencias: int
    projetos: int
    conquistas: int
    competencias: int


class HistoricoRevisoes(BaseModel):
    revisoes: list[RegistroRevisao] = Field(default_factory=list)


def hash_do_conjunto(vagas: list[Vaga]) -> str:
    base = "|".join(sorted(v.id for v in vagas))
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def instantaneo(
    perfil: PerfilMestre, vagas: list[Vaga], nota_total: float, cobertos: int, total_termos: int
) -> RegistroRevisao:
    return RegistroRevisao(
        hash_vagas=hash_do_conjunto(vagas),
        nota_total=nota_total,
        termos_cobertos=cobertos,
        total_termos=total_termos,
        experiencias=len(perfil.experiencias),
        projetos=len(perfil.projetos),
        conquistas=len(perfil.banco_conquistas),
        competencias=len(perfil.competencias_tecnicas),
    )


def caminho_revisoes() -> Path:
    return diretorio_dados() / ARQUIVO_REVISOES


def carregar_revisoes() -> HistoricoRevisoes:
    caminho = caminho_revisoes()
    if not caminho.is_file():
        return HistoricoRevisoes()
    return HistoricoRevisoes.model_validate_json(caminho.read_text(encoding="utf-8"))


def registrar_revisao(registro: RegistroRevisao) -> RegistroRevisao | None:
    """Guarda a revisão e devolve a anterior, se houver."""
    historico = carregar_revisoes()
    anterior = historico.revisoes[-1] if historico.revisoes else None
    historico.revisoes.append(registro)
    caminho = caminho_revisoes()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(historico.model_dump_json(indent=2), encoding="utf-8")
    return anterior


def revisao_pendente(vagas: list[Vaga], agora: datetime | None = None) -> str | None:
    """Motivo pelo qual uma revisão está pendente, ou None se estiver em dia."""
    agora = agora or datetime.now(timezone.utc)
    historico = carregar_revisoes()
    if not historico.revisoes:
        return "nenhuma revisão registrada ainda"
    ultima = historico.revisoes[-1]
    dias = (agora - ultima.quando).days
    if dias > DIAS_ENTRE_REVISOES:
        return f"última revisão há {dias} dias (limite: {DIAS_ENTRE_REVISOES})"
    if ultima.hash_vagas != hash_do_conjunto(vagas):
        return "o conjunto de vagas-alvo mudou desde a última revisão"
    return None


def comparar(anterior: RegistroRevisao, atual: RegistroRevisao) -> list[str]:
    """Antes × depois entre duas revisões."""
    linhas: list[str] = []

    def _linha(rotulo: str, a: float, b: float) -> None:
        if a != b:
            linhas.append(f"{rotulo}: {a} → {b}")

    _linha("nota ATS", anterior.nota_total, atual.nota_total)
    _linha(
        "termos cobertos",
        f"{anterior.termos_cobertos}/{anterior.total_termos}",
        f"{atual.termos_cobertos}/{atual.total_termos}",
    )
    _linha("experiências", anterior.experiencias, atual.experiencias)
    _linha("projetos", anterior.projetos, atual.projetos)
    _linha("conquistas", anterior.conquistas, atual.conquistas)
    _linha("competências técnicas", anterior.competencias, atual.competencias)
    if anterior.hash_vagas != atual.hash_vagas:
        linhas.append("conjunto de vagas-alvo mudou")
    return linhas
