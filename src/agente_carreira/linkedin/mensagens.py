"""Rascunhos de pedido de recomendação e de nota de convite (RF-LI-11).

O envio é sempre manual (RN-04, RN-11). Os rascunhos só citam o que está no
perfil-mestre (RN-02) e não guardam dados de terceiros em disco (RNF-05).
"""

from __future__ import annotations

from typing import Literal

from ..models import PerfilMestre
from .limites import LIMITES

Relacao = Literal["orientador", "professor", "colega"]

# Frases neutras quanto a gênero, de quem pede e de quem recebe.
FRASE_RELACAO: dict[str, str] = {
    "orientador": "você me orientou em",
    "professor": "tive aula com você em",
    "colega": "trabalhamos juntos em",
}


def _primeiro_nome(perfil: PerfilMestre) -> str:
    return perfil.contato.nome.split()[0]


def rascunho_recomendacao(
    perfil: PerfilMestre, nome: str, relacao: Relacao, contexto: str, pontos: list[str] | None = None
) -> str:
    objetivo = f" para a busca de vagas de {perfil.objetivo}" if perfil.objetivo else " para a busca de vagas"
    linhas = [
        f"Olá, {nome}! Tudo bem?",
        "",
        f"Estou atualizando meu perfil no LinkedIn{objetivo}. Como {FRASE_RELACAO[relacao]} {contexto}, "
        "uma recomendação sua teria um peso especial.",
        "",
        f"Se puder, você poderia escrever algumas linhas sobre {contexto}?",
    ]
    if pontos:
        linhas += ["Alguns pontos que você acompanhou e que podem ajudar:"]
        linhas += [f"- {p}" for p in pontos]
    linhas += [
        "",
        "Sem pressa nenhuma, e fico à disposição para retribuir. Agradeço desde já!",
        _primeiro_nome(perfil),
    ]
    return "\n".join(linhas)


def rascunho_convite(perfil: PerfilMestre, nome: str, motivo: str) -> str:
    motivo = motivo.strip()
    if motivo and motivo[-1] not in ".!?":
        motivo += "."
    return f"Olá, {nome}! {motivo} Vamos nos conectar? {_primeiro_nome(perfil)}"


def validar_convite(texto: str) -> list[str]:
    limite = LIMITES["nota_convite"]
    if len(texto) > limite:
        return [f"{len(texto)} caracteres, acima do limite de {limite} da nota de convite — encurte o motivo"]
    return []
