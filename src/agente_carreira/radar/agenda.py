"""Agendamento da rodada diária (RF-VG-03; padrão: todo dia às 7h) e do relatório semanal (UC-11).

No Windows, a tarefa do Agendador roda o pythonw.exe do Python base (sem janela de console) com um script
de partida em data/app (fora do git), que carrega os pacotes do venv e chama operacao/agendada.py. A tarefa
é criada a partir de um XML, que liga o que o comando simples do schtasks não liga:

- se o PC estiver desligado ou suspenso no horário, a tarefa roda assim que ele voltar;
- roda também na bateria, e não para se o notebook sair da tomada;
- nunca roda duas vezes ao mesmo tempo, e para sozinha depois de 2 horas.

Em outros sistemas, devolve a linha do cron.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

NOME_TAREFA = "AgenteCarreira-RodadaVagas"
NOME_TAREFA_SEMANAL = "AgenteCarreira-RelatorioSemanal"
SCRIPT_TAREFA = "tarefa.pyw"

DIAS_SEMANA = {"segunda": "MON", "terca": "TUE", "terça": "TUE", "quarta": "WED", "quinta": "THU",
               "sexta": "FRI", "sabado": "SAT", "sábado": "SAT", "domingo": "SUN"}
DIAS_CRON = {"MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6, "SUN": 0}
DIAS_XML = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday",
            "SAT": "Saturday", "SUN": "Sunday"}
DIAS_PYTHON = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


def validar_hora(hora: str) -> str:
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", hora.strip())
    if not m:
        raise ValueError(f"Hora inválida: {hora!r}. Use HH:MM, ex.: 07:00.")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def validar_dia_hora(texto: str) -> tuple[str, str]:
    """'domingo 20:00' → ('SUN', '20:00')."""
    partes = texto.strip().lower().split()
    if len(partes) != 2 or partes[0].removesuffix("-feira") not in DIAS_SEMANA:
        raise ValueError(f"Use 'dia HH:MM', ex.: 'domingo 20:00' (recebido: {texto!r}).")
    return DIAS_SEMANA[partes[0].removesuffix("-feira")], validar_hora(partes[1])


# ---------------------------------------------------------------- Windows

def script_tarefa(site_packages: Path, raiz: Path, diretorio_dados: str | None = None) -> str:
    """Script de partida da tarefa: Python base sem console + pacotes do venv do projeto."""
    linhas = [
        "# Gerado por 'agente vagas agendar': roda o agente sem janela (Python base + pacotes do venv do projeto).",
        "import os", "import site", "import sys", "",
        f"site.addsitedir({str(site_packages)!r})",
        f"os.chdir({str(raiz)!r})",
    ]
    if diretorio_dados:
        linhas.append(f"os.environ['AGENTE_CARREIRA_DATA'] = {diretorio_dados!r}")
    linhas += ["", "from agente_carreira.operacao.agendada import rodar", "", "sys.exit(rodar(sys.argv[1:]))", ""]
    return "\n".join(linhas)


def proxima_vez(hora: str, agora: datetime, dia: str | None = None) -> datetime:
    """O próximo horário a partir de agora. Começar no futuro evita que a tarefa rode na hora em que é criada."""
    h, m = map(int, validar_hora(hora).split(":"))
    candidata = agora.replace(hour=h, minute=m, second=0, microsecond=0)
    if dia is None:
        return candidata if candidata > agora else candidata + timedelta(days=1)
    candidata += timedelta(days=(DIAS_PYTHON[dia] - agora.weekday()) % 7)
    return candidata if candidata > agora else candidata + timedelta(days=7)


def xml_tarefa(executavel: Path, argumentos: str, pasta: Path, inicio: datetime, descricao: str,
               dia: str | None = None) -> str:
    """Definição da tarefa no formato do Agendador do Windows (gravar em UTF-16)."""
    if dia is None:
        agenda = "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
    else:
        agenda = (f"<ScheduleByWeek><WeeksInterval>1</WeeksInterval><DaysOfWeek><{DIAS_XML[dia]} />"
                  "</DaysOfWeek></ScheduleByWeek>")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{escape(descricao)}</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{inicio:%Y-%m-%dT%H:%M:%S}</StartBoundary>
      <Enabled>true</Enabled>
      {agenda}
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(executavel))}</Command>
      <Arguments>{escape(argumentos)}</Arguments>
      <WorkingDirectory>{escape(str(pasta))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def comando_criar(nome: str, xml: Path) -> list[str]:
    return ["schtasks", "/Create", "/TN", nome, "/XML", str(xml), "/F"]


def tarefa_agendada(nome: str = NOME_TAREFA, *, executar=None) -> bool | None:
    """True/False se a tarefa existe no Agendador do Windows; None fora do Windows (não dá para saber)."""
    import subprocess
    import sys

    if sys.platform != "win32":
        return None
    executar = executar or subprocess.run
    try:
        resultado = executar(["schtasks", "/Query", "/TN", nome], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        return None
    return resultado.returncode == 0


# ---------------------------------------------------------------- outros sistemas

def linha_cron(diretorio_projeto: Path, uv: str, hora: str) -> str:
    h, m = validar_hora(hora).split(":")
    dados = os.environ.get("AGENTE_CARREIRA_DATA")
    prefixo = f"AGENTE_CARREIRA_DATA='{dados}' " if dados else ""
    return f"{int(m)} {int(h)} * * * cd '{diretorio_projeto}' && {prefixo}'{uv}' run agente vagas rodada >> data/rodada.log 2>&1"


def linha_cron_semanal(diretorio_projeto: Path, uv: str, dia: str, hora: str) -> str:
    h, m = validar_hora(hora).split(":")
    dados = os.environ.get("AGENTE_CARREIRA_DATA")
    prefixo = f"AGENTE_CARREIRA_DATA='{dados}' " if dados else ""
    return (f"{int(m)} {int(h)} * * {DIAS_CRON[dia]} cd '{diretorio_projeto}' && {prefixo}'{uv}' run agente "
            "relatorio semanal --notificar >> data/relatorio.log 2>&1")
