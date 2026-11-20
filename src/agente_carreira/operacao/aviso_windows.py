"""Aviso na tela do Windows (a notificação do canto da tela), sem e-mail, senha nem serviço externo (RF-EV-02).

Usa o próprio Windows (WinRT pelo PowerShell que já vem no sistema). O aviso mostra o título e as primeiras
linhas; o texto completo continua em data/notificacoes/. Fora do Windows, não faz nada.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from xml.sax.saxutils import escape

# Identificador do PowerShell do Windows: aceito pelo sistema sem registrar um app novo.
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
    "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null; "
    "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; $xml.LoadXml($env:AGENTE_AVISO_XML); "
    "$aviso = [Windows.UI.Notifications.ToastNotification]::new($xml); "
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:AGENTE_AVISO_APP).Show($aviso)"
)
LIMITE_TEXTO = 220


def resumo_curto(corpo: str, limite: int = LIMITE_TEXTO) -> str:
    """As primeiras linhas úteis do texto, sem marcação de Markdown nem links."""
    linhas = []
    for linha in corpo.splitlines():
        limpa = re.sub(r"https?://\S+", "", linha)
        limpa = re.sub(r"^\s*(#{1,6}|>|[-*+]|\d+\.)\s+", "", limpa)  # título, citação e item de lista (não o "#" de C#)
        limpa = re.sub(r"\*\*|__|`", "", limpa).replace("|", " ").strip(" -·:")
        if limpa:
            linhas.append(limpa)
        if sum(len(l) for l in linhas) >= limite:
            break
    texto = " · ".join(linhas)
    return texto if len(texto) <= limite else texto[:limite - 1].rstrip() + "…"


def xml_aviso(titulo: str, corpo: str) -> str:
    return ('<toast><visual><binding template="ToastGeneric">'
            f"<text>{escape('Agente de Carreira: ' + titulo)}</text><text>{escape(resumo_curto(corpo))}</text>"
            "</binding></visual></toast>")


def avisar_na_tela(titulo: str, corpo: str, *, executar=subprocess.run) -> bool:
    """Mostra o aviso; devolve False se não deu (fora do Windows, avisos desligados no sistema etc.)."""
    if sys.platform != "win32":
        return False
    ambiente = dict(os.environ, AGENTE_AVISO_XML=xml_aviso(titulo, corpo), AGENTE_AVISO_APP=APP_ID)
    try:
        resultado = executar(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", SCRIPT], env=ambiente,
                             capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return False
    return resultado.returncode == 0
