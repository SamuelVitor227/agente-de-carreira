"""Resultado estruturado de uma importação (RF-PM-02)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import ExperienciaRascunho, FormacaoRascunho


class CertificacaoRascunho(BaseModel):
    nome: str
    emissor: str | None = None
    data_texto: str | None = None
    url: str | None = None


class IdiomaRascunho(BaseModel):
    idioma: str
    nivel: str | None = None


class ResultadoImportacao(BaseModel):
    """Tudo o que foi extraído de uma fonte, para exibição e confirmação."""

    origem: str
    nome: str | None = None
    email: str | None = None
    telefone: str | None = None
    github: str | None = None
    linkedin: str | None = None
    outros_links: list[str] = Field(default_factory=list)
    resumo: str | None = None
    competencias: list[str] = Field(default_factory=list)
    idiomas: list[IdiomaRascunho] = Field(default_factory=list)
    experiencias: list[ExperienciaRascunho] = Field(default_factory=list)
    formacoes: list[FormacaoRascunho] = Field(default_factory=list)
    certificacoes: list[CertificacaoRascunho] = Field(default_factory=list)
    texto_bruto: str | None = None

    def vazio(self) -> bool:
        return not any(
            [
                self.nome,
                self.email,
                self.telefone,
                self.github,
                self.linkedin,
                self.outros_links,
                self.resumo,
                self.competencias,
                self.idiomas,
                self.experiencias,
                self.formacoes,
                self.certificacoes,
                self.texto_bruto,
            ]
        )
