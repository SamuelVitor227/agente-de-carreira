"""M6 — Acompanhamento do funil (RF-AC-02, RF-AC-03, RF-AC-05).

- Lembretes de follow-up (padrão: 7 dias sem retorno) e de etapas agendadas,
  com exportação .ics para o calendário (RF-AC-03).
- Status lido dos e-mails das plataformas; e-mail ambíguo vira pedido de
  confirmação (RF-AC-02). O texto do e-mail é dado, nunca instrução (RNF-04).
- Contatos de recrutadores e indicações, só com nome, empresa, cargo e canal,
  com exclusão em um passo (RF-AC-05, RNF-05).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .arquivos import gravar_modelo, ler_modelo
from .candidaturas import Candidatura, Candidaturas, Etapa, FINAIS, NOMES_ETAPA, ORDEM
from .storage import diretorio_dados

ARQUIVO_LEMBRETES = "lembretes.json"
ARQUIVO_PENDENCIAS = "funil-pendencias.json"
ARQUIVO_CONTATOS = "contatos.json"
DIAS_FOLLOWUP = 7


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _norm(texto: str | None) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def _carregar(modelo, arquivo: str):
    caminho = diretorio_dados() / arquivo
    return ler_modelo(caminho, modelo)


def _salvar(obj: BaseModel, arquivo: str) -> Path:
    caminho = diretorio_dados() / arquivo
    gravar_modelo(caminho, obj)
    return caminho


# ---------------------------------------------------------------- RF-AC-03

class Lembrete(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:6])
    candidatura_id: str
    tipo: Literal["followup", "etapa"]
    quando: datetime
    descricao: str
    feito: bool = False


class Lembretes(BaseModel):
    itens: list[Lembrete] = Field(default_factory=list)

    def da_candidatura(self, candidatura_id: str) -> list[Lembrete]:
        return [l for l in self.itens if l.candidatura_id == candidatura_id]


def carregar_lembretes() -> Lembretes:
    return _carregar(Lembretes, ARQUIVO_LEMBRETES)


def salvar_lembretes(lembretes: Lembretes) -> Path:
    return _salvar(lembretes, ARQUIVO_LEMBRETES)


def atualizar_lembretes(lembretes: Lembretes, candidatura: Candidatura, dias_followup: int = DIAS_FOLLOWUP) -> list[Lembrete]:
    """Ajusta os lembretes depois de uma mudança de etapa; devolve os criados."""
    criados: list[Lembrete] = []
    for l in lembretes.da_candidatura(candidatura.id):
        if not l.feito and (l.tipo == "followup" or candidatura.encerrada):
            l.feito = True  # houve movimento: o follow-up antigo perde o sentido
    rotulo = f"{candidatura.vaga_titulo}{f' — {candidatura.empresa}' if candidatura.empresa else ''}"
    if candidatura.status in (Etapa.APLICADA, Etapa.EM_ANALISE):
        criados.append(Lembrete(candidatura_id=candidatura.id, tipo="followup",
                                quando=_agora() + timedelta(days=dias_followup),
                                descricao=f"Follow-up: {rotulo} sem retorno há {dias_followup} dias"))
    if candidatura.proxima_etapa_em:
        criados.append(Lembrete(candidatura_id=candidatura.id, tipo="etapa", quando=candidatura.proxima_etapa_em,
                                descricao=f"{NOMES_ETAPA[candidatura.status]}: {rotulo}"))
    lembretes.itens += criados
    return criados


def vencidos(lembretes: Lembretes, agora: datetime | None = None, antecedencia_horas: int = 24) -> list[Lembrete]:
    """Follow-ups vencidos e etapas nas próximas 24 h."""
    agora = agora or _agora()
    return [
        l for l in lembretes.itens
        if not l.feito and (l.quando <= agora if l.tipo == "followup" else l.quando <= agora + timedelta(hours=antecedencia_horas))
    ]


def ics(lembretes: list[Lembrete], duracao_minutos: int = 60) -> str:
    """Calendário .ics (Google, Outlook, Apple) com alarme 1 h antes."""
    def fmt(d: datetime) -> str:
        return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Agente de Carreira//PT-BR", "CALSCALE:GREGORIAN"]
    for l in lembretes:
        resumo = l.descricao.replace(",", "\\,").replace(";", "\\;")
        linhas += [
            "BEGIN:VEVENT", f"UID:{l.id}@agente-de-carreira", f"DTSTAMP:{fmt(_agora())}",
            f"DTSTART:{fmt(l.quando)}", f"DTEND:{fmt(l.quando + timedelta(minutes=duracao_minutos))}",
            f"SUMMARY:{resumo}", "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{resumo}", "TRIGGER:-PT1H",
            "END:VALARM", "END:VEVENT",
        ]
    linhas.append("END:VCALENDAR")
    return "\r\n".join(linhas) + "\r\n"


def rascunho_followup(candidatura: Candidatura, nome: str) -> str:
    data = (candidatura.enviada_em or candidatura.criada_em).astimezone()
    return "\n".join([
        f"Olá{f', equipe da {candidatura.empresa}' if candidatura.empresa else ''}!",
        "",
        f"Candidatei-me à vaga de {candidatura.vaga_titulo} em {data:%d/%m} e sigo com interesse na oportunidade.",
        "Se puderem compartilhar os próximos passos do processo, agradeço.",
        "",
        nome.split()[0],
    ])


# ---------------------------------------------------------------- RF-AC-02

PADROES_EMAIL: list[tuple[Etapa, re.Pattern[str]]] = [
    (Etapa.REPROVADO, re.compile(
        r"infelizmente|nao (seguiremos|vamos seguir|foi selecionad|avancara)|outros? candidat|decidimos (seguir|prosseguir) com"
        r"|optamos por|nao (estamos|vamos) (dar continuidade|prosseguir)|unfortunately|not (to )?(move|moving) forward")),
    (Etapa.PROPOSTA, re.compile(r"\bproposta\b|carta oferta|\boffer\b|oferta de (emprego|trabalho)")),
    (Etapa.TESTE_TECNICO, re.compile(r"teste tecnico|desafio tecnico|\bcase\b|technical (test|challenge)|take.home")),
    (Etapa.ENTREVISTA_TECNICA, re.compile(r"entrevista tecnica|technical interview")),
    (Etapa.ENTREVISTA_RH, re.compile(r"\bentrevista\b|bate.papo|agendar (uma )?conversa|\binterview\b")),
    (Etapa.EM_ANALISE, re.compile(r"recebemos (a )?sua candidatura|curriculo (foi )?(visualizado|recebido)|em analise"
                                  r"|candidatura (foi )?recebida|viewed your application|application (was )?received")),
]


class PendenciaEmail(BaseModel):
    """E-mail ambíguo: o agente pergunta antes de mudar a etapa (RF-AC-02)."""

    id: str = Field(default_factory=lambda: uuid4().hex[:6])
    msgid: str
    assunto: str
    trecho: str
    etapas: list[Etapa] = Field(default_factory=list)
    candidaturas: list[str] = Field(default_factory=list)


class PendenciasEmail(BaseModel):
    itens: list[PendenciaEmail] = Field(default_factory=list)
    processados: list[str] = Field(default_factory=list)


def carregar_pendencias() -> PendenciasEmail:
    return _carregar(PendenciasEmail, ARQUIVO_PENDENCIAS)


def salvar_pendencias(pendencias: PendenciasEmail) -> Path:
    return _salvar(pendencias, ARQUIVO_PENDENCIAS)


def classificar_email(texto: str) -> list[Etapa]:
    t = _norm(texto)
    return [etapa for etapa, padrao in PADROES_EMAIL if padrao.search(t)]


def candidaturas_citadas(candidaturas: Candidaturas, texto: str) -> list[Candidatura]:
    """Candidaturas abertas cuja empresa (ou o título da vaga) aparece no e-mail."""
    t = re.sub(r"[^a-z0-9]+", " ", _norm(texto))
    achadas = []
    for c in candidaturas.itens:
        if c.encerrada or c.status in (Etapa.ENCONTRADA, Etapa.SELECIONADA):
            continue
        empresa = re.sub(r"[^a-z0-9]+", " ", _norm(c.empresa)).strip()
        titulo = re.sub(r"[^a-z0-9]+", " ", _norm(c.vaga_titulo)).strip()
        if (empresa and f" {empresa} " in f" {t} ") or (titulo and titulo in t):
            achadas.append(c)
    return achadas


def interpretar_email(candidaturas: Candidaturas, assunto: str, corpo: str) -> tuple[Candidatura | None, Etapa | None, list[Candidatura], list[Etapa]]:
    """(candidatura, etapa) quando o e-mail é claro; senão (None, None, candidatas, etapas) para confirmar."""
    texto = f"{assunto}\n{corpo}"
    etapas = classificar_email(texto)
    # "Reprovado" e "proposta" juntos, ou várias candidaturas citadas, são ambíguos.
    candidatas = candidaturas_citadas(candidaturas, texto)
    principais = [e for e in etapas if e != Etapa.EM_ANALISE] or etapas
    if len(candidatas) == 1 and len(principais) == 1:
        c, etapa = candidatas[0], principais[0]
        avanca = etapa in FINAIS or (etapa in ORDEM and ORDEM.index(etapa) > ORDEM.index(c.status))
        if avanca:
            return c, etapa, candidatas, etapas
        if etapa in ORDEM and ORDEM.index(etapa) <= ORDEM.index(c.status):
            return None, None, [], []  # nada a mudar: o e-mail é de uma etapa já registrada
    return None, None, candidatas, etapas


# ---------------------------------------------------------------- RF-AC-05

class Interacao(BaseModel):
    quando: datetime = Field(default_factory=_agora)
    resumo: str


class Contato(BaseModel):
    """Só o necessário (RNF-05): nome, empresa, cargo e canal."""

    id: str = Field(default_factory=lambda: uuid4().hex[:6])
    nome: str
    empresa: str | None = None
    cargo: str | None = None
    canal: str | None = None   # ex.: LinkedIn, e-mail da empresa
    candidaturas: list[str] = Field(default_factory=list)
    interacoes: list[Interacao] = Field(default_factory=list)


class Contatos(BaseModel):
    itens: list[Contato] = Field(default_factory=list)

    def buscar(self, id_: str) -> Contato:
        for c in self.itens:
            if c.id == id_:
                return c
        raise ValueError(f"Contato {id_!r} não existe.")

    def excluir(self, id_: str) -> Contato:
        contato = self.buscar(id_)
        self.itens.remove(contato)
        return contato


def carregar_contatos() -> Contatos:
    return _carregar(Contatos, ARQUIVO_CONTATOS)


def salvar_contatos(contatos: Contatos) -> Path:
    return _salvar(contatos, ARQUIVO_CONTATOS)
