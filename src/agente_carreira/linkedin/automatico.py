"""Navegador automático no LinkedIn: opção do usuário, ciente do risco (RN-04). Desligado por padrão.

Quando ligado ('agente li automatico ligar --aceito-o-risco'):
- usa o navegador do agente (perfil em data/navegador), onde VOCÊ entrou na conta (RN-03);
- busca vagas pelas suas buscas salvas, poucas páginas por rodada, com pausas aleatórias (RN-05);
- na Candidatura Simplificada, preenche cada etapa e avança, mas para antes de "Enviar candidatura":
  o clique de envio é sempre seu (RN-01, RF-CA-03, CA-11);
- só responde com o que está no seu perfil ou nas respostas aprovadas; o resto fica para você (RN-09);
- login expirado, verificação de segurança ou CAPTCHA: para e avisa (RN-03);
- página diferente do esperado: para e marca o adaptador (RF-OP-07, RNF-08).

Os termos de uso do LinkedIn proíbem automação: a conta pode ser restringida. Por isso o modo é opcional,
lento de propósito e registra quando você aceitou o risco.
"""

from __future__ import annotations

import random
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from ..configuracao import LinkedInAutomatico
from ..operacao.saude import LayoutMudou
from ..radar.extracao import campos_de_jobposting, html_para_texto, jobpostings
from ..radar.modelos import BuscaSalva, ConfigVagas, VagaBruta

ORIGEM = "linkedin:navegador"
ADAPTADOR = "navegador:linkedin"
USO_NAVEGADOR = "a busca de vagas no LinkedIn"
URL_BUSCA = "https://www.linkedin.com/jobs/search/"
URL_LOGIN = "https://www.linkedin.com/login"
URL_FEED = "https://www.linkedin.com/feed/"

# Nível do agente → filtro de experiência do LinkedIn (1 estágio, 2 assistente/júnior, 3 pleno).
NIVEL_LINKEDIN = {"estagio": "1", "trainee": "2", "junior": "2", "pleno": "3", "senior": "4"}
CONTRATO_LINKEDIN = {"estagio": "I", "clt": "F", "pj": "C"}

Dormir = Callable[[float], None]


class LoginNecessario(Exception):
    """Sem sessão, sessão expirada, verificação de segurança ou CAPTCHA: é com você (RN-03)."""


def _norm(texto: str | None) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower().strip()


def pausa(cfg: LinkedInAutomatico, dormir: Dormir, aleatorio: random.Random | None = None) -> None:
    dormir((aleatorio or random).uniform(cfg.intervalo_min_s, cfg.intervalo_max_s))


# ---------------------------------------------------------------- sessão

def checar_pagina(pagina) -> None:
    url = (pagina.url or "").lower()
    if any(p in url for p in ("/login", "/checkpoint", "/authwall", "/uas/", "challenge")):
        raise LoginNecessario("O LinkedIn pediu login ou uma verificação de segurança. Entre na conta pelo "
                              "navegador do agente ('agente li automatico entrar') e tente de novo.")


_LOGADO = ("/feed", "/jobs", "/in/", "/mynetwork", "/messaging", "/notifications")


def _url_logada(url: str) -> bool:
    url = (url or "").lower()
    return "linkedin.com" in url and any(p in url for p in _LOGADO) and not any(
        p in url for p in ("/login", "/checkpoint", "/authwall", "/uas/"))


def esta_logado(pagina, dormir: Dormir = time.sleep) -> bool:
    """Abre o feed: se o LinkedIn não mandar para o login, a sessão vale. Nunca trava (tempo limite)."""
    try:
        pagina.goto(URL_FEED, wait_until="domcontentloaded", timeout=30_000)
    except Exception:  # noqa: BLE001 - sem rede ou página lenta: trata como não logado
        return False
    dormir(2)
    return _url_logada(pagina.url)


def esperar_login(pagina, minutos: int = 10, dormir: Dormir = time.sleep) -> bool:
    """Abre a tela de login e espera você entrar em qualquer aba (login, 2FA e CAPTCHA são seus)."""
    try:
        pagina.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=30_000)
    except Exception:  # noqa: BLE001 - a pessoa ainda pode entrar pela aba aberta
        pass
    for _ in range(minutos * 30):
        dormir(2)
        if getattr(pagina, "is_closed", lambda: False)():
            return False  # você fechou a aba de login
        try:
            abertas = [p for p in pagina.context.pages if not p.is_closed()]
        except Exception:  # noqa: BLE001 - navegador fechado pela pessoa
            return False
        if not abertas:
            return False
        if any(_url_logada(p.url) for p in abertas):
            return True
    return False


# ---------------------------------------------------------------- busca

