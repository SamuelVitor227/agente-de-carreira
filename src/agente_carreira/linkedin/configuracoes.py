"""Pacotes de configuração do LinkedIn (RF-LI-06 a RF-LI-09), em copiloto.

O agente prepara os valores e o passo a passo; o usuário aplica na própria
sessão. Pacotes ficam salvos em data/ para consulta e para a auditoria.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..arquivos import gravar_modelo
from ..models import PerfilMestre
from ..storage import diretorio_dados
from .limites import LIMITES

ARQUIVO_OPEN_TO_WORK = "linkedin-open-to-work.json"
ARQUIVO_ALERTAS = "linkedin-alertas.json"

# Cargos de busca por foco (termos de pesquisa, não afirmações de CV).
CARGOS_POR_FOCO: dict[str, list[str]] = {
    "backend-dotnet": ["Desenvolvedor Backend Júnior", "Desenvolvedor .NET", "Estagiário de Desenvolvimento"],
    "cloud-aws": ["Estagiário de Cloud", "Analista de Cloud Júnior"],
    "mobile": ["Desenvolvedor Mobile Júnior", "Desenvolvedor React Native"],
    "dados": ["Estagiário de Dados", "Analista de Dados Júnior"],
    "suporte": ["Analista de Suporte Júnior", "Estagiário de Suporte de TI"],
}


# ---------------------------------------------------------------- RF-LI-06

class PacoteOpenToWork(BaseModel):
    cargos: list[str]
    tipos_de_local: list[str] = Field(default_factory=lambda: ["presencial", "híbrido", "remoto"])
    localidades: list[str]
    inicio: Literal["imediato", "flexivel"] = "imediato"
    tipos_de_vaga: list[str] = Field(default_factory=lambda: ["estágio", "tempo integral"])
    visibilidade: Literal["so_recrutadores", "todos_os_membros", "decidir_ao_aplicar"] = "decidir_ao_aplicar"
    gerado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("cargos")
    @classmethod
    def _ate_cinco(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("informe ao menos um cargo")
        if len(v) > LIMITES["open_to_work_cargos"]:
            raise ValueError(f"o Open to Work aceita até {LIMITES['open_to_work_cargos']} cargos")
        return v


def montar_open_to_work(perfil: PerfilMestre, cargos: list[str], visibilidade: str) -> PacoteOpenToWork:
    cidade = ", ".join(p for p in [perfil.contato.cidade, perfil.contato.uf] if p)
    localidades = [loc for loc in [cidade or None, f"{perfil.contato.pais} (remoto)"] if loc]
    return PacoteOpenToWork(cargos=cargos, localidades=localidades, visibilidade=visibilidade)  # type: ignore[arg-type]


def passos_open_to_work(pacote: PacoteOpenToWork) -> list[str]:
    visibilidade = {
        "so_recrutadores": "Somente recrutadores",
        "todos_os_membros": "Todos os membros do LinkedIn (adiciona a moldura verde #OpenToWork à foto)",
        "decidir_ao_aplicar": "decida na hora: só recrutadores, ou todos (moldura verde na foto)",
    }[pacote.visibilidade]
    return [
        "No LinkedIn: foto de perfil > Disponível para > Encontrar um novo emprego.",
        f"Cargos ({len(pacote.cargos)} de {LIMITES['open_to_work_cargos']}): " + "; ".join(pacote.cargos),
        "Tipos de local: " + ", ".join(pacote.tipos_de_local),
        "Localidades: " + "; ".join(pacote.localidades),
        f"Início: {pacote.inicio}",
        "Tipos de vaga: " + ", ".join(pacote.tipos_de_vaga),
        f"Visibilidade: {visibilidade}",
        "Revise tudo e salve — nada é aplicado pelo agente (RN-01/RN-04).",
    ]


# ---------------------------------------------------------------- RF-LI-07

URL_VALIDA = re.compile(r"^[A-Za-z0-9-]+$")


def validar_url_personalizada(trecho: str) -> list[str]:
    """Valida o trecho final de linkedin.com/in/<trecho> (RF-LI-07)."""
    erros: list[str] = []
    if not LIMITES["url_personalizada_min"] <= len(trecho) <= LIMITES["url_personalizada_max"]:
        erros.append(
            f"deve ter entre {LIMITES['url_personalizada_min']} e {LIMITES['url_personalizada_max']} caracteres"
        )
    if " " in trecho:
        erros.append("não pode ter espaços")
    if not URL_VALIDA.fullmatch(trecho):
        erros.append("use apenas letras, números e hífens (sem símbolos)")
    return erros


def sugerir_url(nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", base)[: LIMITES["url_personalizada_max"]]


def pacote_ajustes(perfil: PerfilMestre) -> list[tuple[str, str]]:
    """Ajustes de perfil prontos para aplicar: campo → valor preparado (RF-LI-07)."""
    ajustes: list[tuple[str, str]] = []
    local = ", ".join(p for p in [perfil.contato.cidade, perfil.contato.uf] if p)
    ajustes.append(("Localização", local or "PENDENTE: registre cidade/UF no perfil-mestre"))

    sugestao = sugerir_url(perfil.contato.nome)
    erros = validar_url_personalizada(sugestao)
    ajustes.append((
        "URL personalizada",
        f"linkedin.com/in/{sugestao}" + (f" (ajustar: {'; '.join(erros)})" if erros else "")
        + f" — até {LIMITES['url_trocas_por_semestre']} trocas em 6 meses",
    ))

    contato = " | ".join(p for p in [perfil.contato.email, perfil.links.github, perfil.links.portfolio] if p)
    ajustes.append(("Informações de contato", contato or "PENDENTE: e-mail/GitHub/portfólio no perfil-mestre"))

    destaque = [p for p in [perfil.links.github, perfil.links.portfolio] if p]
    destaque += [p.url for p in perfil.projetos if p.url]
    ajustes.append(("Em destaque", "; ".join(dict.fromkeys(destaque)) or "PENDENTE: links de projetos/portfólio"))

    if perfil.certificacoes:
        linhas = [
            c.nome
            + (f" — ID {c.id_credencial}" if c.id_credencial else " — SEM ID")
            + (f" — {c.url_credencial}" if c.url_credencial else " — SEM LINK")
            for c in perfil.certificacoes
        ]
        ajustes.append(("Certificações (com ID e link)", "; ".join(linhas)))
    if perfil.idiomas:
        ajustes.append(("Idiomas", ", ".join(f"{i.idioma}: {i.nivel}" for i in perfil.idiomas)))
    return ajustes


# ---------------------------------------------------------------- RF-LI-08

def passos_rodada(pendencias_altas: list[str]) -> list[str]:
    """Roteiro de uma rodada grande de edições (RF-LI-08)."""
    passos = [
        'ANTES: desligue "Compartilhar atualizações do perfil" em Configurações e privacidade > '
        "Visibilidade (cobre mudanças de cargo, formação e aniversários de trabalho).",
    ]
    passos += [f"Aplicar: {p}" for p in pendencias_altas] or ["Aplicar as mudanças aprovadas da auditoria."]
    passos += [
        "Confira cada campo salvo (quem visitar o perfil já vê as edições).",
        "DEPOIS (opcional): religue o compartilhamento se quiser anunciar a busca com um post curto.",
    ]
    return passos


# ---------------------------------------------------------------- RF-LI-09

class AlertaVaga(BaseModel):
    termos: str
    local: str
    frequencia: str = "diária"
    canal: str = "e-mail"


class PacoteAlertas(BaseModel):
    alertas: list[AlertaVaga]
    gerado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("alertas")
    @classmethod
    def _ate_vinte(cls, v: list[AlertaVaga]) -> list[AlertaVaga]:
        if len(v) > LIMITES["alertas"]:
            raise ValueError(f"o LinkedIn aceita até {LIMITES['alertas']} alertas")
        return v


def gerar_alertas(perfil: PerfilMestre, focos: list[str]) -> PacoteAlertas:
    cidade = ", ".join(p for p in [perfil.contato.cidade, perfil.contato.uf] if p)
    locais = [loc for loc in [cidade or None, f"{perfil.contato.pais} (remoto)"] if loc]
    alertas: list[AlertaVaga] = []
    for foco in focos:
        for cargo in CARGOS_POR_FOCO.get(foco, []):
            for local in locais:
                if len(alertas) >= LIMITES["alertas"]:
                    return PacoteAlertas(alertas=alertas)
                alertas.append(AlertaVaga(termos=cargo, local=local))
    return PacoteAlertas(alertas=alertas)


def salvar_pacote(pacote: BaseModel, nome_arquivo: str) -> Path:
    caminho = diretorio_dados() / nome_arquivo
    gravar_modelo(caminho, pacote)
    return caminho
