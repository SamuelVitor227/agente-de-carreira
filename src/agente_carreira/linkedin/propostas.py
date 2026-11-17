"""Propostas de alteração com antes × depois e validação (RF-LI-13).

Cada proposta compara o valor conhecido do LinkedIn com o texto gerado do
perfil-mestre. Só entra o que mudou, e só é aprovável o que passa no limite de
caracteres do campo e não tem frase [A CONFIRMAR] (RN-02, RNF-09).
"""

from __future__ import annotations

import unicodedata

from pydantic import BaseModel

from ..confirmacao import MARCADOR
from ..models import PerfilMestre
from .estado import EstadoLinkedIn, chave_experiencia
from .limites import LIMITES
from .textos import gerar_experiencias, gerar_sobre, gerar_titulos

ROTULOS = {"titulo": "Título", "sobre": "Sobre", "localizacao": "Localização", "competencias": "Competências"}


class Proposta(BaseModel):
    campo: str
    rotulo: str
    anterior: str | None = None
    novo: str


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def limite_do_campo(campo: str) -> int | None:
    base = campo.removeprefix("en:")
    if base == "titulo":
        return LIMITES["titulo"]
    if base == "sobre":
        return LIMITES["sobre"]
    if base.startswith("experiencia:"):
        return LIMITES["experiencia"]
    return None


def rotulo_do_campo(campo: str) -> str:
    prefixo = "[EN] " if campo.startswith("en:") else ""
    base = campo.removeprefix("en:")
    if base.startswith("experiencia:"):
        return prefixo + "Experiência: " + base.removeprefix("experiencia:")
    return prefixo + ROTULOS.get(base, base)


def validar_texto(campo: str, texto: str) -> list[str]:
    problemas: list[str] = []
    limite = limite_do_campo(campo)
    if limite and len(texto) > limite:
        problemas.append(f"{len(texto)} caracteres, acima do limite de {limite}")
    if MARCADOR in texto:
        problemas.append(f"contém {MARCADOR} — confirme ou reescreva a frase antes de aprovar (RN-02)")
    return problemas


def _proposta(estado: EstadoLinkedIn, campo: str, novo: str) -> Proposta | None:
    novo = novo.strip()
    anterior = estado.campos.get(campo)
    if not novo or (anterior or "").strip() == novo:
        return None
    return Proposta(campo=campo, rotulo=rotulo_do_campo(campo), anterior=anterior, novo=novo)


def gerar_propostas(
    perfil: PerfilMestre, estado: EstadoLinkedIn, foco: str, cargo_alvo: str, opcao_titulo: int = 1
) -> list[Proposta]:
    candidatas: list[tuple[str, str]] = []

    titulos = gerar_titulos(perfil, foco, cargo_alvo)
    if titulos:
        if not 1 <= opcao_titulo <= len(titulos):
            raise ValueError(f"Opção de título {opcao_titulo} não existe (há {len(titulos)}).")
        candidatas.append(("titulo", titulos[opcao_titulo - 1].texto))

    local = ", ".join(p for p in [perfil.contato.cidade, perfil.contato.uf] if p)
    publicado = estado.campos.get("localizacao", "")
    # "Belo Horizonte, MG" e "Belo Horizonte, Minas Gerais, Brasil" são a mesma cidade.
    if local and not (perfil.contato.cidade and _norm(perfil.contato.cidade) in _norm(publicado)):
        candidatas.append(("localizacao", local))

    candidatas.append(("sobre", gerar_sobre(perfil, foco).texto))
    for exp in gerar_experiencias(perfil):
        candidatas.append((chave_experiencia(exp.cargo, exp.empresa), exp.texto))

    return [p for campo, novo in candidatas if (p := _proposta(estado, campo, novo))]


def propostas_de_textos(estado: EstadoLinkedIn, textos: dict[str, str]) -> list[Proposta]:
    """Propostas a partir de textos prontos (ex.: tradução aprovada para o perfil em inglês)."""
    return [p for campo, novo in textos.items() if (p := _proposta(estado, campo, novo))]
