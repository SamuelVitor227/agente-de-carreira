"""Leitura das seções de um CV em texto (RF-PM-02).

Reconhece os cabeçalhos usuais (objetivo, formação, habilidades, projetos,
experiência, certificações, idiomas) e extrai o que está escrito em cada um.
Nada é inferido além do texto (RN-02): experiências e formações viram
rascunhos para o usuário completar e confirmar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

BULLETS = "•●▪◦‣-–—*·"

CABECALHOS = {
    "objetivo": r"objetivo( profissional)?|career objective|objective",
    "resumo": r"resumo( profissional)?|sobre( mim)?|perfil( profissional)?|summary|about( me)?",
    "formacao": r"forma[cç][aã]o( acad[eê]mica)?|escolaridade|education",
    "habilidades": r"habilidades( e compet[eê]ncias)?|compet[eê]ncias( t[eé]cnicas)?|conhecimentos|skills",
    "projetos": r"projetos( de desenvolvimento| pessoais| acad[eê]micos)?|projects",
    "experiencia": r"experi[eê]ncias?( profissiona(l|is))?|hist[oó]rico profissional|experience|work experience",
    "certificacoes": r"(cursos e )?certifica[cç][oõ]es|cursos( complementares)?|certifications|licen[cç]as e certificados",
    "idiomas": r"idiomas|languages",
    "complementares": r"informa[cç][oõ]es (complementares|adicionais)|outras informa[cç][oõ]es|additional information",
}
_CABECALHO = {chave: re.compile(rf"^({padrao})\s*:?$", re.IGNORECASE) for chave, padrao in CABECALHOS.items()}

ESTADOS = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
    "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP",
    "sergipe": "SE", "tocantins": "TO",
}
_PERIODO = re.compile(
    r"((?:\d{1,2}/)?\d{4}|(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\w*\.?\s+(?:de\s+)?\d{4})"
    r"\s*[–—-]\s*((?:\d{1,2}/)?\d{4}|atual|o momento|presente|hoje|(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\w*\.?\s+(?:de\s+)?\d{4})",
    re.IGNORECASE,
)


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def _sem_bullet(linha: str) -> str:
    return linha.strip().lstrip(BULLETS).strip()


def _eh_bullet(linha: str) -> bool:
    limpa = linha.strip()
    return bool(limpa) and limpa[0] in BULLETS


@dataclass
class ProjetoLido:
    nome: str
    tecnologias: list[str] = field(default_factory=list)
    descricao: str | None = None


@dataclass
class ExperienciaLida:
    cargo: str | None
    empresa: str | None
    periodo: str | None
    descricao: str | None


@dataclass
class FormacaoLida:
    curso: str | None
    instituicao: str | None
    periodo: str | None
    observacoes: str | None


@dataclass
class CertificacaoLida:
    nome: str
    emissor: str | None = None
    data: str | None = None


@dataclass
class SecoesCV:
    nome: str | None = None
    cidade: str | None = None
    uf: str | None = None
    objetivo: str | None = None
    resumo: str | None = None
    competencias: list[str] = field(default_factory=list)
    idiomas: list[tuple[str, str | None]] = field(default_factory=list)
    projetos: list[ProjetoLido] = field(default_factory=list)
    experiencias: list[ExperienciaLida] = field(default_factory=list)
    formacoes: list[FormacaoLida] = field(default_factory=list)
    certificacoes: list[CertificacaoLida] = field(default_factory=list)


def dividir_secoes(texto: str) -> tuple[list[str], dict[str, list[str]]]:
    """(linhas antes da primeira seção, linhas de cada seção)."""
    topo: list[str] = []
    secoes: dict[str, list[str]] = {}
    atual: list[str] = topo
    for linha in texto.splitlines():
        limpa = linha.strip()
        if limpa and len(limpa) <= 50 and not _eh_bullet(limpa):
            sem_acento = _norm(limpa)
            chave = next((c for c, p in _CABECALHO.items() if p.match(limpa) or p.match(sem_acento)), None)
            if chave:
                atual = secoes.setdefault(chave, [])
                continue
        atual.append(linha.rstrip())
    return topo, secoes


def _nome(topo: list[str]) -> str | None:
    for linha in topo:
        limpa = linha.strip()
        if not limpa:
            continue
        palavras = limpa.split()
        if 2 <= len(palavras) <= 6 and all(re.fullmatch(r"[A-Za-zÀ-ÿ'.-]+", p) for p in palavras):
            return limpa
        return None
    return None


def _cidade_uf(topo: list[str]) -> tuple[str | None, str | None]:
    for linha in topo:
        m = re.match(r"\s*(endere[cç]o|localiza[cç][aã]o|cidade|local)\s*:\s*(.+)", linha, re.IGNORECASE)
        if not m:
            continue
        partes = [p.strip() for p in m.group(2).split(",") if p.strip()]
        if not partes:
            return None, None
        cidade, uf = partes[0], None
        for parte in partes[1:]:
            if re.fullmatch(r"[A-Z]{2}", parte):
                uf = parte
            elif _norm(parte) in ESTADOS:
                uf = ESTADOS[_norm(parte)]
        return cidade, uf
    return None, None


def _paragrafos(linhas: list[str]) -> list[str]:
    """Junta linhas quebradas pelo PDF em parágrafos (bullets abrem um novo)."""
    blocos: list[str] = []
    for linha in linhas:
        limpa = linha.strip()
        if not limpa:
            blocos.append("")
            continue
        if _eh_bullet(limpa) or not blocos or not blocos[-1]:
            blocos.append(_sem_bullet(limpa))
        else:
            blocos[-1] = f"{blocos[-1]} {limpa}"
    return [b for b in blocos if b]


def _objetivo_resumo(linhas: list[str]) -> tuple[str | None, str | None]:
    limpas = [l.strip() for l in linhas if l.strip()]
    if not limpas:
        return None, None
    objetivo = limpas[0]
    resto = _paragrafos(linhas[linhas.index(next(l for l in linhas if l.strip())) + 1:])
    return objetivo, " ".join(resto) or None


def _itens_com_titulo(linhas: list[str]) -> list[tuple[str, list[str]]]:
    """Blocos 'linha de título' + detalhes abaixo dela (projetos, experiências, formações)."""
    return [(bloco[0], bloco[1:]) for bloco in _blocos_brutos(linhas)]


def _blocos_brutos(linhas: list[str]) -> list[list[str]]:
    """Cada bloco: [linha de título, detalhe, detalhe...]; linhas quebradas pelo PDF são reunidas."""
    blocos: list[list[str]] = []
    for linha in linhas:
        limpa = linha.strip()
        if not limpa:
            continue
        if _eh_bullet(limpa):
            if blocos:
                blocos[-1].append(_sem_bullet(limpa))
            else:
                blocos.append([_sem_bullet(limpa)])
        elif not blocos or "|" in limpa or _PERIODO.search(limpa):
            blocos.append([limpa])                   # novo item: "Nome | tecnologias" ou com período
        elif len(blocos[-1]) > 1:
            blocos[-1][-1] = f"{blocos[-1][-1]} {limpa}"  # continuação do detalhe anterior
        else:
            blocos[-1].append(limpa)                 # primeiro detalhe sem marcador
    return blocos


def _projetos(linhas: list[str]) -> list[ProjetoLido]:
    projetos = []
    for titulo, detalhes in _itens_com_titulo(linhas):
        nome, _, techs = titulo.partition("|")
        projetos.append(ProjetoLido(
            nome=nome.strip(),
            tecnologias=[t.strip() for t in re.split(r",|/", techs) if t.strip()],
            descricao=" ".join(detalhes) or None,
        ))
    return projetos


def _experiencias(linhas: list[str]) -> list[ExperienciaLida]:
    experiencias = []
    for titulo, detalhes in _itens_com_titulo(linhas):
        periodo = None
        if m := _PERIODO.search(titulo):
            periodo = f"{m.group(1)} – {m.group(2)}"
            titulo = (titulo[: m.start()] + titulo[m.end():]).strip(" ,;-–|")
        empresa, cargo = titulo, None
        if "|" in titulo:
            empresa, _, cargo = (p.strip() for p in titulo.partition("|"))
        elif " - " in titulo:
            cargo, _, empresa = (p.strip() for p in titulo.partition(" - "))
        experiencias.append(ExperienciaLida(cargo=cargo or None, empresa=empresa or None, periodo=periodo,
                                            descricao=" ".join(detalhes) or None))
    return experiencias


def _formacoes(linhas: list[str]) -> list[FormacaoLida]:
    formacoes = []
    for titulo, detalhes in _itens_com_titulo(linhas):
        partes = [p.strip() for p in re.split(r"\s+[–—-]\s+", titulo) if p.strip()]
        curso = partes[0] if partes else None
        instituicao = partes[1] if len(partes) > 1 else None
        periodo = None
        if m := re.search(r"(previs[aã]o de conclus[aã]o|conclus[aã]o|conclu[ií]do em)\s*:?\s*([\w/ ]+)", titulo, re.IGNORECASE):
            periodo = f"{m.group(1)}: {m.group(2).strip()}"
        extras = [p for p in partes[2:]] + detalhes
        formacoes.append(FormacaoLida(curso=curso, instituicao=instituicao, periodo=periodo,
                                      observacoes=" ".join(extras) or None))
    return formacoes


def _certificacoes(linhas: list[str]) -> list[CertificacaoLida]:
    certificacoes = []
    for paragrafo in _paragrafos(linhas):
        data = None
        if m := re.search(r"\((\d{4})\)", paragrafo):
            data = m.group(1)
            paragrafo = (paragrafo[: m.start()] + paragrafo[m.end():]).strip()
        emissor, sep, nome = paragrafo.partition(" - ")
        certificacoes.append(CertificacaoLida(nome=(nome if sep else emissor).strip(),
                                              emissor=emissor.strip() if sep else None, data=data))
    return certificacoes


def _habilidades(linhas: list[str]) -> tuple[list[str], list[tuple[str, str | None]]]:
    competencias: list[str] = []
    idiomas: list[tuple[str, str | None]] = []
    for paragrafo in _paragrafos(linhas):
        categoria, sep, itens = paragrafo.partition(":")
        texto_itens = itens if sep else paragrafo
        if sep and re.match(r"idiomas?|languages?", _norm(categoria)):
            idiomas += _idiomas_de(texto_itens)
            continue
        for item in re.split(r",|\s/\s", texto_itens):
            item = item.strip().rstrip(".")
            if item and len(item) <= 40 and item not in competencias:
                competencias.append(item)
    return competencias, idiomas


def _idiomas_de(texto: str) -> list[tuple[str, str | None]]:
    idiomas = []
    for parte in re.split(r",|;|\se\s", texto):
        parte = parte.strip().rstrip(".")
        if not parte:
            continue
        m = re.match(r"([A-Za-zÀ-ÿ]+)\s*(?:\((.+?)\)|[-–:]\s*(.+))?$", parte)
        if m:
            idiomas.append((m.group(1), (m.group(2) or m.group(3) or "").strip() or None))
    return idiomas


def ler_secoes(texto: str) -> SecoesCV:
    topo, secoes = dividir_secoes(texto)
    lido = SecoesCV(nome=_nome(topo))
    lido.cidade, lido.uf = _cidade_uf(topo)
    if "objetivo" in secoes:
        lido.objetivo, lido.resumo = _objetivo_resumo(secoes["objetivo"])
    if "resumo" in secoes:
        lido.resumo = " ".join(_paragrafos(secoes["resumo"])) or lido.resumo
    if "habilidades" in secoes:
        lido.competencias, lido.idiomas = _habilidades(secoes["habilidades"])
    if "idiomas" in secoes:
        lido.idiomas += _idiomas_de(" , ".join(_paragrafos(secoes["idiomas"])))
    if "projetos" in secoes:
        lido.projetos = _projetos(secoes["projetos"])
    if "experiencia" in secoes:
        lido.experiencias = _experiencias(secoes["experiencia"])
    if "formacao" in secoes:
        lido.formacoes = _formacoes(secoes["formacao"])
    if "certificacoes" in secoes:
        lido.certificacoes = _certificacoes(secoes["certificacoes"])
    return lido
