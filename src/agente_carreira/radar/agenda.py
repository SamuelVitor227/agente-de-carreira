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


def script_windows(diretorio_projeto: Path, uv: str, diretorio_dados: str | None = None,
                   comando: str = "vagas rodada", log: str = "rodada.log") -> str:
    linhas = ["@echo off", "chcp 65001 >nul", f'cd /d "{diretorio_projeto}"']
    if diretorio_dados:
        linhas.append(f'set "AGENTE_CARREIRA_DATA={diretorio_dados}"')
    linhas.append(f'"{uv}" run agente {comando} >> "data\\{log}" 2>&1')
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


# ---------------------------------------------------------------- relatório semanal (UC-11)

NOME_TAREFA_SEMANAL = "AgenteCarreira-RelatorioSemanal"
DIAS_SEMANA = {"segunda": "MON", "terca": "TUE", "terça": "TUE", "quarta": "WED", "quinta": "THU",
               "sexta": "FRI", "sabado": "SAT", "sábado": "SAT", "domingo": "SUN"}
DIAS_CRON = {"MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6, "SUN": 0}


def validar_dia_hora(texto: str) -> tuple[str, str]:
    """'domingo 20:00' → ('SUN', '20:00')."""
    partes = texto.strip().lower().split()
    if len(partes) != 2 or partes[0].removesuffix("-feira") not in DIAS_SEMANA:
        raise ValueError(f"Use 'dia HH:MM', ex.: 'domingo 20:00' (recebido: {texto!r}).")
    return DIAS_SEMANA[partes[0].removesuffix("-feira")], validar_hora(partes[1])


def comando_schtasks_semanal(script: Path, dia: str, hora: str) -> list[str]:
    return ["schtasks", "/Create", "/SC", "WEEKLY", "/D", dia, "/ST", validar_hora(hora),
            "/TN", NOME_TAREFA_SEMANAL, "/TR", f'"{script}"', "/F"]


def linha_cron_semanal(diretorio_projeto: Path, uv: str, dia: str, hora: str) -> str:
    h, m = validar_hora(hora).split(":")
    dados = os.environ.get("AGENTE_CARREIRA_DATA")
    prefixo = f"AGENTE_CARREIRA_DATA='{dados}' " if dados else ""
    return (f"{int(m)} {int(h)} * * {DIAS_CRON[dia]} cd '{diretorio_projeto}' && {prefixo}'{uv}' run agente "
            "relatorio semanal --notificar >> data/relatorio.log 2>&1")
