"""Busca direta no portal de vagas da Gupy (portal.gupy.io), além dos alertas por e-mail.

- O portal é público: o agente usa um navegador próprio, invisível e SEM a sua conta (nada de login).
- Respeita o robots.txt e faz pausas entre as buscas (RN-05); poucas buscas por rodada.
- Cada vaga vira o link normal da Gupy (empresa.gupy.io/jobs/NÚMERO): a mesma vaga dos alertas de
  e-mail não entra duas vezes, e a descrição completa é lida depois pela leitura de páginas da Gupy.
"""

from __future__ import annotations

import base64
import json
import random
import re
import time
from collections.abc import Callable
from datetime import date
from urllib.parse import quote, urlparse

from .modelos import VagaBruta

ORIGEM = "gupy:portal"
ADAPTADOR = "pagina:gupy-portal"
URL_BUSCA = "https://portal.gupy.io/job-search/term="
Dormir = Callable[[float], None]

JS_CARTOES = r"""() => [...document.querySelectorAll('li')].map(li => {
  const a = li.querySelector('a[href*=".gupy.io/job"]');
  return a ? {href: a.href, linhas: (li.innerText || '').split('\n').map(s => s.trim()).filter(Boolean)} : null;
}).filter(Boolean)"""

MODELOS = {"presencial": "presencial", "híbrido": "hibrido", "hibrido": "hibrido", "remoto": "remoto"}
TIPOS = {
    "estágio": "estagio", "estagio": "estagio", "efetivo": "clt", "trainee": "clt", "temporário": "clt",
    "jovem aprendiz": "clt", "aprendiz": "clt", "prestador de serviços": "pj", "autônomo": "pj", "associado": "pj",
    "terceiro": "pj", "banco de talentos": None, "talentos": None, "lecionar": None,
}
_PUBLICADA = re.compile(r"publicada em:?\s*(\d{2})/(\d{2})/(\d{4})", re.I)
_LOCAL = re.compile(r"^.+\s-\s[A-Z]{2}$")


def id_da_vaga(href: str) -> str | None:
    """'https://x.gupy.io/job/eyJqb2JJZCI6MTI4MDU1MjAs...' → '12805520' (o trecho é JSON em base64)."""
    m = re.search(r"/job/([A-Za-z0-9_\-+/=]+)", href)
    if m:
        bruto = m.group(1)
        try:
            dados = json.loads(base64.b64decode(bruto + "=" * (-len(bruto) % 4), altchars=b"-_").decode("utf-8"))
            if dados.get("jobId"):
                return str(dados["jobId"])
        except (ValueError, UnicodeDecodeError):
            pass
    m = re.search(r"/jobs/(\d+)", href)
    return m.group(1) if m else None


def completar_cidade(local: str) -> str:
    """O portal corta nomes longos ('Belo Horiz... - MG'): completa pela região de BH quando dá."""
    from .modelos import REGIAO_BH
    from .texto import norm

    if "..." not in local and "…" not in local:
        return local
    cidade, _, uf = local.partition(" - ")
    prefixo = norm(cidade.replace("…", "").replace("...", "")).strip()
    achadas = [c for c in REGIAO_BH if norm(c).startswith(prefixo)] if len(prefixo) >= 3 else []
    return f"{achadas[0]} - {uf}" if len(achadas) == 1 and uf else local


def cartao_para_vaga(cartao: dict) -> VagaBruta | None:
    href, linhas = cartao.get("href") or "", [l for l in cartao.get("linhas") or [] if l]
    vaga_id = id_da_vaga(href)
    host = urlparse(href).hostname or ""
    if not vaga_id or not host.endswith("gupy.io") or len(linhas) < 2:
        return None
    publicada = modelo = contrato = local = None
    for linha in linhas[2:]:
        baixa = linha.lower()
        if m := _PUBLICADA.search(linha):
            try:
                publicada = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass
        elif baixa in MODELOS:
            modelo = MODELOS[baixa]
        elif baixa in TIPOS:
            contrato = TIPOS[baixa]
        elif local is None and (_LOCAL.match(linha) or baixa in ("remoto", "brasil")):
            local = completar_cidade(linha)
    return VagaBruta(
        titulo=linhas[1], empresa=linhas[0], local=local, modelo=modelo, contrato=contrato, publicada_em=publicada,
        link=f"https://{host}/jobs/{vaga_id}", fonte_tipo="pagina", fonte_origem=ORIGEM,
    )


