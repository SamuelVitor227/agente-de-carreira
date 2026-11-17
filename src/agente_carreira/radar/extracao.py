"""Extração de dados de vagas: HTML, JSON-LD (schema.org JobPosting) e campos do texto (RF-VG-04)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser

from .texto import norm

BLOCOS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td",
    "section", "article", "header", "footer", "table", "hr",
}
IGNORADAS = {"script", "style", "noscript", "svg", "template"}


# ---------------------------------------------------------------- HTML

@dataclass
class PaginaHTML:
    texto: str
    titulo: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)  # (href, texto da âncora)
    jsonld: list[str] = field(default_factory=list)


class _Parser(HTMLParser):
    def __init__(self, links_no_texto: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.links_no_texto = links_no_texto
        self.partes: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.jsonld: list[str] = []
        self.titulo = ""
        self._ignorar = 0
        self._em_jsonld = False
        self._buffer: list[str] = []
        self._em_titulo = False
        self._href: str | None = None
        self._ancora: list[str] = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "script" and (atributos.get("type") or "").lower() == "application/ld+json":
            self._em_jsonld = True
            self._buffer = []
            return
        if tag in IGNORADAS:
            self._ignorar += 1
            return
        if tag == "title":
            self._em_titulo = True
        if tag in BLOCOS:
            self.partes.append("\n")
        if tag == "li":
            self.partes.append("- ")
        if tag == "a":
            self._href = atributos.get("href") or ""
            self._ancora = []

    def handle_endtag(self, tag):
        if tag == "script" and self._em_jsonld:
            self.jsonld.append("".join(self._buffer))
            self._em_jsonld = False
            return
        if tag in IGNORADAS:
            self._ignorar = max(0, self._ignorar - 1)
            return
        if tag == "title":
            self._em_titulo = False
        if tag == "a" and self._href is not None:
            texto = " ".join("".join(self._ancora).split())
            self.links.append((self._href, texto))
            if self.links_no_texto:
                # Em e-mails de alerta, cada link vira uma linha "texto da âncora<TAB>url".
                self.partes.append(f"\n{texto}\t{self._href}\n")
            self._href = None
        if tag in BLOCOS:
            self.partes.append("\n")

    def handle_data(self, data):
        if self._em_jsonld:
            self._buffer.append(data)
            return
        if self._ignorar:
            return
        if self._em_titulo:
            self.titulo += data
            return
        if self._href is not None:
            self._ancora.append(data)
            if self.links_no_texto:
                return
        self.partes.append(data)


def _limpar(texto: str) -> str:
    linhas: list[str] = []
    for linha in texto.splitlines():
        limpa = re.sub(r"[ \f\v\r ]+", " ", linha).strip(" ")
        if limpa or (linhas and linhas[-1]):
            linhas.append(limpa)
    return "\n".join(linhas).strip()


def analisar_html(html: str, links_no_texto: bool = False) -> PaginaHTML:
    parser = _Parser(links_no_texto)
    parser.feed(html)
    parser.close()
    return PaginaHTML(
        texto=_limpar("".join(parser.partes)),
        titulo=" ".join(parser.titulo.split()),
        links=parser.links,
        jsonld=parser.jsonld,
    )


def html_para_texto(html: str) -> str:
    return analisar_html(html).texto if "<" in (html or "") else (html or "").strip()


# ---------------------------------------------------------------- JSON-LD

def jobpostings(brutos: list[str]) -> list[dict]:
    """Objetos schema.org JobPosting encontrados nos blocos JSON-LD da página."""
    achados: list[dict] = []

    def visitar(obj: object) -> None:
        if isinstance(obj, list):
            for item in obj:
                visitar(item)
        elif isinstance(obj, dict):
            tipo = obj.get("@type")
            tipos = tipo if isinstance(tipo, list) else [tipo]
            if "JobPosting" in tipos:
                achados.append(obj)
            if "@graph" in obj:
                visitar(obj["@graph"])

    for bruto in brutos:
        try:
            visitar(json.loads(bruto.strip()))
        except (json.JSONDecodeError, ValueError):
            continue
    return achados


def _data(valor: object) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def _numero(valor: object) -> float | None:
    try:
        return float(valor) if valor not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _nome(valor: object) -> str | None:
    if isinstance(valor, dict):
        valor = valor.get("name")
    return str(valor).strip() if valor else None


def campos_de_jobposting(d: dict) -> dict:
    local = None
    locais = d.get("jobLocation")
    primeiro = (locais[0] if locais else None) if isinstance(locais, list) else locais
    if isinstance(primeiro, dict):
        endereco = primeiro.get("address")
        if isinstance(endereco, dict):
            partes = [endereco.get("addressLocality"), endereco.get("addressRegion")]
            local = ", ".join(str(p) for p in partes if p) or None
        elif isinstance(endereco, str):
            local = endereco

    modelo = "remoto" if str(d.get("jobLocationType", "")).upper() == "TELECOMMUTE" else None

    contrato = None
    tipos = d.get("employmentType")
    for tipo in tipos if isinstance(tipos, list) else [tipos]:
        tipo = str(tipo or "").upper()
        if tipo == "INTERN":
            contrato = "estagio"
            break
        if tipo == "CONTRACTOR":
            contrato = "pj"
        elif tipo == "FULL_TIME" and contrato is None:
            contrato = "clt"

    salario_min = salario_max = None
    salario = d.get("baseSalary")
    if isinstance(salario, dict):
        valor = salario.get("value")
        if isinstance(valor, dict):
            salario_min = _numero(valor.get("minValue")) or _numero(valor.get("value"))
            salario_max = _numero(valor.get("maxValue")) or salario_min
        else:
            salario_min = salario_max = _numero(valor)

    return {
        "titulo": _nome(d.get("title")),
        "empresa": _nome(d.get("hiringOrganization")),
        "local": local,
        "modelo": modelo,
        "contrato": contrato,
        "salario_min": salario_min,
        "salario_max": salario_max,
        "publicada_em": _data(d.get("datePosted")),
        "valida_ate": _data(d.get("validThrough")),
        "descricao": html_para_texto(str(d.get("description") or "")),
        "link": d.get("url") if isinstance(d.get("url"), str) else None,
    }


# ---------------------------------------------------------------- campos do texto

_NIVEIS_TITULO = [
    ("estagio", re.compile(r"\bestagi|\bintern(ship)?\b")),
    ("trainee", re.compile(r"\btrainee\b")),
    ("junior", re.compile(r"\bjunior\b|\bjr\b")),
    ("pleno", re.compile(r"\bpleno\b|\bmid[- ]?level\b")),
    ("senior", re.compile(r"\bsenior\b|\bsr\b|\bespecialista\b|\btech lead\b|\blead\b")),
]


def detectar_nivel(titulo: str, descricao: str = "") -> str | None:
    t = norm(titulo)
    for nivel, padrao in _NIVEIS_TITULO:
        if padrao.search(t):
            return nivel
    d = norm(descricao)
    if re.search(r"vaga de estagio|programa de estagio|bolsa[- ]auxilio", d):
        return "estagio"
    if re.search(r"programa de trainee", d):
        return "trainee"
    return None


def detectar_modelo(*textos: str | None) -> str | None:
    for texto in textos:
        t = norm(texto)
        if re.search(r"\bhibrid|\bhybrid", t):
            return "hibrido"
        if re.search(r"\bremot|home[- ]?office|\bremote\b|teletrabalho|\banywhere\b", t):
            return "remoto"
        if re.search(r"\bpresencial|\bon[- ]?site\b", t):
            return "presencial"
    return None


def detectar_contrato(titulo: str, descricao: str = "") -> str | None:
    t = norm(f"{titulo}\n{descricao}")
    if re.search(r"\bestagi|bolsa[- ]auxilio", t):
        return "estagio"
    if re.search(r"\bclt\b|\befetiv", t):
        return "clt"
    if re.search(r"\bpj\b|pessoa juridica|\bcontractor\b", t):
        return "pj"
    return None


_VALOR = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?"
_SALARIO = re.compile(rf"R\$\s*{_VALOR}(?:\s*(?:a|at[eé]|-|–)\s*(?:R\$\s*)?{_VALOR})?", re.IGNORECASE)


def _valor(inteiro: str, centavos: str | None) -> float:
    return float(inteiro.replace(".", "") + ("." + centavos if centavos else ""))


def extrair_salario(texto: str) -> tuple[float | None, float | None]:
    m = _SALARIO.search(texto or "")
    if not m:
        return None, None
    minimo = _valor(m.group(1), m.group(2))
    maximo = _valor(m.group(3), m.group(4)) if m.group(3) else minimo
    return minimo, max(minimo, maximo)


_HORAS_DIA = re.compile(r"(\d{1,2})\s*(?:h|hrs?|horas?)\s*(?:/\s*dia|por\s+dia|diarias|ao\s+dia|diariamente)")
_HORAS_SEMANA = re.compile(r"(\d{1,2})\s*(?:h|hrs?|horas?)\s*(?:/\s*semana|por\s+semana|semanais|semanalmente|na\s+semana)")


def extrair_horas(texto: str) -> tuple[int | None, int | None]:
    t = norm(texto)
    dia = max((int(m) for m in _HORAS_DIA.findall(t)), default=None)
    semana = max((int(m) for m in _HORAS_SEMANA.findall(t)), default=None)
    return dia, semana


_ANOS = [
    re.compile(r"(\d{1,2})\s*\+?\s*anos?\s+de\s+experiencia"),
    re.compile(r"experiencia\s+(?:minima\s+)?de\s+(\d{1,2})\s+anos?"),
    re.compile(r"(\d{1,2})\s*\+?\s*years?\s+(?:of\s+)?experience"),
]


def extrair_anos_experiencia(texto: str) -> int | None:
    t = norm(texto)
    valores = [int(v) for padrao in _ANOS for v in padrao.findall(t)]
    return max(valores) if valores else None


IDIOMAS = {"ingles": re.compile(r"ingles|english"), "espanhol": re.compile(r"espanhol|spanish|castelhano")}
NIVEIS_IDIOMA = [
    (5, re.compile(r"nativo|native|bilingu")),
    (4, re.compile(r"fluente|fluencia|fluent|full professional")),
    (3, re.compile(r"avancado|advanced|professional working")),
    (2, re.compile(r"intermediario|intermediate|limited working")),
    (1, re.compile(r"basico|basic|elementary")),
]
NOMES_NIVEL_IDIOMA = {0: "não registrado", 1: "básico", 2: "intermediário", 3: "avançado", 4: "fluente", 5: "nativo"}
_DESEJAVEL = re.compile(r"desejave|diferencial|nice to have|\bplus\b|seria legal")


def nivel_idioma(texto: str | None) -> int:
    t = norm(texto)
    for nivel, padrao in NIVEIS_IDIOMA:
        if padrao.search(t):
            return nivel
    return 0


def idiomas_exigidos(texto_obrigatorio: str) -> dict[str, int]:
    """Idiomas com nível citados nos requisitos obrigatórios (menção sem nível não elimina)."""
    exigidos: dict[str, int] = {}
    for linha in (texto_obrigatorio or "").splitlines():
        n = norm(linha)
        if _DESEJAVEL.search(n):
            continue
        for idioma, padrao in IDIOMAS.items():
            if padrao.search(n) and (nivel := nivel_idioma(n)):
                exigidos[idioma] = max(exigidos.get(idioma, 0), nivel)
    return exigidos


_PT = {"de", "para", "com", "voce", "que", "experiencia", "conhecimento", "vaga", "nao", "em", "uma", "os"}
_EN = {"the", "and", "with", "you", "experience", "we", "our", "for", "skills", "will", "to", "of"}


def detectar_idioma(texto: str) -> str | None:
    palavras = re.findall(r"[a-z]+", norm(texto))
    if len(palavras) < 20:
        return None
    pt = sum(1 for p in palavras if p in _PT)
    en = sum(1 for p in palavras if p in _EN)
    return "en" if en > pt * 1.2 and en >= 5 else "pt"


_CAB_DESEJ = re.compile(
    r"^(requisitos desejave\w*|desejave\w*|diferencia\w*|nice[- ]to[- ]have|plus|bonus|seria (legal|um diferencial)"
    r"|sera um diferencial|pontos extras)\b"
)
_CAB_OBRIG = re.compile(
    r"^(requisitos?( obrigat\w*| minimos?| tecnicos?)?|requirements?|qualificac\w*|o que (voce precisa|esperamos|buscamos)"
    r"|pre[- ]?requisitos|must[- ]have|what you need|you have|voce precisa ter|obrigatori\w*|necessari\w*)\b"
)
_CAB_OUTRA = re.compile(
    r"^(beneficios?|responsabilidades|atividades|sobre|o que oferecemos|local( de trabalho)?|salario|remuneracao"
    r"|como sera|etapas|informacoes|about|benefits|responsibilities|what you.?ll do|descricao|quem somos|jornada)\b"
)


def secoes_requisitos(texto: str) -> tuple[list[str], list[str]]:
    """Requisitos obrigatórios e desejáveis, pelas seções do anúncio (ou por palavras-chave)."""
    obrigatorios: list[str] = []
    desejaveis: list[str] = []
    atual: list[str] | None = None
    achou_cabecalho = False
    for linha in (texto or "").splitlines():
        bruta = linha.strip()
        if not bruta:
            continue
        antes, _, resto = bruta.partition(":")
        cabecalho = norm(antes if resto else bruta).strip(" #*-•").strip()
        if len(cabecalho) <= 60:
            alvo = None
            if _CAB_DESEJ.match(cabecalho):
                alvo = desejaveis
            elif _CAB_OBRIG.match(cabecalho):
                alvo = obrigatorios
            elif _CAB_OUTRA.match(cabecalho):
                atual = None
                continue
            if alvo is not None:
                atual = alvo
                achou_cabecalho = True
                if resto.strip():
                    atual.append(resto.strip())
                continue
        if atual is not None:
            item = re.sub(r"^\d+[.)]\s*", "", bruta.lstrip("-•*·– ").strip())
            if item:
                atual.append(item)

    if not achou_cabecalho:
        for linha in (texto or "").splitlines():
            limpa = linha.strip(" -•*\t")
            n = norm(limpa)
            if not limpa:
                continue
            if _DESEJAVEL.search(n):
                desejaveis.append(limpa)
            elif re.search(r"obrigatori|necessari|imprescindive|required|must have", n):
                obrigatorios.append(limpa)
    return obrigatorios, desejaveis


def texto_obrigatorio(descricao: str, obrigatorios: list[str]) -> str:
    if obrigatorios:
        return "\n".join(obrigatorios)
    return "\n".join(l for l in (descricao or "").splitlines() if not _DESEJAVEL.search(norm(l)))


def extrair_campos(titulo: str, descricao: str, local: str | None = None) -> dict:
    """Todos os campos que dá para tirar do título, do local e da descrição."""
    obrigatorios, desejaveis = secoes_requisitos(descricao)
    essencial = texto_obrigatorio(descricao, obrigatorios)
    salario_min, salario_max = extrair_salario(descricao)
    horas_dia, horas_semana = extrair_horas(descricao)
    return {
        "nivel": detectar_nivel(titulo, descricao),
        "modelo": detectar_modelo(titulo, local, descricao),
        "contrato": detectar_contrato(titulo, descricao),
        "salario_min": salario_min,
        "salario_max": salario_max,
        "horas_dia": horas_dia,
        "horas_semana": horas_semana,
        "anos_experiencia": extrair_anos_experiencia(essencial),
        "idiomas_exigidos": idiomas_exigidos(essencial),
        "idioma": detectar_idioma(descricao),
        "requisitos_obrigatorios": obrigatorios,
        "requisitos_desejaveis": desejaveis,
    }
