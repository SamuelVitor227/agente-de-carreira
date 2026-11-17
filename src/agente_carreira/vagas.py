"""Vagas-alvo salvas pelo usuário (RF-CV-01).

O conjunto de análise por foco usa por padrão as 30 vagas mais recentes
(salvas manualmente agora; vindas do resumo diário quando o M4 chegar).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from .storage import diretorio_dados

ARQUIVO_VAGAS = "vagas-alvo.json"
TAMANHO_PADRAO_CONJUNTO = 30


class Vaga(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    titulo: str
    empresa: str | None = None
    foco: str  # ex.: backend-dotnet, cloud-aws, mobile, dados, suporte
    url: str | None = None
    fonte: str | None = None  # ex.: linkedin, gupy, pagina da empresa
    descricao: str
    salva_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VagasAlvo(BaseModel):
    vagas: list[Vaga] = Field(default_factory=list)


def caminho_vagas() -> Path:
    return diretorio_dados() / ARQUIVO_VAGAS


def carregar_vagas() -> VagasAlvo:
    caminho = caminho_vagas()
    if not caminho.is_file():
        return VagasAlvo()
    return VagasAlvo.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_vagas(colecao: VagasAlvo) -> Path:
    caminho = caminho_vagas()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(colecao.model_dump_json(indent=2), encoding="utf-8")
    return caminho


def conjunto_de_analise(
    colecao: VagasAlvo, foco: str | None = None, limite: int = TAMANHO_PADRAO_CONJUNTO
) -> list[Vaga]:
    """As vagas mais recentes do foco (ou todas), limitadas ao tamanho do conjunto."""
    vagas = [v for v in colecao.vagas if foco is None or v.foco == foco]
    vagas.sort(key=lambda v: v.salva_em, reverse=True)
    return vagas[:limite]