def url_busca(cargo: str, local: str | None, niveis: list[str], contratos: list[str], *, remoto: bool = False,
              ultimas_horas: int = 24) -> str:
    parametros = {"keywords": cargo, "sortBy": "DD", "f_TPR": f"r{max(1, ultimas_horas) * 3600}"}
    if local:
        parametros["location"] = local
    experiencia = sorted({NIVEL_LINKEDIN[n] for n in niveis if n in NIVEL_LINKEDIN})
    if experiencia:
        parametros["f_E"] = ",".join(experiencia)
    tipos = sorted({CONTRATO_LINKEDIN[c] for c in contratos if c in CONTRATO_LINKEDIN})
    if tipos:
        parametros["f_JT"] = ",".join(tipos)
    if remoto:
        parametros["f_WT"] = "2"
    return f"{URL_BUSCA}?{urlencode(parametros)}"


def _local_da_busca(busca: BuscaSalva, padrao: str) -> str:
    if not busca.localidades:
        return padrao
    primeira = busca.localidades[0]
    return padrao if _norm(primeira) == "belo horizonte" else f"{primeira}, Brasil"


def consultas(config: ConfigVagas, cfg: LinkedInAutomatico, hoje: date | None = None) -> list[tuple[str, str]]:
    """(busca, url): uma pesquisa geral de TI em toda rodada e as áreas revezando a cada dia, até o limite."""
    from ..radar.modelos import PESQUISAS_GERAIS_LINKEDIN

    hoje = hoje or date.today()
    por_busca: list[list[tuple[str, str]]] = []
    if config.buscas:
        niveis = sorted({n for b in config.buscas for n in b.niveis})
        contratos = sorted({c for b in config.buscas for c in b.contratos})
        local = _local_da_busca(config.buscas[0], cfg.local_padrao)
        termo = PESQUISAS_GERAIS_LINKEDIN[hoje.toordinal() % len(PESQUISAS_GERAIS_LINKEDIN)]
        geral = [("geral", url_busca(termo, local, niveis, contratos, ultimas_horas=cfg.ultimas_horas))]
    else:
        geral = []
    buscas = list(config.buscas)
    if buscas:  # revezamento: cada dia começa por uma área diferente
        inicio = hoje.toordinal() % len(buscas)
        buscas = buscas[inicio:] + buscas[:inicio]
    for busca in buscas:
        itens = []
        cargos = list(dict.fromkeys(busca.cargos))[:2]
        for cargo in cargos:
            itens.append((busca.nome, url_busca(cargo, _local_da_busca(busca, cfg.local_padrao), busca.niveis,
                                                busca.contratos, ultimas_horas=cfg.ultimas_horas)))
        if busca.remoto_brasil and cargos:
            itens.append((busca.nome, url_busca(cargos[0], "Brasil", busca.niveis, busca.contratos, remoto=True,
                                                ultimas_horas=cfg.ultimas_horas)))
        por_busca.append(itens)
    intercaladas = geral + [item for grupo in zip_longo(por_busca) for item in grupo]
    return intercaladas[:cfg.consultas_por_rodada]


def zip_longo(listas: list[list]) -> list[list]:
    maior = max((len(l) for l in listas), default=0)
    return [[l[i] for l in listas if i < len(l)] for i in range(maior)]


# Lê os cartões de vaga da página de resultados: robusto a classes CSS, ancorado no link /jobs/view/ID.
# Duas páginas de resultados: a antiga (/jobs/search/, cartões com link /jobs/view/ID) e a nova
# (/jobs/search-results/, RF-EV-03): cartões sem link, com o número da vaga em componentkey="job-card-component-ref-ID".
JS_CARTOES = r"""
() => {
  const vistos = new Set(); const saida = [];
  const linhasDe = e => ((e && e.innerText) || '').split('\n').map(s => s.trim()).filter(Boolean);
  for (const cartao of document.querySelectorAll('[componentkey^="job-card-component-ref-"]')) {
    const m = (cartao.getAttribute('componentkey') || '').match(/(\d{6,})$/);
    if (!m || vistos.has(m[1])) continue;
    vistos.add(m[1]);
    const linhas = linhasDe(cartao).map(l => l.replace(/^(Selecionada|Selected),\s*/i, ''));
    saida.push({id: m[1], titulo: linhas[0] || '', linhas});
  }
  for (const a of document.querySelectorAll('a[href*="/jobs/view/"]')) {
    const m = (a.getAttribute('href') || '').match(/\/jobs\/view\/(?:[^/?#]*-)?(\d{6,})/) || (a.href || '').match(/\/jobs\/view\/(?:[^/?#]*-)?(\d{6,})/);
    if (!m || vistos.has(m[1])) continue;
    vistos.add(m[1]);
    const cartao = a.closest('li') || a.closest('[data-job-id]') || a.parentElement;
    saida.push({id: m[1], titulo: ((a.innerText || a.getAttribute('aria-label') || '').split('\n')[0] || '').trim(),
                linhas: linhasDe(cartao || a)});
  }
  return saida;
}
"""

