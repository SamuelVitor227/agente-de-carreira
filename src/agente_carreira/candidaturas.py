"""Candidaturas e funil (RF-CV-14, RF-CA-06, RF-AC-01, RF-AC-06).

Cada candidatura avança etapa por etapa — Encontrada, Selecionada, Aplicada,
Em análise, Teste técnico (se houver), Entrevista RH, Entrevista técnica,
Proposta, Contratado — e pode sair em qualquer uma: Reprovado, Desistência ou
Vaga encerrada. Cada mudança fica registrada com a data (RF-AC-01), e saídas
por reprovação ou desistência guardam o motivo (RF-AC-06).
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .storage import diretorio_dados

ARQUIVO_CANDIDATURAS = "candidaturas.json"
DIR_CVS_ENVIADOS = "candidaturas"


class Etapa(str, Enum):
    ENCONTRADA = "encontrada"
    SELECIONADA = "selecionada"
    APLICADA = "aplicada"
    EM_ANALISE = "em_analise"
    TESTE_TECNICO = "teste_tecnico"
    ENTREVISTA_RH = "entrevista_rh"
    ENTREVISTA_TECNICA = "entrevista_tecnica"
    PROPOSTA = "proposta"
    CONTRATADO = "contratado"
    REPROVADO = "reprovado"
    DESISTENCIA = "desistencia"
    VAGA_ENCERRADA = "vaga_encerrada"
    # Nomes antigos (antes do funil completo), mantidos como sinônimos.
    PREPARADA = "selecionada"
    ENVIADA = "aplicada"
    RETORNO = "em_analise"
    ENTREVISTA = "entrevista_rh"
    RECUSADA = "reprovado"
    SEM_RESPOSTA = "aplicada"


StatusCandidatura = Etapa  # compatibilidade

ORDEM = [
    Etapa.ENCONTRADA, Etapa.SELECIONADA, Etapa.APLICADA, Etapa.EM_ANALISE, Etapa.TESTE_TECNICO,
    Etapa.ENTREVISTA_RH, Etapa.ENTREVISTA_TECNICA, Etapa.PROPOSTA, Etapa.CONTRATADO,
]
SAIDAS = {Etapa.REPROVADO, Etapa.DESISTENCIA, Etapa.VAGA_ENCERRADA}
FINAIS = SAIDAS | {Etapa.CONTRATADO}
ETAPAS_COM_DATA = {Etapa.TESTE_TECNICO, Etapa.ENTREVISTA_RH, Etapa.ENTREVISTA_TECNICA}
NOMES_ETAPA = {
    Etapa.ENCONTRADA: "Encontrada", Etapa.SELECIONADA: "Selecionada", Etapa.APLICADA: "Aplicada",
    Etapa.EM_ANALISE: "Em análise", Etapa.TESTE_TECNICO: "Teste técnico", Etapa.ENTREVISTA_RH: "Entrevista RH",
    Etapa.ENTREVISTA_TECNICA: "Entrevista técnica", Etapa.PROPOSTA: "Proposta", Etapa.CONTRATADO: "Contratado",
    Etapa.REPROVADO: "Reprovado", Etapa.DESISTENCIA: "Desistência", Etapa.VAGA_ENCERRADA: "Vaga encerrada",
}

# Etapas que contam como retorno da empresa no desempenho por variante (RF-CV-10).
STATUS_DE_RETORNO = {
    Etapa.EM_ANALISE, Etapa.TESTE_TECNICO, Etapa.ENTREVISTA_RH, Etapa.ENTREVISTA_TECNICA, Etapa.PROPOSTA, Etapa.CONTRATADO,
}

# RF-AC-06: motivos que alimentam os relatórios (M7).
MOTIVOS_SAIDA = {
    Etapa.REPROVADO: ["perfil técnico", "experiência", "inglês", "salário", "localização ou modelo", "sem retorno", "outro"],
    Etapa.DESISTENCIA: ["outra proposta", "salário", "processo longo", "modelo de trabalho", "empresa", "outro"],
    Etapa.VAGA_ENCERRADA: ["vaga encerrada", "vaga congelada", "outro"],
}

_LEGADO = {"preparada": "selecionada", "enviada": "aplicada", "retorno": "em_analise", "entrevista": "entrevista_rh",
           "recusada": "reprovado", "sem_resposta": "aplicada"}


def _converter_legado(valor):
    return _LEGADO.get(valor, valor) if isinstance(valor, str) else valor


class MudancaStatus(BaseModel):
    quando: datetime
    de: Etapa
    para: Etapa
    motivo: str | None = None

    @field_validator("de", "para", mode="before")
    @classmethod
    def _legado(cls, valor):
        return _converter_legado(valor)


class Candidatura(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    vaga_id: str | None = None
    vaga_titulo: str
    empresa: str | None = None
    foco: str
    variante: str  # nome da variante usada (ex.: cv-backend-dotnet-pt)
    idioma: str = "pt"
    criada_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Etapa = Etapa.SELECIONADA
    historico: list[MudancaStatus] = Field(default_factory=list)
    cv_enviado: list[str] = Field(default_factory=list)  # RF-CV-14: cópias guardadas
    # M5
    vaga_link: str | None = None
    plataforma: str | None = None
    nota_aderencia: int | None = None
    kit_dir: str | None = None                            # RF-CA-06: vaga, CV, mensagem e respostas enviados
    enviada_em: datetime | None = None
    # M6
    motivo_saida: str | None = None                       # RF-AC-06
    detalhe_saida: str | None = None
    proxima_etapa_em: datetime | None = None
    contatos: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _legado(cls, valor):
        return _converter_legado(valor)

    @property
    def encerrada(self) -> bool:
        return self.status in FINAIS

    def mudar_status(self, novo: Etapa, motivo: str | None = None, detalhe: str | None = None,
                     quando: datetime | None = None) -> None:
        """Avança no funil (sem voltar etapa) ou sai dele; registra a data de cada mudança (RF-AC-01)."""
        novo = Etapa(_converter_legado(novo.value if isinstance(novo, Etapa) else novo))
        if self.status in FINAIS:
            raise ValueError(f"A candidatura já foi encerrada ({NOMES_ETAPA[self.status]}).")
        if novo not in SAIDAS and ORDEM.index(novo) <= ORDEM.index(self.status):
            raise ValueError(f"O funil não volta: de {NOMES_ETAPA[self.status]} não dá para ir para {NOMES_ETAPA[novo]}.")
        agora = datetime.now(timezone.utc)
        self.historico.append(MudancaStatus(quando=agora, de=self.status, para=novo, motivo=motivo))
        self.status = novo
        if novo == Etapa.APLICADA and self.enviada_em is None:
            self.enviada_em = agora
        if novo in SAIDAS:
            self.motivo_saida, self.detalhe_saida = motivo, detalhe
        self.proxima_etapa_em = quando if novo in ETAPAS_COM_DATA else None


class Candidaturas(BaseModel):
    itens: list[Candidatura] = Field(default_factory=list)

    def buscar(self, id_: str) -> Candidatura:
        for c in self.itens:
            if c.id == id_:
                return c
        raise ValueError(f"Candidatura {id_!r} não existe.")


def caminho_candidaturas() -> Path:
    return diretorio_dados() / ARQUIVO_CANDIDATURAS


def carregar_candidaturas() -> Candidaturas:
    caminho = caminho_candidaturas()
    if not caminho.is_file():
        return Candidaturas()
    return Candidaturas.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_candidaturas(colecao: Candidaturas) -> Path:
    caminho = caminho_candidaturas()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(colecao.model_dump_json(indent=2), encoding="utf-8")
    return caminho


def pasta_candidatura(candidatura: Candidatura) -> Path:
    destino = diretorio_dados() / DIR_CVS_ENVIADOS / candidatura.id
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def guardar_cv_enviado(candidatura: Candidatura, arquivos: list[Path]) -> list[Path]:
    """RF-CV-14: copia os arquivos de CV enviados para a pasta da candidatura."""
    destino_dir = pasta_candidatura(candidatura)
    guardados: list[Path] = []
    for arquivo in arquivos:
        destino = destino_dir / arquivo.name
        if arquivo.resolve() != destino.resolve():
            shutil.copy2(arquivo, destino)
        candidatura.cv_enviado.append(str(destino))
        guardados.append(destino)
    return guardados
