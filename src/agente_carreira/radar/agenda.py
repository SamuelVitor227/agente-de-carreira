"""Agendamento da rodada diária (RF-VG-03; padrão: todo dia às 7h).

No Windows, cria uma tarefa no Agendador de Tarefas que roda um script .cmd
guardado em data/ (fora do git). Em outros sistemas, devolve a linha do cron.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

NOME_TAREFA = "AgenteCarreira-RodadaVagas"


def validar_hora(hora: str) -> str:
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", hora.strip())
    if not m:
        raise ValueError(f"Hora inválida: {hora!r}. Use HH:MM, ex.: 07:00.")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def script_windows(diretorio_projeto: Path, uv: str, diretorio_dados: str | None = None) -> str:
    linhas = ["@echo off", "chcp 65001 >nul", f'cd /d "{diretorio_projeto}"']
    if diretorio_dados:
        linhas.append(f'set "AGENTE_CARREIRA_DATA={diretorio_dados}"')
    linhas.append(f'"{uv}" run agente vagas rodada >> "data\\rodada.log" 2>&1')
    return "\r\n".join(linhas) + "\r\n"


def comando_schtasks(script: Path, hora: str) -> list[str]:
    return [
        "schtasks", "/Create", "/SC", "DAILY", "/ST", validar_hora(hora),
        "/TN", NOME_TAREFA, "/TR", f'"{script}"', "/F",
    ]


def linha_cron(diretorio_projeto: Path, uv: str, hora: str) -> str:
    h, m = validar_hora(hora).split(":")
    dados = os.environ.get("AGENTE_CARREIRA_DATA")
    prefixo = f"AGENTE_CARREIRA_DATA='{dados}' " if dados else ""
    return f"{int(m)} {int(h)} * * * cd '{diretorio_projeto}' && {prefixo}'{uv}' run agente vagas rodada >> data/rodada.log 2>&1"
