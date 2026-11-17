"""Saúde dos adaptadores (RF-OP-07): ao detectar mudança de layout ou erro, parar e avisar.

Adaptadores são os leitores de cada fonte: alertas de e-mail por plataforma,
páginas de carreira, IMAP e GitHub (e, na fase 2, os de cadastro). Uma falha
deixa o adaptador degradado; falhas seguidas, ou um sinal claro de layout
novo, o deixam parado — ele não roda mais até o usuário reativar, para não
gravar dados errados. Antes de preencher um formulário, o adaptador confere
se os campos esperados existem (RNF-08).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..storage import diretorio_dados

ARQUIVO = "saude-adaptadores.json"
LIMITE_FALHAS = 3


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class LayoutMudou(Exception):
    """Os campos esperados não estão na página: parar e voltar ao copiloto (RNF-08)."""


class SaudeAdaptador(BaseModel):
    nome: str
    status: Literal["ok", "degradado", "parado"] = "ok"
    falhas_seguidas: int = 0
    ultimo_erro: str | None = None
    ultima_verificacao: datetime | None = None
    ultimo_sucesso: datetime | None = None
    parado_em: datetime | None = None


class RegistroSaude(BaseModel):
    adaptadores: dict[str, SaudeAdaptador] = Field(default_factory=dict)

    def obter(self, nome: str) -> SaudeAdaptador:
        return self.adaptadores.setdefault(nome, SaudeAdaptador(nome=nome))

    def pode_usar(self, nome: str) -> bool:
        return self.obter(nome).status != "parado"

    def sucesso(self, nome: str) -> None:
        adaptador = self.obter(nome)
        adaptador.status = "ok"
        adaptador.falhas_seguidas = 0
        adaptador.ultima_verificacao = adaptador.ultimo_sucesso = _agora()

    def falha(self, nome: str, erro: str, parar: bool = False) -> bool:
        """Registra a falha; devolve True se o adaptador acabou de ser parado."""
        adaptador = self.obter(nome)
        adaptador.falhas_seguidas += 1
        adaptador.ultimo_erro = erro
        adaptador.ultima_verificacao = _agora()
        if parar or adaptador.falhas_seguidas >= LIMITE_FALHAS:
            ja_parado = adaptador.status == "parado"
            adaptador.status = "parado"
            adaptador.parado_em = adaptador.parado_em if ja_parado else _agora()
            return not ja_parado
        adaptador.status = "degradado"
        return False

    def reativar(self, nome: str) -> None:
        if nome not in self.adaptadores:
            raise ValueError(f"Adaptador {nome!r} não existe.")
        adaptador = self.adaptadores[nome]
        adaptador.status = "ok"
        adaptador.falhas_seguidas = 0
        adaptador.parado_em = None


def problema_no_email(plataforma: str | None, links: int, vagas: int, remetente_conhecido: bool) -> str | None:
    """Sinal de layout novo no alerta de e-mail de uma plataforma."""
    if links and not vagas:
        return f"o alerta tem {links} link(s) de vaga, mas nenhum título foi reconhecido: o layout do e-mail mudou"
    if remetente_conhecido and not links:
        return f"alerta de {plataforma} sem nenhum link de vaga reconhecível: o formato dos links mudou"
    return None


def verificar_campos(esperados: list[str], encontrados: list[str]) -> None:
    """RNF-08: antes de preencher, todos os campos esperados precisam existir."""
    faltando = [c for c in esperados if c not in set(encontrados)]
    if faltando:
        raise LayoutMudou(f"campos esperados não encontrados: {', '.join(faltando)}")


def carregar_saude() -> RegistroSaude:
    caminho = diretorio_dados() / ARQUIVO
    if not caminho.is_file():
        return RegistroSaude()
    return RegistroSaude.model_validate_json(caminho.read_text(encoding="utf-8"))


def salvar_saude(registro: RegistroSaude) -> Path:
    caminho = diretorio_dados() / ARQUIVO
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(registro.model_dump_json(indent=2), encoding="utf-8")
    return caminho
