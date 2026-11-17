"""Notificações por e-mail ou push (RF-OP-04).

Eventos: resumo diário, vaga acima do limiar, pedido de aprovação e falha de
adaptador. Toda notificação fica também em data/notificacoes/; se o canal não
estiver configurado ou falhar, o arquivo garante que nada se perde.

Credenciais só por variáveis de ambiente (RNF-01):
- e-mail: AGENTE_SMTP_HOST, AGENTE_SMTP_PORTA (587), AGENTE_SMTP_USUARIO, AGENTE_SMTP_SENHA;
- push (ntfy): AGENTE_NTFY_TOPICO e, opcionalmente, AGENTE_NTFY_SERVIDOR.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from email.header import Header
from email.message import EmailMessage
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..configuracao import Configuracao
from ..storage import diretorio_dados

LIMITE_PUSH = 3500


@dataclass
class ResultadoNotificacao:
    canal: str            # canal efetivamente usado
    arquivo: Path
    erro: str | None = None


def config_smtp(ambiente: dict[str, str] | None = None) -> dict[str, str] | None:
    env = os.environ if ambiente is None else ambiente
    host, usuario, senha = env.get("AGENTE_SMTP_HOST"), env.get("AGENTE_SMTP_USUARIO"), env.get("AGENTE_SMTP_SENHA")
    if not (host and usuario and senha):
        return None
    return {"host": host, "porta": env.get("AGENTE_SMTP_PORTA", "587"), "usuario": usuario, "senha": senha}


def enviar_email(smtp: dict[str, str], para: str, titulo: str, corpo: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"[Agente de Carreira] {titulo}"
    msg["From"] = smtp["usuario"]
    msg["To"] = para
    msg.set_content(corpo)
    porta = int(smtp["porta"])
    contexto = ssl.create_default_context()
    if porta == 465:
        with smtplib.SMTP_SSL(smtp["host"], porta, timeout=20, context=contexto) as servidor:
            servidor.login(smtp["usuario"], smtp["senha"])
            servidor.send_message(msg)
    else:
        with smtplib.SMTP(smtp["host"], porta, timeout=20) as servidor:
            servidor.starttls(context=contexto)
            servidor.login(smtp["usuario"], smtp["senha"])
            servidor.send_message(msg)


def enviar_push(servidor: str, topico: str, titulo: str, corpo: str) -> None:
    pedido = Request(
        f"{servidor.rstrip('/')}/{topico}",
        data=corpo[:LIMITE_PUSH].encode("utf-8"),
        headers={"Title": Header(titulo, "utf-8").encode(), "Tags": "briefcase"},
        method="POST",
    )
    with urlopen(pedido, timeout=15):
        pass


def _salvar_arquivo(evento: str, titulo: str, corpo: str) -> Path:
    agora = datetime.now()
    destino = diretorio_dados() / "notificacoes" / f"{agora:%Y%m%d-%H%M%S-%f}-{evento}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(f"# {titulo}\n\n_{agora:%d/%m/%Y %H:%M} · {evento}_\n\n{corpo}\n", encoding="utf-8")
    return destino


def notificar(
    evento: str, titulo: str, corpo: str, config: Configuracao, *,
    envio_email: Callable[..., None] = enviar_email, envio_push: Callable[..., None] = enviar_push,
    ambiente: dict[str, str] | None = None,
) -> ResultadoNotificacao | None:
    """Notifica pelo canal configurado; devolve None se o evento estiver desligado."""
    if not config.notificacao.eventos.get(evento, True):
        return None
    env = os.environ if ambiente is None else ambiente
    arquivo = _salvar_arquivo(evento, titulo, corpo)
    canal = config.notificacao.canal
    erro: str | None = None
    try:
        if canal == "email":
            smtp = config_smtp(env)
            if not smtp or not config.notificacao.email_para:
                erro = "e-mail não configurado (variáveis AGENTE_SMTP_* e notificacao.email_para)"
            else:
                envio_email(smtp, config.notificacao.email_para, titulo, corpo)
        elif canal == "push":
            topico = env.get("AGENTE_NTFY_TOPICO")
            if not topico:
                erro = "push não configurado (variável AGENTE_NTFY_TOPICO)"
            else:
                envio_push(env.get("AGENTE_NTFY_SERVIDOR", "https://ntfy.sh"), topico, titulo, corpo)
    except (OSError, smtplib.SMTPException, URLError, ValueError) as falha:
        erro = f"falha ao enviar por {canal}: {falha}"
    if erro:
        with arquivo.open("a", encoding="utf-8") as f:
            f.write(f"\n> Não enviada por {canal}: {erro}. Ficou só neste arquivo.\n")
        return ResultadoNotificacao(canal="arquivo", arquivo=arquivo, erro=erro)
    return ResultadoNotificacao(canal=canal, arquivo=arquivo)
