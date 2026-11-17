"""Registro de candidaturas (base do funil do M6).

Aqui entram o RF-CV-14 (guardar a versão de CV enviada junto da candidatura)
e os dados que alimentam o desempenho por variante (RF-CV-10).
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from .storage import diretorio_dados

ARQUIVO_CANDIDATURAS = "candidaturas.json"
DIR_CVS_ENVIADOS = "candidaturas"


class StatusCandidatura(str, Enum):
    PREPARADA = "preparada"
    ENVIADA = "enviada"
    RETORNO = "retorno"
    ENTREVISTA = "entrevista"
    PROPOSTA = "proposta"
    RECUSADA = "recusada"
    SEM_RESPOSTA = "sem_resposta"


# Status que contam como retorno positivo para o desempenho (RF-CV-10).
STATUS_DE_RETORNO = {
    StatusCandidatura.RETORNO,
    StatusCandidatura.ENTREVISTA,
    StatusCandidatura.PROPOSTA,
}


class MudancaStatus(BaseModel):
    quando: datetime
    de: StatusCandidatura
    para: StatusCandidatura


class Candidatura(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    vaga_id: str | None = None
    vaga_titulo: str
    empresa: str | None = None
    foco: str
    variante: str  # nome da variante usada (ex.: cv-backend-dotnet-pt)
    idioma: str = "pt"
    criada_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: StatusCandidatura = StatusCandidatura.PREPARADA
    historico: list[MudancaStatus] = Field(default_factory=list)
    cv_enviado: list[str] = Field(default_factory=list)  # RF-CV-14: cópias guardadas

    def mudar_status(self, novo: StatusCandidatura) -> None:
        self.historico.append(
            MudancaStatus(quando=datetime.now(timezone.utc), de=self.status, para=novo)
        )
        self.status = novo


class Candidaturas(BaseModel):
    itens: list[Candidatura] = Field(default_factory=list)


def caminho_candidaturas() -> Path:
    return diretorio_dados() / ARQUIVO_CANDIDATURAS


def carregar_candidaturas() -> Candidaturas:
    caminho = caminho_candidaturas()
    if not caminho.is_file():
        return Candidaturas()
    return Candidaturas.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_candidaturas(colecao: Candidaturas) -> Path:
    caminho = caminho_candidaturas()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(colecao.model_dump_json(indent=2), encoding="utf-8")
    return caminho


def guardar_cv_enviado(candidatura: Candidatura, arquivos: list[Path]) -> list[Path]:
    """RF-CV-14: copia os arquivos de CV enviados para a pasta da candidatura."""
    destino_dir = diretorio_dados() / DIR_CVS_ENVIADOS / candidatura.id
    destino_dir.mkdir(parents=True, exist_ok=True)
    guardados: list[Path] = []
    for arquivo in arquivos:
        destino = destino_dir / arquivo.name
        shutil.copy2(arquivo, destino)
        candidatura.cv_enviado.append(str(destino))
        guardados.append(destino)
    return guardados
