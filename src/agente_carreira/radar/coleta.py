"""Coleta só de fontes permitidas (RF-VG-02): e-mails de alerta, páginas de carreira e links do usuário.

Sem raspagem em massa (RN-04): os e-mails são lidos em modo somente leitura
(RNF-03), as páginas só são abertas se o robots.txt permitir, uma por vez e com
intervalo, e plataformas cujos termos proíbem leitura automatizada (LinkedIn,
Indeed...) ficam no modo copiloto: o usuário cola a descrição.
"""

from __future__ import annotations

import email
import imaplib
import os
import re
from collections import Counter
from collections.abc import Callable
from datetime import date
from email import policy
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from .extracao import analisar_html, campos_de_jobposting, jobpostings
from .modelos import VagaBruta
from .texto import casa_cargo

USER_AGENT = "AgenteCarreira/0.1 (uso pessoal)"
INTERVALO_SEGUNDOS = 2.0
LIMITE_BYTES = 2_000_000
_MESES_IMAP = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

Baixador = Callable[[str], tuple[int, str]]


class ColetaErro(Exception):
    """Falha numa fonte; a rodada segue com as outras (RNF-07)."""


class ColetaCopiloto(Exception):
    """Plataforma cujos termos proíbem leitura automatizada: o usuário cola a descrição (RN-04)."""


# ---------------------------------------------------------------- rede

def baixar(url: str, timeout: float = 15) -> tuple[int, str]:
    pedido = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"})
    try:
        with urlopen(pedido, timeout=timeout) as resposta:
            charset = resposta.headers.get_content_charset() or "utf-8"
            return resposta.status, resposta.read(LIMITE_BYTES).decode(charset, errors="replace")
    except HTTPError as erro:
        return erro.code, ""
    except (URLError, TimeoutError, OSError, ValueError) as erro:
        raise ColetaErro(f"falha ao acessar {url}: {erro}") from erro


def dominio(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def dominio_em(url: str, lista: list[str]) -> bool:
    d = dominio(url)
    return any(d == x or d.endswith("." + x) for x in lista)


def robots_permite(url: str, baixar_fn: Baixador) -> bool:
    partes = urlparse(url)
    try:
        status, texto = baixar_fn(f"{partes.scheme}://{partes.netloc}/robots.txt")
    except ColetaErro:
        return False
    if status in (401, 403):
        return False
    if status >= 400:
        return True  # sem robots.txt: leitura permitida
    leitor = RobotFileParser()
    leitor.parse(texto.splitlines())
    return leitor.can_fetch(USER_AGENT, url)


# ---------------------------------------------------------------- e-mails de alerta

PADROES_LINK_VAGA: dict[str, re.Pattern[str]] = {
    "linkedin": re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:comm/)?jobs/view/(?:[\w-]*?-)?(\d{6,})", re.I),
    "indeed": re.compile(r"https?://[a-z.]*indeed\.com/(?:rc/clk|viewjob|pagead/clk)[^\s\"'<>]*?[?&]jk=([a-z0-9]+)", re.I),
    "gupy": re.compile(r"https?://[\w-]+\.gupy\.io/jobs/(\d+)", re.I),
    "vagas.com.br": re.compile(r"https?://(?:www\.)?vagas\.com\.br/vagas/(v\d+)", re.I),
    "programathor": re.compile(r"https?://(?:www\.)?programathor\.com\.br/jobs/(\d+)", re.I),
    "geekhunter": re.compile(r"https?://(?:www\.)?geekhunter\.com\.br/vagas/([\w-]+)", re.I),
    # Alertas do Glassdoor: o identificador vem em jl= ou jobListingId= (link direto ou de parceiro).
    "glassdoor": re.compile(r"https?://[\w.-]*glassdoor\.com(?:\.br)?/[^\s\"'<>]*?[?&](?:jl|jobListingId)=(\d{6,})", re.I),
}
_URL = re.compile(r"https?://\S+")
_IGNORAR = re.compile(
    r"^(ver vaga|ver todas|ver mais|view job|see (all )?jobs|candidatura simplificada|easy apply|promovida|promoted"
    # Selo "Nova"/"Novo"/"New" só quando está sozinho na linha: "Nova Lima, MG" é cidade, não selo.
    r"|nova\s*$|novo\s*$|new\s*$|candidate-se|candidatar|apply( now)?|ativamente recrutando|actively recruiting|saiba mais"
    r"|mais vagas|\d+\s+(candidaturas?|applicants?|candidatos?)|h[aá]\s+\d+|\d+\s+(dias?|horas?|days?|hours?)"
    # Dicas do LinkedIn que aparecem embaixo da vaga e não são local nem empresa.
    r"|recrutando agora|\d+\s+ex-alunos?|\d+\s+conex(ão|ões|ao|oes)|muitas competências relevantes"
    r"|.*competências relevantes|.*ex-alunos da instituição)\b",
    re.I,
)