_RUIDO = re.compile(
    r"^(promovid[ao]|promoted|candidatura simplificada|easy apply|visualizad[ao]|viewed|salv[ao]|saved|"
    r"ativamente recrutando|actively recruiting|seja um dos|be an early applicant|novo|new|"
    r"h[aá] \d|\d+ (minutos?|horas?|dias?|semanas?|meses|minutes?|hours?|days?|weeks?|months?)|"
    r".*candidat(o|os|ura|uras)$|.*applicants?$|.*conex(ão|ões|ao|oes) trabalh|.*alumni|.*verifica[cç][aã]o$|"
    r"with verification|com verifica[cç][aã]o|\d+ benef|visto|·|.*ex-alunos|.*trabalham aqui|anunciada h[aá])",
    re.IGNORECASE,
)


def limpar_titulo(titulo: str) -> str:
    return re.sub(r"\s*(with verification|com verifica[cç][aã]o|\((vaga verificada|verified job)\))\s*$", "", titulo,
                  flags=re.IGNORECASE).strip()


def cartoes_para_vagas(cartoes: list[dict]) -> list[VagaBruta]:
    vagas = []
    for c in cartoes:
        titulo = limpar_titulo(c.get("titulo") or "")
        linhas = [limpar_titulo(l) for l in c.get("linhas") or []]
        if not titulo and linhas:
            titulo = linhas[0]
        resto = [l for l in linhas if l and _norm(l) != _norm(titulo) and not _norm(l).startswith(_norm(titulo))
                 and not _RUIDO.match(l)]
        if not titulo:
            continue
        vagas.append(VagaBruta(
            titulo=titulo, empresa=resto[0] if resto else None, local=resto[1] if len(resto) > 1 else None,
            link=f"https://www.linkedin.com/jobs/view/{c['id']}", fonte_tipo="pagina", fonte_origem=ORIGEM,
        ))
    return vagas


def _rolar_resultados(pagina, dormir: Dormir) -> None:
    """Rola a lista de resultados (que carrega mais cartões ao rolar): a da página antiga ou a da nova."""
    for _ in range(4):
        pagina.evaluate("""() => {
            const cartao = document.querySelector('[componentkey^="job-card-component-ref-"]');
            let lista = null;
            for (let e = cartao && cartao.parentElement; e; e = e.parentElement) {
                const estilo = getComputedStyle(e);
                if (e.scrollHeight > e.clientHeight + 40 && /(auto|scroll)/.test(estilo.overflowY)) { lista = e; break; }
            }
            lista = lista || document.querySelector('.jobs-search-results-list, .scaffold-layout__list > div, main');
            (lista || document.scrollingElement).scrollBy(0, 1600);
        }""")
        dormir(1.2)


def ler_resultados(pagina, url: str, cfg: LinkedInAutomatico, dormir: Dormir) -> list[VagaBruta]:
    pagina.goto(url, wait_until="domcontentloaded")
    checar_pagina(pagina)
    dormir(2.5)
    _rolar_resultados(pagina, dormir)
    return cartoes_para_vagas(pagina.evaluate(JS_CARTOES))[:cfg.vagas_por_consulta]


JS_JSONLD = "() => [...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(s => s.textContent || '')"


_LOCAL_TOPO = re.compile(r"^\s*([^\n·]+?,[^\n·]+?)\s+·\s+(?:há|h[áa]\s|reposted|publicad|\d)", re.I | re.M)
_MODELOS_TOPO = {"presencial": "presencial", "híbrido": "hibrido", "hibrido": "hibrido", "remoto": "remoto",
                 "on-site": "presencial", "hybrid": "hibrido", "remote": "remoto"}


_ENCERRADA_TOPO = re.compile(
    r"n[aã]o aceita mais candidaturas|no longer accepting applications|candidaturas encerradas"
    r"|esta vaga n[aã]o est[aá] mais dispon[ií]vel|this job is no longer available", re.I)
_IDADE_TOPO = re.compile(
    r"(?:h[aá]|publicad[ao]\s+h[aá]|republicad[ao]\s+h[aá])\s+(\d+|um|uma)\s+(minuto|hora|dia|semana|m[eê]s|meses|ano)"
    r"|(\d+|an?)\s+(minute|hour|day|week|month|year)s?\s+ago", re.I)
