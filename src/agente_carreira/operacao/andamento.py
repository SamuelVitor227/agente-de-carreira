"""Andamento das tarefas longas, para você ver o que o agente está fazendo agora.

Toda tarefa longa (a busca de vagas, inclusive a agendada das 7h) grava a etapa atual em
data/andamento.json e uma linha por etapa em data/andamento.log. O app mostra isso numa faixa no topo
de todas as telas; no terminal, 'agente andamento'. Se o processo morrer no meio, a tarefa aparece
como interrompida (o agente confere se o processo ainda existe).
"""

from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..storage import diretorio_dados

ARQUIVO = "andamento.json"
ARQUIVO_LOG = "andamento.log"
LINHAS_LOG = 400

_atual: dict | None = None
_TRAVA = threading.Lock()  # as fontes paralelas também marcam etapas


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _caminho() -> Path:
    return diretorio_dados() / ARQUIVO


def _gravar(estado: dict) -> None:
    caminho = _caminho()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    temporario.replace(caminho)


def _log(texto: str) -> None:
    caminho = diretorio_dados() / ARQUIVO_LOG
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linha = f"{datetime.now():%d/%m %H:%M:%S}  {texto}\n"
    antigas = caminho.read_text(encoding="utf-8").splitlines(keepends=True)[-LINHAS_LOG:] if caminho.is_file() else []
    caminho.write_text("".join(antigas) + linha, encoding="utf-8")


def processo_vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32
        alca = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not alca:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(alca, ctypes.byref(codigo))) and codigo.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(alca)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def ler() -> dict | None:
    """Estado mais recente, com 'rodando' conferido pelo processo ('interrompida' se ele morreu no meio)."""
    caminho = _caminho()
    if not caminho.is_file():
        return None
    try:
        estado = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if estado.get("rodando") and not processo_vivo(int(estado.get("pid", 0))):
        estado["rodando"] = False
        estado["situacao"] = "interrompida"
    return estado


def em_andamento(tarefa: str | None = None) -> dict | None:
    estado = ler()
    if estado and estado.get("rodando") and (tarefa is None or estado.get("tarefa") == tarefa):
        return estado
    return None


def ultimas_linhas(quantidade: int = 60) -> list[str]:
    caminho = diretorio_dados() / ARQUIVO_LOG
    if not caminho.is_file():
        return []
    return caminho.read_text(encoding="utf-8").splitlines()[-quantidade:]


def etapa(texto: str, atual: int | None = None, total: int | None = None) -> None:
    """Marca a etapa atual da tarefa em andamento (não faz nada se nenhuma tarefa foi iniciada)."""
    with _TRAVA:
        if _atual is None:
            return
        _atual.update(etapa=texto, atual=atual, total=total, atualizado=_agora())
        _gravar(_atual)
        if atual is None or atual in (1, total) or (total and atual % 10 == 0):
            _log(f"{_atual['tarefa']}: {texto}" + (f" ({atual}/{total})" if atual and total else ""))


@contextmanager
def tarefa(nome: str):
    """Registra a tarefa do início ao fim. Use etapa() dentro dela e defina 'resultado' no dicionário devolvido."""
    global _atual
    _atual = {"tarefa": nome, "rodando": True, "situacao": "rodando", "pid": os.getpid(), "inicio": _agora(),
              "etapa": "começando", "atual": None, "total": None, "atualizado": _agora(), "resultado": None}
    _gravar(_atual)
    _log(f"{nome}: começou")
    situacao = "concluida"
    try:
        yield _atual
    except BaseException:
        situacao = "falhou"
        raise
    finally:
        _atual.update(rodando=False, situacao=situacao, fim=_agora(), etapa="terminou", atual=None, total=None)
        _gravar(_atual)
        _log(f"{nome}: {'terminou' if situacao == 'concluida' else 'falhou'}"
             + (f" — {_atual['resultado']}" if _atual.get("resultado") else ""))
        _atual = None


def descrever(estado: dict, agora: datetime | None = None) -> str:
    """Uma linha em português para a faixa do app e o terminal."""
    agora = agora or datetime.now(timezone.utc)
    inicio = datetime.fromisoformat(estado["inicio"])
    minutos = max(0, int((agora - inicio).total_seconds() // 60))
    if estado.get("rodando"):
        progresso = f" ({estado['atual']} de {estado['total']})" if estado.get("atual") and estado.get("total") else ""
        return f"{estado['tarefa']} rodando: {estado.get('etapa', '')}{progresso} · há {minutos} min"
    fim = datetime.fromisoformat(estado.get("fim", estado["inicio"])).astimezone()
    if estado.get("situacao") == "interrompida":
        return f"{estado['tarefa']} foi interrompida (o processo fechou no meio)"
    if estado.get("situacao") == "falhou":
        return f"{estado['tarefa']} falhou às {fim:%H:%M}. Veja o andamento."
    return f"{estado['tarefa']} terminou às {fim:%H:%M}" + (f": {estado['resultado']}" if estado.get("resultado") else "")
