"""Alterações do LinkedIn enviadas para a fila de aprovações (RF-OP-05), em vez do fluxo interativo."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from ..storage import diretorio_dados
from .propostas import Proposta

ARQUIVO = "linkedin-pendentes.json"


class PropostaPendente(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    criada_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    campo: str
    rotulo: str
    anterior: str | None = None
    novo: str
    motor: str | None = None  # RF-IA-06: quem escreveu o texto


class PropostasPendentes(BaseModel):
    itens: list[PropostaPendente] = Field(default_factory=list)

    def buscar(self, id_: str) -> PropostaPendente:
        for item in self.itens:
            if item.id == id_:
                return item
        raise ValueError(f"Alteração pendente {id_!r} não existe.")

    def campos(self) -> set[str]:
        return {i.campo for i in self.itens}


def enfileirar(pendentes: PropostasPendentes, propostas: list[Proposta], motor: str | None = None) -> int:
    """Põe as propostas na fila, sem duplicar campos que já estão lá."""
    ja_na_fila = pendentes.campos()
    novas = 0
    for p in propostas:
        if p.campo in ja_na_fila:
            continue
        pendentes.itens.append(PropostaPendente(campo=p.campo, rotulo=p.rotulo, anterior=p.anterior, novo=p.novo, motor=motor))
        ja_na_fila.add(p.campo)
        novas += 1
    return novas


def carregar_pendentes() -> PropostasPendentes:
    caminho = diretorio_dados() / ARQUIVO
    if not caminho.is_file():
        return PropostasPendentes()
    return PropostasPendentes.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_pendentes(pendentes: PropostasPendentes) -> Path:
    caminho = diretorio_dados() / ARQUIVO
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(pendentes.model_dump_json(indent=2), encoding="utf-8")
    return caminho
