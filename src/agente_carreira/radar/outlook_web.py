"""Alertas de vaga pelo Outlook na web, no navegador do agente (opção do usuário).

Para quem usa o Outlook (o novo Outlook do Windows não permite automação e a conta não usa senha de app):
- você entra na conta uma vez, no navegador do agente (login e 2FA são seus, RN-03);
- o agente usa a PESQUISA do Outlook, que procura na caixa inteira (Prioritário e Outros), só pelos
  remetentes de alerta de vaga configurados;
- abre cada alerta novo, copia o corpo e devolve como um e-mail comum para a leitura de vagas que já
  existe (radar.coleta.vagas_de_email);
- só lê: não apaga, não move, não responde; se o Outlook marcar um alerta como lido, o agente desmarca
  (RNF-03);
- alertas já lidos em rodadas anteriores não são abertos de novo.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timezone

URL_OUTLOOK = "https://outlook.live.com/mail/0/"
DOMINIOS_CAIXA = ("outlook.live.com/mail", "outlook.office.com/mail", "outlook.office365.com/mail")
SELETOR_PESQUISA = 'input[aria-label*="Pesquis"], input[aria-label*="Search"]'
SELETOR_CORPO = '[role=document][aria-label="Corpo da mensagem"], [role=document][aria-label="Message body"], div[id^="UniqueMessageBody"]'
NOMES_NAO_LIDO = ("Não lido", "Marcar como não lido", "Unread", "Mark as unread")
PREFIXOS_NAO_LIDO = ("Não lidos", "Não lido", "Unread")
ADAPTADOR = "email:outlook-web"

Dormir = Callable[[float], None]

JS_LINHAS = r"""() => [...document.querySelectorAll('[role=option][data-convid]')].map(o => ({
  convid: o.getAttribute('data-convid'), rotulo: (o.getAttribute('aria-label') || '')
}))"""
JS_ASSUNTO = r"""() => {
  const h = document.querySelector('[role=main] [role=heading], [role=main] h1, [role=main] h2');
  return h ? (h.innerText || '').trim() : '';
}"""


class LoginOutlook(Exception):
    """Sem sessão no Outlook: entre pela tela de e-mail do app ('agente email entrar')."""


def remetente_da_consulta(consulta: str) -> str:
    """'from:jobalerts-noreply@linkedin.com' → o endereço; 'from:indeed.com' → 'alertas@indeed.com'."""
    valor = consulta.split(":", 1)[-1].strip()
    return valor if "@" in valor else f"alertas@{valor}"


def nao_lido(rotulo: str) -> bool:
    return rotulo.strip().startswith(PREFIXOS_NAO_LIDO)


def montar_email(convid: str, remetente: str, assunto: str, html: str, recebido: datetime | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = remetente
    msg["Subject"] = assunto or "Alerta de vagas"
    msg["Message-ID"] = f"<outlook-web-{convid}>"
    msg["Date"] = format_datetime(recebido or datetime.now(timezone.utc))
    msg.set_content(html, subtype="html")
    return msg


def caixa_aberta(pagina, espera_s: float = 25, dormir: Dormir = time.sleep) -> None:
    """Abre o Outlook e espera a caixa de pesquisa; se cair no login, levanta LoginOutlook."""
    pagina.goto(URL_OUTLOOK, wait_until="domcontentloaded", timeout=45_000)
    passos = int(espera_s / 1.5)
    for _ in range(passos):
        url = (pagina.url or "").lower()
        if "login." in url or "/oauth2/" in url:
            raise LoginOutlook("O Outlook pediu login. Entre na sua conta pelo app (Configurações → e-mail → "
                               "'Entrar no Outlook') ou com 'agente email entrar'.")
        if any(d in url for d in DOMINIOS_CAIXA) and pagina.locator(SELETOR_PESQUISA).count():
            return
        dormir(1.5)
    raise LoginOutlook("A caixa do Outlook não abriu (sem login ou página diferente do esperado).")


def pesquisar(pagina, consulta: str, dormir: Dormir = time.sleep) -> list[dict]:
    caixa = pagina.locator(SELETOR_PESQUISA).first
    caixa.click()
    dormir(0.8)
    caixa.fill(consulta)
    caixa.press("Enter")
    for _ in range(8):  # até ~12 s para os resultados aparecerem
        dormir(1.5)
        linhas = pagina.evaluate(JS_LINHAS)
        if linhas:
            return linhas
    return []


def _restaurar_nao_lido(pagina, convid: str, dormir: Dormir) -> bool:
    linha = pagina.locator(f'[role=option][data-convid="{convid}"]')
    if not linha.count() or nao_lido(linha.first.get_attribute("aria-label") or ""):
        return False
    for nome in NOMES_NAO_LIDO:
        botao = pagina.get_by_role("button", name=nome, exact=True)
        if botao.count():
            botao.first.click()
            dormir(1)
            return True
    return False


def ler_alertas(pagina, consultas: list[str], ja_processados: set[str], *, por_consulta: int = 15,
                dormir: Dormir = time.sleep) -> tuple[list[tuple[str, EmailMessage]], list[str]]:
    """Devolve ([(message-id, e-mail)], avisos). Só abre alertas que ainda não foram lidos pelo agente."""
    caixa_aberta(pagina, dormir=dormir)
    mensagens: list[tuple[str, EmailMessage]] = []
    avisos: list[str] = []
    from ..operacao import andamento

    for n, consulta in enumerate(consultas, 1):
        andamento.etapa(f"Outlook: lendo alertas de {consulta.split(':', 1)[-1]}", n, len(consultas))
        linhas = pesquisar(pagina, consulta, dormir)[:por_consulta]
        novas = [l for l in linhas if f"<outlook-web-{l['convid']}>" not in ja_processados]
        for linha in novas:
            convid = linha["convid"]
            try:
                pagina.locator(f'[role=option][data-convid="{convid}"]').first.click()
                corpo = pagina.locator(SELETOR_CORPO).first
                corpo.wait_for(timeout=15_000)
                dormir(1.5)
                html = corpo.inner_html()
                assunto = pagina.evaluate(JS_ASSUNTO) or linha["rotulo"][:120]
                if nao_lido(linha["rotulo"]):
                    _restaurar_nao_lido(pagina, convid, dormir)  # RNF-03: continua não lido para você
            except Exception as erro:  # noqa: BLE001 - um alerta com problema não para a leitura
                avisos.append(f"Outlook: não consegui abrir um alerta de '{consulta}': {type(erro).__name__}")
                continue
            msg = montar_email(convid, remetente_da_consulta(consulta), assunto, html)
            mensagens.append((msg["Message-ID"], msg))
            dormir(1.5)
    return mensagens, avisos


def leitor_da_rodada(consultas: list[str], saude, *, por_consulta: int = 15, abrir_sessao=None,
                     dormir: Dormir = time.sleep):
    """Fonte de e-mails da rodada: recebe os message-ids já processados e devolve (mensagens, avisos, falhas)."""
    def ler(ja_processados: set[str]):
        if not saude.pode_usar(ADAPTADOR):
            return [], [f"{ADAPTADOR}: parado após erro (agente saude reativar {ADAPTADOR})"], []
        from ..navegador import NavegadorOcupado, SessaoNavegador, erro_curto, fechado_pela_pessoa, playwright_disponivel
        from ..operacao.saude import LayoutMudou

        if abrir_sessao is None and not playwright_disponivel():
            return [], ["Outlook: a leitura pelo navegador precisa do Playwright ('uv sync')"], []
        try:
            with (abrir_sessao or SessaoNavegador)() as sessao:
                mensagens, avisos = ler_alertas(sessao.pagina, consultas, ja_processados, por_consulta=por_consulta,
                                                dormir=dormir)
        except NavegadorOcupado as erro:
            return [], [f"E-mail não lido nesta rodada: {erro}"], []
        except LoginOutlook as erro:
            saude.falha(ADAPTADOR, str(erro))
            return [], [f"Outlook: {erro}"], [f"Outlook: {erro}"]
        except LayoutMudou as erro:
            parou = saude.falha(ADAPTADOR, str(erro), parar=True)
            return [], [f"Outlook: {erro}"], [f"{ADAPTADOR}: {erro}"] if parou else []
        except Exception as erro:  # noqa: BLE001 - a leitura do e-mail não derruba a rodada
            if fechado_pela_pessoa(erro):
                return [], ["Outlook: o navegador do agente foi fechado no meio da busca; fica para a próxima rodada"], []
            saude.falha(ADAPTADOR, erro_curto(erro))
            return [], [f"Outlook: {erro_curto(erro)}"], []
        saude.sucesso(ADAPTADOR)
        return mensagens, avisos, []

    return ler
