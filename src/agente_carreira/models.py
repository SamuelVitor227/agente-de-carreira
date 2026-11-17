"""Modelos do perfil-mestre.

Cobre os requisitos:
- RF-PM-01: perfil-mestre estruturado (contato, objetivo, resumo, experiências,
  formação, certificações, projetos, competências, idiomas e links).
- RF-PM-03: experiência com cargo, empresa, vínculo, período, local, modelo de
  trabalho, responsabilidades, conquistas e tecnologias.
- RF-PM-04: banco de conquistas reutilizáveis (verbo de ação, resultado,
  tecnologias, competências e evidência).
- RF-PM-05: experiências fora de TI e projetos acadêmicos, com competências
  transferíveis.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


class Vinculo(str, Enum):
    CLT = "clt"
    ESTAGIO = "estagio"
    TRAINEE = "trainee"
    PJ = "pj"
    FREELANCE = "freelance"
    VOLUNTARIO = "voluntario"
    PROJETO_ACADEMICO = "projeto_academico"
    OUTRO = "outro"


class ModeloTrabalho(str, Enum):
    PRESENCIAL = "presencial"
    HIBRIDO = "hibrido"
    REMOTO = "remoto"


class Area(str, Enum):
    TI = "ti"
    FORA_DE_TI = "fora_de_ti"


class Periodo(BaseModel):
    inicio: date
    fim: date | None = None  # None = atual

    @model_validator(mode="after")
    def _fim_depois_do_inicio(self) -> "Periodo":
        if self.fim is not None and self.fim < self.inicio:
            raise ValueError("fim do período não pode ser anterior ao início")
        return self

    @property
    def atual(self) -> bool:
        return self.fim is None


class Contato(BaseModel):
    nome: str = Field(min_length=1)
    email: str
    telefone: str | None = None
    cidade: str | None = None
    uf: str | None = None
    pais: str = "Brasil"

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError(f"e-mail inválido: {v!r}")
        return v


class Links(BaseModel):
    github: str | None = None
    linkedin: str | None = None
    portfolio: str | None = None
    credenciais: list[str] = Field(default_factory=list)
    outros: list[str] = Field(default_factory=list)


class Conquista(BaseModel):
    """RF-PM-04 — conquista reutilizável do banco de conquistas."""

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    verbo_acao: str = Field(min_length=1, description="Verbo de ação que abre a conquista (ex.: 'Reduzi')")
    descricao: str = Field(min_length=1)
    resultado: str | None = Field(default=None, description="Resultado obtido, em texto")
    numero: str | None = Field(default=None, description="Número que quantifica o resultado, quando houver (ex.: '30%')")
    tecnologias: list[str] = Field(default_factory=list)
    competencias: list[str] = Field(default_factory=list)
    evidencia: str | None = Field(default=None, description="O que sustenta a conquista (link, documento, pessoa)")

    @field_validator("verbo_acao")
    @classmethod
    def _verbo_simples(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("verbo de ação é obrigatório")
        return v


class Experiencia(BaseModel):
    """RF-PM-03 e RF-PM-05 — experiência profissional, fora de TI ou projeto acadêmico."""

    cargo: str = Field(min_length=1)
    empresa: str = Field(min_length=1)
    vinculo: Vinculo
    periodo: Periodo
    local: str | None = None
    modelo_trabalho: ModeloTrabalho | None = None
    area: Area = Area.TI
    responsabilidades: list[str] = Field(default_factory=list)
    conquista_ids: list[str] = Field(default_factory=list, description="Referências ao banco de conquistas")
    tecnologias: list[str] = Field(default_factory=list)
    competencias_transferiveis: list[str] = Field(
        default_factory=list,
        description="RF-PM-05: competências transferíveis (ex.: atendimento, compras e estoque, escala de equipe)",
    )


class Formacao(BaseModel):
    curso: str
    instituicao: str
    nivel: str | None = None  # ex.: graduação, técnico, pós
    inicio: date | None = None
    conclusao: date | None = None
    conclusao_prevista: str | None = None  # ex.: "2026/2"
    status: str | None = None  # cursando, concluído, trancado


class Certificacao(BaseModel):
    nome: str
    emissor: str | None = None
    data: date | None = None
    id_credencial: str | None = None
    url_credencial: str | None = None


class Projeto(BaseModel):
    nome: str
    descricao: str | None = None
    tipo: str = "pessoal"  # pessoal, academico, profissional
    tecnologias: list[str] = Field(default_factory=list)
    url: str | None = None
    conquista_ids: list[str] = Field(default_factory=list)
    competencias_transferiveis: list[str] = Field(default_factory=list)


class Idioma(BaseModel):
    idioma: str
    nivel: str  # ex.: básico, intermediário, avançado, fluente, nativo


class ExperienciaRascunho(BaseModel):
    """Experiência extraída na importação (RF-PM-02), pendente de confirmação e completude."""

    cargo: str | None = None
    empresa: str | None = None
    periodo_texto: str | None = None
    local: str | None = None
    descricao: str | None = None
    origem: str | None = None


class FormacaoRascunho(BaseModel):
    curso: str | None = None
    instituicao: str | None = None
    periodo_texto: str | None = None
    observacoes: str | None = None
    origem: str | None = None


class Rascunhos(BaseModel):
    """Itens importados ainda não convertidos em registros definitivos (RN-02)."""

    experiencias: list[ExperienciaRascunho] = Field(default_factory=list)
    formacoes: list[FormacaoRascunho] = Field(default_factory=list)


class PerfilMestre(BaseModel):
    """RF-PM-01 — base única e versionada dos dados de carreira."""

    contato: Contato
    objetivo: str | None = None
    resumo: str | None = None
    experiencias: list[Experiencia] = Field(default_factory=list)
    formacao: list[Formacao] = Field(default_factory=list)
    certificacoes: list[Certificacao] = Field(default_factory=list)
    projetos: list[Projeto] = Field(default_factory=list)
    competencias_tecnicas: list[str] = Field(default_factory=list)
    competencias_comportamentais: list[str] = Field(default_factory=list)
    idiomas: list[Idioma] = Field(default_factory=list)
    links: Links = Field(default_factory=Links)
    banco_conquistas: list[Conquista] = Field(default_factory=list)
    rascunhos: Rascunhos = Field(default_factory=Rascunhos)
    atualizado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _referencias_de_conquistas_existem(self) -> "PerfilMestre":
        ids = {c.id for c in self.banco_conquistas}
        for exp in self.experiencias:
            for cid in exp.conquista_ids:
                if cid not in ids:
                    raise ValueError(
                        f"experiência {exp.cargo!r} referencia conquista inexistente: {cid!r}"
                    )
        for proj in self.projetos:
            for cid in proj.conquista_ids:
                if cid not in ids:
                    raise ValueError(
                        f"projeto {proj.nome!r} referencia conquista inexistente: {cid!r}"
                    )
        return self

    def tocar(self) -> None:
        """Atualiza o carimbo de modificação."""
        self.atualizado_em = datetime.now(timezone.utc)