def canonizar(plataforma: str, m: re.Match[str]) -> str:
    if plataforma == "linkedin":
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    if plataforma == "indeed":
        return f"https://br.indeed.com/viewjob?jk={m.group(1)}"
    if plataforma == "glassdoor":
        return f"https://www.glassdoor.com.br/partner/jobListing.htm?jobListingId={m.group(1)}"
    return m.group(0).split("?")[0]


def canonizar_link(url: str) -> str:
    """Link estável da vaga (sem rastreamento), para remover duplicatas entre fontes."""
    for plataforma, padrao in PADROES_LINK_VAGA.items():
        if m := padrao.search(url):
            return canonizar(plataforma, m)
    return url.split("#")[0]


def _eh_link_de_vaga(linha: str) -> bool:
    return any(p.search(linha) for p in PADROES_LINK_VAGA.values())


def _util(linha: str) -> bool:
    return bool(linha) and not _URL.search(linha) and not _IGNORAR.match(linha)


def _anteriores(linhas: list[str], i: int, maximo: int = 3) -> list[str]:
    bloco: list[str] = []
    j = i - 1
    while j >= 0 and len(bloco) < maximo:
        if _eh_link_de_vaga(linhas[j]):
            break
        atual = linhas[j].strip(" -–|•\t")
        if not atual:
            if bloco:
                break
        elif _util(atual):
            bloco.insert(0, atual)
        j -= 1
    return bloco


def _seguintes(linhas: list[str], i: int, maximo: int = 2, parar_em_branco: bool = True) -> list[str]:
    bloco: list[str] = []
    j = i + 1
    while j < len(linhas) and len(bloco) < maximo:
        if _eh_link_de_vaga(linhas[j]):
            break
        atual = linhas[j].strip(" -–|•\t")
        if not atual:
            if bloco and parar_em_branco:
                break
        elif _util(atual):
            bloco.append(atual)
        j += 1
    return bloco


def _partes(msg: Message) -> tuple[str | None, str | None]:
    plano = html = None
    for parte in msg.walk():
        if parte.is_multipart() or parte.get_content_disposition() == "attachment":
            continue
        try:
            conteudo = parte.get_content()
        except (LookupError, KeyError, AttributeError):
            continue
        if not isinstance(conteudo, str):
            continue
        if parte.get_content_type() == "text/plain" and plano is None:
            plano = conteudo
        elif parte.get_content_type() == "text/html" and html is None:
            html = conteudo
    return plano, html


def _data_email(msg: Message) -> date | None:
    try:
        return parsedate_to_datetime(msg["Date"]).date() if msg["Date"] else None
    except (TypeError, ValueError):
        return None


_ASSUNTO_ALERTA = re.compile(r"vaga|job|oportunidade|alerta|recomenda|contratando|hiring|emprego|position|est[aá]gio",
                             re.I)


def parece_alerta(msg: Message) -> bool:
    """E-mail de alerta de vagas (pelo assunto ou pelo remetente de alertas), não aviso de termos, cadastro etc."""
    remetente = parseaddr(str(msg.get("From", "")))[1].lower()
    return bool(_ASSUNTO_ALERTA.search(str(msg.get("Subject", "")))) or any(
        p in remetente for p in ("jobalert", "jobs-listings", "job-alert"))


def so_links_de_rastreamento(msg: Message) -> bool:
    """Todos os links passam por rastreamento (ex.: tracking.recomendacao.vagas.com.br): não dá para saber a vaga."""
    plano, html = _partes(msg)
    links = _URL.findall("\n".join(t for t in (plano, html) if t))
    links = [l for l in links if not re.search(r"\.(png|jpe?g|gif)\b", l, re.I)]
    return bool(links) and all(re.search(r"//[^/]*(track|click|clk|links?\.|email\.)", l, re.I) for l in links)