_DIAS_POR_UNIDADE = {"minuto": 0, "hora": 0, "dia": 1, "semana": 7, "mes": 30, "mês": 30, "meses": 30, "ano": 365,
                     "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def situacao_do_topo(texto: str, hoje: date | None = None) -> tuple[str | None, date | None]:
    """Do topo da vaga no LinkedIn: (aviso de encerrada, data aproximada da publicação).

    "Não aceita mais candidaturas" e "Belo Horizonte, MG · há 6 meses · Mais de 100 candidaturas"
    → ("Não aceita mais candidaturas", hoje − 180 dias).
    """
    hoje = hoje or date.today()
    encerrada = _ENCERRADA_TOPO.search(texto or "")
    publicada = None
    if (m := _IDADE_TOPO.search(texto or "")):
        numero, unidade = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        quantidade = 1 if numero.lower() in ("um", "uma", "a", "an") else int(numero)
        publicada = hoje - timedelta(days=quantidade * _DIAS_POR_UNIDADE[unidade.lower()])
    return (encerrada.group(0)[:1].upper() + encerrada.group(0)[1:] if encerrada else None), publicada


def local_e_modelo_do_topo(texto: str) -> tuple[str | None, str | None]:
    """Do topo da vaga no LinkedIn: ('Nova Lima, Minas Gerais, Brasil', 'presencial')."""
    m = _LOCAL_TOPO.search(texto or "")
    modelo = next((_MODELOS_TOPO[l.strip().lower()] for l in (texto or "").splitlines()
                   if l.strip().lower() in _MODELOS_TOPO), None)
    return (m.group(1).strip() if m else None), modelo


def ler_detalhe(pagina, vaga: VagaBruta, cfg: LinkedInAutomatico, dormir: Dormir) -> VagaBruta:
    """Abre a vaga e completa descrição (e o que o JSON-LD trouxer)."""
    pagina.goto(vaga.link, wait_until="domcontentloaded")
    checar_pagina(pagina)
    dormir(2)
    dados = {}
    postings = jobpostings(pagina.evaluate(JS_JSONLD))
    if postings:
        dados = {k: v for k, v in campos_de_jobposting(postings[0]).items() if v}
        if not dados.get("descricao") and postings[0].get("description"):
            dados["descricao"] = html_para_texto(str(postings[0]["description"]))
    if not dados.get("descricao"):
        for seletor in cfg.seletores_descricao:
            alvo = pagina.locator(seletor)
            if alvo.count():
                dados["descricao"] = alvo.first.inner_text().strip()
                break
    # Topo da vaga: "Nova Lima, Minas Gerais, Brasil · há 2 dias · 30 candidaturas", uma linha "Presencial" e,
    # se ela fechou, "Não aceita mais candidaturas".
    topo = pagina.evaluate("() => ((document.querySelector('main') || document.body).innerText || '').slice(0, 2000)")
    local_topo, modelo_topo = local_e_modelo_do_topo(topo)
    if local_topo and not vaga.local:
        dados["local"] = local_topo
    if modelo_topo and not vaga.modelo:
        dados["modelo"] = modelo_topo
    encerrada, publicada = situacao_do_topo(topo)
    if encerrada:
        dados["encerrada"] = encerrada
    if publicada and not dados.get("publicada_em"):
        dados["publicada_em"] = publicada
    if not dados.get("empresa") and not vaga.empresa:
        # O título da aba é "Cargo | Empresa | LinkedIn".
        partes = [p.strip() for p in (pagina.title() or "").split("|")]
        if len(partes) >= 3 and partes[-1].lower() == "linkedin" and partes[-2]:
            dados["empresa"] = partes[-2]
    campos = {k: v for k, v in dados.items() if k in VagaBruta.model_fields and k not in ("fonte_tipo", "fonte_origem", "link")}
    return vaga.model_copy(update={k: v for k, v in campos.items() if not getattr(vaga, k, None) or k == "descricao"})


@dataclass
class ResultadoBusca:
    vagas: list[VagaBruta] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    consultas: int = 0


def buscar_vagas(pagina, config: ConfigVagas, cfg: LinkedInAutomatico, links_conhecidos: set[str], *,
                 dormir: Dormir = time.sleep, aleatorio: random.Random | None = None) -> ResultadoBusca:
    """Busca pelas buscas salvas e lê a descrição das vagas novas. LoginNecessario/LayoutMudou sobem para quem chamou."""
    resultado = ResultadoBusca()
    encontradas: dict[str, VagaBruta] = {}
    lista = consultas(config, cfg)
    if not lista:
        resultado.avisos.append("LinkedIn: nenhuma busca salva para pesquisar")
        return resultado
    vazias = 0
    from ..operacao import andamento

    for i, (nome, url) in enumerate(lista):
        andamento.etapa("LinkedIn: pesquisando vagas", i + 1, len(lista))
        if i:
            pausa(cfg, dormir, aleatorio)
        vagas = ler_resultados(pagina, url, cfg, dormir)
        resultado.consultas += 1
        if not vagas:
            vazias += 1
        for v in vagas:
            encontradas.setdefault(v.link, v)
    if vazias == len(lista):
        corpo = _norm(pagina.evaluate("() => document.body ? document.body.innerText.slice(0, 4000) : ''"))
        if not any(p in corpo for p in ("nenhuma vaga", "no matching jobs", "nao encontramos", "no jobs found")):
            raise LayoutMudou("nenhum cartão de vaga nas páginas de busca do LinkedIn (o layout pode ter mudado)")
    novas = [v for link, v in encontradas.items() if link not in links_conhecidos]
    for j, vaga in enumerate(novas):
        if j < cfg.detalhes_por_rodada:
            andamento.etapa("LinkedIn: lendo as vagas novas", j + 1, min(len(novas), cfg.detalhes_por_rodada))
            pausa(cfg, dormir, aleatorio)
            try:
                vaga = ler_detalhe(pagina, vaga, cfg, dormir)
            except LoginNecessario:
                raise
            except Exception as erro:  # noqa: BLE001 - uma vaga com problema não derruba a busca
                resultado.avisos.append(f"LinkedIn: não li a descrição de '{vaga.titulo}': {type(erro).__name__}")
        resultado.vagas.append(vaga)
    if len(novas) > cfg.detalhes_por_rodada:
        resultado.avisos.append(f"LinkedIn: {len(novas) - cfg.detalhes_por_rodada} vaga(s) nova(s) entraram só com "
                                "título; a descrição é lida nas próximas rodadas ou quando você abrir a vaga")
    return resultado


def coletor_da_rodada(config: ConfigVagas, cfg: LinkedInAutomatico, saude, *, abrir_sessao=None,
                      dormir: Dormir = time.sleep):
    """Fonte extra da rodada diária (radar.rodada.ColetorExtra). Erros viram avisos; a rodada continua."""
    def coletar(base) -> tuple[list[VagaBruta], list[str], list[str]]:
        if not saude.pode_usar(ADAPTADOR):
            return [], [f"{ADAPTADOR}: parado após erro (agente saude reativar {ADAPTADOR})"], []
        from ..navegador import NavegadorOcupado, SessaoNavegador, erro_curto, fechado_pela_pessoa, playwright_disponivel

        if abrir_sessao is None and not playwright_disponivel():
            return [], ["LinkedIn: o navegador automático precisa do Playwright ('uv sync')"], []
        conhecidos = {v.link for v in base.itens if v.link} | {f.url for v in base.itens for f in v.fontes if f.url}
        try:
            with (abrir_sessao or SessaoNavegador)(**({} if abrir_sessao else {"uso": USO_NAVEGADOR})) as sessao:
                resultado = buscar_vagas(sessao.pagina, config, cfg, conhecidos, dormir=dormir)
        except NavegadorOcupado as erro:  # não é falha do LinkedIn: só fica para a próxima rodada
            return [], [f"LinkedIn não pesquisado nesta rodada: {erro}"], []
        except LoginNecessario as erro:
            saude.falha(ADAPTADOR, str(erro))
            return [], [f"LinkedIn: {erro}"], [f"LinkedIn: {erro}"]
        except LayoutMudou as erro:
            parou = saude.falha(ADAPTADOR, str(erro), parar=True)
            return [], [f"LinkedIn: {erro}"], [f"{ADAPTADOR}: {erro}"] if parou else []
        except Exception as erro:  # noqa: BLE001 - a busca no LinkedIn não derruba a rodada
            if fechado_pela_pessoa(erro):
                return [], ["LinkedIn: o navegador do agente foi fechado no meio da busca; fica para a próxima rodada"], []
            saude.falha(ADAPTADOR, erro_curto(erro))
            return [], [f"LinkedIn: {erro_curto(erro)}"], []
        saude.sucesso(ADAPTADOR)
        return resultado.vagas, resultado.avisos, []

    return coletar


# ---------------------------------------------------------------- Candidatura Simplificada

JS_CAMPOS = r"""
(raiz) => {
  const saida = []; let i = 0;
  const rotulo = (el) => {
    if (el.labels && el.labels.length) return el.labels[0].innerText;
    const ids = el.getAttribute('aria-labelledby');
    if (ids) { const t = ids.split(' ').map(x => document.getElementById(x)).filter(Boolean).map(e => e.innerText).join(' '); if (t) return t; }
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
  };
  for (const el of raiz.querySelectorAll('input, textarea, select')) {
    const tipo = (el.getAttribute('type') || '').toLowerCase();
    if (['hidden', 'radio', 'checkbox', 'submit', 'button'].includes(tipo) || el.disabled) continue;
    if (tipo !== 'file' && el.offsetParent === null) continue;
    el.setAttribute('data-agente', String(i));
    const tag = el.tagName.toLowerCase();
    saida.push({i: i++, tag, tipo, rotulo: (rotulo(el) || '').trim(),
      obrigatorio: el.required || el.getAttribute('aria-required') === 'true',
      valor: tag === 'select' ? (el.selectedIndex >= 0 ? el.options[el.selectedIndex].text.trim() : '') : (tipo === 'file' ? '' : (el.value || '')),
      opcoes: tag === 'select' ? [...el.options].map(o => o.text.trim()) : []});
  }
  for (const fs of raiz.querySelectorAll('fieldset')) {
    const radios = [...fs.querySelectorAll('input[type=radio]')];
    if (!radios.length) continue;
    fs.setAttribute('data-agente', String(i));
    const legenda = ((fs.querySelector('legend') || fs).innerText || '').split('\n')[0].trim();
    saida.push({i: i++, tag: 'fieldset', tipo: 'radio', rotulo: legenda,
      obrigatorio: radios.some(r => r.required) || fs.getAttribute('aria-required') === 'true' || /\*|obrigat|required/i.test(legenda),
      valor: radios.some(r => r.checked) ? 'marcado' : '',
      opcoes: radios.map(r => ((r.labels && r.labels[0] ? r.labels[0].innerText : r.value) || '').trim())});
  }
  return saida;
}
"""

_SELECIONE = re.compile(r"^(selecion|select|escolh|choose)", re.IGNORECASE)
_EQUIVALENTES = {"sim": {"sim", "yes"}, "nao": {"nao", "no"}, "yes": {"sim", "yes"}, "no": {"nao", "no"}}


def escolher_opcao(resposta: str, opcoes: list[str]) -> str | None:
    """A opção que corresponde à resposta (Sim/Não valem em português e inglês)."""
    alvo = _norm(re.split(r"[—–-]", resposta, maxsplit=1)[0])
    aceitas = _EQUIVALENTES.get(alvo, {alvo})
    for opcao in opcoes:
        if _norm(opcao) in aceitas:
            return opcao
    for opcao in opcoes:
        if alvo and len(alvo) >= 3 and (_norm(opcao).startswith(alvo) or alvo.startswith(_norm(opcao)) and _norm(opcao)):
            return opcao
    return None


def _so_numero(resposta: str) -> str | None:
    m = re.search(r"\d+(?:[.,]\d+)?", resposta.replace(".", "") if re.search(r"\d\.\d{3}", resposta) else resposta)
    return m.group(0).replace(",", ".") if m else None


@dataclass
class ResultadoCandidatura:
    parou: str = ""                      # revisao | pergunta_sem_resposta | sem_candidatura_simplificada | layout | erro | limite
    etapas: int = 0
    preenchidos: list[str] = field(default_factory=list)
    sem_resposta: list[str] = field(default_factory=list)
    mensagem: str = ""
    captura: Path | None = None


def _botao(escopo, nomes: list[str]):
    padrao = re.compile(r"^\s*(" + "|".join(re.escape(n) for n in nomes) + r")\b", re.IGNORECASE)
    alvo = escopo.get_by_role("button", name=padrao)
    for k in range(alvo.count()):
        if alvo.nth(k).is_visible():
            return alvo.nth(k)
    return None


def preencher_etapa(dialogo, responder: Callable[[str], str | None], cv: Path | None, *, cfg: LinkedInAutomatico,
                    dormir: Dormir, resultado: ResultadoCandidatura, acoes_restantes: list[int]) -> list[str]:
    """Preenche os campos vazios da etapa; devolve as perguntas obrigatórias que ficaram sem resposta."""
    faltando: list[str] = []
    for campo in dialogo.evaluate(JS_CAMPOS):
        rotulo = re.sub(r"\s+", " ", campo["rotulo"]).strip(" *")
        vazio = not campo["valor"] or (campo["tag"] == "select" and _SELECIONE.match(campo["valor"]))
        if not vazio:
            continue
        alvo = dialogo.locator(f'[data-agente="{campo["i"]}"]')
        if campo["tipo"] == "file":
            if cv and cv.is_file() and acoes_restantes[0] > 0:
                alvo.set_input_files(str(cv))
                resultado.preenchidos.append("currículo (arquivo)")
                acoes_restantes[0] -= 1
            continue
        resposta = responder(rotulo) if rotulo else None
        valor: str | None = None
        if resposta:
            if campo["tag"] in ("select", "fieldset"):
                valor = escolher_opcao(resposta, campo["opcoes"])
            elif campo["tipo"] == "number":
                valor = _so_numero(resposta)
            else:
                valor = resposta
        if valor is None:
            if campo["obrigatorio"]:
                faltando.append(rotulo or "(campo sem rótulo)")
            continue
        if acoes_restantes[0] <= 0:
            faltando.append(rotulo)
            continue
        pausa(cfg, dormir)
        if campo["tag"] == "select":
            alvo.select_option(label=valor)
        elif campo["tag"] == "fieldset":
            alvo.get_by_label(valor, exact=True).first.check()
        else:
            alvo.fill(valor)
        acoes_restantes[0] -= 1
        resultado.preenchidos.append(rotulo)
    return faltando


def candidatura_simplificada(pagina, url: str, responder: Callable[[str], str | None], cv: Path | None,
                             cfg: LinkedInAutomatico, *, limite_acoes: int = 30, dormir: Dormir = time.sleep,
                             pasta_capturas: Path | None = None) -> ResultadoCandidatura:
    """Abre a vaga, abre a Candidatura Simplificada e avança as etapas. Nunca clica em enviar."""
    resultado = ResultadoCandidatura()
    pagina.goto(url, wait_until="domcontentloaded")
    checar_pagina(pagina)
    dormir(2.5)
    abrir = _botao(pagina, cfg.botoes_candidatura)
    if abrir is None:
        resultado.parou = "sem_candidatura_simplificada"
        resultado.mensagem = ("Esta vaga não tem Candidatura Simplificada: a inscrição é no site da empresa. "
                              "Clique em 'Candidatar-se' no LinkedIn e siga por lá.")
        return resultado
    abrir.click()  # abre o formulário; não envia nada
    dormir(2)
    acoes = [limite_acoes]
    for _ in range(cfg.max_etapas_candidatura):
        dialogo = pagina.get_by_role("dialog")
        if not dialogo.count():
            raise LayoutMudou("o formulário da Candidatura Simplificada não abriu como esperado")
        dialogo = dialogo.first
        resultado.etapas += 1
        faltando = preencher_etapa(dialogo, responder, cv, cfg=cfg, dormir=dormir, resultado=resultado,
                                   acoes_restantes=acoes)
        if _botao(dialogo, cfg.botoes_enviar) is not None:
            resultado.parou = "revisao"
            resultado.sem_resposta += faltando
            resultado.mensagem = "Parei na revisão. Confira tudo no navegador e clique em 'Enviar candidatura' você mesmo."
            break
        if faltando:
            resultado.parou = "pergunta_sem_resposta"
            resultado.sem_resposta += faltando
            resultado.mensagem = ("Há perguntas que só você pode responder (o agente não inventa respostas). "
                                  "Responda no navegador, avance e envie você mesmo.")
            break
        if acoes[0] <= 0:
            resultado.parou = "limite"
            resultado.mensagem = "Cheguei ao limite de ações desta sessão (ritmo humano). Termine você no navegador."
            break
        avancar = _botao(dialogo, cfg.botoes_avancar)
        if avancar is None:
            raise LayoutMudou("não achei o botão de avançar na Candidatura Simplificada")
        pausa(cfg, dormir)
        avancar.click()
        dormir(1.5)
        erro = dialogo.locator(".artdeco-inline-feedback--error, [role=alert]")
        if erro.count() and erro.first.is_visible() and erro.first.inner_text().strip():
            resultado.parou = "erro"
            resultado.mensagem = f"O LinkedIn apontou um problema: {erro.first.inner_text().strip()}. Corrija no navegador."
            break
    else:
        resultado.parou = "limite"
        resultado.mensagem = "Muitas etapas: parei por segurança. Termine você no navegador."
    if pasta_capturas is not None:
        pasta_capturas.mkdir(parents=True, exist_ok=True)
        resultado.captura = pasta_capturas / f"linkedin-{datetime.now():%Y%m%d-%H%M%S}.png"
        pagina.screenshot(path=str(resultado.captura))
    return resultado


def responder_com_perfil(perfil, banco, contrato: str | None = None) -> Callable[[str], str | None]:
    """Respostas só do banco aprovado e do perfil (RN-09); telefone, e-mail e cidade vêm do contato."""
    from ..candidatar.kit import responder

    contato = perfil.contato
    diretos = [
        (re.compile(r"telefone|celular|phone|mobile|whats", re.I), contato.telefone),
        (re.compile(r"e-?mail", re.I), contato.email),
        (re.compile(r"^(cidade|city|localiza|location)", re.I), ", ".join(p for p in (contato.cidade, contato.uf) if p) or None),
        (re.compile(r"^(nome|first name|primeiro nome)", re.I), contato.nome.split()[0] if contato.nome else None),
        (re.compile(r"^(sobrenome|last name)", re.I), " ".join(contato.nome.split()[1:]) or None if contato.nome else None),
    ]

    def responder_rotulo(rotulo: str) -> str | None:
        for padrao, valor in diretos:
            if padrao.search(rotulo):
                return valor or None
        return responder(rotulo, perfil, banco, contrato).resposta

    return responder_rotulo


# ---------------------------------------------------------------- descrições das vagas dos alertas

def aplicar_conferencia(vaga, lida: VagaBruta, agora: datetime | None = None) -> None:
    """O que a página aberta agora diz da vaga: data real de publicação, prazo e se ela fechou."""
    vaga.conferida_em = agora or datetime.now(timezone.utc)
    # O alerta de e-mail chega depois da publicação: a data mais antiga é a verdadeira.
    if lida.publicada_em and (vaga.publicada_em is None or lida.publicada_em < vaga.publicada_em):
        vaga.publicada_em = lida.publicada_em
    if lida.valida_ate and not vaga.valida_ate:
        vaga.valida_ate = lida.valida_ate
    if lida.encerrada:
        vaga.motivo_expiracao = f"o LinkedIn diz: {lida.encerrada}"


def enriquecedor_da_rodada(cfg: LinkedInAutomatico, saude, *, abrir_sessao=None, dormir: Dormir = time.sleep,
                           limite: int | None = None):
    """Abre no navegador do agente as vagas do LinkedIn e lê a página: descrição, local, data e se ela ainda aceita
    candidaturas ("Não aceita mais candidaturas" vira vaga expirada).

    Vão as sem descrição ou sem local (ex.: as dos alertas) e as abertas que ninguém confere há dias. Só leitura, com
    pausas; no máximo `limite` vagas (padrão: detalhes_por_rodada). Devolve quantas páginas foram lidas.
    """
    def enriquecer(vagas, *, conferir_todas: bool = False) -> int:
        from ..radar.coleta import separar_empresa_local
        from ..radar.rodada import precisa_conferir

        for v in vagas:  # "Empresa · Cidade" vira empresa e local antes de qualquer leitura
            v.empresa, v.local = separar_empresa_local(v.empresa, v.local)
        alvo = [v for v in vagas if v.link and "linkedin.com/jobs/view/" in v.link
                and (not v.descricao or not v.local or conferir_todas or precisa_conferir(v))]
        # Cada uma na sua cota (RF-EV-12): descrições novas primeiro, depois as conferências; as de maior nota antes.
        sem_descricao = sorted((v for v in alvo if not v.descricao or not v.local), key=lambda v: -v.nota)
        conferir = sorted((v for v in alvo if v.descricao and v.local), key=lambda v: -v.nota)
        if limite:
            alvo = (sem_descricao + conferir)[:limite]
        else:
            alvo = sem_descricao[:cfg.detalhes_por_rodada] + conferir[:cfg.conferencias_por_rodada]
        if not alvo or not saude.pode_usar(ADAPTADOR):
            return 0
        from ..navegador import NavegadorOcupado, SessaoNavegador
        from ..operacao import andamento
        from ..radar.dedup import mesclar
        from ..radar.rodada import de_bruta, reextrair

        lidas = 0
        try:
            with (abrir_sessao or SessaoNavegador)(**({} if abrir_sessao else {"uso": USO_NAVEGADOR})) as sessao:
                for i, vaga in enumerate(alvo, 1):
                    andamento.etapa("LinkedIn: lendo e conferindo as vagas", i, len(alvo))
                    if i > 1:
                        pausa(cfg, dormir)
                    bruta = VagaBruta(titulo=vaga.titulo, empresa=vaga.empresa, local=vaga.local, link=vaga.link,
                                      fonte_tipo="pagina", fonte_origem=ORIGEM)
                    try:
                        lida = ler_detalhe(sessao.pagina, bruta, cfg, dormir)
                    except LoginNecessario:
                        raise
                    except Exception:  # noqa: BLE001 - uma vaga com problema não para as outras
                        continue
                    aplicar_conferencia(vaga, lida)
                    lidas += 1
                    if lida.local and not vaga.local:
                        vaga.local = lida.local
                    if lida.modelo and not vaga.modelo:
                        vaga.modelo = lida.modelo
                    if lida.descricao and not vaga.descricao:
                        mesclar(vaga, de_bruta(lida))
                        reextrair(vaga)
        except (NavegadorOcupado, LoginNecessario):
            return lidas
        if lidas:
            saude.sucesso(ADAPTADOR)
        return lidas

    return enriquecer