def termos_da_rodada(buscas, gerais: list[str], limite: int, hoje: date | None = None) -> list[str]:
    """Termos gerais de TI + o primeiro cargo de cada busca, revezando a cada dia, até o limite."""
    hoje = hoje or date.today()
    termos = list(dict.fromkeys([*gerais, *(b.cargos[0] for b in buscas if b.cargos)]))
    if not termos:
        return []
    inicio = hoje.toordinal() % len(termos)
    return (termos[inicio:] + termos[:inicio])[:limite]


def buscar(abrir_pagina, termos: list[str], *, dormir: Dormir = time.sleep, aleatorio: random.Random | None = None,
           espera_s: float = 4) -> tuple[list[VagaBruta], list[str]]:
    """Abre a busca do portal para cada termo e lê os cartões. abrir_pagina(url) devolve a página carregada."""
    vagas: dict[str, VagaBruta] = {}
    avisos: list[str] = []
    for i, termo in enumerate(termos):
        if i:
            dormir((aleatorio or random).uniform(3, 7))
        pagina = abrir_pagina(URL_BUSCA + quote(termo))
        dormir(espera_s)
        cartoes = pagina.evaluate(JS_CARTOES)
        if not cartoes:
            avisos.append(f"Gupy: nenhuma vaga para '{termo}'")
        for cartao in cartoes:
            vaga = cartao_para_vaga(cartao)
            if vaga:
                vagas.setdefault(vaga.link, vaga)
    return list(vagas.values()), avisos


def coletor_da_rodada(config, termos: list[str], saude, *, abrir_navegador=None, permite=None,
                      dormir: Dormir = time.sleep):
    """Fonte extra da rodada diária. O navegador é invisível e sem conta; erros viram avisos."""
    def coletar(base) -> tuple[list[VagaBruta], list[str], list[str]]:
        if not saude.pode_usar(ADAPTADOR):
            return [], [f"{ADAPTADOR}: parado após erro (agente saude reativar {ADAPTADOR})"], []
        from ..navegador import erro_curto
        from .coleta import baixar, robots_permite

        if not (permite or (lambda url: robots_permite(url, baixar)))(URL_BUSCA + quote(termos[0] if termos else "ti")):
            return [], ["Gupy: o robots.txt do portal não permite a busca agora"], []
        try:
            with (abrir_navegador or NavegadorPublico)() as abrir_pagina:
                vagas, avisos = buscar(abrir_pagina, termos, dormir=dormir)
        except Exception as erro:  # noqa: BLE001 - a busca na Gupy não derruba a rodada
            saude.falha(ADAPTADOR, erro_curto(erro))
            return [], [f"Gupy: {erro_curto(erro)}"], []
        if termos and not vagas and len(avisos) == len(termos):
            parou = saude.falha(ADAPTADOR, "nenhum cartão de vaga no portal (o layout pode ter mudado)", parar=True)
            return [], avisos, [f"{ADAPTADOR}: nenhum cartão de vaga"] if parou else []
        saude.sucesso(ADAPTADOR)
        return vagas, [a for a in avisos if len(avisos) < len(termos)], []

    return coletar


class NavegadorPublico:
    """Chromium invisível, sem perfil e sem login, para sites públicos (não usa o navegador da sua conta)."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._navegador = self._pw.chromium.launch()
        self._pagina = self._navegador.new_page(locale="pt-BR")
        self._pagina.set_default_navigation_timeout(45_000)

        def abrir(url: str):
            self._pagina.goto(url, wait_until="domcontentloaded")
            return self._pagina

        return abrir

    def __exit__(self, *exc) -> None:
        try:
            self._navegador.close()
        finally:
            self._pw.stop()