def separar_empresa_local(empresa: str | None, local: str | None) -> tuple[str | None, str | None]:
    """Alertas novos do LinkedIn trazem 'Empresa · Cidade, UF (Modelo)' numa linha só; dicas não são local."""
    if local and _IGNORAR.match(local.strip()):
        local = None
    if empresa and " · " in empresa:
        nome, _, resto = empresa.partition(" · ")
        return nome.strip() or None, resto.strip() or local
    return empresa, local


def vagas_de_email(msg: Message) -> list[VagaBruta]:
    """Vagas citadas num e-mail de alerta: link da vaga + título, empresa e local ao redor."""
    plano, html = _partes(msg)
    if plano and _eh_link_de_vaga(plano):
        texto, modo_html = plano, False
    elif html:
        texto, modo_html = analisar_html(html, links_no_texto=True).texto, True
    else:
        return []

    data = _data_email(msg)
    linhas = texto.splitlines()
    vagas: list[VagaBruta] = []
    vistos: set[str] = set()
    for i, linha in enumerate(linhas):
        for plataforma, padrao in PADROES_LINK_VAGA.items():
            for m in padrao.finditer(linha):
                link = canonizar(plataforma, m)
                if link in vistos:
                    continue
                antes = linha[: m.start()].strip(" -–:|•\t")
                if _util(antes):
                    # Título na mesma linha do link (âncora no HTML): empresa e local vêm depois.
                    # No HTML, linhas em branco são só quebras de bloco (div, td), não separam vagas.
                    contexto = [antes] + _seguintes(linhas, i, parar_em_branco=not modo_html)
                elif modo_html:
                    continue  # âncora sem texto (logo, botão): o link com título aparece em outra linha
                else:
                    contexto = _anteriores(linhas, i)  # texto puro: título, empresa e local vêm antes
                if not contexto:
                    continue
                vistos.add(link)
                titulo, empresa, local = (contexto + [None, None])[:3]
                empresa, local = separar_empresa_local(empresa, local)
                vagas.append(VagaBruta(
                    titulo=titulo, empresa=empresa, local=local, link=link,
                    fonte_tipo="email", fonte_origem=f"{plataforma}-alerta", publicada_em=data,
                ))
    return vagas


REMETENTES_CONHECIDOS = {
    "linkedin.com": "linkedin", "indeed.com": "indeed", "gupy.io": "gupy", "vagas.com.br": "vagas.com.br",
    "programathor.com.br": "programathor", "geekhunter.com.br": "geekhunter", "glassdoor.com": "glassdoor",
    "glassdoor.com.br": "glassdoor",
}


def diagnostico_email(msg: Message) -> tuple[str | None, int, bool]:
    """(plataforma, nº de links de vaga distintos, remetente é uma plataforma conhecida) — para RF-OP-07."""
    plano, html = _partes(msg)
    texto = "\n".join(t for t in (plano, html) if t)
    links: set[str] = set()
    por_plataforma: Counter[str] = Counter()
    for plataforma, padrao in PADROES_LINK_VAGA.items():
        for m in padrao.finditer(texto):
            link = canonizar(plataforma, m)
            if link not in links:
                links.add(link)
                por_plataforma[plataforma] += 1
    dominio_remetente = parseaddr(str(msg.get("From", "")))[1].lower().rpartition("@")[2]
    do_remetente = next(
        (p for d, p in REMETENTES_CONHECIDOS.items() if dominio_remetente == d or dominio_remetente.endswith("." + d)),
        None,
    )
    plataforma = do_remetente or (por_plataforma.most_common(1)[0][0] if por_plataforma else None)
    return plataforma, len(links), do_remetente is not None


def ler_eml(caminho: Path) -> Message:
    return email.message_from_bytes(caminho.read_bytes(), policy=policy.default)


def config_imap(ambiente: dict[str, str] | None = None) -> dict[str, str] | None:
    """Credenciais só por variáveis de ambiente (RNF-01); nunca em arquivo do projeto."""
    env = os.environ if ambiente is None else ambiente
    host, usuario, senha = env.get("AGENTE_IMAP_HOST"), env.get("AGENTE_IMAP_USUARIO"), env.get("AGENTE_IMAP_SENHA")
    if not (host and usuario and senha):
        return None
    return {"host": host, "usuario": usuario, "senha": senha, "pasta": env.get("AGENTE_IMAP_PASTA", "Vagas")}


