"""Busca de vagas no site do Glassdoor, no navegador do agente (só leitura).

- O Glassdoor pede uma verificação de "humano" (Cloudflare). Ela é SUA, como login e CAPTCHA (RN-03): o
  agente para, avisa e espera você resolver no navegador dele; nunca tenta contornar.
- Depois de uma verificação, o site costuma lembrar do navegador por um tempo.
- Numa busca sem ninguém por perto (a das 7h), se a verificação aparecer e não for resolvida em poucos
  minutos, o Glassdoor fica para a próxima rodada e você é avisado.
- Só lê: não altera nada na sua conta, não salva vagas lá e não se candidata.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from datetime import date
from urllib.parse import quote

from .modelos import VagaBruta

ORIGEM = "glassdoor:site"
ADAPTADOR = "navegador:glassdoor"
URL_BUSCA = "https://www.glassdoor.com.br/Job/jobs.htm"
Dormir = Callable[[float], None]

JS_DESAFIO = r"""() => /um momento|just a moment|humans only|verify you are human|verificando se|confirme que você é humano|checking your browser/i
  .test((document.title || '') + ' ' + ((document.body && document.body.innerText) || '').slice(0, 2000))"""

# Cartões da lista de resultados: ancorados no link com o identificador da vaga (jl=).
JS_CARTOES = r"""() => {
  const vistos = new Set(); const saida = [];
  const cartoes = document.querySelectorAll('li[data-test="jobListing"], [data-test="jobListing"]');
  const fontes = cartoes.length ? [...cartoes] : [...document.querySelectorAll('a[href*="jl="]')].map(a => a.closest('li') || a.parentElement);
  for (const c of fontes) {
    if (!c) continue;
    const a = c.querySelector('a[href*="jl="], a[data-test="job-title"], a[data-test="job-link"]');
    if (!a) continue;
    const m = (a.href || '').match(/[?&]jl=(\d{6,})/) || (c.getAttribute('data-jobid') || '').match(/(\d{6,})/);
    if (!m || vistos.has(m[1])) continue;
    vistos.add(m[1]);
    const texto = sel => { const e = c.querySelector(sel); return e ? (e.innerText || '').trim() : null; };
    saida.push({
      id: m[1],
      titulo: texto('[data-test="job-title"]') || (a.innerText || '').trim(),
      empresa: texto('[class*="EmployerProfile_compactEmployerName"], [class*="employerName"], [data-test="employer-name"]'),
      local: texto('[data-test="emp-location"], [class*="location"]'),
      linhas: (c.innerText || '').split('\n').map(s => s.trim()).filter(Boolean).slice(0, 10),
    });
  }
  return saida;
}"""


class VerificacaoPendente(Exception):
    """A verificação de humano não foi resolvida a tempo: o Glassdoor fica para a próxima rodada."""


def url_busca(termo: str, local: str | None) -> str:
    url = f"{URL_BUSCA}?sc.keyword={quote(termo)}"
    return url + (f"&locKeyword={quote(local)}" if local else "")


def em_verificacao(pagina) -> bool:
    try:
        return bool(pagina.evaluate(JS_DESAFIO))
    except Exception:  # noqa: BLE001 - página trocando (a verificação recarrega a página)
        return True


def esperar_humano(pagina, minutos: float, avisar: Callable[[str], None], dormir: Dormir = time.sleep) -> None:
    """Se houver verificação, avisa uma vez e espera você resolver; levanta VerificacaoPendente no fim do prazo."""
    if not em_verificacao(pagina):
        return
    from ..operacao import andamento

    andamento.etapa("Glassdoor: ESPERANDO VOCÊ resolver a verificação de humano no navegador do agente")
    avisar("O Glassdoor pediu a verificação de humano. Resolva no navegador do agente; ele continua sozinho depois.")
    for _ in range(max(1, int(minutos * 60 / 3))):
        dormir(3)
        if not em_verificacao(pagina):
            dormir(2)
            return
    raise VerificacaoPendente("a verificação de humano do Glassdoor não foi resolvida a tempo")


def cartao_para_vaga(cartao: dict) -> VagaBruta | None:
    titulo = (cartao.get("titulo") or "").split("\n")[0].strip()
    if not cartao.get("id") or not titulo:
        return None
    empresa = (cartao.get("empresa") or "").split("\n")[0].strip() or None
    if empresa:
        empresa = re.sub(r"\s*\d[.,]\d\s*★?$", "", empresa).strip() or None  # tira a nota da empresa ("Omega 4,1")
    local = (cartao.get("local") or "").split("\n")[0].strip() or None
    return VagaBruta(
        titulo=titulo, empresa=empresa, local=local,
        link=f"https://www.glassdoor.com.br/partner/jobListing.htm?jobListingId={cartao['id']}",
        fonte_tipo="pagina", fonte_origem=ORIGEM,
    )


def termos_da_rodada(buscas, gerais: list[str], limite: int, hoje: date | None = None) -> list[str]:
    hoje = hoje or date.today()
    termos = list(dict.fromkeys([*gerais, *(b.cargos[0] for b in buscas if b.cargos)]))
    if not termos:
        return []
    inicio = hoje.toordinal() % len(termos)
    return (termos[inicio:] + termos[:inicio])[:limite]


def buscar(pagina, termos: list[str], local: str | None, *, minutos_verificacao: float,
           avisar: Callable[[str], None], dormir: Dormir = time.sleep,
           aleatorio: random.Random | None = None) -> tuple[list[VagaBruta], list[str]]:
    vagas: dict[str, VagaBruta] = {}
    avisos: list[str] = []
    from ..operacao import andamento

    for i, termo in enumerate(termos):
        andamento.etapa(f"Glassdoor: pesquisando '{termo}'", i + 1, len(termos))
        if i:
            dormir((aleatorio or random).uniform(4, 9))
        pagina.goto(url_busca(termo, local), wait_until="domcontentloaded")
        dormir(3)
        esperar_humano(pagina, minutos_verificacao, avisar, dormir)
        dormir(3)
        cartoes = pagina.evaluate(JS_CARTOES)
        if not cartoes:
            avisos.append(f"Glassdoor: nenhuma vaga para '{termo}'")
        for cartao in cartoes:
            if vaga := cartao_para_vaga(cartao):
                vagas.setdefault(vaga.link, vaga)
    return list(vagas.values()), avisos


def coletor_da_rodada(termos: list[str], local: str | None, saude, *, minutos_verificacao: float = 5,
                      avisar: Callable[[str], None] = print, abrir_sessao=None, dormir: Dormir = time.sleep):
    """Fonte extra da rodada diária. Verificação não resolvida, navegador ocupado ou erro viram aviso."""
    def coletar(base) -> tuple[list[VagaBruta], list[str], list[str]]:
        if not saude.pode_usar(ADAPTADOR):
            return [], [f"{ADAPTADOR}: parado após erro (agente saude reativar {ADAPTADOR})"], []
        from ..navegador import NavegadorOcupado, SessaoNavegador, erro_curto, fechado_pela_pessoa

        try:
            with (abrir_sessao or SessaoNavegador)() as sessao:
                vagas, avisos = buscar(sessao.pagina, termos, local, minutos_verificacao=minutos_verificacao,
                                       avisar=avisar, dormir=dormir)
        except NavegadorOcupado as erro:
            return [], [f"Glassdoor não pesquisado nesta rodada: {erro}"], []
        except VerificacaoPendente as erro:
            return [], [f"Glassdoor: {erro}; fica para a próxima rodada"], [f"Glassdoor: {erro}"]
        except Exception as erro:  # noqa: BLE001 - o Glassdoor não derruba a rodada
            if fechado_pela_pessoa(erro):
                return [], ["Glassdoor: o navegador do agente foi fechado no meio da busca; fica para a próxima rodada"], []
            saude.falha(ADAPTADOR, erro_curto(erro))
            return [], [f"Glassdoor: {erro_curto(erro)}"], []
        if termos and not vagas and len(avisos) == len(termos):
            parou = saude.falha(ADAPTADOR, "nenhum cartão de vaga no Glassdoor (o layout pode ter mudado)", parar=True)
            return [], avisos, [f"{ADAPTADOR}: nenhum cartão de vaga"] if parou else []
        saude.sucesso(ADAPTADOR)
        return vagas, [a for a in avisos if len(avisos) < len(termos)], []

    return coletar
