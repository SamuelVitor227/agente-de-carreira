"""Status da conta em cada plataforma (RF-PL-09) e propagação de mudanças (RF-PL-08)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..storage import diretorio_dados
from .pacote import PacoteCadastro

ARQUIVO = "plataformas-contas.json"
StatusConta = Literal["nao_iniciado", "em_andamento", "completo", "desatualizado"]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class ContaPlataforma(BaseModel):
    plataforma: str
    status: StatusConta = "nao_iniciado"
    iniciado_em: datetime | None = None
    concluido_em: datetime | None = None
    ultima_revisao: datetime | None = None
    completude: int | None = None
    pacote: PacoteCadastro | None = None   # o que foi gravado na plataforma
    tarefa_id: str | None = None


class Contas(BaseModel):
    itens: dict[str, ContaPlataforma] = Field(default_factory=dict)

    def obter(self, plataforma: str) -> ContaPlataforma:
        return self.itens.setdefault(plataforma, ContaPlataforma(plataforma=plataforma))


def status_efetivo(conta: ContaPlataforma, assinatura_atual: str | None) -> StatusConta:
    """Conta já cadastrada cujo pacote mudou no perfil-mestre fica desatualizada (RN-06)."""
    if conta.status in ("completo", "em_andamento") and conta.pacote and assinatura_atual \
            and conta.pacote.assinatura != assinatura_atual:
        return "desatualizado"
    return conta.status


def registrar_gravacao(conta: ContaPlataforma, pacote: PacoteCadastro, completude: int | None, completo: bool) -> None:
    conta.pacote = pacote
    conta.ultima_revisao = _agora()
    conta.completude = completude
    conta.status = "completo" if completo else "em_andamento"
    if completo:
        conta.concluido_em = conta.ultima_revisao


def carregar_contas() -> Contas:
    caminho = diretorio_dados() / ARQUIVO
    if not caminho.is_file():
        return Contas()
    return Contas.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_contas(contas: Contas) -> Path:
    caminho = diretorio_dados() / ARQUIVO
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(contas.model_dump_json(indent=2), encoding="utf-8")
    return caminho