def ler_imap(cfg: dict[str, str], desde: date, imap_factory=imaplib.IMAP4_SSL) -> list[tuple[str, Message]]:
    """E-mails da pasta de alertas desde a data, em modo somente leitura e sem marcar como lidos (RNF-03)."""
    conexao = imap_factory(cfg["host"])
    try:
        conexao.login(cfg["usuario"], cfg["senha"])
        tipo, _ = conexao.select(f'"{cfg["pasta"]}"', readonly=True)
        if tipo != "OK":
            raise ColetaErro(f"pasta '{cfg['pasta']}' não encontrada na caixa de e-mail")
        criterio = f"{desde.day:02d}-{_MESES_IMAP[desde.month - 1]}-{desde.year}"
        tipo, dados = conexao.search(None, "SINCE", criterio)
        if tipo != "OK":
            raise ColetaErro("a busca na caixa de e-mail falhou")
        mensagens: list[tuple[str, Message]] = []
        for numero in (dados[0] or b"").split():
            tipo, partes = conexao.fetch(numero, "(BODY.PEEK[])")
            if tipo != "OK":
                continue
            bruto = next((p[1] for p in partes if isinstance(p, tuple)), None)
            if not bruto:
                continue
            msg = email.message_from_bytes(bruto, policy=policy.default)
            msgid = (msg.get("Message-ID") or f"imap-{numero.decode()}").strip()
            mensagens.append((msgid, msg))
        return mensagens
    finally:
        try:
            conexao.logout()
        except Exception:  # noqa: BLE001 - encerramento best-effort
            pass


# ---------------------------------------------------------------- páginas e links

def _bruta_jobposting(d: dict, url: str, tipo: str, origem: str, empresa_padrao: str | None) -> VagaBruta:
    c = campos_de_jobposting(d)
    return VagaBruta(
        titulo=c["titulo"] or "(sem título)", empresa=c["empresa"] or empresa_padrao, local=c["local"],
        link=canonizar_link(urljoin(url, c["link"])) if c["link"] else canonizar_link(url),
        descricao=c["descricao"], fonte_tipo=tipo, fonte_origem=origem,  # type: ignore[arg-type]
        publicada_em=c["publicada_em"], valida_ate=c["valida_ate"], modelo=c["modelo"], contrato=c["contrato"],
        salario_min=c["salario_min"], salario_max=c["salario_max"],
    )


def vagas_de_pagina(url: str, html: str, cargos: list[str], empresa: str | None = None) -> list[VagaBruta]:
    """Vagas da página de carreira que casam com os cargos das buscas (JSON-LD ou links)."""
    pagina = analisar_html(html)
    origem = f"pagina:{dominio(url)}"
    jobs = jobpostings(pagina.jsonld)
    if jobs:
        return [
            _bruta_jobposting(j, url, "pagina", origem, empresa)
            for j in jobs
            if casa_cargo(str(j.get("title") or ""), cargos)
        ]
    vagas: list[VagaBruta] = []
    vistos: set[str] = set()
    for href, texto in pagina.links:
        if not texto or not casa_cargo(texto, cargos):
            continue
        link = canonizar_link(urljoin(url, href))
        if link in vistos:
            continue
        vistos.add(link)
        vagas.append(VagaBruta(titulo=texto, empresa=empresa, link=link, fonte_tipo="pagina", fonte_origem=origem))
    return vagas


def vaga_de_html(url: str, html: str, tipo: str = "link") -> VagaBruta:
    pagina = analisar_html(html)
    origem = f"{tipo}:{dominio(url)}"
    jobs = jobpostings(pagina.jsonld)
    if jobs:
        return _bruta_jobposting(jobs[0], url, tipo, origem, None)
    titulo = re.split(r"\s[|–-]\s", pagina.titulo)[0].strip() if pagina.titulo else ""
    return VagaBruta(titulo=titulo or url, link=canonizar_link(url), descricao=pagina.texto,
                     fonte_tipo=tipo, fonte_origem=origem)  # type: ignore[arg-type]


def vaga_de_link(url: str, baixar_fn: Baixador, dominios_copiloto: list[str]) -> VagaBruta:
    """Abre um link enviado pelo usuário, se o site permitir (RF-VG-02)."""
    if dominio_em(url, dominios_copiloto):
        raise ColetaCopiloto(dominio(url))
    if not robots_permite(url, baixar_fn):
        raise ColetaErro("o robots.txt do site não permite a leitura desta página")
    status, html = baixar_fn(url)
    if status in (404, 410):
        raise ColetaErro("a página da vaga não existe mais (vaga encerrada)")
    if status >= 400:
        raise ColetaErro(f"o site respondeu HTTP {status}")
    return vaga_de_html(url, html, "link")
