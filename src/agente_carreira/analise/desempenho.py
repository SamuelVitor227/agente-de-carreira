"""Desempenho por variante de CV: candidaturas × retornos (RF-CV-10)."""

from __future__ import annotations

from pydantic import BaseModel

from ..candidaturas import STATUS_DE_RETORNO, Candidaturas


class DesempenhoVariante(BaseModel):
    variante: str
    foco: str
    candidaturas: int
    retornos: int

    @property
    def taxa(self) -> float:
        return round(self.retornos / self.candidaturas, 2) if self.candidaturas else 0.0


def medir(colecao: Candidaturas) -> list[DesempenhoVariante]:
    por_variante: dict[tuple[str, str], DesempenhoVariante] = {}
    for cand in colecao.itens:
        chave = (cand.variante, cand.foco)
        registro = por_variante.setdefault(
            chave, DesempenhoVariante(variante=cand.variante, foco=cand.foco, candidaturas=0, retornos=0)
        )
        registro.candidaturas += 1
        passou_por_retorno = cand.status in STATUS_DE_RETORNO or any(
            m.para in STATUS_DE_RETORNO for m in cand.historico
        )
        if passou_por_retorno:
            registro.retornos += 1
    return sorted(por_variante.values(), key=lambda d: (-d.taxa, -d.candidaturas))


def recomendar_por_foco(desempenhos: list[DesempenhoVariante]) -> dict[str, DesempenhoVariante]:
    """A melhor variante de cada foco (maior taxa de retorno; empate: mais candidaturas)."""
    melhor: dict[str, DesempenhoVariante] = {}
    for d in desempenhos:
        atual = melhor.get(d.foco)
        if atual is None or (d.taxa, d.candidaturas) > (atual.taxa, atual.candidaturas):
            melhor[d.foco] = d
    return melhor
