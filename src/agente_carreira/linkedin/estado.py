"""Estado conhecido do LinkedIn, log de alterações e reauditoria (RF-LI-13 a RF-LI-15).

O agente não lê o LinkedIn por automação (RN-04). O "estado" é o que se sabe
do perfil publicado: a exportação de dados oficial (sincronização) mais cada
alteração que o usuário aprovou e confirmou ter aplicado. O log guarda data,
campo, valor anterior e novo valor de cada alteração, permitindo reverter.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

from ..arquivos import gravar_modelo, ler_modelo
from ..importadores.linkedin import abrir_exportacao
from ..models import PerfilMestre
from ..storage import diretorio_dados

ARQUIVO_ESTADO = "linkedin-estado.json"
ARQUIVO_LOG = "linkedin-log.json"
DIAS_ENTRE_AUDITORIAS = 30


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def chave_experiencia(cargo: str, empresa: str) -> str:
    return f"experiencia:{cargo} — {empresa}"


class ExperienciaPublicada(BaseModel):
    cargo: str
    empresa: str
    inicio: str | None = None  # como o LinkedIn exporta (ex.: "Jan 2022")
    fim: str | None = None


class EstadoLinkedIn(BaseModel):
    campos: dict[str, str] = Field(default_factory=dict)
    experiencias: list[ExperienciaPublicada] = Field(default_factory=list)
    sincronizado_em: datetime | None = None
    ultima_auditoria: datetime | None = None
    hash_perfil_auditado: str | None = None


class EntradaLog(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    aprovado_em: datetime = Field(default_factory=_agora)
    campo: str
    anterior: str | None = None
    novo: str
    tipo: Literal["alteracao", "reversao"] = "alteracao"
    status: Literal["aprovado", "aplicado", "revertido"] = "aprovado"
    aplicado_em: datetime | None = None
    reverte: str | None = None  # id da alteração que esta entrada desfaz
    motor: str | None = None    # RF-IA-06: motor que escreveu o texto (None = motor local)


class LogLinkedIn(BaseModel):
    entradas: list[EntradaLog] = Field(default_factory=list)


# ---------------------------------------------------------------- persistência

M = TypeVar("M", bound=BaseModel)


def _carregar(modelo: type[M], arquivo: str) -> M:
    caminho = diretorio_dados() / arquivo
    return ler_modelo(caminho, modelo)


def _salvar(obj: BaseModel, arquivo: str) -> Path:
    caminho = diretorio_dados() / arquivo
    gravar_modelo(caminho, obj)
    return caminho


def carregar_estado() -> EstadoLinkedIn:
    return _carregar(EstadoLinkedIn, ARQUIVO_ESTADO)


def salvar_estado(estado: EstadoLinkedIn) -> Path:
    return _salvar(estado, ARQUIVO_ESTADO)


def carregar_log() -> LogLinkedIn:
    return _carregar(LogLinkedIn, ARQUIVO_LOG)


def salvar_log(log: LogLinkedIn) -> Path:
    return _salvar(log, ARQUIVO_LOG)


# ---------------------------------------------------------------- RF-LI-13 / RF-LI-14

def buscar(log: LogLinkedIn, id_: str) -> EntradaLog:
    for entrada in log.entradas:
        if entrada.id == id_:
            return entrada
    raise ValueError(f"Entrada {id_!r} não existe no log.")


def registrar_aprovacao(
    log: LogLinkedIn,
    campo: str,
    anterior: str | None,
    novo: str,
    tipo: Literal["alteracao", "reversao"] = "alteracao",
    reverte: str | None = None,
    motor: str | None = None,
) -> EntradaLog:
    entrada = EntradaLog(campo=campo, anterior=anterior, novo=novo, tipo=tipo, reverte=reverte, motor=motor)
    log.entradas.append(entrada)
    return entrada


def marcar_aplicado(log: LogLinkedIn, estado: EstadoLinkedIn, id_: str) -> EntradaLog:
    """O usuário confirmou que colou e salvou o valor no LinkedIn."""
    entrada = buscar(log, id_)
    if entrada.status != "aprovado":
        raise ValueError(f"A entrada {id_} está '{entrada.status}'; só entradas aprovadas podem ser marcadas como aplicadas.")
    entrada.status = "aplicado"
    entrada.aplicado_em = _agora()
    estado.campos[entrada.campo] = entrada.novo
    if entrada.reverte:
        buscar(log, entrada.reverte).status = "revertido"
    return entrada


def preparar_reversao(log: LogLinkedIn, id_: str) -> EntradaLog:
    """Cria a alteração inversa (novo → anterior), já aprovada, aguardando aplicação."""
    original = buscar(log, id_)
    if original.status != "aplicado":
        raise ValueError("Só alterações aplicadas podem ser revertidas.")
    if any(e.reverte == original.id and e.status == "aprovado" for e in log.entradas):
        raise ValueError("Já existe uma reversão aprovada aguardando aplicação para esta alteração.")
    return registrar_aprovacao(
        log, original.campo, original.novo, original.anterior or "", tipo="reversao", reverte=original.id
    )


def pendentes_de_aplicacao(log: LogLinkedIn) -> list[EntradaLog]:
    return [e for e in log.entradas if e.status == "aprovado"]


# ---------------------------------------------------------------- sincronização

def sincronizar_exportacao(estado: EstadoLinkedIn, caminho: Path) -> list[str]:
    """Atualiza o estado conhecido a partir da exportação oficial de dados do LinkedIn."""
    tabelas = abrir_exportacao(caminho)
    lidos: list[str] = []

    perfil_li = (tabelas.get("profile.csv") or [{}])[0]
    for coluna, campo in (("Headline", "titulo"), ("Summary", "sobre"), ("Geo Location", "localizacao")):
        if valor := perfil_li.get(coluna):
            estado.campos[campo] = valor
            lidos.append(campo)

    posicoes = tabelas.get("positions.csv", [])
    if posicoes:
        estado.experiencias = []
        for pos in posicoes:
            cargo, empresa = pos.get("Title", ""), pos.get("Company Name", "")
            if not cargo or not empresa:
                continue
            estado.experiencias.append(ExperienciaPublicada(
                cargo=cargo, empresa=empresa,
                inicio=pos.get("Started On") or None, fim=pos.get("Finished On") or None,
            ))
            chave = chave_experiencia(cargo, empresa)
            estado.campos[chave] = pos.get("Description", "")
            lidos.append(chave)

    competencias = [s["Name"] for s in tabelas.get("skills.csv", []) if s.get("Name")]
    if competencias:
        estado.campos["competencias"] = ", ".join(competencias)
        lidos.append("competencias")

    estado.sincronizado_em = _agora()
    return lidos


# ---------------------------------------------------------------- RF-LI-15

MESES = {
    "jan": 1, "feb": 2, "fev": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "mai": 5,
    "jun": 6, "jul": 7, "aug": 8, "ago": 8, "sep": 9, "set": 9, "oct": 10, "out": 10,
    "nov": 11, "dec": 12, "dez": 12,
}


def mes_ano(texto: str | None) -> tuple[int, int | None] | None:
    """Converte datas do LinkedIn ("Jan 2022", "01/2022", "2022") em (ano, mês)."""
    t = _norm(texto or "")
    if not t:
        return None
    if m := re.fullmatch(r"([a-z]{3})[a-z]*\.?\s+(?:de\s+)?(\d{4})", t):
        mes = MESES.get(m.group(1))
        return (int(m.group(2)), mes) if mes else None
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", t):
        return int(m.group(2)), int(m.group(1))
    if m := re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-\d{2})?", t):
        return int(m.group(1)), int(m.group(2)) if m.group(2) else None
    return None


def _mesma_data(d: date, publicada: tuple[int, int | None] | None) -> bool:
    if publicada is None:
        return False
    ano, mes = publicada
    return d.year == ano and (mes is None or d.month == mes)


def _fmt(d: date) -> str:
    return f"{d.month:02d}/{d.year}"


def hash_perfil(perfil: PerfilMestre) -> str:
    conteudo = perfil.model_dump_json(exclude={"atualizado_em"})
    return hashlib.sha1(conteudo.encode("utf-8")).hexdigest()[:12]


def reauditoria_pendente(estado: EstadoLinkedIn, perfil: PerfilMestre, agora: datetime | None = None) -> str | None:
    agora = agora or _agora()
    if estado.ultima_auditoria is None:
        return "o perfil do LinkedIn ainda não foi auditado"
    dias = (agora - estado.ultima_auditoria).days
    if dias > DIAS_ENTRE_AUDITORIAS:
        return f"última auditoria há {dias} dias (limite: {DIAS_ENTRE_AUDITORIAS})"
    if estado.hash_perfil_auditado != hash_perfil(perfil):
        return "o perfil-mestre mudou desde a última auditoria"
    return None


def registrar_auditoria(estado: EstadoLinkedIn, perfil: PerfilMestre, agora: datetime | None = None) -> None:
    estado.ultima_auditoria = agora or _agora()
    estado.hash_perfil_auditado = hash_perfil(perfil)


class Divergencia(BaseModel):
    tipo: str
    mensagem: str


def divergencias(estado: EstadoLinkedIn, perfil: PerfilMestre) -> list[Divergencia]:
    """Divergências entre o LinkedIn conhecido e o CV (perfil-mestre)."""
    achados: list[Divergencia] = []

    if not estado.experiencias:
        if perfil.experiencias:
            achados.append(Divergencia(
                tipo="sem-dados",
                mensagem="Sem experiências do LinkedIn para comparar — sincronize com 'agente li sincronizar <exportação.zip>'.",
            ))
    else:
        publicadas = {(_norm(e.cargo), _norm(e.empresa)): e for e in estado.experiencias}
        vistas: set[tuple[str, str]] = set()
        for exp in perfil.experiencias:
            chave = (_norm(exp.cargo), _norm(exp.empresa))
            rotulo = f"{exp.cargo} — {exp.empresa}"
            li = publicadas.get(chave)
            if li is None:
                achados.append(Divergencia(tipo="falta-no-linkedin", mensagem=f"{rotulo}: está no CV mas não no LinkedIn."))
                continue
            vistas.add(chave)
            if not _mesma_data(exp.periodo.inicio, mes_ano(li.inicio)):
                achados.append(Divergencia(
                    tipo="inicio-diferente",
                    mensagem=f"{rotulo}: início no CV {_fmt(exp.periodo.inicio)} × LinkedIn {li.inicio or 'vazio'}.",
                ))
            if exp.periodo.fim is None:
                if li.fim:
                    achados.append(Divergencia(
                        tipo="fim-diferente",
                        mensagem=f"{rotulo}: atual no CV × encerrado em {li.fim} no LinkedIn.",
                    ))
            elif not _mesma_data(exp.periodo.fim, mes_ano(li.fim)):
                achados.append(Divergencia(
                    tipo="fim-diferente",
                    mensagem=f"{rotulo}: fim no CV {_fmt(exp.periodo.fim)} × LinkedIn {li.fim or 'atual'}.",
                ))
        for chave, li in publicadas.items():
            if chave not in vistas:
                achados.append(Divergencia(
                    tipo="falta-no-cv",
                    mensagem=f"{li.cargo} — {li.empresa}: está no LinkedIn mas não no perfil-mestre "
                             "(RN-06: a correção começa no perfil-mestre).",
                ))

    local = estado.campos.get("localizacao")
    if local and perfil.contato.cidade and _norm(perfil.contato.cidade) not in _norm(local):
        achados.append(Divergencia(
            tipo="localizacao",
            mensagem=f"Localização: CV {perfil.contato.cidade} × LinkedIn {local}.",
        ))
    return achados
