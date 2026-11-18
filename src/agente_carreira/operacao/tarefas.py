"""Tarefas que podem ser pausadas, retomadas e canceladas (RF-OP-03).

Uma tarefa tem passos; retomar continua do primeiro passo depois do último
confirmado, e confirmar de novo um passo já confirmado não faz nada — a
retomada nunca duplica ações (RNF-07). Tarefas recorrentes (a rodada diária
de vagas) ficam bloqueadas enquanto estiverem pausadas ou canceladas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from ..arquivos import gravar_modelo, ler_modelo
from ..storage import diretorio_dados

ARQUIVO = "tarefas.json"
TAREFA_RODADA = "rodada-vagas"

StatusTarefa = Literal["ativa", "pausada", "concluida", "cancelada", "falhou"]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Passo(BaseModel):
    nome: str
    descricao: str = ""
    status: Literal["pendente", "confirmado", "pulado"] = "pendente"
    concluido_em: datetime | None = None


class Tarefa(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    tipo: str
    descricao: str
    recorrente: bool = False
    status: StatusTarefa = "ativa"
    criada_em: datetime = Field(default_factory=_agora)
    atualizada_em: datetime = Field(default_factory=_agora)
    passos: list[Passo] = Field(default_factory=list)
    dados: dict[str, str] = Field(default_factory=dict)
    erro: str | None = None

    def proximo_passo(self) -> Passo | None:
        return next((p for p in self.passos if p.status == "pendente"), None)

    def ultimo_confirmado(self) -> Passo | None:
        feitos = [p for p in self.passos if p.status != "pendente"]
        return feitos[-1] if feitos else None

    def pendentes(self) -> list[str]:
        return [p.nome for p in self.passos if p.status == "pendente"]

    @property
    def progresso(self) -> str:
        if not self.passos:
            return "—"
        return f"{sum(1 for p in self.passos if p.status != 'pendente')}/{len(self.passos)}"

    @property
    def bloqueada(self) -> bool:
        return self.status in ("pausada", "cancelada")


class Tarefas(BaseModel):
    itens: list[Tarefa] = Field(default_factory=list)

    def buscar(self, id_: str) -> Tarefa:
        for tarefa in self.itens:
            if tarefa.id == id_:
                return tarefa
        raise ValueError(f"Tarefa {id_!r} não existe.")

    def aberta_do_tipo(self, tipo: str) -> Tarefa | None:
        return next((t for t in reversed(self.itens) if t.tipo == tipo and t.status in ("ativa", "pausada", "falhou")), None)


def criar_tarefa(tarefas: Tarefas, tipo: str, descricao: str, passos: list[tuple[str, str]] | None = None,
                 *, id_: str | None = None, recorrente: bool = False) -> Tarefa:
    tarefa = Tarefa(
        tipo=tipo, descricao=descricao, recorrente=recorrente,
        passos=[Passo(nome=n, descricao=d) for n, d in (passos or [])],
    )
    if id_:
        tarefa.id = id_
    tarefas.itens.append(tarefa)
    return tarefa


def garantir_tarefa_rodada(tarefas: Tarefas) -> Tarefa:
    try:
        return tarefas.buscar(TAREFA_RODADA)
    except ValueError:
        return criar_tarefa(tarefas, "rodada-vagas", "Rodada diária de vagas (coleta, triagem e resumo)",
                            id_=TAREFA_RODADA, recorrente=True)


def confirmar_passo(tarefa: Tarefa, nome: str, pulado: bool = False) -> bool:
    """Confirma um passo; devolve False se ele já estava concluído (sem duplicar)."""
    passo = next((p for p in tarefa.passos if p.nome == nome), None)
    if passo is None:
        raise ValueError(f"A tarefa {tarefa.id} não tem o passo {nome!r}.")
    if passo.status != "pendente":
        return False
    passo.status = "pulado" if pulado else "confirmado"
    passo.concluido_em = tarefa.atualizada_em = _agora()
    if not tarefa.recorrente and tarefa.proximo_passo() is None:
        tarefa.status = "concluida"
    return True


def pausar(tarefa: Tarefa) -> None:
    if tarefa.status != "ativa":
        raise ValueError(f"Só tarefas ativas podem ser pausadas (status: {tarefa.status}).")
    tarefa.status = "pausada"
    tarefa.atualizada_em = _agora()


def retomar(tarefa: Tarefa) -> Passo | None:
    """Volta a tarefa a ativa e devolve o próximo passo (o primeiro depois do último confirmado)."""
    permitidos = ("pausada", "falhou", "cancelada") if tarefa.recorrente else ("pausada", "falhou")
    if tarefa.status not in permitidos:
        raise ValueError(f"Não dá para retomar uma tarefa {tarefa.status}.")
    tarefa.status = "ativa"
    tarefa.erro = None
    tarefa.atualizada_em = _agora()
    return tarefa.proximo_passo()


def cancelar(tarefa: Tarefa) -> None:
    if tarefa.status in ("concluida", "cancelada"):
        raise ValueError(f"A tarefa já está {tarefa.status}.")
    tarefa.status = "cancelada"
    tarefa.atualizada_em = _agora()


def falhar(tarefa: Tarefa, erro: str) -> None:
    tarefa.erro = erro
    tarefa.atualizada_em = _agora()
    if not tarefa.recorrente:
        tarefa.status = "falhou"  # retomável do último passo confirmado
    else:
        tarefa.dados["ultima_falha"] = f"{_agora():%d/%m/%Y %H:%M} — {erro}"


def carregar_tarefas() -> Tarefas:
    caminho = diretorio_dados() / ARQUIVO
    return ler_modelo(caminho, Tarefas)


def salvar_tarefas(tarefas: Tarefas) -> Path:
    caminho = diretorio_dados() / ARQUIVO
    gravar_modelo(caminho, tarefas)
    return caminho
